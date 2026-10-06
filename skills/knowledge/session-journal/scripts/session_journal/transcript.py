"""Read Claude Code and Codex transcripts (JSONL) into plain prompt/reply turns.

Tool calls, tool output, thinking, injected context and subagent turns are dropped:
the summarizer only needs what the person asked and what the agent answered.
"""
from __future__ import annotations

import json
import re
from dataclasses import dataclass, field
from pathlib import Path
from typing import Iterator, List, Optional, Tuple

TURN_CAP = 4000
DEFAULT_CAP = 60000
CUT_MARK = "\n[... middle of session cut ...]\n"
COMMAND_RE = re.compile(r"<command-name>\s*(/?[^<]*?)\s*</command-name>")
ARGS_RE = re.compile(r"<command-args>(.*?)</command-args>", re.DOTALL)


@dataclass
class Transcript:
    agent: str
    session_id: str = ""
    cwd: str = ""
    date: str = ""
    interactive: bool = True
    prompts: List[str] = field(default_factory=list)
    turns: List[Tuple[str, str]] = field(default_factory=list)

    def add(self, role: str, text: str) -> None:
        text = text.strip()
        if not text:
            return
        if role == "user":
            self.prompts.append(text)
        self.turns.append((role, text))


def _rows(path: Path) -> Iterator[dict]:
    with open(path, encoding="utf-8", errors="replace") as fh:
        for line in fh:
            try:
                row = json.loads(line)
            except ValueError:
                continue
            if isinstance(row, dict):
                yield row


def _user_text(text: str) -> str:
    """A real prompt, a slash command with its args, or '' for injected context."""
    text = text.strip()
    cmd = COMMAND_RE.search(text)
    if cmd:
        args = ARGS_RE.search(text)
        return f"{cmd.group(1)} {args.group(1).strip()}".strip() if args else cmd.group(1)
    if text.startswith("<") or text.startswith("# AGENTS.md") or text.startswith("Caveat:"):
        return ""
    return text


def _blocks(content, kind: str) -> str:
    if isinstance(content, str):
        return content
    if not isinstance(content, list):
        return ""
    return "\n".join(b.get("text", "") for b in content if isinstance(b, dict) and b.get("type") == kind)


def parse_claude(path: Path) -> Transcript:
    t = Transcript(agent="claude", session_id=path.stem)
    for row in _rows(path):
        t.session_id = row.get("sessionId") or t.session_id
        t.cwd = t.cwd or row.get("cwd", "")
        t.date = t.date or str(row.get("timestamp", ""))[:10]
        if row.get("entrypoint") == "sdk-cli":
            t.interactive = False
        if row.get("isMeta") or row.get("isSidechain"):
            continue
        msg = row.get("message") or {}
        if row.get("type") == "user":
            t.add("user", _user_text(_blocks(msg.get("content"), "text")))
        elif row.get("type") == "assistant":
            t.add("assistant", _blocks(msg.get("content"), "text"))
    return t


def parse_codex(path: Path) -> Transcript:
    t = Transcript(agent="codex")
    for row in _rows(path):
        payload = row.get("payload") or {}
        if row.get("type") == "session_meta":
            t.session_id = payload.get("id") or payload.get("session_id") or ""
            t.cwd = payload.get("cwd", "")
            t.date = str(payload.get("timestamp") or row.get("timestamp", ""))[:10]
            t.interactive = payload.get("source") != "exec" and payload.get("originator") != "codex_exec"
            continue
        if row.get("type") != "response_item" or payload.get("type") != "message":
            continue
        role = payload.get("role")
        if role == "user":
            t.add("user", _user_text(_blocks(payload.get("content"), "input_text")))
        elif role == "assistant":
            t.add("assistant", _blocks(payload.get("content"), "output_text"))
    return t


def _first_row(path: Path) -> Optional[dict]:
    return next(_rows(path), None)


def parse(path: Path) -> Transcript:
    first = _first_row(path) or {}
    if first.get("type") == "session_meta" or "/.codex/" in str(path):
        return parse_codex(path)
    return parse_claude(path)


def condense(t: Transcript, cap: int = DEFAULT_CAP) -> str:
    """Turns as 'USER:/ASSISTANT:' text; long sessions keep the first third and the last two thirds."""
    parts = []
    for role, text in t.turns:
        if len(text) > TURN_CAP:
            text = text[: TURN_CAP // 2] + " [...] " + text[-TURN_CAP // 2:]
        parts.append(f"{role.upper()}: {text}")
    out = "\n\n".join(parts)
    if len(out) <= cap:
        return out
    head = cap // 3
    tail = cap - head - len(CUT_MARK)
    return out[:head] + CUT_MARK + out[-tail:]
