#!/usr/bin/env python3
"""vault-memory CLI. See ../SKILL.md.

  memory.py hook start|end           (stdin: hook JSON)
  memory.py context [CWD]
  memory.py commit
  memory.py migrate [--apply] [--vault DIR] [--also-redact FILE] [--claude-projects DIR] [--codex-memories DIR]
"""
from __future__ import annotations

import argparse
import os
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))

from vault_memory import config, gitsync, hooks, migrate  # noqa: E402


def _print_report(r: migrate.Report, apply: bool) -> None:
    print(f"migrate: {r.written} notes {'written' if apply else 'would be written (dry run)'}")
    print(f"unchanged: {r.unchanged}; existing and different, skipped ({len(r.skipped_existing)}):")
    for d in r.skipped_existing:
        print(f"  {d}")
    print(f"unresolved project folders ({len(r.unresolved)}): {', '.join(r.unresolved) or '-'}")
    print(f"collisions ({len(r.collisions)}):")
    for c in r.collisions:
        print(f"  {c}")
    print(f"redactions ({sum(len(x.hits) for x in r.redactions)} in {len(r.redactions)} notes):")
    for red in r.redactions:
        for hit in red.hits:
            print(f"  {red.dest}:{hit.line} [{hit.kind}] {hit.preview}")


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(prog="memory.py")
    sub = ap.add_subparsers(dest="cmd", required=True)
    h = sub.add_parser("hook")
    h.add_argument("event", choices=["start", "end"])
    c = sub.add_parser("context")
    c.add_argument("cwd", nargs="?", default=os.getcwd())
    sub.add_parser("commit")
    m = sub.add_parser("migrate")
    m.add_argument("--apply", action="store_true")
    m.add_argument("--also-redact", type=Path, help="file with one exact secret string per line")
    m.add_argument("--vault", type=Path, help="write here instead of the configured vault")
    m.add_argument("--claude-projects", type=Path, default=Path("~/.claude/projects").expanduser())
    m.add_argument("--codex-memories", type=Path, default=Path("~/.codex/memories").expanduser())
    args = ap.parse_args(argv)

    if args.cmd == "hook":
        return hooks.safe_handle(args.event, config.load)
    if args.cmd == "migrate":
        vault = args.vault or config.load().vault
        literals = tuple(l.strip() for l in args.also_redact.read_text().splitlines()
                         if l.strip()) if args.also_redact else ()
        report = migrate.run(vault, args.claude_projects, args.codex_memories, apply=args.apply,
                             literals=literals)
        _print_report(report, args.apply)
        return 0
    cfg = config.load()
    if args.cmd == "context":
        print(hooks.context(cfg, args.cwd))
    elif args.cmd == "commit":
        n = gitsync.commit_memory(cfg.vault, cfg.lock_dir)
        print(f"commit: {n} file{'' if n == 1 else 's'}", flush=True)
    return 0


if __name__ == "__main__":
    sys.exit(main())
