"""Write files into a git repo under a lock: pull, write, commit, push (with retry)."""
from __future__ import annotations

import fcntl
import hashlib
import subprocess
import time
from contextlib import contextmanager
from pathlib import Path
from typing import Dict, Iterable, Iterator

PUSH_TRIES = 3


class GitError(Exception):
    pass


def _git(repo: Path, *args: str, check: bool = True) -> subprocess.CompletedProcess:
    proc = subprocess.run(["git", *args], cwd=repo, capture_output=True, text=True, timeout=120)
    if check and proc.returncode != 0:
        raise GitError(f"git {' '.join(args)}: {proc.stderr.strip()[:500]}")
    return proc


@contextmanager
def repo_lock(repo: Path, state_dir: Path) -> Iterator[None]:
    """One writer per repo across processes (hooks, sweeps, exports)."""
    state_dir.mkdir(parents=True, exist_ok=True)
    key = hashlib.sha1(str(repo.resolve()).encode()).hexdigest()[:12]
    with open(state_dir / f"repo-{key}.lock", "w") as fh:
        fcntl.flock(fh, fcntl.LOCK_EX)
        try:
            yield
        finally:
            fcntl.flock(fh, fcntl.LOCK_UN)


def _has_remote(repo: Path) -> bool:
    return bool(_git(repo, "remote", check=False).stdout.strip())


def _safe_target(repo: Path, rel: str) -> Path:
    target = (repo / rel).resolve()
    if repo.resolve() not in target.parents:
        raise ValueError(f"path escapes repo: {rel}")
    return target


def _pull(repo: Path) -> None:
    _git(repo, "pull", "-q", "--rebase", "--autostash")


def sync_write(repo: Path, files: Dict[str, str], message: str, state_dir: Path,
               deletes: Iterable[str] = ()) -> bool:
    """Make the repo hold `files` (and not `deletes`), commit only those paths, push.
    Returns True when a commit was made."""
    targets = {rel: _safe_target(repo, rel) for rel in files}
    gone = {rel: _safe_target(repo, rel) for rel in deletes}
    with repo_lock(repo, state_dir):
        remote = _has_remote(repo)
        if remote:
            _pull(repo)
        for rel, path in targets.items():
            path.parent.mkdir(parents=True, exist_ok=True)
            path.write_text(files[rel], encoding="utf-8")
        for path in gone.values():
            if path.exists():
                path.unlink()
        paths = list(targets) + list(gone)
        if not paths:
            return False
        _git(repo, "add", "-A", "--", *paths)
        if not _git(repo, "diff", "--cached", "--name-only", "--", *paths).stdout.strip():
            return False
        _git(repo, "commit", "-q", "-m", message, "--", *paths)
        if remote:
            _push(repo)
        return True


def _push(repo: Path) -> None:
    for attempt in range(PUSH_TRIES):
        if _git(repo, "push", "-q", check=False).returncode == 0:
            return
        time.sleep(1 + attempt * 2)
        _pull(repo)
    raise GitError(f"push failed after {PUSH_TRIES} tries in {repo}")
