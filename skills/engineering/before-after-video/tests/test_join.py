"""Joining takes of different sizes into one video, plus its contact sheet."""
import contextlib
import io
import subprocess
import sys
import unittest
from unittest import mock

from helpers import TempDirCase, clip, duration, needs_ffmpeg

import join


def run_main(*argv: str) -> str:
    out = io.StringIO()
    with mock.patch.object(sys, "argv", ["join.py", *argv]), contextlib.redirect_stdout(out), \
            contextlib.redirect_stderr(io.StringIO()):
        join.main()
    return out.getvalue()


def size_of(path) -> tuple:
    out = subprocess.run(["ffprobe", "-v", "error", "-select_streams", "v:0", "-show_entries", "stream=width,height",
                          "-of", "csv=p=0", str(path)], capture_output=True, text=True, check=True)
    w, h = out.stdout.strip().split(",")
    return int(w), int(h)


class CanvasTest(unittest.TestCase):
    def test_largest_part_sets_the_canvas(self):
        self.assertEqual(join.canvas([(390, 844), (1440, 810)]), (1440, 810))

    def test_odd_sizes_round_up_to_even(self):
        self.assertEqual(join.canvas([(391, 845)]), (392, 846))

    def test_size_option_wins(self):
        self.assertEqual(join.canvas([(390, 844)], "640x360"), (640, 360))

    def test_bad_size_option_is_refused(self):
        for bad in ("640", "640x", "x360", "0x360", "640x-2", "axb"):
            with self.subTest(bad=bad), self.assertRaisesRegex(ValueError, "WIDTHxHEIGHT"):
                join.canvas([(390, 844)], bad)


class ArgumentTest(TempDirCase):
    def test_missing_part_exits_with_the_file_names(self):
        with mock.patch.object(join, "require_ffmpeg"):
            with self.assertRaisesRegex(SystemExit, "t_ADMIN.mp4"):
                run_main(str(self.tmp), "--topic", "t", "--parts", "admin")

    def test_output_named_like_one_of_several_parts_is_refused(self):
        for name in ("shop", "demo"):
            (self.tmp / f"t_{name.upper()}.mp4").write_bytes(b"x")
        with mock.patch.object(join, "require_ffmpeg"):
            with self.assertRaisesRegex(SystemExit, "overwrite"):
                run_main(str(self.tmp), "--topic", "t", "--parts", "shop", "demo")

    def test_the_same_part_twice_is_allowed(self):
        self.assertEqual(join.part_paths(self.tmp, "t", ["a", "a"]), [self.tmp / "t_A.mp4"] * 2)


@needs_ffmpeg
class JoinTest(TempDirCase):
    def test_parts_of_different_sizes_play_in_order_on_one_canvas(self):
        clip(self.tmp / "t_PHONE.mp4", 1.0, "red", "100x200")
        clip(self.tmp / "t_PC.mp4", 1.5, "green", "320x180")
        out = run_main(str(self.tmp), "--topic", "t", "--parts", "phone", "pc", "--gif")
        demo = self.tmp / "t_DEMO.mp4"
        self.assertIn(str(demo), out)
        self.assertEqual(size_of(demo), (320, 180))
        self.assertAlmostEqual(duration(demo), 2.5, delta=0.2)
        for name in ("t_DEMO_sheet.png", "t_DEMO.gif"):
            self.assertTrue((self.tmp / name).exists(), name)

    def test_size_and_name_options(self):
        clip(self.tmp / "a.mp4", 0.5, "red", "100x200")
        clip(self.tmp / "b.mp4", 0.5, "blue", "200x100")
        run_main(str(self.tmp), "--parts", "a", "b", "--name", "walkthrough", "--size", "160x90")
        self.assertEqual(size_of(self.tmp / "walkthrough.mp4"), (160, 90))

    def test_one_part_named_like_the_output_only_gets_a_sheet(self):
        demo = clip(self.tmp / "t_DEMO.mp4", 0.5, "red", "64x48")
        before = demo.read_bytes()
        out = run_main(str(self.tmp), "--topic", "t", "--parts", "demo")
        self.assertEqual(demo.read_bytes(), before)
        self.assertIn("t_DEMO_sheet.png", out)
        self.assertTrue((self.tmp / "t_DEMO_sheet.png").exists())

    def test_encode_uses_a_fixed_thread_count(self):
        clip(self.tmp / "a.mp4", 0.5, "red")
        with mock.patch.object(join, "run_ffmpeg", wraps=join.run_ffmpeg) as spy:
            join.join([self.tmp / "a.mp4"], self.tmp / "out.mp4", size=(64, 48), crf=20)
        cmd = spy.call_args_list[0].args[0]
        self.assertEqual(cmd[cmd.index("-threads") + 1], "4")


if __name__ == "__main__":
    unittest.main()
