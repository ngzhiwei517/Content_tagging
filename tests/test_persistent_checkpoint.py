import ast
import copy
import json
import shutil
import tempfile
import unittest
from datetime import date, datetime, timezone
from pathlib import Path
from typing import Dict, List
from urllib.parse import urlencode
from unittest.mock import Mock

import pandas as pd
import requests

from ugc_tagger.batch_checkpoint import BatchCheckpointStore
from ugc_tagger.persistent_checkpoint import (
    PersistentCheckpointConfig,
    PostgresCheckpointBackend,
    RecoveryCheckpointObjects,
    SupabaseCheckpointBackend,
    checkpoint_error_code,
    create_persistent_checkpoint_backend,
)


APP_PATH = Path(__file__).resolve().parents[1] / "app.py"
APP_SOURCE = APP_PATH.read_text(encoding="utf-8")
APP_TREE = ast.parse(APP_SOURCE)


def load_function(name, namespace):
    node = next(item for item in APP_TREE.body if isinstance(item, ast.FunctionDef) and item.name == name)
    module = ast.Module(body=[node], type_ignores=[])
    ast.fix_missing_locations(module)
    exec(compile(module, str(APP_PATH), "exec"), namespace)
    return namespace[name]


class MemoryObjectStore:
    def __init__(self):
        self.objects = {}
        self.list_prefix_calls = 0

    def save(self, key, payload):
        self.objects[key] = copy.deepcopy(payload)

    def load(self, key):
        return copy.deepcopy(self.objects.get(key))

    def list_prefix(self, prefix):
        self.list_prefix_calls += 1
        return {
            key: copy.deepcopy(payload)
            for key, payload in self.objects.items()
            if key.startswith(prefix)
        }

    def delete(self, key):
        self.objects.pop(key, None)

    def delete_prefix(self, prefix):
        for key in [key for key in self.objects if key.startswith(prefix)]:
            self.objects.pop(key, None)


class ChunkWriteFailureObjectStore(MemoryObjectStore):
    """Simulate a transient remote failure while compacting one chunk."""

    def save(self, key, payload):
        if "/chunk_" in key or key.startswith("chunk_"):
            raise RuntimeError("simulated remote chunk failure")
        super().save(key, payload)


