"""Memory notes: frontmatter, project names, and the index the agent sees at start."""
from __future__ import annotations

import json
import re
from pathlib import Path
from typing import List, Tuple

MEMORY_DIR = "memory"
GLOBAL = "_global"
KINDS = ("user", "feedback", "project", "reference")
MAX_LINES = 200
MAX_BYTES = 25_000
MAX_DESC = 200
HEAD_BYTES = 8192  # frontmatter sits at the top; the index never reads whole notes
_PLAIN = re.compile(r"^[A-Za-z0-9_][A-Za-z0-9_ ./+-]*$")
_AMBIGUOUS = re.compile(r"^(?:true|false|yes|no|y|n|on|off|null|~|[-+]?[0-9][0-9_.eE+-]*)$", re.I)


def _value(raw: str):
    raw = raw.strip()
    if raw.startswith('"'):
        try:
            return json.loads(raw)
        except ValueError:
            return raw.strip('"')
    if raw.startswith("'") and raw.endswith("'") and len(raw) > 1:
        return raw[1:-1].replace("''", "'")
    return raw


def split(text: str) -> Tuple[dict, str]:
    """(frontmatter dict, body). Reads flat keys, one level of nested keys, and block lists."""
    text = text.replace("\r\n", "\n")
    if not text.startswith("---\n"):
        return {}, text
    end = text.find("\n---\n", 3)
    if end < 0:
        return {}, text
    meta: dict = {}
    key = None
    for line in text[4:end].splitlines():
        if not line.strip():
            continue
        stripped = line.lstrip()
        indented = line != stripped
        if indented and key is not None and stripped.startswith("- "):
            meta[key] = (meta[key] if isinstance(meta[key], list) else []) + [_value(stripped[2:])]
        elif indented and key is not None and ":" in stripped:
            sub, val = stripped.split(":", 1)
            meta[key] = {**(meta[key] if isinstance(meta[key], dict) else {}), sub.strip(): _value(val)}
        elif ":" in line:
            key, val = line.split(":", 1)
            key = key.strip()
            meta[key] = _value(val) if val.strip() else ""
    body = text[end + 5:]
    return meta, body[1:] if body.startswith("\n") else body


def _render_value(value) -> str:
    text = str(value)
    plain = _PLAIN.match(text) and not _AMBIGUOUS.match(text) and text == text.strip()
    return text if plain else json.dumps(text, ensure_ascii=False)


def render(meta: dict, body: str) -> str:
    lines = [f"{k}: {_render_value(v)}" for k, v in meta.items()]
    return "---\n" + "\n".join(lines) + "\n---\n\n" + body


def project_name(cwd: str) -> str:
    """Git top-level folder name, else the last folder of cwd. Same rule as session-journal's
    note.project_name, so sessions and memory share one `project` value."""
    if not cwd:
        return ""
    path = Path(cwd).expanduser()
    for p in [path, *path.parents]:
        if (p / ".git").exists():
            return p.name
    return path.name


def folder(project: str) -> str:
    """The memory/ subfolder for a project; names that would leave memory/ fall back to _global."""
    return project if project not in ("", ".", "..") and "/" not in project and "\\" not in project else GLOBAL


def one_line(text: str, limit: int = MAX_DESC) -> str:
    text = " ".join(str(text).split())
    return text if len(text) <= limit else text[: limit - 1] + "…"


def load_folder(vault: Path, project: str) -> List[Tuple[str, dict]]:
    """(name, meta) of memory notes in one project folder, newest first."""
    folder = vault / MEMORY_DIR / project
    found = []
    for path in sorted(folder.glob("*.md")) if folder.is_dir() else []:
        with open(path, encoding="utf-8", errors="replace") as fh:
            meta, _ = split(fh.read(HEAD_BYTES))
        if meta.get("type") == "memory":
            found.append((path.stem, meta))
    return sorted(found, key=lambda nm: (str(nm[1].get("updated", "")), nm[0]), reverse=True)


def index_lines(vault: Path, project: str) -> List[str]:
    folders = [GLOBAL] + ([project] if project and project != GLOBAL else [])
    lines: List[str] = []
    def desc(meta: dict) -> str:
        value = meta.get("description", "")
        return one_line(value) if isinstance(value, str) else ""

    for folder in folders:
        found = load_folder(vault, folder)
        if not found:
            continue
        title = "Global" if folder == GLOBAL else f"Project {folder}"
        lines.append(f"{title} ({MEMORY_DIR}/{folder}/):")
        lines += [f"- [[{name}]] ({meta.get('kind', 'project')}) {desc(meta)}"
                  for name, meta in found]
    return lines


def cap(lines: List[str], max_lines: int = MAX_LINES, max_bytes: int = MAX_BYTES) -> List[str]:
    def fits(chunk: List[str]) -> bool:
        return len(chunk) <= max_lines and len("\n".join(chunk).encode()) <= max_bytes

    if fits(lines):
        return lines
    keep = min(len(lines), max_lines - 1)
    while keep > 0:
        more = f"… {len(lines) - keep} more not shown; list the folder to see them all."
        if fits(lines[:keep] + [more]):
            return lines[:keep] + [more]
        keep -= 1
    return [f"… {len(lines)} lines not shown; list the folder to see them all."]
