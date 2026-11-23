"""Frame timing, cuts and stills of the screencast encoder (no browser needed)."""
import io
import unittest

from helpers import TempDirCase, duration, jpeg, needs_ffmpeg

from encoder import FrameClock, FrameEncoder


class FakeClock:
    def __init__(self, ms: float = 1_000_000.0):
        self.ms = ms

    def __call__(self) -> float:
        return self.ms


class FakeProc:
    """Stands in for the ffmpeg process: collects what the encoder writes."""

    def __init__(self, *_a, **_k):
        self.stdin = io.BytesIO()
        self.stdin.close = lambda: None  # keep the buffer readable after finish()
        self.stderr = io.BytesIO(b"")
        self.killed = False
        self.waited = False
        self.code = 0

    def wait(self) -> int:
        self.waited = True
        return self.code

    def kill(self) -> None:
        self.killed = True


class DeadPipe(io.BytesIO):
    def write(self, _data):
        raise BrokenPipeError(32, "Broken pipe")


class DeadProc(FakeProc):
    """ffmpeg that died: every write fails, stderr says why."""

    def __init__(self, *a, **k):
        super().__init__(*a, **k)
        self.stdin = DeadPipe()
        self.stderr = io.BytesIO(b"Invalid data found when processing input")
        self.code = 1


class FrameClockTest(unittest.TestCase):
    def test_first_frame_is_slot_zero(self):
        c = FrameClock(30, now_ms=FakeClock())
        self.assertEqual(c.slot(5000.0), 0)

    def test_slot_follows_browser_time(self):
        c = FrameClock(30, now_ms=FakeClock())
        c.slot(5000.0)
        self.assertEqual(c.slot(6000.0), 30)

    def test_now_slot_is_none_before_first_frame(self):
        self.assertIsNone(FrameClock(30, now_ms=FakeClock()).now_slot())

    def test_now_slot_follows_wall_clock(self):
        wall = FakeClock()
        c = FrameClock(30, now_ms=wall)
        c.slot(5000.0)
        wall.ms += 2000
        self.assertEqual(c.now_slot(), 60)

    def test_skip_removes_the_gap(self):
        wall = FakeClock()
        c = FrameClock(30, now_ms=wall)
        c.slot(5000.0)
        c.skip(10_000)
        self.assertEqual(c.slot(16_000.0), 30)  # 11 s later in browser time, 10 s of it cut
        wall.ms += 11_000
        self.assertEqual(c.now_slot(), 30)

    def test_skip_before_first_frame_does_nothing(self):
        c = FrameClock(30, now_ms=FakeClock())
        c.skip(10_000)
        self.assertEqual(c.slot(5000.0), 0)


