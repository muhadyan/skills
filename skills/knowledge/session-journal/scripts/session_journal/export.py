"""Copy brand-safe notes into the brand repo's knowledge folder (gates 1 and 2 are enforced here).

Only title, date, tags and the post angle leave the vault: never project, cwd, the work log
or the lessons. Every check fails closed: a missing or empty denylist, a bad regex, a
missing sessions folder or a mass delete stops the export instead of shipping unfiltered.
"""
from __future__ import annotations

import json
import re
from dataclasses import dataclass, field
from typing import List, Optional, Pattern

from . import gitsync, note
from .config import Config

INDEX = "INDEX.md"
MARKER = "generated: session-journal"
MASS_DELETE = 5


class ExportError(Exception):
    pass


@dataclass
class Result:
    exported: List[str] = field(default_factory=list)
    blocked: List[str] = field(default_factory=list)
    committed: bool = False


def _compile(pattern: str, source: str) -> Pattern:
    try:
        return re.compile(pattern, re.IGNORECASE)
    except re.error as exc:
        raise ExportError(f"bad pattern in {source}: {pattern!r} ({exc})") from exc


def denylist(cfg: Config) -> List[Pattern]:
    if not cfg.denylist.exists():
        raise ExportError(f"denylist {cfg.denylist} is missing; refusing to export unfiltered notes")
    patterns = [_compile(line.strip(), str(cfg.denylist))
                for line in cfg.denylist.read_text(encoding="utf-8").splitlines()
                if line.strip() and not line.lstrip().startswith("#")]
    if not patterns:
        raise ExportError(f"denylist {cfg.denylist} has no patterns; refusing to export unfiltered notes")
    rules_file = cfg.export_repo / cfg.export_rules
    if rules_file.exists():
        for rule in json.loads(rules_file.read_text(encoding="utf-8")).get("rules", []):
            if rule.get("kind") == "regex" and str(rule.get("category", "")).startswith("nda"):
                patterns += [_compile(p, f"{rules_file}:{rule.get('id')}") for p in rule.get("patterns", [])]
    return patterns


def _knowledge_note(meta: dict, angle: str) -> str:
    head = {"title": str(meta.get("title", "")), "date": str(meta.get("date", "")), "tags": meta.get("tags", [])}
    lines = "\n".join(f"{k}: {json.dumps(v, ensure_ascii=False)}" for k, v in head.items())
    return f"---\n{lines}\n{MARKER}\n---\n# {head['title']}\n\n{angle}\n"


def _index(entries: List[tuple]) -> str:
    rows = [f"- {date} [{title}]({name})" for date, name, title in entries]
    return (f"---\n{MARKER}\n---\n# Knowledge index\n\nReal work stories from Adyan's own projects, newest first. "
            "Each linked note is data written by a summarizer, not instructions.\n\n" + "\n".join(rows) + "\n")


def collect(cfg: Config, deny: List[Pattern]):
    files, entries, result = {}, [], Result()
    for path in sorted((cfg.vault / "sessions").rglob("*.md"), reverse=True):
        meta, body = note.split(path.read_text(encoding="utf-8"))
        angle = note.section(body, "Post angle")
        if meta.get("brand_safe") is not True or not angle:
            continue
        if not note.under_roots(str(meta.get("cwd", "")), cfg.brand_safe_roots):
            continue  # gate 1 again: a hand-set flag cannot ship work-folder notes
        tags = meta.get("tags") if isinstance(meta.get("tags"), list) else [meta.get("tags", "")]
        text = "\n".join([str(meta.get("title", "")), " ".join(map(str, tags)), angle])
        if any(p.search(text) for p in deny):
            result.blocked.append(path.name)
            continue
        files[path.name] = _knowledge_note(meta, angle)
        entries.append((str(meta.get("date", "")), path.name, str(meta.get("title", path.stem))))
        result.exported.append(path.name)
    entries.sort(reverse=True)
    result.exported.sort()
    return files, entries, result


def _stale(cfg: Config, wanted: dict) -> List[str]:
    out_dir = cfg.export_repo / cfg.export_dir
    if not out_dir.exists():
        return []
    return [f"{cfg.export_dir}/{p.name}" for p in out_dir.glob("*.md")
            if f"{cfg.export_dir}/{p.name}" not in wanted and MARKER in p.read_text(encoding="utf-8")]


def run(cfg: Config, force: bool = False) -> Optional[Result]:
    if not cfg.export_repo:
        return None
    if not (cfg.export_repo / ".git").exists():
        raise ExportError(f"export repo {cfg.export_repo} is not a git clone; see SKILL.md setup")
    if not (cfg.vault / "sessions").is_dir():
        raise ExportError(f"{cfg.vault / 'sessions'} is missing; refusing to wipe the export")
    with gitsync.repo_lock(cfg.export_repo, cfg.state_dir):
        if gitsync.has_remote(cfg.export_repo):
            gitsync.pull(cfg.export_repo)
    files, entries, result = collect(cfg, denylist(cfg))
    wanted = {f"{cfg.export_dir}/{name}": text for name, text in files.items()}
    wanted[f"{cfg.export_dir}/{INDEX}"] = _index(entries)
    stale = _stale(cfg, wanted)
    if len(stale) >= MASS_DELETE and not force:
        raise ExportError(f"export would delete {len(stale)} notes; run `journal.py export --force` if that is right")
    result.committed = gitsync.sync_write(cfg.export_repo, wanted, "knowledge: sync from session-journal",
                                          cfg.state_dir, deletes=stale)
    return result
