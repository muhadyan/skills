"""Commit and push the vault's memory/ folder, under session-journal's lock for the same repo.

Other writers do not all take that lock (the obsidian-git plugin, the user in Obsidian), so this
never stashes, rebases over, or otherwise touches files outside memory/."""
from __future__ import annotations

import fcntl
import hashlib
import subprocess
import time
from contextlib import contextmanager
from pathlib import Path
from typing import Iterator, List

from .notes import MEMORY_DIR

PUSH_TRIES = 3
LOCK_TRIES = 5


class GitError(Exception):
    pass


def _git(repo: Path, *args: str, check: bool = True) -> subprocess.CompletedProcess:
    for attempt in range(LOCK_TRIES):
        proc = subprocess.run(["git", *args], cwd=repo, capture_output=True, text=True, timeout=120)
        if proc.returncode == 0 or "index.lock" not in proc.stderr:
            break
        time.sleep(0.5 + attempt)  # obsidian-git or the user holds the index for a moment
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


def _git_dir(repo: Path) -> Path:
    return Path(repo, _git(repo, "rev-parse", "--git-dir").stdout.strip())


def _rebasing(repo: Path) -> bool:
    gd = _git_dir(repo)
    return (gd / "rebase-merge").exists() or (gd / "rebase-apply").exists()


def _changed(repo: Path) -> List[str]:
    out = _git(repo, "diff", "--cached", "--name-only", "-z", "--", MEMORY_DIR).stdout
    return [name for name in out.split("\0") if name]


def _sync(repo: Path) -> None:
    """Pull with rebase and push, only when no tracked file outside our commit is dirty."""
    if not _git(repo, "remote", check=False).stdout.strip():
        return
    if _git(repo, "rev-parse", "--abbrev-ref", "--symbolic-full-name", "@{u}", check=False).returncode:
        print("sync: branch has no upstream; memory commit stays local", flush=True)
        return
    if _git(repo, "status", "--porcelain", "--untracked-files=no").stdout.strip():
        print("sync: tracked files are being edited; memory commit waits for the next sync", flush=True)
        return
    if _git(repo, "pull", "-q", "--rebase", check=False).returncode:
        if _rebasing(repo):
            _git(repo, "rebase", "--abort", check=False)
        print("sync: pull failed; memory commit stays local until the next sync", flush=True)
        return
    for attempt in range(PUSH_TRIES):
        if _git(repo, "push", "-q", check=False).returncode == 0:
            return
        time.sleep(1 + attempt * 2)
        if _git(repo, "pull", "-q", "--rebase", check=False).returncode:
            if _rebasing(repo):
                _git(repo, "rebase", "--abort", check=False)
            break
    raise GitError(f"push failed in {repo}; the commit stays local until the next sync")


def commit_memory(repo: Path, lock_dir: Path) -> int:
    """Commit every change under memory/ (and nothing else), then pull and push.
    Returns the number of files committed."""
    with repo_lock(repo, lock_dir):
        if _rebasing(repo):
            print("sync: a rebase is in progress; leaving the vault alone", flush=True)
            return 0
        if (repo / MEMORY_DIR).exists() or _git(repo, "ls-files", "--", MEMORY_DIR).stdout.strip():
            _git(repo, "add", "-A", "--", MEMORY_DIR)
        changed = _changed(repo)
        if changed:
            noun = "file" if len(changed) == 1 else "files"
            _git(repo, "commit", "-q", "-m", f"vault: memory ({len(changed)} {noun})", "--", MEMORY_DIR)
        _sync(repo)
        return len(changed)
