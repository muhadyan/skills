"""Screencast JPEG frames → constant-frame-rate H.264 MP4.

No Playwright import, so the timing logic is unit-testable on its own.
"""
from __future__ import annotations

import subprocess
import time
from pathlib import Path
from typing import Callable, Optional

from media import EVEN_DIMS


def _wall_ms() -> float:
    return time.time() * 1000


class FrameClock:
    """Maps browser frame timestamps (ms) to video frame slots.

    The browser sends a frame only when the screen changes, so the encoder
    repeats the last frame up to the next frame's slot; that keeps pauses their
    real length. ``skip`` removes a stretch of time (a cut) from the timeline.
    """

    def __init__(self, fps: int, now_ms: Callable[[], float] = _wall_ms):
        self.fps = fps
        self._now = now_ms
        self.t0: Optional[float] = None  # browser timestamp of the first frame
        self.wall0 = 0.0                 # wall clock at the first frame

    def slot(self, ts_ms: float) -> int:
        if self.t0 is None:
            self.t0, self.wall0 = ts_ms, self._now()
        return int((ts_ms - self.t0) * self.fps / 1000)

    def now_slot(self) -> Optional[int]:
        if self.t0 is None:
            return None
        return int((self._now() - self.wall0) * self.fps / 1000)

    def skip(self, gap_ms: float) -> None:
        if self.t0 is not None:
            self.t0 += gap_ms
            self.wall0 += gap_ms


class FrameEncoder:
    """Pipes frames into ffmpeg, filling time gaps with the last frame."""

    def __init__(self, dst: Path, fps: int, crf: int, *, clock: Optional[FrameClock] = None,
                 popen: Callable[..., subprocess.Popen] = subprocess.Popen):
        self.dst = Path(dst)
        self.fps = fps
        self.clock = clock or FrameClock(fps)
        self.slots = 0                  # frames written so far
        self.last: Optional[bytes] = None
        self.broken: Optional[OSError] = None  # set when ffmpeg died; raised by finish()
        self.proc = popen(
            ["ffmpeg", "-v", "error", "-y", "-f", "image2pipe", "-c:v", "mjpeg", "-framerate", str(fps), "-i", "-",
             "-vf", EVEN_DIMS, "-c:v", "libx264", "-preset", "medium", "-tune", "animation", "-crf", str(crf),
             "-pix_fmt", "yuv420p", "-movflags", "+faststart", "-an", str(self.dst)],
            stdin=subprocess.PIPE, stderr=subprocess.PIPE)

    # Older flow scripts cut a load by shifting these by hand; keep them writable.
    @property
    def t0(self) -> Optional[float]:
        return self.clock.t0

    @t0.setter
    def t0(self, value: float) -> None:
        self.clock.t0 = value

    @property
    def wall0(self) -> float:
        return self.clock.wall0

    @wall0.setter
    def wall0(self, value: float) -> None:
        self.clock.wall0 = value

    def _write(self, data: bytes) -> None:
        if self.broken is None:
            try:
                self.proc.stdin.write(data)
            except OSError as e:  # ffmpeg died; finish() reports why
                self.broken = e
        self.slots += 1

    def _fill_to(self, slot: int) -> None:
        while self.slots < slot and self.last is not None:
            self._write(self.last)

    def on_frame(self, frame) -> None:
        """Called from the screencast callback, so it never raises."""
        slot = self.clock.slot(frame["timestamp"])
        if slot < self.slots:  # this slot is written already: keep the newest frame for the next one
            self.last = frame["data"]
            return
        self._fill_to(slot)
        self.last = frame["data"]
        self._write(self.last)

    def skip(self, gap_ms: float) -> None:
        self.clock.skip(gap_ms)

    def snapshot(self, path: Path) -> Optional[Path]:
        """Write the newest frame (a JPEG) to ``path``; None before the first frame."""
        if self.last is None:
            return None
        path = Path(path)
        path.write_bytes(self.last)
        return path

    def finish(self) -> Path:
        now = self.clock.now_slot()
        if now is not None:  # hold the last frame up to "now"
            self._fill_to(now)
        try:
            self.proc.stdin.close()
        except OSError as e:
            self.broken = self.broken or e
        err = self.proc.stderr.read().decode(errors="replace")
        code = self.proc.wait()
        if code != 0 or self.last is None or self.broken is not None:
            self.dst.unlink(missing_ok=True)
            reason = err.strip() or (str(self.broken) if self.broken else "no frames captured")
            raise RuntimeError(f"ffmpeg failed for {self.dst}: {reason}")
        return self.dst

    def abort(self) -> None:
        self.proc.kill()
        self.proc.wait()
        for pipe in (self.proc.stdin, self.proc.stderr):
            try:
                pipe.close()
            except OSError:
                pass
        self.dst.unlink(missing_ok=True)
