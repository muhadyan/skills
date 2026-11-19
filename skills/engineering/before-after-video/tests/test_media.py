"""File names, ffmpeg errors and the size warning."""
import contextlib
import io
import unittest
from unittest import mock

from helpers import TempDirCase

import media


class VideoNameTest(unittest.TestCase):
    def test_topic_prefix_and_upper_mode(self):
        self.assertEqual(media.video_name("before", "discount"), "discount_BEFORE.mp4")

    def test_no_topic(self):
        self.assertEqual(media.video_name("after"), "after.mp4")


class RequireFfmpegTest(unittest.TestCase):
    def test_missing_ffmpeg_says_how_to_install(self):
        with mock.patch.object(media.shutil, "which", return_value=None):
            with self.assertRaisesRegex(RuntimeError, "brew install ffmpeg"):
                media.require_ffmpeg()


class RunFfmpegTest(unittest.TestCase):
    def test_failure_carries_stderr(self):
        with self.assertRaisesRegex(RuntimeError, "boom"):
            media.run_ffmpeg(["sh", "-c", "echo boom >&2; exit 3"])


class ReportSizeTest(TempDirCase):
    def report(self, size: int) -> str:
        path = self.tmp / "v.mp4"
        path.write_bytes(b"\0" * size)
        err = io.StringIO()
        with contextlib.redirect_stderr(err):
            media.report_size(path)
        return err.getvalue()

    def test_small_file_has_no_warning(self):
        self.assertNotIn("over", self.report(1000))

    def test_big_file_warns(self):
        self.assertIn("over 10 MB", self.report(11 * 1_048_576))


if __name__ == "__main__":
    unittest.main()