class PersistentLargeBatchTests(unittest.TestCase):
    def test_compact_partial_snapshot_replaces_per_post_remote_writes(self):
        selected = pd.DataFrame([
            {
                "Link": f"https://www.tiktok.com/@creator/video/{5000 + index}",
                "Platform": "TikTok",
            }
            for index in range(50)
        ])
        remote = MemoryObjectStore()
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory) / "active"
            store = BatchCheckpointStore(
                root,
                chunk_size=50,
                persistent_store=remote,
            )
            manifest = store.prepare(
                "e" * 32,
                selected,
                model="gemini-test",
                comparison_run_id="compact-partial",
                comparison_started_utc="2026-08-04T00:00:00+00:00",
            )
            for position in range(5):
                store.save_partial_row(
                    manifest["job_id"],
                    0,
                    position,
                    {
                        "Link": selected.iloc[position]["Link"],
                        "Creative Type": "Others",
                    },
                    persist_remote=False,
                )
            self.assertTrue(store.save_partial_snapshot(manifest["job_id"], 0))

            remote_keys = list(remote.objects)
            self.assertTrue(any(key.endswith("/snapshot.json") for key in remote_keys))
            self.assertFalse(any("/row_" in key for key in remote_keys))

            restarted_root = Path(directory) / "restarted"
            restarted = BatchCheckpointStore(
                restarted_root,
                chunk_size=50,
                persistent_store=remote,
            )
            resumed = restarted.find(
                "e" * 32,
                selected,
                model="gemini-test",
            )
            restored = restarted.load_saved_results(resumed)
            self.assertEqual(resumed["saved_rows"], 5)
            self.assertEqual(len(restored), 5)

    def test_remote_job_prefix_is_hydrated_once_per_local_container(self):
        selected = pd.DataFrame([
            {
                "Link": f"https://www.tiktok.com/@creator/video/{6000 + index}",
                "Platform": "TikTok",
            }
            for index in range(256)
        ])
        remote = MemoryObjectStore()
        with tempfile.TemporaryDirectory() as directory:
            original = BatchCheckpointStore(
                Path(directory) / "original",
                chunk_size=50,
                persistent_store=remote,
            )
            manifest = original.prepare(
                "f" * 32,
                selected,
                model="gemini-test",
                comparison_run_id="hydrate-once",
                comparison_started_utc="2026-08-04T00:00:00+00:00",
            )
            original.save_partial_row(
                manifest["job_id"],
                0,
                0,
                {"Link": selected.iloc[0]["Link"], "Creative Type": "Dance"},
            )

            restarted_root = Path(directory) / "restarted"
            restarted = BatchCheckpointStore(
                restarted_root,
                chunk_size=50,
                persistent_store=remote,
            )
            resumed = restarted.find(
                "f" * 32,
                selected,
                model="gemini-test",
            )
            calls_after_first_hydration = remote.list_prefix_calls
            self.assertEqual(resumed["saved_rows"], 1)
            self.assertEqual(calls_after_first_hydration, 1)

            # A fresh store object models the next Streamlit script rerun while
            # keeping the same local container filesystem.
            next_rerun = BatchCheckpointStore(
                restarted_root,
                chunk_size=50,
                persistent_store=remote,
            )
            resumed_again = next_rerun.find(
                "f" * 32,
                selected,
                model="gemini-test",
            )
            self.assertEqual(resumed_again["saved_rows"], 1)
            self.assertEqual(remote.list_prefix_calls, calls_after_first_hydration)

    def test_partial_row_rehydrates_after_local_container_is_removed(self):
        selected = pd.DataFrame([
            {"Link": f"https://www.tiktok.com/@creator/video/{7000 + index}", "Platform": "TikTok"}
            for index in range(60)
        ])
        remote = MemoryObjectStore()
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory) / "tagging_jobs"
            store = BatchCheckpointStore(root, chunk_size=50, persistent_store=remote)
            manifest = store.prepare(
                "a" * 32,
                selected,
                model="gemini-test",
                comparison_run_id="run-1",
                comparison_started_utc="2026-08-02T00:00:00+00:00",
            )
            store.save_partial_row(
                manifest["job_id"],
                0,
                0,
                {"Link": selected.iloc[0]["Link"], "Creative Type": "Dance"},
            )
            shutil.rmtree(root)

            restarted = BatchCheckpointStore(root, chunk_size=50, persistent_store=remote)
            resumed = restarted.find("a" * 32, selected, model="gemini-test")
            restored = restarted.load_saved_results(resumed)

            self.assertEqual(resumed["saved_rows"], 1)
            self.assertEqual(len(restored), 1)
            self.assertEqual(restored.iloc[0]["Creative Type"], "Dance")

    def test_twenty_five_saved_rows_resume_at_post_twenty_six_after_container_restart(self):
        selected = pd.DataFrame([
            {
                "Link": f"https://www.tiktok.com/@creator/video/{7500 + index}",
                "Platform": "TikTok",
            }
            for index in range(50)
        ])
        remote = MemoryObjectStore()
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory) / "tagging_jobs"
            runtime_id = "9" * 32
            store = BatchCheckpointStore(root, chunk_size=50, persistent_store=remote)
            manifest = store.prepare(
                runtime_id,
                selected,
                model="gemini-test",
                comparison_run_id="twenty-five-restart",
                comparison_started_utc="2026-08-13T00:00:00+00:00",
            )
            for position in range(25):
                store.save_partial_row(
                    manifest["job_id"],
                    0,
                    position,
                    {
                        "Link": selected.iloc[position]["Link"],
                        "Creative Type": "Others",
                    },
                )
            manifest = store.mark_continuation_ready(manifest)
            self.assertEqual(manifest["saved_rows"], 25)

            # Model a Streamlit Cloud container replacement: all local files
            # disappear, while the persistent checkpoint remains available.
            shutil.rmtree(root)
            restarted = BatchCheckpointStore(root, chunk_size=50, persistent_store=remote)
            resumed = restarted.find(runtime_id, selected, model="gemini-test")
            restored = restarted.load_saved_results(resumed)
            saved_positions = restarted.partial_positions(resumed["job_id"], 0)
            remaining_positions = [
                position for position in range(50) if position not in saved_positions
            ]

            self.assertEqual(resumed["saved_rows"], 25)
            self.assertEqual(len(restored), 25)
            self.assertEqual(saved_positions, list(range(25)))
            self.assertEqual(remaining_positions[0], 25)
            self.assertEqual(
                restored.iloc[-1]["Link"],
                selected.iloc[24]["Link"],
            )
            self.assertTrue(resumed["continuation_ready"])

    def test_remote_rows_exclude_secrets_and_downloaded_media(self):
        remote = MemoryObjectStore()
        with tempfile.TemporaryDirectory() as directory:
            store = BatchCheckpointStore(Path(directory), persistent_store=remote)
            manifest = store.prepare(
                "b" * 32,
                pd.DataFrame([{"Link": "https://example.com/post"}]),
                model="gemini-test",
                comparison_run_id="run-2",
                comparison_started_utc="2026-08-02T00:00:00+00:00",
            )
            store.save_scraped_records(
                manifest["job_id"],
                0,
                [{"url": "https://example.com/post", "api_token": "secret-value", "video_bytes": b"media"}],
            )
            serialized = json.dumps(remote.objects)
            self.assertNotIn("secret-value", serialized)
            self.assertNotIn("media", serialized)
            self.assertNotIn("video_bytes", serialized)

    def test_failed_remote_chunk_write_keeps_row_backups_for_restart(self):
        selected = pd.DataFrame([
            {
                "Link": f"https://www.tiktok.com/@creator/video/{8000 + index}",
                "Platform": "TikTok",
            }
            for index in range(250)
        ])
        remote = ChunkWriteFailureObjectStore()
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory) / "tagging_jobs"
            store = BatchCheckpointStore(
                root,
                chunk_size=50,
                persistent_store=remote,
            )
            runtime_id = "f" * 32
            manifest = store.prepare(
                runtime_id,
                selected,
                model="gemini-test",
                comparison_run_id="run-restart",
                comparison_started_utc="2026-08-04T00:00:00+00:00",
            )
            first_chunk = store.chunk_frame(selected, manifest, 0)
            for position, row in first_chunk.iterrows():
                store.save_partial_row(
                    manifest["job_id"],
                    0,
                    position,
                    {**row.to_dict(), "Creative Type": "Others"},
                )

            manifest = store.save_completed_chunk(
                manifest,
                0,
                first_chunk.assign(**{"Creative Type": "Others"}),
                elapsed_seconds=1.0,
            )
            self.assertEqual(manifest["completed_rows"], 50)
            self.assertEqual(
                len([key for key in remote.objects if "/partial_00000/" in key]),
                50,
            )

            # A replacement Streamlit container has no local files. Recovery
            # must retain the 50 completed rows instead of restarting at zero.
            shutil.rmtree(root)
            restarted = BatchCheckpointStore(
                root,
                chunk_size=50,
                persistent_store=remote,
            )
            recovered = restarted.find(
                runtime_id,
                selected,
                model="gemini-test",
            )
            restored_rows = restarted.load_saved_results(recovered)

            self.assertEqual(recovered["saved_rows"], 50)
            self.assertEqual(restarted.next_chunk_index(recovered), 0)
            self.assertEqual(len(restored_rows), 50)


