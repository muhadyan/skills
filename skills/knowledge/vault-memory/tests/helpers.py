"""Shared fixtures: a temp vault, temp config, throwaway git repos."""
from __future__ import annotations

import json
import os
import subprocess
import sys
import tempfile
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "scripts"))

from vault_memory.config import Config  # noqa: E402


def git(cwd: Path, *args: str) -> str:
    return subprocess.run(["git", *args], cwd=cwd, check=True, capture_output=True, text=True).stdout


def make_repo(root: Path, name: str, files: dict | None = None) -> tuple:
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


def write(path: Path, text: str) -> Path:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(text, encoding="utf-8")
    return path


def write_jsonl(path: Path, rows: list) -> Path:
    return write(path, "".join(json.dumps(r) + "\n" for r in rows))


def memory_note(kind: str, description: str, body: str, updated: str = "2026-10-01",
                project: str = "app") -> str:
    return (f"---\ntype: memory\nkind: {kind}\ndescription: {json.dumps(description)}\n"
            f"project: {project}\nupdated: {updated}\n---\n\n{body}\n")


class TempDirCase:
    """Mixin: self.tmp is a fresh directory per test; self.cfg a config rooted in it."""

    def setUp(self):  # noqa: N802
        self._td = tempfile.TemporaryDirectory()
        self.tmp = Path(self._td.name).resolve()
        self.vault = self.tmp / "vault"
        self.vault.mkdir()
        self.cfg = Config(vault=self.vault, state_dir=self.tmp / "state", lock_dir=self.tmp / "locks")
        for key in ("VAULT_MEMORY", "SESSION_JOURNAL"):
            os.environ.pop(key, None)

    def tearDown(self):  # noqa: N802
        self._td.cleanup()
