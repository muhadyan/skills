"""Side-by-side video, contact sheets and the GIF."""
import contextlib
import io
import sys
import unittest
from unittest import mock

from helpers import TempDirCase, clip, duration, needs_ffmpeg

import compose


def run_main(*argv: str) -> str:
    out = io.StringIO()
    with mock.patch.object(sys, "argv", ["compose.py", *argv]), contextlib.redirect_stdout(out), \
            contextlib.redirect_stderr(io.StringIO()):
        compose.main()
    return out.getvalue()


class MissingTakeTest(TempDirCase):
    def test_missing_take_exits_with_a_hint(self):
        with mock.patch.object(compose, "require_ffmpeg"):
            with self.assertRaisesRegex(SystemExit, "Record both before composing"):
                run_main(str(self.tmp), "--topic", "x")


@needs_ffmpeg
class ComposeTest(TempDirCase):
    def test_side_by_side_lasts_as_long_as_the_longer_take(self):
        clip(self.tmp / "t_BEFORE.mp4", 1.0, "red")
        clip(self.tmp / "t_AFTER.mp4", 2.0, "green")
        out = run_main(str(self.tmp), "--topic", "t", "--width", "64", "--gif")
        sbs = self.tmp / "t_SIDE_BY_SIDE.mp4"
        self.assertIn(str(sbs), out)
        self.assertAlmostEqual(duration(sbs), 2.0, delta=0.2)
        for name in ("t_BEFORE_sheet.png", "t_AFTER_sheet.png", "t_SIDE_BY_SIDE.gif"):
            self.assertTrue((self.tmp / name).exists(), name)

    def test_no_topic_uses_plain_names(self):
        clip(self.tmp / "before.mp4", 1.0)
        clip(self.tmp / "after.mp4", 1.0)
        run_main(str(self.tmp), "--width", "64")
        self.assertTrue((self.tmp / "side_by_side.mp4").exists())

    def test_side_by_side_runs_on_a_fixed_thread_count(self):
        clip(self.tmp / "t_BEFORE.mp4", 0.5, "red")
        clip(self.tmp / "t_AFTER.mp4", 0.5, "green")
        with mock.patch.object(compose, "run_ffmpeg", wraps=compose.run_ffmpeg) as spy:
            run_main(str(self.tmp), "--topic", "t", "--width", "64")
        cmd = spy.call_args_list[0].args[0]
        self.assertEqual(cmd[cmd.index("-threads") + 1], "4")

    def test_duration_errors_are_clear(self):
        with self.assertRaisesRegex(RuntimeError, "ffprobe failed"):
            compose.duration(self.tmp / "nope.mp4")


if __name__ == "__main__":
    unittest.main()
