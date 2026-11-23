"""Join takes into one MP4, in order, even when their sizes differ, plus a contact sheet.

Usage: python join.py OUT_DIR --parts shop admin [--topic X] [--name demo] [--size WxH] [--crf 20] [--gif]

Reads OUT_DIR/<topic>_SHOP.mp4, <topic>_ADMIN.mp4, ... (the names Recorder gives
each take) and writes <topic>_DEMO.mp4 and <topic>_DEMO_sheet.png next to them.
Each part is scaled to fit the canvas (by default the largest part's size) and
centred on a dark background, so a phone take and a PC take play in one video.
One part named like the output (``--parts demo``) gets only the sheet.
"""
from __future__ import annotations

import argparse
import os
import re
import subprocess
import sys
from pathlib import Path
from typing import Optional, Sequence

from compose import contact_sheet, to_gif
from media import ENCODE_THREADS, report_size, require_ffmpeg, run_ffmpeg, video_name

BACKGROUND = "0x111827"  # the caption bar's dark grey, so the bars read as a frame around the take
FPS = 30
MAX_SIDE = 7680  # 8K: a bigger canvas only makes ffmpeg fail after a long wait


def frame_size(path: Path) -> tuple[int, int]:
    out = subprocess.run(["ffprobe", "-v", "error", "-select_streams", "v:0", "-show_entries", "stream=width,height",
                          "-of", "csv=p=0", str(path)], capture_output=True, text=True)
    if out.returncode != 0:
        raise RuntimeError(f"ffprobe failed on {path}: {out.stderr.strip()}")
    width, height = out.stdout.strip().split(",")[:2]
    return int(width), int(height)


def canvas(sizes: Sequence[tuple[int, int]], size: Optional[str] = None) -> tuple[int, int]:
    """``size`` ("1440x810") if given, else the largest part by area, rounded up to even numbers."""
    if size is not None:
        match = re.fullmatch(r"([1-9]\d*)x([1-9]\d*)", size)
        if not match:
            raise ValueError(f"--size must be WIDTHxHEIGHT, for example 1440x810, not {size!r}")
        width, height = int(match.group(1)), int(match.group(2))
        if max(width, height) > MAX_SIDE:
            raise ValueError(f"--size must be WIDTHxHEIGHT with sides up to {MAX_SIDE}, not {size!r}")
    else:
        width, height = max(sizes, key=lambda s: s[0] * s[1])
    return width + width % 2, height + height % 2  # libx264 + yuv420p rejects odd sizes


def join(parts: Sequence[Path], dst: Path, *, size: tuple[int, int], crf: int) -> Path:
    width, height = size
    fit = (f"setpts=PTS-STARTPTS,fps={FPS},scale={width}:{height}:force_original_aspect_ratio=decrease,"
           f"pad={width}:{height}:(ow-iw)/2:(oh-ih)/2:color={BACKGROUND},setsar=1,format=yuv420p")
    chains = ";".join(f"[{i}:v]{fit}[v{i}]" for i in range(len(parts)))
    inputs = "".join(f"[v{i}]" for i in range(len(parts)))
    cmd = ["ffmpeg", "-v", "error", "-y"]
    for part in parts:
        cmd += ["-i", str(part)]
    # ffmpeg writes the output while it encodes: a failed run must not leave a short file under the final name
    part = dst.with_name(f".{dst.stem}.part{dst.suffix}")
    cmd += ["-filter_complex", f"{chains};{inputs}concat=n={len(parts)}:v=1:a=0[v]", "-map", "[v]",
            "-c:v", "libx264", "-preset", "medium", "-tune", "animation", "-crf", str(crf), "-pix_fmt", "yuv420p",
            *ENCODE_THREADS, "-movflags", "+faststart", "-an", str(part)]
    try:
        run_ffmpeg(cmd)
        os.replace(part, dst)
    finally:
        part.unlink(missing_ok=True)
    return dst


def part_paths(out_dir: Path, topic: Optional[str], parts: Sequence[str]) -> list[Path]:
    return [out_dir / video_name(part, topic) for part in parts]


def main() -> None:
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument("out_dir", type=Path)
    ap.add_argument("--parts", nargs="+", required=True, help="take names in play order, as given to Recorder")
    ap.add_argument("--topic", help="file prefix used when recording")
    ap.add_argument("--name", default="demo", help="name of the joined video (default: demo)")
    ap.add_argument("--size", help="canvas as WIDTHxHEIGHT (default: the largest part's size)")
    ap.add_argument("--crf", type=int, default=20, help="H.264 quality: lower = sharper and bigger")
    ap.add_argument("--gif", action="store_true", help="also write a GIF of the joined video")
    args = ap.parse_args()

    require_ffmpeg()
    try:
        paths = part_paths(args.out_dir, args.topic, args.parts)
        dst = args.out_dir / video_name(args.name, args.topic)
    except ValueError as e:
        sys.exit(str(e))
    missing = [str(p) for p in paths if not p.exists()]
    if missing:
        sys.exit(f"missing take(s): {', '.join(missing)}. Record every part before joining.")
    if dst in paths and len(paths) > 1:
        sys.exit(f"{dst.name} is also a part: joining would overwrite it. Pick another --name.")

    if paths != [dst]:
        try:
            size = canvas([frame_size(p) for p in paths], args.size)
        except ValueError as e:
            sys.exit(str(e))
        join(paths, dst, size=size, crf=args.crf)
    report_size(dst)
    print(dst)
    print(contact_sheet(dst, dst.with_name(f"{dst.stem}_sheet.png")))
    if args.gif:
        gif = to_gif(dst, dst.with_suffix(".gif"), width=min(960, frame_size(dst)[0]))
        report_size(gif)
        print(gif)


if __name__ == "__main__":
    main()
