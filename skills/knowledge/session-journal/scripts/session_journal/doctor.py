"""`journal.py doctor`: find the failures that are otherwise silent.

Untrusted Codex hooks are skipped without a word, and a vault that cannot sync keeps its
notes local. Each check returns (level, name, message); level is OK, WARN or FAIL.
"""
from __future__ import annotations

import json
import subprocess
import sys
from pathlib import Path
from typing import IO, List, Optional, Tuple

from . import state
from .config import Config

Check = Tuple[str, str, str]
MARK = "session-journal/scripts/journal.py hook"
EVENTS = (("SessionStart", "start"), ("SessionEnd", "end"))


def _git(repo: Path, *args: str) -> subprocess.CompletedProcess:
    return subprocess.run(["git", *args], cwd=repo, capture_output=True, text=True, timeout=30)


def _hook_slots(path: Path) -> dict:
    """{event: (group index, hook index)} of this skill's hooks in a Claude/Codex hooks file."""
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return {}
    slots = {}
    for event, verb in EVENTS:
        for gi, group in enumerate(data.get("hooks", {}).get(event, [])):
            for hi, hook in enumerate(group.get("hooks", [])):
                if f"{MARK} {verb}" in str(hook.get("command", "")):
                    slots[event] = (gi, hi)
    return slots


def check_claude_hooks(cfg: Config) -> Check:
    missing = [e for e, _ in EVENTS if e not in _hook_slots(cfg.claude_settings)]
    if missing:
        return "FAIL", "claude hooks", f"{', '.join(missing)} missing in {cfg.claude_settings}; see SKILL.md setup"
    return "OK", "claude hooks", "SessionStart and SessionEnd installed"


def check_codex_hooks(cfg: Config) -> Check:
    slots = _hook_slots(cfg.codex_hooks)
    missing = [e for e, _ in EVENTS if e not in slots]
    if missing:
        return "FAIL", "codex hooks", f"{', '.join(missing)} missing in {cfg.codex_hooks}"
    try:
        trusted = cfg.codex_config.read_text(encoding="utf-8")
    except OSError:
        trusted = ""
    untrusted = []
    for event, (gi, hi) in slots.items():
        key = f'"{cfg.codex_hooks}:{event[:7].lower()}_{event[7:].lower()}:{gi}:{hi}"'
        if key not in trusted:
            untrusted.append(event)
    if untrusted:
        return "FAIL", "codex hooks", (f"{', '.join(untrusted)} not trusted, so Codex skips them silently: "
                                       "open `codex`, run /hooks, approve the session-journal hooks")
    return "OK", "codex hooks", "installed and trusted"


def check_denylist(cfg: Config) -> Check:
    try:
        lines = [x for x in cfg.denylist.read_text(encoding="utf-8").splitlines()
                 if x.strip() and not x.lstrip().startswith("#")]
    except OSError:
        return "FAIL", "denylist", f"{cfg.denylist} is missing; export refuses to run"
    if not lines:
        return "FAIL", "denylist", f"{cfg.denylist} has no patterns; export refuses to run"
    return "OK", "denylist", f"{len(lines)} patterns"


def check_repo(cfg: Config, repo: Optional[Path], name: str) -> Check:
    if repo is None:
        return "OK", name, "not configured"
    if not (repo / ".git").exists():
        return "FAIL", name, f"{repo} is not a git clone"
    head = _git(repo, "symbolic-ref", "-q", "--short", "HEAD").stdout.strip()
    if head != cfg.branch:
        return "FAIL", name, f"{repo} is on {head or 'a detached HEAD'}; notes are only written on {cfg.branch}"
    return "OK", name, f"{repo} on {cfg.branch}"


def sync_problem(cfg: Config) -> Optional[str]:
    """Why vault notes are not reaching the remote, or None. Cheap enough for the start hook."""
    vault = cfg.vault
    if not (vault / ".git").exists():
        return None
    ahead = _git(vault, "rev-list", "--count", "@{u}..HEAD").stdout.strip()
    if ahead.isdigit() and int(ahead) > 0:
        dirty = _git(vault, "status", "--porcelain", "--untracked-files=no").stdout.split("\n")
        files = [line[3:] for line in dirty if line.strip()]
        why = f"; uncommitted edits to {', '.join(files[:3])} block the pull" if files else ""
        return f"{ahead} unpushed note commit(s) in {vault}{why}"
    return None


def check_sync(cfg: Config) -> Check:
    problem = sync_problem(cfg)
    return ("WARN", "vault sync", problem) if problem else ("OK", "vault sync", "nothing waiting to push")


def check_failures(cfg: Config) -> Check:
    stuck = [p for p, e in state.load(cfg).items() if e.get("fails", 0) >= state.MAX_FAILS]
    if stuck:
        return "WARN", "failures", (f"{len(stuck)} transcript(s) failed {state.MAX_FAILS}x and were skipped; "
                                    f"see journal.log, then delete them from processed.json to retry")
    return "OK", "failures", "none given up"


def checks(cfg: Config) -> List[Check]:
    return [check_repo(cfg, cfg.vault, "vault"), check_sync(cfg), check_repo(cfg, cfg.export_repo, "export repo"),
            check_denylist(cfg), check_claude_hooks(cfg), check_codex_hooks(cfg), check_failures(cfg)]


def run(cfg: Config, out: IO[str] = sys.stdout) -> int:
    results = checks(cfg)
    for level, name, message in results:
        out.write(f"{level:4} {name}: {message}\n")
    return 1 if any(level == "FAIL" for level, _, _ in results) else 0
