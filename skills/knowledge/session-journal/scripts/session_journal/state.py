"""processed.json, outside the vault: transcript path -> {"mtime": float, "fails": int}.

A transcript is due again only when its mtime changes (a resumed session). A failing one
is retried until it has failed MAX_FAILS times at the same mtime, so a broken setup
cannot burn model calls forever.
"""
from __future__ import annotations

import fcntl
import json
import os
import tempfile
from contextlib import contextmanager
from pathlib import Path
from typing import Dict, Iterator

from .config import Config

MAX_FAILS = 3


def _file(cfg: Config) -> Path:
    cfg.state_dir.mkdir(parents=True, exist_ok=True)
    return cfg.state_dir / "processed.json"


def load(cfg: Config) -> Dict[str, dict]:
    try:
        data = json.loads(_file(cfg).read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return {}
    return {k: v for k, v in data.items() if isinstance(v, dict)} if isinstance(data, dict) else {}


@contextmanager
def _locked(cfg: Config) -> Iterator[None]:
    """Hooks and sweeps update this file from different processes: read-modify-write under a lock."""
    with open(_file(cfg).with_suffix(".lock"), "w") as fh:
        fcntl.flock(fh, fcntl.LOCK_EX)
        try:
            yield
        finally:
            fcntl.flock(fh, fcntl.LOCK_UN)


def _save(cfg: Config, data: Dict[str, dict]) -> None:
    fd, tmp = tempfile.mkstemp(dir=str(cfg.state_dir), prefix="processed.", suffix=".tmp")
    with os.fdopen(fd, "w", encoding="utf-8") as fh:
        json.dump(data, fh, indent=0)
    os.replace(tmp, _file(cfg))


def _update(cfg: Config, path: Path, mtime: float, failed: bool) -> None:
    with _locked(cfg):
        data = load(cfg)
        entry = data.get(str(path), {})
        fails = (entry.get("fails", 0) + 1 if entry.get("mtime") == mtime else 1) if failed else 0
        data[str(path)] = {"mtime": mtime, "fails": fails}
        _save(cfg, data)


def mark_done(cfg: Config, path: Path, mtime: float) -> None:
    _update(cfg, path, mtime, failed=False)


def mark_failed(cfg: Config, path: Path, mtime: float) -> None:
    _update(cfg, path, mtime, failed=True)


def is_settled(entry: dict, mtime: float) -> bool:
    """Done, or given up, for this exact transcript version."""
    return entry.get("mtime") == mtime and (entry.get("fails", 0) == 0 or entry.get("fails", 0) >= MAX_FAILS)
