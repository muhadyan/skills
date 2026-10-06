"""Settings from ~/.config/session-journal/config.env (KEY=VALUE lines, ~ expanded)."""
from __future__ import annotations

import os
from dataclasses import dataclass
from pathlib import Path
from typing import Optional, Tuple

DEFAULT_PATH = Path("~/.config/session-journal/config.env").expanduser()
DEFAULT_MODEL = "claude-sonnet-5-5"


class ConfigError(Exception):
    pass


@dataclass(frozen=True)
class Config:
    vault: Path
    model: str
    claude_bin: str
    brand_safe_roots: Tuple[Path, ...]
    denylist: Path
    export_repo: Optional[Path]
    export_remote: str
    export_dir: str
    export_rules: str
    state_dir: Path
    min_prompts: int
    idle_hours: float
    claude_projects: Path
    codex_sessions: Path


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
    path = path or Path(os.environ.get("SESSION_JOURNAL_CONFIG", DEFAULT_PATH))
    if not path.exists():
        raise ConfigError(f"missing config file {path}; see SKILL.md")
    v = _read_env_file(path)
    if not v.get("VAULT"):
        raise ConfigError(f"VAULT is not set in {path}")
    vault = _path(v["VAULT"])
    roots = tuple(_path(r) for r in v.get("BRAND_SAFE_ROOTS", "").split(":") if r.strip())
    return Config(
        vault=vault,
        model=v.get("MODEL", DEFAULT_MODEL),
        claude_bin=v.get("CLAUDE_BIN", "claude"),
        brand_safe_roots=roots,
        denylist=_path(v["DENYLIST"]) if v.get("DENYLIST") else vault / "_meta" / "nda-denylist.txt",
        export_repo=_path(v["EXPORT_REPO"]) if v.get("EXPORT_REPO") else None,
        export_remote=v.get("EXPORT_REMOTE", ""),
        export_dir=v.get("EXPORT_DIR", "knowledge"),
        export_rules=v.get("EXPORT_RULES", "rules.json"),
        state_dir=_path(v.get("STATE_DIR", "~/.local/state/session-journal")),
        min_prompts=int(v.get("MIN_PROMPTS", "2")),
        idle_hours=float(v.get("IDLE_HOURS", "2")),
        claude_projects=_path(v.get("CLAUDE_PROJECTS", "~/.claude/projects")),
        codex_sessions=_path(v.get("CODEX_SESSIONS", "~/.codex/sessions")),
    )
