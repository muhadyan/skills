"""SessionStart / SessionEnd hook entry. Must return fast and never break the agent:
heavy work goes to a detached child; every error is logged, never raised."""
from __future__ import annotations

import json
import os
import subprocess
import sys
import traceback
from pathlib import Path
from typing import IO, List

from . import note
from .config import Config

GUARD = "SESSION_JOURNAL"
JOURNAL = Path(__file__).resolve().parents[1] / "journal.py"
MAX_LESSONS = 10
MAX_NOTES_SCANNED = 300
CONTEXT_CAP = 2000
LOG_MAX_BYTES = 5_000_000


def child_env() -> dict:
    env = {k: v for k, v in os.environ.items()
           if not (k.startswith("CLAUDECODE") or k.startswith("CLAUDE_CODE_") or k == "CLAUDE_PID")}
    env[GUARD] = "1"
    return env


def log_path(cfg: Config) -> Path:
    """journal.log, rotated to journal.log.1 past LOG_MAX_BYTES."""
    cfg.state_dir.mkdir(parents=True, exist_ok=True)
    log = cfg.state_dir / "journal.log"
    if log.exists() and log.stat().st_size > LOG_MAX_BYTES:
        log.replace(log.with_suffix(".log.1"))
    return log


def spawn(cfg: Config, args: List[str]) -> None:
    """Start `journal.py <args>` fully detached so the hook returns at once."""
    with open(log_path(cfg), "a") as log:
        subprocess.Popen([sys.executable, str(JOURNAL), *args], stdin=subprocess.DEVNULL, stdout=log,
                         stderr=subprocess.STDOUT, env=child_env(), cwd="/", start_new_session=True)


def lessons_for(cfg: Config, project: str) -> List[str]:
    notes = sorted((cfg.vault / "sessions").rglob("*.md"), reverse=True)[:MAX_NOTES_SCANNED]
    out: List[str] = []
    for path in notes:
        meta, body = note.split(path.read_text(encoding="utf-8", errors="replace"))
        if meta.get("project") != project:
            continue
        for line in note.section(body, "Lessons").splitlines():
            line = line.strip()
            if line.startswith("- ") and line != "- (none)" and line not in out:
                out.append(line)
        if len(out) >= MAX_LESSONS:
            break
    return out[:MAX_LESSONS]


def start_context(cfg: Config, cwd: str) -> str:
    project = note.project_name(cwd)
    lines = [f"Session journal is on: this session is logged to the Obsidian vault {cfg.vault} when it ends."]
    lessons = lessons_for(cfg, project) if project else []
    if lessons:
        lines.append(f"Lessons from past sessions in '{project}':")
        lines += lessons
    return "\n".join(lines)[:CONTEXT_CAP]


def handle(event: str, agent: str, stdin: IO[str], cfg: Config, out: IO[str] = sys.stdout) -> None:
    if os.environ.get(GUARD):
        return
    try:
        payload = json.load(stdin)
    except ValueError:
        return
    if not isinstance(payload, dict) or payload.get("agent_id"):
        return
    transcript = payload.get("transcript_path") or ""
    if event == "end" and transcript:
        spawn(cfg, ["summarize", "--agent", agent, transcript])
    elif event == "start":
        ctx = start_context(cfg, payload.get("cwd") or os.getcwd())
        out.write(json.dumps({"hookSpecificOutput": {"hookEventName": "SessionStart", "additionalContext": ctx}}))
        spawn(cfg, ["sweep"])


def safe_handle(event: str, agent: str, cfg_loader) -> int:
    try:
        handle(event, agent, sys.stdin, cfg_loader())
    except Exception:  # a hook must never fail the agent session
        try:
            with open(Path("~/.local/state/session-journal/journal.log").expanduser(), "a") as log:
                log.write(traceback.format_exc())
        except OSError:
            pass
    return 0
