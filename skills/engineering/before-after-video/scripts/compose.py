"""Combine the before/after takes into one side-by-side MP4 (and optionally a GIF).

Usage: python compose.py OUT_DIR [--topic X] [--gif] [--width 960] [--crf 20]

Reads OUT_DIR/<topic>_BEFORE.mp4 and <topic>_AFTER.mp4 (or before.mp4 / after.mp4
without --topic), writes <topic>_SIDE_BY_SIDE.mp4 next to them. The takes carry
their own BEFORE/AFTER corner badge (drawn by recorder.py), so no text filter is
needed here. The shorter take holds its last frame until the longer one ends.
"""
from __future__ import annotations

import argparse
import subprocess
import sys
from pathlib import Path

from media import report_size, require_ffmpeg, run_ffmpeg, video_name


def duration(path: Path) -> float:
    out = subprocess.run(["ffprobe", "-v", "error", "-show_entries", "format=duration", "-of", "csv=p=0", str(path)],
                                capture_output=True, text=True)
    if out.returncode != 0:
        raise RuntimeError(f"ffprobe failed on {path}: {out.stderr.strip()}")
    return float(out.stdout.strip())


def side_by_side(before: Path, after: Path, dst: Path, *, width: int, crf: int) -> Path:
    longest = max(duration(before), duration(after))
    # each take scaled to `width` (960 + 960 = 1920, a full-HD frame), padded with its own last frame
    pane = f"setpts=PTS-STARTPTS,scale={width}:-2,tpad=stop_mode=clone:stop_duration={longest:.2f}"
    run_ffmpeg(["ffmpeg", "-v", "error", "-y", "-i", str(before), "-i", str(after), "-filter_complex",
                f"[0:v]{pane}[a];[1:v]{pane}[b];[a][b]hstack=inputs=2[v]", "-map", "[v]", "-t", f"{longest:.2f}",
                "-r", "30", "-c:v", "libx264", "-preset", "medium", "-tune", "animation", "-crf", str(crf),
                "-pix_fmt", "yuv420p", "-movflags", "+faststart", "-an", str(dst)])
    return dst


def to_gif(src: Path, dst: Path, *, width: int) -> Path:
    # 12 fps and a per-clip palette keep UI text readable at a fraction of the size
    run_ffmpeg(["ffmpeg", "-v", "error", "-y", "-i", str(src), "-vf",
                f"fps=12,scale={width}:-1:flags=lanczos,split[s0][s1];[s0]palettegen=stats_mode=diff[p];"
                "[s1][p]paletteuse=dither=bayer:bayer_scale=5:diff_mode=rectangle", "-loop", "0", str(dst)])
    return dst


def main() -> None:
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument("out_dir", type=Path)
    ap.add_argument("--topic", help="file prefix used when recording")
    ap.add_argument("--gif", action="store_true", help="also write a GIF of the side-by-side")
    ap.add_argument("--width", type=int, default=960, help="width of each pane in px")
    ap.add_argument("--crf", type=int, default=20, help="H.264 quality: lower = sharper and bigger")
    args = ap.parse_args()

    require_ffmpeg()
    before, after = (args.out_dir / video_name(m, args.topic) for m in ("before", "after"))
    missing = [str(p) for p in (before, after) if not p.exists()]
    if missing:
        sys.exit(f"missing take(s): {', '.join(missing)}. Record both before composing.")

    stem = f"{args.topic}_SIDE_BY_SIDE" if args.topic else "side_by_side"
    mp4 = side_by_side(before, after, args.out_dir / f"{stem}.mp4", width=args.width, crf=args.crf)
    report_size(mp4)
    print(mp4)
    if args.gif:
        gif = to_gif(mp4, args.out_dir / f"{stem}.gif", width=args.width)
        report_size(gif)
        print(gif)


if __name__ == "__main__":
    main()
