import unittest

import pandas as pd

from taggy_cloud.client import dataframe_records
from taggy_cloud.sanitize import sanitize_mapping


class CloudSanitizationTests(unittest.TestCase):
    def test_input_rows_drop_secret_and_binary_fields(self):
        rows = dataframe_records(
            pd.DataFrame(
                [
                    {
                        "Link": "https://www.tiktok.com/@creator/video/1234567890",
                        "Track": "Test",
                        "api_token": "must-not-leave-streamlit",
                        "video_bytes": b"binary",
                    }
                ]
            )
        )
        self.assertEqual("Test", rows[0]["Track"])
        self.assertNotIn("api_token", rows[0])
        self.assertNotIn("video_bytes", rows[0])

    def test_results_drop_nested_local_media_paths(self):
        result = sanitize_mapping(
            {
                "Creative Type": "Travel",
                "evidence": {
                    "local_video_path": "C:/temp/private.mp4",
                    "caption": "Public caption",
                },
                "downloaded_media": "C:/temp/private.mp4",
            }
        )
        self.assertNotIn("downloaded_media", result)
        self.assertNotIn("local_video_path", result["evidence"])
        self.assertEqual("Public caption", result["evidence"]["caption"])


if __name__ == "__main__":
    unittest.main()
