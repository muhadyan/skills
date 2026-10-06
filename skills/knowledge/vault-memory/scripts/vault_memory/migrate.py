"""One-off import of Claude Code auto memory and Codex memories into the vault."""
from __future__ import annotations

import datetime as dt
import json
import os
import re
from dataclasses import dataclass, field, replace
from pathlib import Path
from typing import Dict, List, Optional, Tuple

from . import notes, scrub

SLUG_CHARS = re.compile(r"[^A-Za-z0-9]")
POINTER = re.compile(r"^\s*[-*]\s*(?:\[[^\]]+\]\(|\[\[)")
MAX_TRANSCRIPT_LINES = 200


@dataclass(frozen=True)
class Item:
    folder: str
    name: str
    meta: dict
    body: str
    source: str
    hits: tuple = ()

    @property
    def dest(self) -> str:
        return f"{notes.MEMORY_DIR}/{self.folder}/{self.name}.md"


@dataclass(frozen=True)
class Redaction:
    dest: str
    source: str
    hits: tuple


@dataclass
class Report:
    written: int = 0
    unchanged: int = 0
    skipped_existing: List[str] = field(default_factory=list)
    redactions: List[Redaction] = field(default_factory=list)
    collisions: List[str] = field(default_factory=list)
    unresolved: List[str] = field(default_factory=list)


def _mtime_date(path: Path) -> str:
    return dt.datetime.fromtimestamp(path.stat().st_mtime).strftime("%Y-%m-%d")


def _slug(text: str) -> str:
    return SLUG_CHARS.sub("-", text)


def _cwd_from_transcripts(project_dir: Path) -> str:
    files = sorted(project_dir.glob("*.jsonl"), key=lambda p: p.stat().st_mtime, reverse=True)
    for path in files:
        with open(path, encoding="utf-8", errors="replace") as fh:
            for i, line in enumerate(fh):
                if i >= MAX_TRANSCRIPT_LINES:
                    break
                try:
                    row = json.loads(line)
                except ValueError:
                    continue
                if isinstance(row, dict) and isinstance(row.get("cwd"), str) and row["cwd"]:
                    return row["cwd"]
    return ""


def _cwd_from_disk(slug: str, base: Path = Path("/")) -> str:
    """Walk the disk for the folder whose Claude slug is `slug` (a '-' may be '/', '.', '_' or '-')."""
    if not slug:
        return str(base)
    try:
        entries = sorted(os.scandir(base), key=lambda e: e.name)
    except OSError:
        return ""
    for entry in entries:
        enc = _slug(entry.name)
        if not entry.is_dir(follow_symlinks=False):
            continue
        if slug == enc:
            return entry.path
        if slug.startswith(enc + "-"):
            found = _cwd_from_disk(slug[len(enc) + 1:], Path(entry.path))
            if found:
                return found
    return ""


def resolve_cwd(project_dir: Path) -> str:
    """The real cwd behind a ~/.claude/projects/<slug> folder. The slug alone is lossy."""
    return _cwd_from_transcripts(project_dir) or _cwd_from_disk(project_dir.name.lstrip("-"))


def _real_index_lines(text: str) -> List[str]:
    return [l for l in text.splitlines()
            if l.strip() and not l.lstrip().startswith("#") and not POINTER.match(l)]


def _item(folder: str, name: str, kind: str, description: str, body: str, updated: str,
          source: str, literals: Tuple[str, ...]) -> Item:
    desc, desc_hits = scrub.scrub(notes.one_line(description), literals)
    body, body_hits = scrub.scrub(body, literals)
    meta = {"type": "memory", "kind": kind if kind in notes.KINDS else "project",
            "description": desc, "project": folder, "updated": updated[:10]}
    return Item(folder, name, meta, body if body.endswith("\n") else body + "\n", source,
                tuple(desc_hits) + tuple(body_hits))


