"""processed.json, outside the vault: transcript path -> {"mtime": float, "fails": int}.

A transcript is due again only when its mtime changes (a resumed session). A failing one
is retried until it has failed MAX_FAILS times at the same mtime, so a broken setup
cannot burn model calls forever.
"""
from __future__ import annotations

import json
from pathlib import Path
from typing import Dict

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


def _save(cfg: Config, data: Dict[str, dict]) -> None:
    tmp = _file(cfg).with_suffix(".tmp")
    tmp.write_text(json.dumps(data, indent=0), encoding="utf-8")
    tmp.replace(_file(cfg))


def _update(cfg: Config, path: Path, mtime: float, fails: int) -> None:
    data = load(cfg)  # re-read: hooks and sweeps write this file from different processes
    data[str(path)] = {"mtime": mtime, "fails": fails}
    _save(cfg, data)


def mark_done(cfg: Config, path: Path, mtime: float) -> None:
    _update(cfg, path, mtime, 0)


def mark_failed(cfg: Config, path: Path, mtime: float) -> None:
    entry = load(cfg).get(str(path), {})
    fails = entry.get("fails", 0) + 1 if entry.get("mtime") == mtime else 1
    _update(cfg, path, mtime, fails)


def is_settled(entry: dict, mtime: float) -> bool:
    """Done, or given up, for this exact transcript version."""
    return entry.get("mtime") == mtime and (entry.get("fails", 0) == 0 or entry.get("fails", 0) >= MAX_FAILS)
