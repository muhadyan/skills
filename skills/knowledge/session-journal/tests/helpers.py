"""Shared fixtures: fake transcripts, a temp config, throwaway git repos."""
from __future__ import annotations

import json
import os
import subprocess
import sys
import tempfile
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "scripts"))

from session_journal.config import Config  # noqa: E402


def write_jsonl(path: Path, rows: list[dict]) -> Path:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text("".join(json.dumps(r) + "\n" for r in rows), encoding="utf-8")
    return path


def claude_rows(session_id="abcdef12-0000", cwd="/home/me/Developer/example/app",
                prompts=("Fix the login bug", "Now add a test"), entrypoint="cli") -> list[dict]:
    rows = [{"type": "permission-mode", "sessionId": session_id}]
    for i, p in enumerate(prompts):
        rows.append({"type": "user", "sessionId": session_id, "cwd": cwd, "entrypoint": entrypoint,
                     "timestamp": f"2026-10-07T0{i}:00:00Z", "message": {"role": "user", "content": p}})
        rows.append({"type": "assistant", "sessionId": session_id, "cwd": cwd,
                     "message": {"role": "assistant", "content": [
                         {"type": "thinking", "thinking": "secret thoughts"},
                         {"type": "tool_use", "name": "Bash", "input": {"command": "ls"}},
                         {"type": "text", "text": f"Done step {i}"}]}})
        rows.append({"type": "user", "sessionId": session_id, "cwd": cwd,
                     "message": {"role": "user", "content": [
                         {"type": "tool_result", "content": "TOOL OUTPUT NOISE"}]}})
    rows.append({"type": "user", "isMeta": True, "message": {"role": "user", "content": "meta prompt"}})
    rows.append({"type": "user", "isSidechain": True, "message": {"role": "user", "content": "subagent task"}})
    rows.append({"type": "user", "message": {"role": "user", "content": "<system-reminder>x</system-reminder>"}})
    return rows


def codex_rows(session_id="01a11323-6e57", cwd="/home/me/Developer/example/app",
               prompts=("Refactor the parser", "Run the tests"), source="cli") -> list[dict]:
    rows = [{"type": "session_meta", "timestamp": "2026-10-07T04:00:00Z",
             "payload": {"id": session_id, "cwd": cwd, "source": source, "originator": "codex_cli_rs"}},
            {"type": "response_item", "payload": {"type": "message", "role": "developer",
                                                  "content": [{"type": "input_text", "text": "dev rules"}]}},
            {"type": "response_item", "payload": {"type": "message", "role": "user",
                                                  "content": [{"type": "input_text",
                                                               "text": "<environment_context>x</environment_context>"}]}}]
    for i, p in enumerate(prompts):
        rows.append({"type": "response_item", "payload": {"type": "message", "role": "user",
                                                          "content": [{"type": "input_text", "text": p}]}})
        rows.append({"type": "response_item", "payload": {"type": "function_call_output", "output": "NOISE"}})
        rows.append({"type": "response_item", "payload": {"type": "message", "role": "assistant",
                                                          "content": [{"type": "output_text", "text": f"ok {i}"}]}})
    return rows


def git(cwd: Path, *args: str) -> str:
    return subprocess.run(["git", *args], cwd=cwd, check=True, capture_output=True, text=True).stdout


def make_repo(root: Path, name: str, files: dict[str, str] | None = None) -> tuple[Path, Path]:
    """A bare 'remote' plus a clone of it with one commit on main."""
    bare = root / f"{name}.git"
    subprocess.run(["git", "init", "-q", "--bare", "-b", "main", str(bare)], check=True)
    clone = root / name
    subprocess.run(["git", "clone", "-q", str(bare), str(clone)], check=True, capture_output=True)
    git(clone, "config", "user.email", "t@example.com")
    git(clone, "config", "user.name", "t")
    for rel, text in {"README.md": "x\n", **(files or {})}.items():
        (clone / rel).parent.mkdir(parents=True, exist_ok=True)
        (clone / rel).write_text(text, encoding="utf-8")
    git(clone, "add", "-A")
    git(clone, "commit", "-q", "-m", "init")
    git(clone, "push", "-q", "-u", "origin", "main")
    return bare, clone


class TempDirCase:
    """Mixin: self.tmp is a fresh directory per test; self.cfg a config rooted in it."""

    def setUp(self):  # noqa: N802
        self._td = tempfile.TemporaryDirectory()
        self.tmp = Path(self._td.name).resolve()
        self.vault = self.tmp / "vault"
        self.vault.mkdir()
        (self.vault / "_meta").mkdir()
        (self.vault / "_meta" / "nda-denylist.txt").write_text("# employer names\nacme\\s*corp\n", encoding="utf-8")
        self.cfg = Config(
            vault=self.vault, model="test-model", claude_bin="claude",
            brand_safe_roots=(self.tmp / "personal",), denylist=self.vault / "_meta" / "nda-denylist.txt",
            export_repo=None, export_dir="knowledge", export_rules="rules.json", branch="main",
            state_dir=self.tmp / "state", min_prompts=2, idle_hours=2.0,
            claude_projects=self.tmp / "claude-projects", codex_sessions=self.tmp / "codex-sessions",
            claude_settings=self.tmp / "no-settings.json", codex_hooks=self.tmp / "no-hooks.json",
            codex_config=self.tmp / "no-config.toml",
        )
        os.environ.pop("SESSION_JOURNAL", None)

    def tearDown(self):  # noqa: N802
        self._td.cleanup()
