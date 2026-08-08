import ast
import copy
import json
import shutil
import tempfile
import unittest
from pathlib import Path
from typing import Dict
from urllib.parse import urlencode
from unittest.mock import Mock

import pandas as pd

from ugc_tagger.batch_checkpoint import BatchCheckpointStore
from ugc_tagger.persistent_checkpoint import (
    PersistentCheckpointConfig,
    PostgresCheckpointBackend,
    RecoveryCheckpointObjects,
    SupabaseCheckpointBackend,
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

    def test_remote_checkpoint_waits_until_the_batch_contains_a_post(self):
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
        self.assertFalse(has_posts(empty_state))
        self.assertTrue(has_posts(populated_state))
        self.assertIn(
            "if not _runtime_checkpoint_has_posts_v68_44(state_payload):",
            APP_SOURCE,
        )

    def test_managed_secrets_and_automatic_recovery_remain_without_manual_controls(self):
        self.assertIn('_managed_api_secret_v68_43("GEMINI_API_KEY")', APP_SOURCE)
        self.assertIn('_managed_api_secret_v68_43("APIFY_TOKEN")', APP_SOURCE)
        self.assertNotIn('key="runtime_save_batch_button_v68_44"', APP_SOURCE)
        self.assertNotIn('with st.expander("Open a saved batch"', APP_SOURCE)
        self.assertNotIn('key="runtime_recovery_button_v68_44"', APP_SOURCE)
        self.assertIn("_restore_runtime_checkpoint_v68_15()", APP_SOURCE)
        self.assertIn("_persist_runtime_checkpoint_v68_15()", APP_SOURCE)
        self.assertNotIn("Current recovery ID", APP_SOURCE)
        self.assertNotIn('(1, "01", "API Keys", "Setup")', APP_SOURCE)

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


if __name__ == "__main__":
    unittest.main()
