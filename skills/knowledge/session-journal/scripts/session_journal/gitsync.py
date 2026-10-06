"""Write files into a git repo under a lock: write, commit, then pull --rebase and push.

The commit happens first so an offline Mac or a rebase conflict never loses a note:
a failed sync aborts the rebase, keeps the local commit, and the next sync pushes it.
There is no autostash: with the user's uncommitted edits in the tree the pull simply
waits for the next sync, so their files are never stashed or merged.
Writes happen only on the configured branch, never on a feature branch or a detached HEAD.
Other tools (obsidian-git, a second vault writer) share the lock file path below.
"""
from __future__ import annotations

import fcntl
import hashlib
import subprocess
import time
from contextlib import contextmanager
from pathlib import Path
from typing import Callable, Dict, Iterable, Iterator, Optional

PUSH_TRIES = 3
INDEX_LOCK_TRIES = 5


class GitError(Exception):
    pass


def _git(repo: Path, *args: str, check: bool = True) -> subprocess.CompletedProcess:
    for attempt in range(INDEX_LOCK_TRIES):
        proc = subprocess.run(["git", *args], cwd=repo, capture_output=True, text=True, timeout=120)
        if "index.lock" not in proc.stderr:  # obsidian-git may hold the index for a moment
            break
        time.sleep(1 + attempt)
    if check and proc.returncode != 0:
        raise GitError(f"git {' '.join(args)}: {proc.stderr.strip()[:500]}")
    return proc


@contextmanager
def repo_lock(repo: Path, state_dir: Path) -> Iterator[None]:
    """One writer per repo across processes. Path contract: repo-<sha1(resolved path)[:12]>.lock."""
    state_dir.mkdir(parents=True, exist_ok=True)
    key = hashlib.sha1(str(repo.resolve()).encode()).hexdigest()[:12]
    with open(state_dir / f"repo-{key}.lock", "w") as fh:
        fcntl.flock(fh, fcntl.LOCK_EX)
        try:
            yield
        finally:
            fcntl.flock(fh, fcntl.LOCK_UN)


def has_remote(repo: Path) -> bool:
    return bool(_git(repo, "remote", check=False).stdout.strip())


def _rebasing(repo: Path) -> bool:
    git_dir = repo / ".git"
    return (git_dir / "rebase-merge").exists() or (git_dir / "rebase-apply").exists()


def pull(repo: Path) -> bool:
    """pull --rebase. Skipped while anyone else is mid-rebase; a rebase this pull started and
    could not finish is aborted, so the repo is never left half-rebased."""
    if _rebasing(repo):
        return False
    if _git(repo, "pull", "-q", "--rebase", check=False).returncode == 0:
        return True
    if _rebasing(repo):
        _git(repo, "rebase", "--abort", check=False)
    return False


def _push(repo: Path) -> bool:
    for attempt in range(PUSH_TRIES):
        if _git(repo, "push", "-q", check=False).returncode == 0:
            return True
        time.sleep(1 + attempt * 2)
        if not pull(repo):
            return False
    return False


def _safe_target(repo: Path, rel: str) -> Path:
    target = (repo / rel).resolve()
    if repo.resolve() not in target.parents or ".git" in Path(rel).parts:
        raise ValueError(f"path escapes repo: {rel}")
    return target


def check_branch(repo: Path, branch: str) -> None:
    head = _git(repo, "symbolic-ref", "-q", "--short", "HEAD", check=False).stdout.strip()
    if head != branch:
        raise GitError(f"{repo} is on {head or 'a detached HEAD'}, not {branch}; not writing")


def sync_write(repo: Path, files: Dict[str, str], message: str, state_dir: Path,
               deletes: Iterable[str] = (), branch: str = "main",
               precheck: Optional[Callable[[], bool]] = None) -> bool:
    """Make the repo hold `files` (and not `deletes`), commit only those paths, then sync.
    `precheck` runs under the lock; False cancels the write. Returns True when a commit
    was made. A failed pull/push is reported, never raised."""
    targets = {rel: _safe_target(repo, rel) for rel in files}
    gone = {rel: _safe_target(repo, rel) for rel in deletes}
    with repo_lock(repo, state_dir):
        check_branch(repo, branch)
        if precheck is not None and not precheck():
            return False
        for rel, path in targets.items():
            path.parent.mkdir(parents=True, exist_ok=True)
            path.write_text(files[rel], encoding="utf-8")
        for path in gone.values():
            if path.exists():
                path.unlink()
        paths = list(targets) + list(gone)
        committed = False
        if paths:
            _git(repo, "add", "-A", "--", *paths)
            if _git(repo, "diff", "--cached", "--name-only", "--", *paths).stdout.strip():
                _git(repo, "commit", "-q", "-m", message, "--", *paths)
                committed = True
        if has_remote(repo) and not (pull(repo) and _push(repo)):
            print(f"gitsync: {repo} not synced; the commit stays local until the next sync", flush=True)
        return committed
