"""Shared test helpers: put scripts/ on the path, make tiny media files with ffmpeg."""
from __future__ import annotations

import shutil
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

SKILL = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(SKILL / "scripts"))

HAS_FFMPEG = bool(shutil.which("ffmpeg") and shutil.which("ffprobe"))
needs_ffmpeg = unittest.skipUnless(HAS_FFMPEG, "ffmpeg/ffprobe not on PATH")


class TempDirCase(unittest.TestCase):
    def setUp(self) -> None:
        self._tmp = tempfile.TemporaryDirectory()
        self.tmp = Path(self._tmp.name)

    def tearDown(self) -> None:
        self._tmp.cleanup()


def jpeg(color: str, size: str = "64x48") -> bytes:
    """One JPEG frame of a flat colour, like a screencast frame."""
    out = subprocess.run(["ffmpeg", "-v", "error", "-f", "lavfi", "-i", f"color=c={color}:s={size}", "-frames:v", "1",
                          "-f", "mjpeg", "-"], capture_output=True, check=True)
    return out.stdout


def clip(path: Path, seconds: float, color: str = "blue", size: str = "64x48") -> Path:
    subprocess.run(["ffmpeg", "-v", "error", "-y", "-f", "lavfi", "-i", f"color=c={color}:s={size}:r=30",
                    "-t", str(seconds), "-c:v", "libx264", "-pix_fmt", "yuv420p", str(path)], check=True)
    return path


def duration(path: Path) -> float:
    out = subprocess.run(["ffprobe", "-v", "error", "-show_entries", "format=duration", "-of", "csv=p=0", str(path)],
                         capture_output=True, text=True, check=True)
    return float(out.stdout.strip())