def claude_items(projects: Path, report: Report, literals: Tuple[str, ...] = ()) -> List[Item]:
    items: List[Item] = []
    for mem in sorted(projects.glob("*/memory")):
        cwd = resolve_cwd(mem.parent)
        if cwd:
            project = notes.folder(notes.project_name(cwd))
        else:
            report.unresolved.append(mem.parent.name)
            project = notes.folder(mem.parent.name.rsplit("-", 1)[-1])
        for path in sorted(mem.glob("*.md")):
            text = path.read_text(encoding="utf-8", errors="replace")
            if path.name == "MEMORY.md":
                if _real_index_lines(text):
                    items.append(_item(project, "project-notes", "project",
                                       "Free-form project notes from the old Claude MEMORY.md index",
                                       text, _mtime_date(path), str(path), literals))
                continue
            meta, body = notes.split(text)
            md = meta.get("metadata") if isinstance(meta.get("metadata"), dict) else {}
            kind = md.get("type") or meta.get("type") or "project"
            first = next((l.strip("# ").strip() for l in body.splitlines() if l.strip()), path.stem)
            updated = str(md.get("modified") or meta.get("modified") or _mtime_date(path))
            folder = notes.GLOBAL if kind == "user" else project
            items.append(_item(folder, path.stem, kind, meta.get("description") or first,
                               body, updated, str(path), literals))
    return items


def codex_items(memories: Path, literals: Tuple[str, ...] = ()) -> List[Item]:
    path = memories / "MEMORY.md"
    if not path.exists():
        return []
    items = []
    parts = re.split(r"(?m)^# ", path.read_text(encoding="utf-8", errors="replace"))
    for part in parts[1:]:
        if not part.startswith("Task Group: "):
            continue
        title, _, body = part[len("Task Group: "):].partition("\n")
        scope = re.search(r"(?m)^scope:\s*(.+)$", body)
        cwd = re.search(r"(?m)^applies_to:\s*cwd=(.+?)(?:;| with |$)", body)
        project = notes.folder(notes.project_name(cwd.group(1))) if cwd else notes.GLOBAL
        name = "codex-" + _slug(title.strip().lower()).strip("-")
        name = re.sub("-+", "-", name)[:80].rstrip("-")
        items.append(_item(project, name, "project", scope.group(1) if scope else title, body.strip(),
                           _mtime_date(path), f"{path}#{title.strip()}", literals))
    return items


def _same(a: Item, b: Item) -> bool:
    return a.body == b.body and a.meta["description"] == b.meta["description"]


def resolve_collisions(items: List[Item], report: Report) -> List[Item]:
    by_dest: Dict[str, List[Item]] = {}
    for item in items:
        by_dest.setdefault(item.dest, []).append(item)
    taken = set(by_dest)
    out: List[Item] = []
    for dest, group in by_dest.items():
        group = sorted(group, key=lambda i: i.meta["updated"], reverse=True)
        unique = [g for n, g in enumerate(group) if not any(_same(g, h) for h in group[:n])]
        out.append(unique[0])
        if len(unique) == 1:
            continue
        if unique[0].folder == notes.GLOBAL:
            report.collisions.append(f"{dest}: kept newest {unique[0].source}; dropped "
                                     + ", ".join(u.source for u in unique[1:]))
            continue
        for n, extra in enumerate(unique[1:], start=2):
            while f"{notes.MEMORY_DIR}/{extra.folder}/{extra.name}-{n}.md" in taken:
                n += 1
            renamed = replace(extra, name=f"{extra.name}-{n}")
            taken.add(renamed.dest)
            out.append(renamed)
            report.collisions.append(f"{dest}: also kept {extra.source} as {renamed.dest}")
    return out


def run(vault: Path, claude_projects: Optional[Path], codex_memories: Optional[Path],
        apply: bool, literals: Tuple[str, ...] = ()) -> Report:
    report = Report()
    items = (claude_items(claude_projects, report, literals)
             if claude_projects and claude_projects.exists() else [])
    items += codex_items(codex_memories, literals) if codex_memories else []
    for item in resolve_collisions(items, report):
        if item.hits:
            report.redactions.append(Redaction(item.dest, item.source, item.hits))
        target, text = vault / item.dest, notes.render(item.meta, item.body)
        if target.exists():  # never replace a note that is already there (it may have been edited)
            if target.read_text(encoding="utf-8", errors="replace") == text:
                report.unchanged += 1
            else:
                report.skipped_existing.append(item.dest)
            continue
        if apply:
            target.parent.mkdir(parents=True, exist_ok=True)
            target.write_text(text, encoding="utf-8")
        report.written += 1
    report.redactions.sort(key=lambda r: r.dest)
    report.skipped_existing.sort()
    return report
