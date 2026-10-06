#!/usr/bin/env python3
"""session-journal CLI. See ../SKILL.md.

  journal.py hook start|end --agent claude|codex   (stdin: hook JSON)
  journal.py summarize [--agent A] TRANSCRIPT
  journal.py sweep [--days 30] [--max 5]           (--max 0 = no limit)
  journal.py export [--force]                     (--force allows deleting 5+ exported notes)
  journal.py context [CWD]
"""
from __future__ import annotations

import argparse
import os
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))

from session_journal import config, export, hooks, summarize, sweep  # noqa: E402


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(prog="journal.py")
    sub = ap.add_subparsers(dest="cmd", required=True)
    h = sub.add_parser("hook")
    h.add_argument("event", choices=["start", "end"])
    h.add_argument("--agent", choices=["claude", "codex"], required=True)
    s = sub.add_parser("summarize")
    s.add_argument("--agent", default="")
    s.add_argument("transcript")
    w = sub.add_parser("sweep")
    w.add_argument("--days", type=float, default=30)
    w.add_argument("--max", type=int, default=sweep.DEFAULT_MAX)
    e = sub.add_parser("export")
    e.add_argument("--force", action="store_true")
    c = sub.add_parser("context")
    c.add_argument("cwd", nargs="?", default=os.getcwd())
    args = ap.parse_args(argv)

    if args.cmd == "hook":
        return hooks.safe_handle(args.event, args.agent, config.load)
    cfg = config.load()
    if args.cmd == "summarize":
        rel = summarize.summarize_file(cfg, Path(args.transcript))
        print(f"summarize: {args.transcript} -> {rel or 'skipped'}", flush=True)
    elif args.cmd == "sweep":
        print(f"sweep: {sweep.run(cfg, days=args.days, max_items=args.max)} summarized", flush=True)
    elif args.cmd == "export":
        r = export.run(cfg, force=args.force)
        print("export: not configured" if r is None else
              f"export: {len(r.exported)} exported, {len(r.blocked)} blocked {r.blocked}, commit={r.committed}")
    elif args.cmd == "context":
        print(hooks.start_context(cfg, args.cwd))
    return 0


if __name__ == "__main__":
    sys.exit(main())
