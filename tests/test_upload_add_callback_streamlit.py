import unittest
from pathlib import Path

from streamlit.testing.v1 import AppTest


APP_PATH = Path(__file__).resolve().parents[1] / "app.py"
VALID_UPLOAD = (
    "Link,Track,Market,Views\n"
    "https://www.tiktok.com/@synthetic.creator/video/7600000000000000001,"
    "Synthetic Track,SG,1234\n"
).encode("utf-8")


class UploadedAddCallbackStreamlitTests(unittest.TestCase):
    def test_prepared_upload_commits_before_competing_file_rerun(self):
        app = AppTest.from_file(APP_PATH, default_timeout=60).run()
        self.assertEqual(len(app.exception), 0)

        app.file_uploader[0].upload(
            "synthetic_upload.csv",
            VALID_UPLOAD,
            "text/csv",
        ).run(timeout=60)
        add_button = next(
            button
            for button in app.button
            if button.label == "Add uploaded rows to batch"
        )
        upload_status = app.get("status")
        self.assertEqual(len(upload_status), 1)
        self.assertEqual(
            upload_status[0].label,
            "Prepared 1 uploaded post. The Add button is ready below.",
        )
        self.assertFalse(add_button.disabled)
        self.assertEqual(
            len(app.session_state["uploaded_table_cache_v68_107"]),
            1,
        )

        # Queue another uploader change with the click. The button callback
        # must commit the rows prepared on the rendered page before the rerun
        # encounters this replacement file with no supported post URL.
        app.file_uploader[0].upload(
            "replacement_without_links.csv",
            b"Unknown,Notes\n1,no supported post URL\n",
            "text/csv",
        )
        add_button.click().run(timeout=60)

        self.assertEqual(len(app.exception), 0)
        self.assertEqual(len(app.session_state["batch_df"]), 1)
        self.assertEqual(
            app.session_state["last_message"],
            "Added 1 uploaded rows. Skipped 0 duplicate rows.",
        )

        continue_button = next(
            button for button in app.button if button.label == "Continue"
        )
        continue_button.click().run(timeout=60)
        self.assertEqual(len(app.exception), 0)
        self.assertEqual(app.session_state["step"], 3)


if __name__ == "__main__":
    unittest.main()
