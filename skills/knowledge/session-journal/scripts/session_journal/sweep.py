"""Backstop + backfill: summarize idle transcripts that have no note yet.

State (path -> mtime) lives outside the vault, so a resumed session (new mtime) is
summarized again and a failed one is retried on the next sweep.
"""
from __future__ import annotations

import fcntl
import json
import time
import traceback
from pathlib import Path
from typing import Dict, Iterator, List

from .config import Config
from .summarize import summarize_file

DEFAULT_MAX = 5


def _state_file(cfg: Config) -> Path:
    cfg.state_dir.mkdir(parents=True, exist_ok=True)
    return cfg.state_dir / "processed.json"


def load_state(cfg: Config) -> Dict[str, float]:
    try:
        return json.loads(_state_file(cfg).read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return {}


def save_state(cfg: Config, state: Dict[str, float]) -> None:
    tmp = _state_file(cfg).with_suffix(".tmp")
    tmp.write_text(json.dumps(state, indent=0), encoding="utf-8")
    tmp.replace(_state_file(cfg))


def candidates(cfg: Config, days: float) -> Iterator[Path]:
    globs = [(cfg.claude_projects, "*/*.jsonl"), (cfg.codex_sessions, "**/rollout-*.jsonl")]
    for root, pattern in globs:
        if root.exists():
            yield from root.glob(pattern)


def due(cfg: Config, days: float, state: Dict[str, float]) -> List[Path]:
    now = time.time()
    out = []
    for path in candidates(cfg, days):
        mtime = path.stat().st_mtime
        if now - mtime > days * 86400 or now - mtime < cfg.idle_hours * 3600:
            continue
        if state.get(str(path)) == mtime:
            continue
        out.append(path)
    return sorted(out, key=lambda p: p.stat().st_mtime)


def run(cfg: Config, days: float = 30, max_items: int = DEFAULT_MAX) -> int:
    """Summarize up to max_items (0 = no limit) due transcripts, oldest first. One sweep at a time."""
    cfg.state_dir.mkdir(parents=True, exist_ok=True)
    with open(cfg.state_dir / "sweep.lock", "w") as lock:
        try:
            fcntl.flock(lock, fcntl.LOCK_EX | fcntl.LOCK_NB)
        except BlockingIOError:
            return 0
        state = load_state(cfg)
        todo = due(cfg, days, state)
        done = 0
        for path in todo[: max_items or None]:
            mtime = path.stat().st_mtime
            try:
                summarize_file(cfg, path)
            except Exception:
                print(f"sweep: failed {path}\n{traceback.format_exc()}", flush=True)
                continue
            state[str(path)] = mtime
            save_state(cfg, state)
            done += 1
        return done
