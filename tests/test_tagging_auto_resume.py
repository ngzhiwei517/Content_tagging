import ast
import re
import tempfile
import time
import unittest
from pathlib import Path
from types import SimpleNamespace
from typing import Dict, Optional

import pandas as pd

from ugc_tagger.batch_checkpoint import BatchCheckpointStore


ROOT = Path(__file__).resolve().parents[1]
APP_PATH = ROOT / "app.py"
APP_SOURCE = APP_PATH.read_text(encoding="utf-8")
APP_TREE = ast.parse(APP_SOURCE)


def _load_functions(names, namespace):
    definitions = [
        node
        for node in APP_TREE.body
        if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef))
        and node.name in names
    ]
    module = ast.Module(body=definitions, type_ignores=[])
    ast.fix_missing_locations(module)
    exec(compile(module, str(APP_PATH), "exec"), namespace)
    return namespace


def _valid_id(value) -> str:
    candidate = str(value or "").strip()
    return candidate if re.fullmatch(r"[a-f0-9]{32}", candidate) else ""


class _ToggleRemote:
    def __init__(self):
        self.objects = {}
        self.fail = False

    def save(self, key, payload):
        if self.fail:
            raise RuntimeError("synthetic remote failure")
        self.objects[key] = payload

    def load(self, key):
        return self.objects.get(key)

    def list_prefix(self, prefix):
        return {
            key: payload
            for key, payload in self.objects.items()
            if key.startswith(prefix)
        }

    def delete(self, key):
        self.objects.pop(key, None)

    def delete_prefix(self, prefix):
        for key in [key for key in self.objects if key.startswith(prefix)]:
            self.objects.pop(key, None)


class AutoResumeStateTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        namespace = {
            "Dict": Dict,
            "Optional": Optional,
            "safe_str": lambda value: str(value or "").strip(),
            "time": time,
            "_valid_runtime_id_v68_15": _valid_id,
        }
        _load_functions(
            {
                "_tagging_auto_resume_action_v68_55",
                "_tagging_active_job_matches_v68_55",
            },
            namespace,
        )
        cls.action = staticmethod(namespace["_tagging_auto_resume_action_v68_55"])
        cls.active_job_matches = staticmethod(
            namespace["_tagging_active_job_matches_v68_55"]
        )

    @staticmethod
    def sample_rows(count=50):
        return pd.DataFrame(
            [
                {
                    "Platform": "TikTok",
                    "Source": "refresh test",
                    "Link": f"https://www.tiktok.com/@creator/video/{880000 + index}",
                    "Market": "SG",
                    "Track": "Refresh track",
                    "Creator": f"creator_{index}",
                }
                for index in range(count)
            ]
        )

    def test_replacement_session_waits_then_continues_only_after_a_safe_yield(self):
        selected = self.sample_rows()
        runtime_id = "a" * 32
        now = int(time.time())
        with tempfile.TemporaryDirectory() as directory:
            store = BatchCheckpointStore(Path(directory), chunk_size=50)
            manifest = store.prepare(
                runtime_id,
                selected,
                model="gemini-3.1-flash-lite",
                comparison_run_id="refresh-test",
                comparison_started_utc="2026-08-05T00:00:00+00:00",
            )
            job_id = manifest["job_id"]

            executing = store.mark_executing(manifest, lease_seconds=600)
            self.assertEqual(
                self.action(job_id, job_id, executing, now_epoch=now),
                "wait",
            )

            ready = store.mark_continuation_ready(executing)
            self.assertEqual(
                self.action(job_id, job_id, ready, now_epoch=now),
                "resume",
            )

    def test_paused_completed_mismatched_and_expired_jobs_never_auto_run(self):
        selected = self.sample_rows()
        runtime_id = "b" * 32
        now = int(time.time())
        with tempfile.TemporaryDirectory() as directory:
            store = BatchCheckpointStore(Path(directory), chunk_size=50)
            manifest = store.prepare(
                runtime_id,
                selected,
                model="gemini-3.1-flash-lite",
                comparison_run_id="guard-test",
                comparison_started_utc="2026-08-05T00:00:00+00:00",
            )
            job_id = manifest["job_id"]
            paused = store.mark_paused(manifest, quota=True)
            self.assertEqual(
                self.action(job_id, job_id, paused, now_epoch=now),
                "manual",
            )

            expired = dict(manifest)
            expired.update(
                status="running",
                continuation_ready=False,
                execution_lease_until=now - 1,
            )
            self.assertEqual(
                self.action(job_id, job_id, expired, now_epoch=now),
                "manual",
            )
            self.assertEqual(
                self.action("c" * 32, job_id, manifest, now_epoch=now),
                "manual",
            )

            chunk = store.chunk_frame(selected, manifest, 0).assign(
                **{"Creative Type": "Others"}
            )
            completed = store.save_completed_chunk(
                manifest,
                0,
                chunk,
                elapsed_seconds=1,
            )
            self.assertEqual(completed["status"], "completed")
            self.assertEqual(
                self.action(job_id, job_id, completed, now_epoch=now),
                "manual",
            )

    def test_exact_start_marker_can_recover_before_first_manifest_write(self):
        job_id = "d" * 32
        self.assertEqual(
            self.action(job_id, job_id, None, now_epoch=int(time.time())),
            "resume",
        )
        self.assertEqual(
            self.action(
                job_id,
                job_id,
                {
                    "job_id": job_id,
                    "status": "running",
                    "continuation_ready": False,
                    "execution_lease_until": 0,
                },
                now_epoch=int(time.time()),
            ),
            "resume",
        )

    def test_active_job_a_cannot_switch_to_expected_job_b(self):
        job_a = "a" * 32
        job_b = "b" * 32
        self.assertTrue(self.active_job_matches(True, job_a, job_a))
        self.assertFalse(self.active_job_matches(True, job_a, job_b))
        self.assertTrue(self.active_job_matches(False, job_a, job_b))
        self.assertTrue(self.active_job_matches(True, "", ""))

    def test_execution_lock_allows_only_one_tab_to_launch_a_paid_unit(self):
        with tempfile.TemporaryDirectory() as directory:
            store = BatchCheckpointStore(Path(directory), chunk_size=50)
            job_id = "1" * 32
            first_owner = "2" * 32
            second_owner = "3" * 32

            self.assertTrue(store.try_acquire_execution(job_id, first_owner))
            self.assertTrue(store.execution_is_active(job_id))
            self.assertFalse(store.try_acquire_execution(job_id, first_owner))
            self.assertFalse(store.try_acquire_execution(job_id, second_owner))

            store.release_execution(job_id, second_owner)
            self.assertTrue(store.execution_is_active(job_id))
            store.release_execution(job_id, first_owner)
            self.assertFalse(store.execution_is_active(job_id))

            self.assertTrue(store.try_acquire_execution(job_id, first_owner))
            store._write_local_json(
                store._execution_lock_path(job_id),
                {"owner_id": first_owner, "lease_until": int(time.time()) - 1},
            )
            self.assertTrue(store.try_acquire_execution(job_id, second_owner))
            store.release_execution(job_id, second_owner)

    def test_remote_execution_fence_must_save_before_provider_work_can_start(self):
        selected = self.sample_rows()
        remote = _ToggleRemote()
        with tempfile.TemporaryDirectory() as directory:
            store = BatchCheckpointStore(
                Path(directory),
                chunk_size=50,
                persistent_store=remote,
            )
            manifest = store.prepare(
                "f" * 32,
                selected,
                model="gemini-3.1-flash-lite",
                comparison_run_id="remote-fence-test",
                comparison_started_utc="2026-08-05T00:00:00+00:00",
            )
            ready = store.mark_continuation_ready(manifest)
            remote.fail = True
            with self.assertRaisesRegex(
                RuntimeError,
                "REMOTE_CHECKPOINT_WRITE_FAILED",
            ):
                store.mark_executing(ready)

        runner = APP_SOURCE.split(
            "def _run_checkpointed_tag_every_link_v68_43",
            1,
        )[1].split("def run_real_tagging_backend", 1)[0]
        self.assertLess(
            runner.index("store.mark_executing(manifest)"),
            runner.index("final_update2_scrape_links(links, apify_token)"),
        )
        self.assertLess(
            runner.index("store.mark_executing(manifest)"),
            runner.index("_tag_remaining_with_row_isolation_v68_43("),
        )
        self.assertIn("remote_records_saved is False", runner)


