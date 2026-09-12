import pathlib
import unittest


ROOT = pathlib.Path(__file__).resolve().parents[1]


class CloudStreamlitIntegrationTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.app_source = (ROOT / "app.py").read_text(encoding="utf-8")

    def test_cloud_path_is_opt_in_before_local_tagging_execution(self):
        switch = "if _cloud_backend_enabled_v68_102():"
        local_path = "saved_large_batch = _large_batch_manifest_v68_43(selected)"
        self.assertIn(switch, self.app_source)
        self.assertLess(self.app_source.index(switch), self.app_source.index(local_path))

    def test_cloud_resume_state_is_part_of_runtime_checkpoint(self):
        for key in (
            "cloud_tagging_job_id_v68_102",
            "cloud_tagging_results_v68_102",
            "cloud_tagging_pending_v68_102",
            "cloud_tagging_attempted_links_v68_102",
        ):
            self.assertGreaterEqual(self.app_source.count(f'"{key}"'), 2)

    def test_deployment_contract_is_additive_and_secret_managed(self):
        schema = (ROOT / "cloud_job_schema.sql").read_text(encoding="utf-8")
        self.assertIn("create table if not exists public.taggy_cloud_jobs", schema)
        self.assertIn("create table if not exists public.taggy_cloud_job_posts", schema)
        self.assertIn("enable row level security", schema)
        self.assertIn("revoke all", schema)
        self.assertNotIn("drop table", schema.casefold())

        secrets_example = (
            ROOT / ".streamlit" / "secrets.toml.example"
        ).read_text(encoding="utf-8")
        self.assertIn("[cloud_backend]", secrets_example)
        self.assertNotIn("@gmail.com", secrets_example)
        self.assertNotIn("@umusic.com", secrets_example)


if __name__ == "__main__":
    unittest.main()