class SupabaseBackendTests(unittest.TestCase):
    def test_data_api_url_is_normalized_to_project_url(self):
        backend = SupabaseCheckpointBackend(
            "https://project.supabase.co/rest/v1/",
            "sb_secret_example",
        )
        self.assertEqual(backend.url, "https://project.supabase.co")
        self.assertEqual(
            backend.endpoint,
            "https://project.supabase.co/rest/v1/batch_checkpoint_objects",
        )

    def test_new_secret_key_uses_apikey_header_without_bearer_auth(self):
        backend = SupabaseCheckpointBackend(
            "https://project.supabase.co",
            "sb_secret_example",
        )
        headers = backend._headers()
        self.assertEqual(headers["apikey"], "sb_secret_example")
        self.assertNotIn("Authorization", headers)

    def test_legacy_service_role_jwt_keeps_bearer_auth(self):
        backend = SupabaseCheckpointBackend(
            "https://project.supabase.co",
            "legacy-service-role-jwt",
        )
        headers = backend._headers()
        self.assertEqual(headers["apikey"], "legacy-service-role-jwt")
        self.assertEqual(headers["Authorization"], "Bearer legacy-service-role-jwt")

    def test_upsert_does_not_embed_server_key_in_payload(self):
        session = Mock()
        response = Mock()
        response.raise_for_status.return_value = None
        session.post.return_value = response
        backend = SupabaseCheckpointBackend(
            "https://project.supabase.co",
            "server-secret",
            session=session,
        )
        backend.save("c" * 32, "runtime.json", {"state": {"step": 3}})
        sent = session.post.call_args.kwargs["json"]
        self.assertNotIn("server-secret", json.dumps(sent))
        self.assertEqual(sent["object_key"], "runtime.json")

    def test_transient_timeout_is_retried_once(self):
        session = Mock()
        response = Mock(status_code=201)
        response.raise_for_status.return_value = None
        session.post.side_effect = [requests.Timeout("slow"), response]
        backend = SupabaseCheckpointBackend(
            "https://project.supabase.co",
            "sb_secret_example",
            session=session,
        )

        backend.save("e" * 32, "runtime.json", {"state": {"step": 3}})

        self.assertEqual(session.post.call_count, 2)

    def test_http_failures_map_to_safe_diagnostic_codes(self):
        response = Mock(status_code=401)
        error = requests.HTTPError(response=response)
        self.assertEqual(checkpoint_error_code(error), "auth_failed")
        response.status_code = 404
        self.assertEqual(checkpoint_error_code(error), "table_missing")
        self.assertEqual(checkpoint_error_code(requests.Timeout("slow")), "timeout")

    def test_empty_configuration_keeps_local_only_mode(self):
        self.assertIsNone(create_persistent_checkpoint_backend(PersistentCheckpointConfig()))


class PostgresBackendTests(unittest.TestCase):
    def test_recovery_id_and_object_key_are_parameterized(self):
        cursor = Mock()
        cursor.__enter__ = Mock(return_value=cursor)
        cursor.__exit__ = Mock(return_value=False)
        connection = Mock()
        connection.__enter__ = Mock(return_value=connection)
        connection.__exit__ = Mock(return_value=False)
        connection.cursor.return_value = cursor
        driver = Mock()
        driver.connect.return_value = connection
        backend = PostgresCheckpointBackend("postgresql://server/database")
        backend._driver = Mock(return_value=driver)
        backend.save("d" * 32, "runtime.json", {"state": {"step": 4}})
        statement, params = cursor.execute.call_args.args
        self.assertNotIn("d" * 32, statement)
        self.assertNotIn("runtime.json", statement)
        self.assertEqual(params[:2], ("d" * 32, "runtime.json"))


class WorkflowCheckpointSafetyTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.to_payload = staticmethod(load_function(
            "_checkpoint_dataframe_to_payload_v68_15",
            {"pd": pd, "json": json, "Dict": Dict},
        ))

    def test_runtime_dataframe_excludes_credentials_and_media(self):
        payload = self.to_payload(pd.DataFrame([{
            "Link": "https://example.com/post",
            "Gemini API Key": "secret-value",
            "local_video_path": "downloaded.mp4",
            "video_bytes": b"media",
        }]))
        serialized = json.dumps(payload)
        self.assertEqual(payload["columns"], ["Link"])
        self.assertNotIn("secret-value", serialized)
        self.assertNotIn("downloaded.mp4", serialized)

    def test_runtime_dataframe_preserves_normalized_melodyiq_export_membership(self):
        scope_ranks = '{"scope-1":1}'
        payload = self.to_payload(pd.DataFrame([{
            "Link": "https://www.tiktok.com/@creator/video/1",
            "_MelodyIQ API Scope Ranks": scope_ranks,
        }]))

        self.assertIn("_MelodyIQ API Scope Ranks", payload["columns"])
        self.assertIn(scope_ranks, payload["data"][0])

    def test_melodyiq_checkpoint_excludes_live_response_and_signed_url(self):
        namespace = {
            "date": date,
            "safe_str": lambda value: str(value or "").strip(),
            "Dict": Dict,
            "List": List,
        }
        namespace["_melodyiq_iso_date_v68_107"] = load_function(
            "_melodyiq_iso_date_v68_107",
            namespace,
        )
        namespace["_checkpoint_melodyiq_import_scope_v68_104"] = load_function(
            "_checkpoint_melodyiq_import_scope_v68_104",
            namespace,
        )
        namespace["_checkpoint_melodyiq_pagination_state_v68_106"] = load_function(
            "_checkpoint_melodyiq_pagination_state_v68_106",
            namespace,
        )
        to_payload = load_function(
            "_checkpoint_melodyiq_reports_to_payload_v68_104",
            namespace,
        )
        from_payload = load_function(
            "_checkpoint_melodyiq_reports_from_payload_v68_104",
            namespace,
        )

        payload = to_payload([
            {
                "report_id": "report-1",
                "report": {
                    "tktk": {
                        "postsExportUrl": "https://signed.example/report.csv?token=secret"
                    }
                },
                "track": "Treat You Better",
                "artist": "Shawn Mendes",
                "sound_ids": ["sound-1", "sound-1", "sound-2"],
                "started_at": "2026-08-21T01:02:03+00:00",
                "timer_scope": "created",
                "import_scope": {
                    "mode": "all",
                    "limit": 20000,
                    "sort_field": "viewCount",
                    "creator_country": "sg",
                    "post_created_at_min": "2026-08-01",
                    "post_created_at_max": "2026-08-21",
                },
                "pagination_state": {
                    "creator_country": "sg",
                    "post_created_at_min": "2026-08-01",
                    "post_created_at_max": "2026-08-21",
                    "next_page": 11,
                    "last_page": 9000,
                    "pages_scanned": 10,
                    "source_posts_scanned": 1000,
                    "matching_posts_found": 37,
                    "api_total": 2500,
                    "complete": False,
                    "posts": [{"url": "https://example.com/private-row"}],
                },
            }
        ])

        serialized = json.dumps(payload)
        self.assertEqual(payload[0]["report_id"], "report-1")
        self.assertEqual(payload[0]["sound_ids"], ["sound-1", "sound-2"])
        self.assertEqual(payload[0]["started_at"], "2026-08-21T01:02:03+00:00")
        self.assertEqual(payload[0]["timer_scope"], "created")
        self.assertEqual(payload[0]["import_scope"]["limit"], 1000)
        self.assertEqual(payload[0]["import_scope"]["creator_country"], "SG")
        self.assertEqual(
            payload[0]["import_scope"]["post_created_at_min"],
            "2026-08-01",
        )
        self.assertEqual(
            payload[0]["pagination_state"]["post_created_at_max"],
            "2026-08-21",
        )
        self.assertEqual(payload[0]["pagination_state"]["next_page"], 11)
        self.assertEqual(payload[0]["pagination_state"]["api_total"], 2500)
        self.assertEqual(
            payload[0]["pagination_state"]["source_posts_scanned"],
            1000,
        )
        self.assertNotIn("report", payload[0])
        self.assertNotIn("private-row", serialized)
        self.assertNotIn("postsExportUrl", serialized)
        self.assertNotIn("token=secret", serialized)
        self.assertEqual(from_payload(payload)[0]["report"], {})

    def test_remote_checkpoint_waits_until_recoverable_work_exists(self):
        has_posts = load_function(
            "_runtime_checkpoint_has_posts_v68_44",
            {
                "pd": pd,
                "RUNTIME_DATAFRAME_KEYS_V68_15": {"batch_df", "selected_df", "tagged_df"},
            },
        )
        empty_state = {
            "batch_df": pd.DataFrame(),
            "selected_df": {"columns": ["Link"], "index": [], "data": []},
        }
        populated_state = {
            "batch_df": {
                "columns": ["Link"],
                "index": [0],
                "data": [["https://example.com/post"]],
            },
        }
        queued_report_state = {
            "batch_df": pd.DataFrame(),
            "melodyiq_reports_v68_100": [{"report_id": "report-1"}],
        }
        self.assertFalse(has_posts(empty_state))
        self.assertTrue(has_posts(populated_state))
        self.assertTrue(has_posts(queued_report_state))
        self.assertIn(
            "if not has_posts:",
            APP_SOURCE,
        )

    def test_reconnect_prefers_populated_checkpoint_over_newer_empty_shell(self):
        namespace = {
            "pd": pd,
            "datetime": datetime,
            "timezone": timezone,
            "safe_str": lambda value: str(value or "").strip(),
            "RUNTIME_DATAFRAME_KEYS_V68_15": {"batch_df", "selected_df", "tagged_df"},
            "Tuple": tuple,
        }
        namespace["_runtime_checkpoint_has_posts_v68_44"] = load_function(
            "_runtime_checkpoint_has_posts_v68_44",
            namespace,
        )
        namespace["_checkpoint_saved_at_v68_44"] = load_function(
            "_checkpoint_saved_at_v68_44",
            namespace,
        )
        rank = load_function(
            "_runtime_checkpoint_candidate_rank_v68_79",
            namespace,
        )
        populated_remote = {
            "saved_at": "2026-08-13T13:56:00+00:00",
            "state": {
                "selected_df": {
                    "columns": ["Link"],
                    "index": [0],
                    "data": [["https://example.com/saved-post"]],
                },
            },
        }
        newer_empty_session = {
            "saved_at": "2026-08-13T13:57:39+00:00",
            "state": {
                "selected_df": {
                    "columns": ["Link"],
                    "index": [],
                    "data": [],
                },
            },
        }

        chosen = max([newer_empty_session, populated_remote], key=rank)
        self.assertIs(chosen, populated_remote)
        self.assertIn("preserve_existing", APP_SOURCE)
        self.assertIn(
            "runtime_restore_checked_v68_15 = bool(restored or not requested_id)",
            APP_SOURCE,
        )

    def test_reconnect_empty_session_does_not_overwrite_populated_local_state(self):
        recovery_id = "8" * 32
        with tempfile.TemporaryDirectory() as directory:
            checkpoint_dir = Path(directory)
            checkpoint_path = checkpoint_dir / f"{recovery_id}.json"
            populated = {
                "version": "test",
                "saved_at": "2026-08-13T13:56:00+00:00",
                "state": {
                    "batch_df": {
                        "columns": ["Link"],
                        "index": [0],
                        "data": [["https://example.com/saved-post"]],
                    },
                },
            }
            checkpoint_path.write_text(json.dumps(populated), encoding="utf-8")

            class FakeStreamlit:
                session_state = {
                    "runtime_run_id_v68_15": recovery_id,
                    "batch_df": pd.DataFrame(),
                }

            namespace = {
                "st": FakeStreamlit(),
                "pd": pd,
                "date": date,
                "datetime": datetime,
                "timezone": timezone,
                "json": json,
                "os": __import__("os"),
                "APP_VERSION": "test",
                "RUNTIME_CHECKPOINT_DIR_V68_15": checkpoint_dir,
                "RUNTIME_CHECKPOINT_STATE_KEYS_V68_15": ("batch_df",),
                "RUNTIME_DATAFRAME_KEYS_V68_15": {"batch_df"},
                "_valid_runtime_id_v68_15": lambda value: value,
                "_checkpoint_dataframe_to_payload_v68_15": self.to_payload,
                "_runtime_checkpoint_path_v68_15": lambda run_id: checkpoint_dir / f"{run_id}.json",
                "_load_local_runtime_checkpoint_v68_44": lambda run_id: json.loads(
                    (checkpoint_dir / f"{run_id}.json").read_text(encoding="utf-8")
                ),
                "_sync_runtime_query_v68_15": lambda: None,
                "_checkpoint_objects_v68_44": lambda run_id: None,
            }
            namespace["_runtime_checkpoint_has_posts_v68_44"] = load_function(
                "_runtime_checkpoint_has_posts_v68_44",
                namespace,
            )
            persist = load_function("_persist_runtime_checkpoint_v68_15", namespace)

            persist()

            after = json.loads(checkpoint_path.read_text(encoding="utf-8"))
            self.assertEqual(after, populated)

    def test_continue_later_verifies_remote_runtime_checkpoint(self):
        recovery_id = "7" * 32
        remote = MemoryObjectStore()

        class SessionState(dict):
            __getattr__ = dict.get
            __setattr__ = dict.__setitem__

        class FakeStreamlit:
            session_state = SessionState({
                "runtime_run_id_v68_15": recovery_id,
                "batch_df": pd.DataFrame([
                    {"Link": "https://www.tiktok.com/@creator/video/1"}
                ]),
            })

        with tempfile.TemporaryDirectory() as directory:
            checkpoint_dir = Path(directory)
            namespace = {
                "st": FakeStreamlit(),
                "pd": pd,
                "datetime": datetime,
                "timezone": timezone,
                "json": json,
                "os": __import__("os"),
                "APP_VERSION": "test",
                "LOGGER": Mock(),
                "safe_str": lambda value: str(value or "").strip(),
                "RUNTIME_CHECKPOINT_DIR_V68_15": checkpoint_dir,
                "RUNTIME_CHECKPOINT_STATE_KEYS_V68_15": ("batch_df",),
                "RUNTIME_DATAFRAME_KEYS_V68_15": {"batch_df"},
                "_valid_runtime_id_v68_15": lambda value: value,
                "_checkpoint_dataframe_to_payload_v68_15": self.to_payload,
                "_runtime_checkpoint_path_v68_15": lambda run_id: checkpoint_dir / f"{run_id}.json",
                "_load_local_runtime_checkpoint_v68_44": lambda run_id: None,
                "_sync_runtime_query_v68_15": lambda: None,
                "_checkpoint_objects_v68_44": lambda run_id: remote,
            }
            namespace["_runtime_checkpoint_has_posts_v68_44"] = load_function(
                "_runtime_checkpoint_has_posts_v68_44",
                namespace,
            )
            persist = load_function("_persist_runtime_checkpoint_v68_15", namespace)

            status = persist(verify_remote=True)

        self.assertEqual(status, "verified")
        self.assertEqual(
            FakeStreamlit.session_state.runtime_checkpoint_remote_status_v68_96,
            "verified",
        )
        self.assertTrue(remote.objects["runtime.json"]["state"]["batch_df"]["data"])

    def test_report_only_checkpoint_is_persisted_without_signed_url(self):
        recovery_id = "9" * 32
        remote = MemoryObjectStore()

        class SessionState(dict):
            __getattr__ = dict.get
            __setattr__ = dict.__setitem__

        class FakeStreamlit:
            session_state = SessionState({
                "runtime_run_id_v68_15": recovery_id,
                "melodyiq_reports_v68_100": [{
                    "report_id": "report-1",
                    "report": {
                        "tktk": {
                            "postsExportUrl": "https://signed.example/report.csv?token=secret"
                        }
                    },
                    "track": "Treat You Better",
                    "artist": "Shawn Mendes",
                    "sound_ids": ["sound-1"],
                    "import_scope": {
                        "mode": "all",
                        "limit": 20000,
                        "sort_field": "viewCount",
                    },
                }],
            })

        with tempfile.TemporaryDirectory() as directory:
            checkpoint_dir = Path(directory)
            namespace = {
                "st": FakeStreamlit(),
                "pd": pd,
                "date": date,
                "datetime": datetime,
                "timezone": timezone,
                "json": json,
                "os": __import__("os"),
                "APP_VERSION": "test",
                "LOGGER": Mock(),
                "safe_str": lambda value: str(value or "").strip(),
                "Dict": Dict,
                "List": List,
                "RUNTIME_CHECKPOINT_DIR_V68_15": checkpoint_dir,
                "RUNTIME_CHECKPOINT_STATE_KEYS_V68_15": (
                    "melodyiq_reports_v68_100",
                ),
                "RUNTIME_DATAFRAME_KEYS_V68_15": set(),
                "_valid_runtime_id_v68_15": lambda value: value,
                "_runtime_checkpoint_path_v68_15": (
                    lambda run_id: checkpoint_dir / f"{run_id}.json"
                ),
                "_load_local_runtime_checkpoint_v68_44": lambda run_id: None,
                "_sync_runtime_query_v68_15": lambda: None,
                "_checkpoint_objects_v68_44": lambda run_id: remote,
            }
            namespace["_melodyiq_iso_date_v68_107"] = load_function(
                "_melodyiq_iso_date_v68_107",
                namespace,
            )
            namespace["_checkpoint_melodyiq_import_scope_v68_104"] = load_function(
                "_checkpoint_melodyiq_import_scope_v68_104",
                namespace,
            )
            namespace["_checkpoint_melodyiq_pagination_state_v68_106"] = load_function(
                "_checkpoint_melodyiq_pagination_state_v68_106",
                namespace,
            )
            namespace["_checkpoint_melodyiq_reports_to_payload_v68_104"] = load_function(
                "_checkpoint_melodyiq_reports_to_payload_v68_104",
                namespace,
            )
            namespace["_runtime_checkpoint_has_posts_v68_44"] = load_function(
                "_runtime_checkpoint_has_posts_v68_44",
                namespace,
            )
            persist = load_function("_persist_runtime_checkpoint_v68_15", namespace)

            status = persist(verify_remote=True)

        saved = remote.objects["runtime.json"]
        serialized = json.dumps(saved)
        self.assertEqual(status, "verified")
        self.assertEqual(
            saved["state"]["melodyiq_reports_v68_100"][0]["report_id"],
            "report-1",
        )
        self.assertNotIn("postsExportUrl", serialized)
        self.assertNotIn("token=secret", serialized)

    def test_report_only_checkpoint_restores_the_queue(self):
        recovery_id = "a" * 32

        class SessionState(dict):
            __getattr__ = dict.get
            __setattr__ = dict.__setitem__

        class FakeStreamlit:
            session_state = SessionState()

        payload = {
            "saved_at": "2026-08-21T00:00:00+00:00",
            "state": {
                "step": 2,
                "melodyiq_reports_v68_100": [{
                    "report_id": "report-1",
                    "track": "Treat You Better",
                    "artist": "Shawn Mendes",
                    "sound_ids": ["sound-1"],
                    "import_scope": {
                        "mode": "all",
                        "limit": 20000,
                        "sort_field": "viewCount",
                    },
                }],
            },
        }
        namespace = {
            "st": FakeStreamlit(),
            "pd": pd,
            "date": date,
            "safe_str": lambda value: str(value or "").strip(),
            "Dict": Dict,
            "List": List,
            "RUNTIME_CHECKPOINT_STATE_KEYS_V68_15": (
                "step",
                "melodyiq_reports_v68_100",
            ),
            "RUNTIME_DATAFRAME_KEYS_V68_15": set(),
            "_valid_runtime_id_v68_15": lambda value: value,
            "_runtime_query_value_v68_15": (
                lambda name: recovery_id if name == "run" else "2"
            ),
            "_runtime_checkpoint_candidates_v68_44": lambda run_id: [payload],
            "_runtime_checkpoint_candidate_rank_v68_79": lambda value: (1, 1),
            "_checkpoint_dataframe_from_payload_v68_15": lambda value: pd.DataFrame(),
            "_sync_runtime_query_v68_15": lambda: None,
            "_persist_runtime_checkpoint_v68_15": lambda: None,
        }
        namespace["_melodyiq_iso_date_v68_107"] = load_function(
            "_melodyiq_iso_date_v68_107",
            namespace,
        )
        namespace["_checkpoint_melodyiq_import_scope_v68_104"] = load_function(
            "_checkpoint_melodyiq_import_scope_v68_104",
            namespace,
        )
        namespace["_checkpoint_melodyiq_pagination_state_v68_106"] = load_function(
            "_checkpoint_melodyiq_pagination_state_v68_106",
            namespace,
        )
        namespace["_checkpoint_melodyiq_reports_to_payload_v68_104"] = load_function(
            "_checkpoint_melodyiq_reports_to_payload_v68_104",
            namespace,
        )
        namespace["_checkpoint_melodyiq_reports_from_payload_v68_104"] = load_function(
            "_checkpoint_melodyiq_reports_from_payload_v68_104",
            namespace,
        )
        namespace["_runtime_checkpoint_has_posts_v68_44"] = load_function(
            "_runtime_checkpoint_has_posts_v68_44",
            namespace,
        )
        restore = load_function("_restore_runtime_checkpoint_v68_15", namespace)

        restore(persist=False)

        restored = FakeStreamlit.session_state["melodyiq_reports_v68_100"]
        self.assertEqual(restored[0]["report_id"], "report-1")
        self.assertEqual(restored[0]["report"], {})
        self.assertTrue(FakeStreamlit.session_state.runtime_resume_notice_v68_15)
        self.assertTrue(FakeStreamlit.session_state.runtime_restore_checked_v68_15)

    def test_runtime_checkpoint_converts_non_dataframe_state_to_strict_json(self):
        recovery_id = "8" * 32
        remote = MemoryObjectStore()

        class SessionState(dict):
            __getattr__ = dict.get
            __setattr__ = dict.__setitem__

        class FakeStreamlit:
            session_state = SessionState({
                "runtime_run_id_v68_15": recovery_id,
                "batch_df": pd.DataFrame([{
                    "Link": "https://www.tiktok.com/@creator/video/1"
                }]),
                "date_start_v68": date(2026, 8, 1),
                "track_date_settings_v68": {
                    "Track A": {
                        "start": pd.Timestamp("2026-08-01", tz="UTC"),
                        "window": float("nan"),
                    }
                },
                "rank_metrics": ("Views", "Total Engagement"),
            })

        with tempfile.TemporaryDirectory() as directory:
            checkpoint_dir = Path(directory)
            namespace = {
                "st": FakeStreamlit(),
                "pd": pd,
                "math": __import__("math"),
                "date": date,
                "datetime_time": __import__("datetime").time,
                "datetime": datetime,
                "timezone": timezone,
                "Path": Path,
                "json": json,
                "os": __import__("os"),
                "APP_VERSION": "test",
                "LOGGER": Mock(),
                "safe_str": lambda value: str(value or "").strip(),
                "RUNTIME_CHECKPOINT_DIR_V68_15": checkpoint_dir,
                "RUNTIME_CHECKPOINT_STATE_KEYS_V68_15": (
                    "batch_df",
                    "date_start_v68",
                    "track_date_settings_v68",
                    "rank_metrics",
                ),
                "RUNTIME_DATAFRAME_KEYS_V68_15": {"batch_df"},
                "_valid_runtime_id_v68_15": lambda value: value,
                "_checkpoint_dataframe_to_payload_v68_15": self.to_payload,
                "_runtime_checkpoint_path_v68_15": lambda run_id: checkpoint_dir / f"{run_id}.json",
                "_load_local_runtime_checkpoint_v68_44": lambda run_id: None,
                "_sync_runtime_query_v68_15": lambda: None,
                "_checkpoint_objects_v68_44": lambda run_id: remote,
            }
            namespace["_checkpoint_json_safe_value_v68_96"] = load_function(
                "_checkpoint_json_safe_value_v68_96",
                namespace,
            )
            namespace["_runtime_checkpoint_has_posts_v68_44"] = load_function(
                "_runtime_checkpoint_has_posts_v68_44",
                namespace,
            )
            persist = load_function("_persist_runtime_checkpoint_v68_15", namespace)

            status = persist(verify_remote=True)

        saved = remote.objects["runtime.json"]
        json.dumps(saved, allow_nan=False)
        self.assertEqual(status, "verified")
        self.assertEqual(saved["state"]["date_start_v68"], "2026-08-01")
        self.assertEqual(
            saved["state"]["track_date_settings_v68"]["Track A"]["start"],
            "2026-08-01T00:00:00+00:00",
        )
        self.assertIsNone(
            saved["state"]["track_date_settings_v68"]["Track A"]["window"]
        )
        self.assertEqual(
            saved["state"]["rank_metrics"],
            ["Views", "Total Engagement"],
        )

    def test_managed_secrets_and_private_continue_later_recovery_remain_available(self):
        self.assertIn('_managed_api_secret_v68_43("GEMINI_API_KEY")', APP_SOURCE)
        self.assertIn('_managed_api_secret_v68_43("APIFY_TOKEN")', APP_SOURCE)
        self.assertNotIn('key="runtime_save_batch_button_v68_44"', APP_SOURCE)
        self.assertNotIn('with st.expander("Open a saved batch"', APP_SOURCE)
        self.assertNotIn('key="runtime_recovery_button_v68_44"', APP_SOURCE)
        self.assertIn('key="runtime_continue_later_v68_85"', APP_SOURCE)
        self.assertIn('@st.dialog("Continue later")', APP_SOURCE)
        self.assertIn("_render_continue_later_v68_85()", APP_SOURCE)
        self.assertIn(
            "_restore_runtime_checkpoint_v68_15(persist=not taggy_companion_session_v68_87)",
            APP_SOURCE,
        )
        self.assertIn("_persist_runtime_checkpoint_v68_15()", APP_SOURCE)
        self.assertNotIn("Current recovery ID", APP_SOURCE)
        self.assertNotIn('(1, "01", "API Keys", "Setup")', APP_SOURCE)

    def test_continue_later_appears_for_a_report_before_posts_are_imported(self):
        events = []

        class FakeColumn:
            def __enter__(self):
                return self

            def __exit__(self, exc_type, exc_value, traceback):
                return False

        class FakeStreamlit:
            session_state = {"batch_df": pd.DataFrame()}

            @staticmethod
            def columns(spec):
                events.append(("columns", spec))
                return FakeColumn(), FakeColumn()

            @staticmethod
            def button(label, **kwargs):
                events.append(("button", label, kwargs))
                return True

        has_work_namespace = {
            "pd": pd,
            "RUNTIME_DATAFRAME_KEYS_V68_15": {"batch_df"},
        }
        has_work = load_function(
            "_runtime_checkpoint_has_posts_v68_44",
            has_work_namespace,
        )
        namespace = {
            "st": FakeStreamlit(),
            "_runtime_checkpoint_has_posts_v68_44": has_work,
            "_persist_runtime_checkpoint_v68_15": lambda **kwargs: events.append(
                ("persist", kwargs)
            ),
            "_show_runtime_save_dialog_v68_44": lambda: events.append("dialog"),
        }
        render = load_function("_render_continue_later_v68_85", namespace)

        render()
        self.assertEqual(events, [])

        FakeStreamlit.session_state["melodyiq_reports_v68_100"] = [
            {"report_id": "report-1"}
        ]
        render()

        self.assertEqual(events[0], ("columns", [5, 1]))
        self.assertEqual(events[1][0:2], ("button", "Continue later"))
        self.assertEqual(events[1][2]["key"], "runtime_continue_later_v68_85")
        self.assertEqual(
            events[-2:],
            [("persist", {"verify_remote": True}), "dialog"],
        )

    def test_save_link_hides_recovery_id_inside_the_url(self):
        recovery_id = "e" * 32

        class FakeContext:
            url = "https://tagging.example.com/app"

        class FakeStreamlit:
            context = FakeContext()
            session_state = {"runtime_run_id_v68_15": recovery_id, "step": 4}

        recovery_url = load_function(
            "_runtime_recovery_url_v68_44",
            {
                "st": FakeStreamlit(),
                "safe_str": lambda value: str(value or "").strip(),
                "_valid_runtime_id_v68_15": lambda value: value,
                "urlencode": urlencode,
            },
        )()
        self.assertEqual(
            recovery_url,
            f"https://tagging.example.com/app?run={recovery_id}&step=4",
        )

    def test_plain_url_starts_a_new_batch_instead_of_reopening_browser_history(self):
        recovery_id = "d" * 32
        browser_pointer_calls = []

        class FakeStreamlit:
            query_params = {}
            session_state = {}

            @staticmethod
            def rerun():
                raise RuntimeError("rerun")

            @staticmethod
            def stop():
                raise AssertionError("browser pointer was already ready")

        namespace = {
            "st": FakeStreamlit(),
            "_browser_recovery_pointer_v68_80": lambda: browser_pointer_calls.append(True),
            "_valid_runtime_id_v68_15": lambda value: value if value == recovery_id else "",
            "_runtime_query_value_v68_15": lambda name: "",
        }
        restore = load_function("_restore_browser_recovery_pointer_v68_80", namespace)

        restore()

        self.assertEqual(browser_pointer_calls, [])
        self.assertEqual(FakeStreamlit.query_params, {})

    def test_explicit_recovery_url_wins_over_browser_pointer(self):
        explicit_id = "a" * 32
        remembered_id = "b" * 32

        class FakeStreamlit:
            query_params = {"run": explicit_id}
            session_state = {}

            @staticmethod
            def rerun():
                raise AssertionError("explicit URL should not be replaced")

            @staticmethod
            def stop():
                raise AssertionError("component is already ready")

        namespace = {
            "st": FakeStreamlit(),
            "_browser_recovery_pointer_v68_80": lambda: None,
            "_valid_runtime_id_v68_15": lambda value: value if value in {explicit_id, remembered_id} else "",
            "_runtime_query_value_v68_15": lambda name: explicit_id if name == "run" else "",
        }
        restore = load_function("_restore_browser_recovery_pointer_v68_80", namespace)

        restore()

        self.assertEqual(FakeStreamlit.query_params["run"], explicit_id)


if __name__ == "__main__":
    unittest.main()
