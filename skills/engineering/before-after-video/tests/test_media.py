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

    def test_names_stay_inside_the_output_folder(self):
        for mode, topic in (("../x", None), ("a/b", None), ("after", "../t"), ("after", "a\\b"), ("after", "pipe:1"),
                            ("after", "x..y"), (".hidden", None), ("-v", None), ("", None)):
            with self.subTest(mode=mode, topic=topic), self.assertRaisesRegex(ValueError, "letters"):
                media.video_name(mode, topic)

    def test_ticket_keys_and_scene_names_are_fine(self):
        self.assertEqual(media.video_name("before-buyer", "PROJ-12"), "PROJ-12_BEFORE-BUYER.mp4")
        self.assertEqual(media.video_name("shop", "z94 order v2.1"), "z94 order v2.1_SHOP.mp4")
        self.assertEqual(media.video_name("demo", "割引"), "割引_DEMO.mp4")


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