class FrameEncoderTest(TempDirCase):
    def make(self, wall=None):
        return FrameEncoder(self.tmp / "x.mp4", 10, 20, clock=FrameClock(10, now_ms=wall or FakeClock()),
                            popen=FakeProc)

    def test_repeats_last_frame_until_next_timestamp(self):
        enc = self.make()
        enc.on_frame({"timestamp": 0.0, "data": b"A"})
        enc.on_frame({"timestamp": 500.0, "data": b"B"})
        self.assertEqual(enc.proc.stdin.getvalue(), b"AAAAAB")

    def test_finish_holds_last_frame_up_to_now(self):
        wall = FakeClock()
        enc = self.make(wall)
        enc.on_frame({"timestamp": 0.0, "data": b"A"})
        wall.ms += 300
        self.assertEqual(enc.finish(), self.tmp / "x.mp4")
        self.assertEqual(enc.proc.stdin.getvalue(), b"AAA")

    def test_skip_leaves_no_frozen_gap(self):
        enc = self.make()
        enc.on_frame({"timestamp": 0.0, "data": b"A"})
        enc.skip(5000)
        enc.on_frame({"timestamp": 5200.0, "data": b"B"})
        self.assertEqual(enc.proc.stdin.getvalue(), b"AAB")

    def test_t0_and_wall0_stay_writable_for_old_flows(self):
        enc = self.make()
        enc.on_frame({"timestamp": 0.0, "data": b"A"})
        enc.t0 += 5000
        enc.wall0 += 5000
        enc.on_frame({"timestamp": 5200.0, "data": b"B"})
        self.assertEqual(enc.proc.stdin.getvalue(), b"AAB")

    def test_snapshot_writes_last_frame(self):
        enc = self.make()
        self.assertIsNone(enc.snapshot(self.tmp / "s.jpg"))
        enc.on_frame({"timestamp": 0.0, "data": b"JPEGDATA"})
        self.assertEqual(enc.snapshot(self.tmp / "s.jpg").read_bytes(), b"JPEGDATA")

    def test_finish_without_frames_raises(self):
        with self.assertRaisesRegex(RuntimeError, "no frames captured"):
            self.make().finish()

    def test_abort_kills_waits_and_removes_file(self):
        enc = self.make()
        (self.tmp / "x.mp4").write_bytes(b"partial")
        enc.abort()
        self.assertTrue(enc.proc.killed)
        self.assertTrue(enc.proc.waited)
        self.assertFalse((self.tmp / "x.mp4").exists())

    def test_frames_faster_than_fps_do_not_stretch_time(self):
        enc = self.make()  # 10 fps: one slot per 100 ms
        for ts, data in ((0.0, b"A"), (20.0, b"B"), (40.0, b"C"), (100.0, b"D")):
            enc.on_frame({"timestamp": ts, "data": data})
        self.assertEqual(enc.proc.stdin.getvalue(), b"AD")  # B and C share slot 0 with A
        self.assertEqual(enc.last, b"D")

    def test_newest_frame_in_a_slot_fills_the_gap(self):
        enc = self.make()
        enc.on_frame({"timestamp": 0.0, "data": b"A"})
        enc.on_frame({"timestamp": 50.0, "data": b"B"})
        enc.on_frame({"timestamp": 300.0, "data": b"C"})
        self.assertEqual(enc.proc.stdin.getvalue(), b"ABBC")

    def test_ffmpeg_runs_on_a_fixed_thread_count(self):
        calls = []
        FrameEncoder(self.tmp / "x.mp4", 30, 20, popen=lambda cmd, **k: calls.append(cmd) or FakeProc())
        cmd = calls[0]
        self.assertEqual(cmd[cmd.index("-threads") + 1], "4")

    def test_dead_ffmpeg_surfaces_at_finish_with_its_error(self):
        enc = FrameEncoder(self.tmp / "x.mp4", 10, 20, clock=FrameClock(10, now_ms=FakeClock()), popen=DeadProc)
        enc.on_frame({"timestamp": 0.0, "data": b"A"})  # must not raise inside the screencast callback
        (self.tmp / "x.mp4").write_bytes(b"partial")
        with self.assertRaisesRegex(RuntimeError, "Invalid data found"):
            enc.finish()
        self.assertFalse((self.tmp / "x.mp4").exists())

    def test_failed_finish_removes_the_partial_file(self):
        enc = self.make()
        enc.proc.code = 1
        enc.on_frame({"timestamp": 0.0, "data": b"A"})
        (self.tmp / "x.mp4").write_bytes(b"partial")
        with self.assertRaises(RuntimeError):
            enc.finish()
        self.assertFalse((self.tmp / "x.mp4").exists())


@needs_ffmpeg
class RealEncodeTest(TempDirCase):
    def test_cut_shortens_the_video(self):
        wall = FakeClock()
        enc = FrameEncoder(self.tmp / "cut.mp4", 30, 23, clock=FrameClock(30, now_ms=wall))
        red, green = jpeg("red"), jpeg("green")
        enc.on_frame({"timestamp": 0.0, "data": red})
        enc.on_frame({"timestamp": 1000.0, "data": red})
        enc.skip(5000)  # 5 s of loading cut out
        enc.on_frame({"timestamp": 6000.0, "data": green})
        wall.ms += 7000  # the take ends 7 s after the first frame
        enc.finish()
        self.assertAlmostEqual(duration(self.tmp / "cut.mp4"), 2.0, delta=0.2)


if __name__ == "__main__":
    unittest.main()
