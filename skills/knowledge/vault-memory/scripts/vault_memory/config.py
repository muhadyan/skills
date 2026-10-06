"""Settings from ~/.config/vault-memory/config.env (KEY=VALUE lines, ~ expanded)."""
from __future__ import annotations

import os
from dataclasses import dataclass
from pathlib import Path
from typing import Optional

DEFAULT_PATH = Path("~/.config/vault-memory/config.env").expanduser()


class ConfigError(Exception):
    pass


@dataclass(frozen=True)
class Config:
    vault: Path
    state_dir: Path
    lock_dir: Path  # shared with session-journal so both never run git in the vault at once


def _read_env_file(path: Path) -> dict:
    values = {}
    for raw in path.read_text(encoding="utf-8").splitlines():
        line = raw.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        key, value = line.split("=", 1)
        values[key.strip()] = value.strip().strip('"').strip("'")
    return values


def _path(value: str) -> Path:
    return Path(os.path.expandvars(value)).expanduser()


def load(path: Optional[Path] = None) -> Config:
    path = path or Path(os.environ.get("VAULT_MEMORY_CONFIG", DEFAULT_PATH))
    if not path.exists():
        raise ConfigError(f"missing config file {path}; see SKILL.md")
    v = _read_env_file(path)
    if not v.get("VAULT"):
        raise ConfigError(f"VAULT is not set in {path}")
    return Config(
        vault=_path(v["VAULT"]),
        state_dir=_path(v.get("STATE_DIR", "~/.local/state/vault-memory")),
        lock_dir=_path(v.get("LOCK_DIR", "~/.local/state/session-journal")),
    )
