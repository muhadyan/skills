"""Remove secret values from text, keep the words around them.

High-confidence shapes (known token formats, key blocks, URL credentials) are safe to strip from
any note at any time. The key/value heuristics also catch passwords in prose, with some false
positives, so they run only for the one-off import, whose report a human reviews."""
from __future__ import annotations

import re
from dataclasses import dataclass
from typing import Iterable, List, Tuple

MARKER = "[secret removed; see .env or password manager]"

_PEM = re.compile(r"-----BEGIN [A-Z ]*PRIVATE KEY-----.*?-----END [A-Z ]*PRIVATE KEY-----", re.S)
_TOKENS = re.compile("|".join([
    r"sk-ant-[A-Za-z0-9_-]{16,}", r"\bsk-[A-Za-z0-9_-]{20,}", r"\b[sr]k_(?:live|test)_[A-Za-z0-9]{10,}",
    r"\bgh[pousr]_[A-Za-z0-9]{30,}", r"\bgithub_pat_[A-Za-z0-9_]{30,}", r"\bAKIA[0-9A-Z]{16}\b",
    r"\bxox[abposr]-[A-Za-z0-9-]{10,}", r"\bAIza[0-9A-Za-z_-]{35}", r"\bglpat-[A-Za-z0-9_-]{20,}",
    r"\bGOCSPX-[A-Za-z0-9_-]{20,}", r"\bEAA[A-Za-z0-9]{20,}", r"\b\d{8,10}:AA[A-Za-z0-9_-]{30,}",
    r"\$2[aby]\$\d\d\$[./A-Za-z0-9]{53}",
    r"https://hooks\.slack\.com/services/[A-Za-z0-9/_-]+",
    r"https://(?:discord|discordapp)\.com/api/webhooks/[A-Za-z0-9/_-]+",
    r"\beyJ[A-Za-z0-9_-]{8,}\.[A-Za-z0-9_-]{8,}\.[A-Za-z0-9_-]{8,}",
]))
_AUTH = re.compile(r"(?i)(\b(?:bearer|basic)\s+)([A-Za-z0-9._~+/=-]{12,})")
_URL_CRED = re.compile(r"(\b[a-z][a-z0-9+.-]*://[^\s:/@]+:)([^\s/]+)(@)")
_KEYS = (r"password|passwd|pwd|secret|token|api[_-]?key|access[_-]?key|private[_-]?key|auth[_-]?key|"
         r"session[_-]?token")
# `key = value`, `key: value`, or `key is `value`` (prose needs the quotes to count)
_KEY_VALUE = re.compile(
    rf"(?i)(\b[A-Za-z0-9_.-]*(?:{_KEYS})[A-Za-z0-9_.-]*[\"']?\s*(?:[=:]\s*[`\"']?|\bis\s+[`\"']))"
    r"([^\s`\"'<>,;)\]]+)")
_COOKIE = re.compile(r"(?i)(\bsessionid=)([A-Za-z0-9]{12,})")
_QUOTED = re.compile(
    rf"(?i)(\b[A-Za-z0-9_.-]*(?:{_KEYS})[A-Za-z0-9_.-]*[\"']?\s*[=:]\s*)([\"'])([^\"'\n]{{6,}})(\2)")
_PROSE_PW = re.compile(r"(?i)(\b(?:pw|pwd|pass|password)\s+`?)([A-Za-z0-9!@#$%^&*._+-]{6,})")
_ENV_NAME = re.compile(r"^[A-Z][A-Z0-9_]+$")
_PROSE = re.compile(r"^[a-z]+(?:[._-][a-z]+)*\.?$")  # lowercase words: prose, not a secret
_CODE_PATH = re.compile(r"^[a-z][A-Za-z0-9]*(?:\.[A-Za-z][A-Za-z0-9]*)+$")  # window.location.href


@dataclass(frozen=True)
class Hit:
    line: int
    kind: str
    preview: str


def _placeholder(value: str) -> bool:
    if not value.isascii() or value.startswith(("$", "%", "{", "<", "[", "(", "/", "~", ".", ":", "*")):
        return True
    if "://" in value[:12]:
        return True
    if re.match(r"^[A-Za-z_][A-Za-z0-9_.]*\(", value):  # a call such as bcrypt(...) or getJwt()
        return True
    if len(set(value)) <= 2 or _CODE_PATH.match(value):
        return True
    return len(value) < 16 and (_ENV_NAME.match(value) is not None or _PROSE.match(value) is not None)


def _looks_secret(value: str) -> bool:
    if len(value) < 6 or _placeholder(value):
        return False
    mixed = re.search(r"[0-9]", value) and re.search(r"[A-Za-z]", value)
    return bool(mixed or re.search(r"[^A-Za-z0-9]", value) or re.search(r"[A-Z]", value) or len(value) >= 16)


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


def scrub(text: str, literals: Iterable[str] = (), high_confidence_only: bool = False
          ) -> Tuple[str, List[Hit]]:
    """`literals`: exact secret strings that no pattern can spot (a bare password in prose)."""
    found: List[Tuple[int, str]] = []
    for literal in sorted({l for l in literals if l}, key=len, reverse=True):
        text = _sub(re.compile(re.escape(literal)), 0, "literal", text, found)
    text = _sub(_PEM, 0, "private-key", text, found)
    text = _sub(_TOKENS, 0, "token", text, found)
    text = _sub(_AUTH, 2, "auth-header", text, found)
    text = _sub(_COOKIE, 2, "cookie", text, found)
    text = _sub(_URL_CRED, 2, "url-password", text, found, check=lambda v: not _placeholder(v))
    if not high_confidence_only:
        text = _sub(_QUOTED, 3, "quoted-value", text, found,
                    check=lambda v: not v.startswith(("$", "%", "{", "<")) and len(set(v)) > 2)
        text = _sub(_KEY_VALUE, 2, "key-value", text, found, check=_looks_secret)
        text = _sub(_PROSE_PW, 2, "prose-password", text, found,
                    check=lambda v: bool(re.search(r"\d", v) and re.search(r"[A-Za-z]", v)))
    lines = text.splitlines()
    hits = [Hit(line, kind, lines[line - 1].strip()[:160]) for line, kind in sorted(found)]
    return text, hits
