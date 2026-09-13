import pathlib
import unittest


ROOT = pathlib.Path(__file__).resolve().parents[1]
APP_SOURCE = (ROOT / "app.py").read_text(encoding="utf-8")


class MultiSessionResponsivenessTests(unittest.TestCase):
    def test_tagging_uses_per_batch_lock_without_a_global_worker_cap(self):
        step_four = APP_SOURCE.split("# STEP 4: Run tagging", 1)[1].split(
            "# STEP 5: Review",
            1,
        )[0]
        self.assertIn("execution_store.try_acquire_execution(", step_four)
        self.assertIn("execution_store.release_execution(", step_four)
        self.assertNotIn("worker_queue.claim(", step_four)
        self.assertNotIn("capacity_full", step_four)
        self.assertNotIn("Semaphore", step_four)

    def test_local_tagging_yields_after_two_completed_posts(self):
        self.assertIn(
            "MAX_LIVE_POSTS_PER_EXECUTION_V68_52 = 2",
            APP_SOURCE,
        )

    def test_recovery_link_warns_against_separate_users_sharing_one_batch(self):
        self.assertIn(
            '"This recovery link opens one saved batch.',
            APP_SOURCE,
        )
        self.assertIn('"Start a separate batch"', APP_SOURCE)
        self.assertIn("_start_separate_batch_v68_104()", APP_SOURCE)

    def test_separate_batch_gets_a_new_recovery_id(self):
        helper = APP_SOURCE.split(
            "def _start_separate_batch_v68_104()",
            1,
        )[1].split("# Display values and engagement metrics", 1)[0]
        self.assertIn("_new_runtime_recovery_id_v68_44()", helper)

    def test_plain_app_url_is_not_changed_into_a_shared_recovery_link(self):
        helper = APP_SOURCE.split(
            "def _sync_runtime_query_v68_15()",
            1,
        )[1].split("def _checkpoint_setting_v68_44", 1)[0]
        self.assertIn("explicit_run_id != run_id", helper)
        self.assertNotIn('st.query_params["run"] = run_id', helper)

    def test_track_catalog_lookup_is_explicit_instead_of_running_on_upload(self):
        helper = APP_SOURCE.split(
            "def render_uploaded_track_catalog_feedback_v68_62(",
            1,
        )[1].split("CREATOR_PROFILE_CACHE_TTL_SECONDS_V68_61", 1)[0]
        self.assertIn('"Confirm track now (optional)"', helper)
        self.assertIn(
            '"still check the official audio automatically during tagging."',
            helper,
        )
        self.assertIn("if st.button(", helper)
        self.assertLess(
            helper.index("if st.button("),
            helper.index("campaign_track_catalog_status_v68_36("),
        )
        paste_section = APP_SOURCE.split("with paste_tab:", 1)[1].split(
            'st.markdown("</div>"',
            1,
        )[0]
        self.assertIn(
            "resolved_paste_artist = render_uploaded_track_catalog_feedback_v68_62(",
            paste_section,
        )

    def test_normal_reruns_queue_remote_runtime_saves(self):
        helper = APP_SOURCE.split(
            "def _persist_runtime_checkpoint_v68_15(",
            1,
        )[1].split("def _render_continue_later_v68_85", 1)[0]
        self.assertIn("_save_runtime_checkpoint_remote_v68_106(", helper)
        self.assertIn("wait=verify_remote", helper)
        self.assertIn('save_status == "queued"', helper)
        self.assertNotIn('remote_store.save("runtime.json", payload)', helper)

    def test_add_posts_continue_navigates_before_checkpoint_autosave(self):
        helper = APP_SOURCE.split(
            "def _continue_to_select_posts_v68_108()",
            1,
        )[1].split("def safe_str", 1)[0]
        self.assertIn("st.session_state.step = 3", helper)
        self.assertIn(
            "st.session_state.defer_pre_render_checkpoint_once_v68_108 = True",
            helper,
        )
        self.assertNotIn("_persist_runtime_checkpoint_v68_15", helper)

        shell = APP_SOURCE.split(
            "defer_pre_render_checkpoint_v68_108 = bool(",
            1,
        )[1].split("managed_gemini_key_v68_43", 1)[0]
        self.assertIn(
            "if not defer_pre_render_checkpoint_v68_108:",
            shell,
        )

        add_posts = APP_SOURCE.split("# STEP 2: Add posts", 1)[1].split(
            "# STEP 3: Select posts",
            1,
        )[0]
        self.assertIn("on_click=_continue_to_select_posts_v68_108", add_posts)

    def test_tagging_batches_remote_partial_results(self):
        runner = APP_SOURCE.split(
            "def _run_checkpointed_tag_every_link_v68_43(",
            1,
        )[1].split("def run_real_tagging_backend", 1)[0]
        self.assertIn("persist_remote=False", runner)
        self.assertIn("def flush_partial_snapshot()", runner)
        self.assertIn("store.save_partial_snapshot(", runner)


if __name__ == "__main__":
    unittest.main()
