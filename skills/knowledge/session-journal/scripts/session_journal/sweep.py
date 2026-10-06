"""Backstop + backfill: summarize idle transcripts that changed since they were last handled."""
from __future__ import annotations

import fcntl
import time
import traceback
from pathlib import Path
from typing import Dict, Iterator, List

from . import state
from .config import Config
from .summarize import summarize_file

DEFAULT_MAX = 5
MAX_FAILS = state.MAX_FAILS


def candidates(cfg: Config) -> Iterator[Path]:
    for root, pattern in ((cfg.claude_projects, "*/*.jsonl"), (cfg.codex_sessions, "**/rollout-*.jsonl")):
        if root.exists():
            yield from root.glob(pattern)


def due(cfg: Config, days: float, seen: Dict[str, dict]) -> List[Path]:
    now = time.time()
    out = []
    for path in candidates(cfg):
        mtime = path.stat().st_mtime
        age = now - mtime
        if age > days * 86400 or age < cfg.idle_hours * 3600:
            continue
        if state.is_settled(seen.get(str(path), {}), mtime):
            continue
        out.append((mtime, path))
    return [p for _, p in sorted(out)]


def load_state(cfg: Config) -> Dict[str, dict]:
    return state.load(cfg)


def run(cfg: Config, days: float = 30, max_items: int = DEFAULT_MAX) -> int:
    """Summarize up to max_items (0 = no limit) due transcripts, oldest first. One sweep at a time."""
    cfg.state_dir.mkdir(parents=True, exist_ok=True)
    with open(cfg.state_dir / "sweep.lock", "w") as lock:
        try:
            fcntl.flock(lock, fcntl.LOCK_EX | fcntl.LOCK_NB)
        except BlockingIOError:
            return 0
        done = 0
        for path in due(cfg, days, state.load(cfg))[: max_items or None]:
            mtime = path.stat().st_mtime
            try:
                summarize_file(cfg, path)
            except Exception:
                state.mark_failed(cfg, path, mtime)
                print(f"sweep: failed {path}\n{traceback.format_exc()}", flush=True)
                continue
            state.mark_done(cfg, path, mtime)
            done += 1
        return done