class AutoResumeQueryTests(unittest.TestCase):
    def setUp(self):
        self.fake_st = SimpleNamespace(query_params={})
        namespace = {
            "TAGGING_CONTINUE_JOB_QUERY_V68_55": "continue_job",
            "TAGGING_CONTINUE_UNTIL_QUERY_V68_55": "continue_until",
            "TAGGING_CONTINUE_TTL_SECONDS_V68_55": 7200,
            "re": re,
            "safe_str": lambda value: str(value or "").strip(),
            "st": self.fake_st,
            "time": time,
        }
        _load_functions(
            {
                "_valid_runtime_id_v68_15",
                "_runtime_query_value_v68_15",
                "_clear_tagging_continue_query_v68_55",
                "_set_tagging_continue_query_v68_55",
                "_tagging_continue_job_v68_55",
            },
            namespace,
        )
        self.set_marker = namespace["_set_tagging_continue_query_v68_55"]
        self.get_marker = namespace["_tagging_continue_job_v68_55"]

    def test_marker_is_job_specific_and_expires(self):
        job_id = "e" * 32
        self.assertTrue(self.set_marker(job_id))
        self.assertEqual(self.get_marker(), job_id)
        self.fake_st.query_params["continue_until"] = str(int(time.time()) - 1)
        self.assertEqual(self.get_marker(), "")
        self.assertNotIn("continue_job", self.fake_st.query_params)
        self.assertNotIn("continue_until", self.fake_st.query_params)

        self.fake_st.query_params.update(
            continue_job="not-a-job",
            continue_until="not-a-time",
        )
        self.assertEqual(self.get_marker(), "")
        self.assertNotIn("continue_job", self.fake_st.query_params)
        self.assertNotIn("continue_until", self.fake_st.query_params)

    def test_recovery_links_and_runtime_state_do_not_persist_auto_run_intent(self):
        recovery = APP_SOURCE.split(
            "def _runtime_recovery_url_v68_44",
            1,
        )[1].split("@st.dialog", 1)[0]
        state_keys = APP_SOURCE.split(
            "RUNTIME_CHECKPOINT_STATE_KEYS_V68_15 = (",
            1,
        )[1].split(")", 1)[0]
        self.assertIn('urlencode({"run": run_id, "step": step})', recovery)
        self.assertNotIn("continue_job", recovery)
        self.assertNotIn("tagging_job_active_v68_43", state_keys)
        self.assertNotIn("Bookmark this page", APP_SOURCE)

    def test_step_four_sets_renews_and_clears_the_temporary_marker(self):
        step_four = APP_SOURCE.split("# STEP 4: Run tagging", 1)[1].split(
            "# STEP 5: Review",
            1,
        )[0]
        self.assertIn("_tagging_auto_resume_action_v68_55(", step_four)
        self.assertIn("_render_tagging_auto_wait_v68_55(", step_four)
        self.assertIn("try_acquire_execution(", step_four)
        self.assertIn("release_execution(", step_four)
        self.assertGreaterEqual(
            step_four.count("_set_tagging_continue_query_v68_55("),
            3,
        )
        self.assertIn("_clear_tagging_continue_query_v68_55()", step_four)
        self.assertIn("if tagged_result is None:", step_four)
        self.assertIn("_tagging_active_job_matches_v68_55(", step_four)
        self.assertLess(
            step_four.index("_tagging_active_job_matches_v68_55("),
            step_four.index("try_acquire_execution("),
        )
        self.assertNotIn('"Analysis model (optional)"', step_four)
        runner = APP_SOURCE.split(
            "def _run_checkpointed_tag_every_link_v68_43",
            1,
        )[1].split("def run_real_tagging_backend", 1)[0]
        self.assertIn("except BaseException as control:", runner)
        self.assertIn("store.mark_continuation_ready(manifest)", runner)

    def test_navigation_and_opening_another_batch_clear_stale_intent(self):
        go_helper = APP_SOURCE.split("def go(step: int):", 1)[1].split(
            "def safe_str",
            1,
        )[0]
        recovery_request = APP_SOURCE.split(
            "def _request_runtime_recovery_v68_44",
            1,
        )[1].split("def _runtime_recovery_url_v68_44", 1)[0]
        self.assertIn("if int(step) != 4:", go_helper)
        self.assertIn("_clear_tagging_continue_query_v68_55()", go_helper)
        self.assertIn(
            "_clear_tagging_continue_query_v68_55()",
            recovery_request,
        )


if __name__ == "__main__":
    unittest.main()
