"""Small ffmpeg/file helpers shared by recorder.py and compose.py (no Playwright needed)."""
from __future__ import annotations

import re
import shutil
import subprocess
import sys
from pathlib import Path

UPLOAD_LIMIT_MB = 10  # GitHub's video limit on free plans; the smallest common target
EVEN_DIMS = "scale=trunc(iw/2)*2:trunc(ih/2)*2"  # libx264 + yuv420p rejects odd sizes
# libx264 starts about 1.5 threads per core by default; four keep a laptop cool and still encode UI video in real time
ENCODE_THREADS = ["-threads", "4"]


# A take or topic name becomes part of a file name: letters, digits, "_", "-", "." and spaces, no path.
_SAFE_NAME = re.compile(r"[^\W_][\w. -]*")


def _check_name(name: str) -> str:
    if not _SAFE_NAME.fullmatch(name) or ".." in name:
        raise ValueError(f"take and topic names take letters, digits, '_', '-', '.' and spaces, "
                         f"starting with a letter or digit: {name!r}")
    return name


def video_name(mode: str, topic: str | None = None) -> str:
    """``<topic>_BEFORE.mp4`` when a topic is given, else ``before.mp4``."""
    _check_name(mode)
    return f"{_check_name(topic)}_{mode.upper()}.mp4" if topic else f"{mode}.mp4"


def require_ffmpeg() -> None:
    if shutil.which("ffmpeg") is None:
        raise RuntimeError("ffmpeg not found on PATH. Install it (macOS: brew install ffmpeg).")


def run_ffmpeg(cmd: list[str]) -> None:
    result = subprocess.run(cmd, capture_output=True, text=True)
    if result.returncode != 0:
        raise RuntimeError(f"ffmpeg failed: {' '.join(cmd)}\n{result.stderr.strip()}")


def report_size(path: Path) -> None:
    mb = path.stat().st_size / 1_048_576
    note = f"  (over {UPLOAD_LIMIT_MB} MB: re-encode with a higher crf before uploading)" if mb > UPLOAD_LIMIT_MB else ""
    print(f"{path}  {mb:.1f} MB{note}", file=sys.stderr)
