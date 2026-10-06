"""Remove secret values from text, keep the words around them."""
from __future__ import annotations

import re
from dataclasses import dataclass
from typing import Iterable, List, Tuple

MARKER = "[secret removed; see .env or password manager]"

_TOKENS = re.compile("|".join([
    r"sk-ant-[A-Za-z0-9_-]{16,}", r"\bsk-[A-Za-z0-9_-]{20,}", r"\bgh[pousr]_[A-Za-z0-9]{30,}",
    r"\bgithub_pat_[A-Za-z0-9_]{30,}", r"\bAKIA[0-9A-Z]{16}\b", r"\bxox[abposr]-[A-Za-z0-9-]{10,}",
    r"\bAIza[0-9A-Za-z_-]{35}", r"\bglpat-[A-Za-z0-9_-]{20,}",
    r"\beyJ[A-Za-z0-9_-]{8,}\.[A-Za-z0-9_-]{8,}\.[A-Za-z0-9_-]{8,}",
]))
_BEARER = re.compile(r"(?i)(\bbearer\s+)([A-Za-z0-9._~+/=-]{16,})")
_URL_CRED = re.compile(r"(\b[a-z][a-z0-9+.-]*://[^\s:/@]+:)([^\s@/]+)(@)")
_KEY_VALUE = re.compile(
    r"(?i)(\b[A-Za-z0-9_.-]*(?:password|passwd|pwd|secret|token|api[_-]?key|access[_-]?key|"
    r"private[_-]?key|auth[_-]?key)[A-Za-z0-9_.-]*[\"']?\s*(?:=|:|\bis\b)\s*[`\"']?)"
    r"([^\s`\"'<>,;)\]]+)")
_ENV_NAME = re.compile(r"^[A-Z][A-Z0-9_]+$")
_WORDS = re.compile(r"^[A-Za-z]+(?:[._-][A-Za-z]+)*\.?$")  # prose or an identifier, not a secret


@dataclass(frozen=True)
class Hit:
    line: int
    kind: str
    preview: str


def _placeholder(value: str) -> bool:
    return (value.startswith(("$", "%", "{", "<", "[", "/", "~", ".", ":", "*"))
            or "://" in value or "(" in value or _ENV_NAME.match(value) is not None
            or _WORDS.match(value) is not None or len(set(value)) <= 2)


def _looks_secret(value: str) -> bool:
    if len(value) < 8 or _placeholder(value):
        return False
    return bool(re.search(r"[0-9]", value) or re.search(r"[^A-Za-z0-9]", value) or len(value) >= 16)


def _sub(pattern: re.Pattern, group: int, kind: str, text: str, hits: List[Tuple[int, str]],
         check=None) -> str:
    def repl(m: re.Match) -> str:
        value = m.group(group)
        if check and not check(value):
            return m.group(0)
        hits.append((text.count("\n", 0, m.start()) + 1, kind))
        start, end = m.start(group) - m.start(), m.end(group) - m.start()
        return m.group(0)[:start] + MARKER + m.group(0)[end:]
    return pattern.sub(repl, text)


def scrub(text: str, literals: Iterable[str] = ()) -> Tuple[str, List[Hit]]:
    """`literals`: exact secret strings that no pattern can spot (a bare password in prose)."""
    found: List[Tuple[int, str]] = []
    for literal in sorted({l for l in literals if l}, key=len, reverse=True):
        text = _sub(re.compile(re.escape(literal)), 0, "literal", text, found)
    text = _sub(_TOKENS, 0, "token", text, found)
    text = _sub(_BEARER, 2, "bearer", text, found)
    text = _sub(_URL_CRED, 2, "url-password", text, found, check=lambda v: not _placeholder(v))
    text = _sub(_KEY_VALUE, 2, "key-value", text, found, check=_looks_secret)
    lines = text.splitlines()
    hits = [Hit(line, kind, lines[line - 1].strip()[:160]) for line, kind in sorted(found)]
    return text, hits
