"""Session notes: path, Markdown with frontmatter, and a small frontmatter reader.

Gate 1 lives here: a note can be brand_safe only when the session ran under a
BRAND_SAFE_ROOTS folder. The model may lower brand_safe, never raise it.
"""
from __future__ import annotations

import json
import re
from pathlib import Path
from typing import Iterable, List, Tuple

from .transcript import Transcript

SECRET_PATTERNS = [
    r"sk-ant-[A-Za-z0-9_\-]{10,}",
    r"sk-[A-Za-z0-9_\-]{20,}",
    r"gh[pousr]_[A-Za-z0-9]{20,}",
    r"github_pat_[A-Za-z0-9_]{20,}",
    r"AKIA[0-9A-Z]{16}",
    r"xox[abprs]-[A-Za-z0-9\-]{10,}",
    r"\d{8,10}:[A-Za-z0-9_\-]{30,}",  # Telegram bot token
    r"-----BEGIN [A-Z ]*PRIVATE KEY-----[\s\S]*?-----END [A-Z ]*PRIVATE KEY-----",
    r"(?i:\b(?:password|passwd|pwd|secret|token|api[_-]?key)\b\s*[:=]\s*\S+)",
    r"(?i:postgres(?:ql)?://[^\s:]+:[^\s@]+@\S+)",
]
SECRET_RE = re.compile("|".join(f"(?:{p})" for p in SECRET_PATTERNS))


def redact(text: str) -> str:
    return SECRET_RE.sub("[REDACTED]", text)


def under_roots(cwd: str, roots: Iterable[Path]) -> bool:
    if not cwd:
        return False
    path = Path(cwd).expanduser().resolve()
    for root in roots:
        root = Path(root).expanduser().resolve()
        if path == root or root in path.parents:
            return True
    return False


def project_name(cwd: str) -> str:
    """Git top-level folder name when it still exists, else the last folder of cwd."""
    if not cwd:
        return ""
    path = Path(cwd)
    for p in [path, *path.parents]:
        if (p / ".git").exists():
            return p.name
    return path.name


def rel_path(t: Transcript) -> str:
    date = t.date or "0000-00-00"
    yyyy, mm = date[:4], date[5:7]
    short = re.sub(r"[^A-Za-z0-9]", "", t.session_id)[:8] or "unknown"
    return f"sessions/{yyyy}/{mm}/{date}-{t.agent}-{short}.md"


def _bullets(items: List[str]) -> str:
    lines = [f"- {redact(str(i)).strip()}" for i in items if str(i).strip()]
    return "\n".join(lines) or "- (none)"


def render(t: Transcript, data: dict, eligible: bool) -> str:
    brand_safe = bool(eligible and data.get("brand_safe") and str(data.get("post_angle", "")).strip())
    tags = [re.sub(r"[^\w\-/]", "-", str(x).lower()).strip("-") for x in data.get("tags", [])][:6]
    meta = {
        "type": "session",
        "title": redact(str(data.get("title", "Untitled session")))[:120],
        "date": t.date,
        "agent": t.agent,
        "session_id": t.session_id,
        "project": project_name(t.cwd),
        "cwd": t.cwd,
        "tags": [x for x in tags if x],
        "prompts": len(t.prompts),
        "brand_safe": brand_safe,
    }
    head = "\n".join(f"{k}: {json.dumps(v, ensure_ascii=False)}" for k, v in meta.items())
    body = [f"# {meta['title']}", "", "## Done", _bullets(data.get("done", [])), "",
            "## Lessons", _bullets(data.get("lessons", []))]
    if brand_safe:
        body += ["", "## Post angle", redact(str(data["post_angle"]).strip())]
    return f"---\n{head}\n---\n" + "\n".join(body) + "\n"


def _scalar(value: str):
    value = value.strip()
    if value.lower() in ("true", "false"):
        return value.lower() == "true"
    try:
        return json.loads(value)
    except ValueError:
        return value.strip("'\"")


def split(text: str) -> Tuple[dict, str]:
    """(frontmatter dict, body). Reads JSON-style values and Obsidian's YAML block lists."""
    if not text.startswith("---\n"):
        return {}, text
    end = text.find("\n---\n", 4)
    if end < 0:
        return {}, text
    meta: dict = {}
    key = None
    for line in text[4:end].splitlines():
        if line.startswith(("  - ", "- ")) and key is not None:
            if not isinstance(meta.get(key), list):
                meta[key] = []
            meta[key].append(_scalar(line.split("- ", 1)[1]))
        elif ":" in line and not line.startswith(" "):
            key, value = line.split(":", 1)
            key = key.strip()
            meta[key] = _scalar(value) if value.strip() else []
    return meta, text[end + 5:]


def section(body: str, name: str) -> str:
    m = re.search(rf"^## {re.escape(name)}\s*\n(.*?)(?=^## |\Z)", body, re.MULTILINE | re.DOTALL)
    return m.group(1).strip() if m else ""
