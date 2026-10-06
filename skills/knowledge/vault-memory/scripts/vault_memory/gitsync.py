"""Commit and push the vault's memory/ folder, under session-journal's lock for the same repo."""
from __future__ import annotations

import fcntl
import hashlib
import subprocess
import time
from contextlib import contextmanager
from pathlib import Path
from typing import Iterator

from .notes import MEMORY_DIR

PUSH_TRIES = 3


class GitError(Exception):
    pass


def _git(repo: Path, *args: str, check: bool = True) -> subprocess.CompletedProcess:
    proc = subprocess.run(["git", *args], cwd=repo, capture_output=True, text=True, timeout=120)
    if check and proc.returncode != 0:
        raise GitError(f"git {' '.join(args)}: {proc.stderr.strip()[:500]}")
    return proc


def lock_path(repo: Path, lock_dir: Path) -> Path:
    """Must stay equal to session-journal's gitsync.repo_lock file name."""
    key = hashlib.sha1(str(repo.resolve()).encode()).hexdigest()[:12]
    return lock_dir / f"repo-{key}.lock"


@contextmanager
def repo_lock(repo: Path, lock_dir: Path) -> Iterator[None]:
    lock_dir.mkdir(parents=True, exist_ok=True)
    with open(lock_path(repo, lock_dir), "w") as fh:
        fcntl.flock(fh, fcntl.LOCK_EX)
        try:
            yield
        finally:
            fcntl.flock(fh, fcntl.LOCK_UN)


def _pull(repo: Path) -> bool:
    """Rebase on the remote. On a conflict, abort and keep the local commit for the next sync."""
    if _git(repo, "pull", "-q", "--rebase", "--autostash", check=False).returncode == 0:
        return True
    _git(repo, "rebase", "--abort", check=False)
    return False


def _push(repo: Path) -> None:
    for attempt in range(PUSH_TRIES):
        if _git(repo, "push", "-q", check=False).returncode == 0:
            return
        time.sleep(1 + attempt * 2)
        if not _pull(repo):
            break
    raise GitError(f"push failed in {repo}; the commit stays local until the next sync")


def commit_memory(repo: Path, lock_dir: Path) -> int:
    """Commit every change under memory/ (and nothing else), then pull and push.
    Returns the number of files committed."""
    with repo_lock(repo, lock_dir):
        tracked = _git(repo, "ls-files", "--", MEMORY_DIR).stdout.strip()
        changed = []
        if (repo / MEMORY_DIR).exists() or tracked:
            _git(repo, "add", "-A", "--", MEMORY_DIR)
            changed = _git(repo, "diff", "--cached", "--name-only", "--", MEMORY_DIR).stdout.split()
        if changed:
            noun = "file" if len(changed) == 1 else "files"
            _git(repo, "commit", "-q", "-m", f"vault: memory ({len(changed)} {noun})", "--", MEMORY_DIR)
        if _git(repo, "remote", check=False).stdout.strip() and (changed or _ahead(repo)):
            if _pull(repo):
                _push(repo)
        return len(changed)


def _ahead(repo: Path) -> bool:
    proc = _git(repo, "rev-list", "--count", "@{u}..HEAD", check=False)
    return proc.returncode == 0 and proc.stdout.strip() not in ("", "0")
