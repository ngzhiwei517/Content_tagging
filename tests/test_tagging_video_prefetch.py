import sys
import tempfile
import threading
import types
import unittest
from pathlib import Path
from unittest.mock import patch


class TaggingVideoPrefetchTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        from ugc_tagger.final_update2_backend import load_backend

        with patch.dict(sys.modules, {"cv2": types.ModuleType("cv2")}):
            cls.backend = load_backend()

    def test_prefetch_runs_asynchronously_and_materializes_bytes(self):
        started = threading.Event()
        release = threading.Event()

        def fake_download(_row, _token):
            started.set()
            self.assertTrue(release.wait(timeout=2))
            return b"video-bytes"

        function_globals = self.backend.start_video_prefetch.__globals__
        original = function_globals["_download_video_bytes_for_prefetch"]
        function_globals["_download_video_bytes_for_prefetch"] = fake_download
        try:
            future = self.backend.start_video_prefetch(
                {
                    "submittedVideoUrl": "https://www.tiktok.com/@creator/video/123",
                    "mediaUrls": ["https://cdn.example.test/video.mp4"],
                    "isSlideshow": False,
                },
                "token",
            )
            self.assertIsNotNone(future)
            self.assertTrue(started.wait(timeout=2))
            self.assertFalse(future.done())
            release.set()
            with tempfile.TemporaryDirectory() as tmp:
                output = Path(tmp) / "video.mp4"
                self.assertTrue(
                    self.backend.materialize_prefetched_video(future, str(output))
                )
                self.assertEqual(output.read_bytes(), b"video-bytes")
        finally:
            release.set()
            function_globals["_download_video_bytes_for_prefetch"] = original

    def test_prefetch_skips_scraper_errors_and_non_video_rows(self):
        self.assertIsNone(
            self.backend.start_video_prefetch(
                {
                    "submittedVideoUrl": "https://www.tiktok.com/@creator/video/123",
                    "mediaUrls": ["https://cdn.example.test/video.mp4"],
                    "errorCode": "POST_NOT_FOUND",
                    "isSlideshow": False,
                },
                "token",
            )
        )
        self.assertIsNone(
            self.backend.start_video_prefetch(
                {
                    "submittedVideoUrl": "https://www.tiktok.com/@creator/photo/123",
                    "mediaUrls": ["https://cdn.example.test/image.jpg"],
                    "isSlideshow": True,
                },
                "token",
            )
        )

    def test_failed_prefetch_preserves_existing_download_fallback(self):
        future = types.SimpleNamespace(result=lambda: (_ for _ in ()).throw(RuntimeError("blocked")))
        with tempfile.TemporaryDirectory() as tmp:
            output = Path(tmp) / "video.mp4"
            self.assertFalse(
                self.backend.materialize_prefetched_video(future, str(output))
            )
            self.assertFalse(output.exists())

    def test_pipeline_keeps_gemini_and_checkpoint_work_serialized(self):
        source = Path(
            "ugc_tagger/final_update2_backend_source.py"
        ).read_text(encoding="utf-8")
        self.assertIn("video_prefetches[next_index] = start_video_prefetch", source)
        self.assertIn("prefetched = materialize_prefetched_video", source)
        self.assertNotIn("executor.submit(call_gemini", source)
        self.assertIn("on_row_done(i + 1, len(df), out", source)


if __name__ == "__main__":
    unittest.main()
