"""Untrusted-content handling: prompt-injection screening, input validation and secret redaction."""
from __future__ import annotations

import re
from dataclasses import dataclass, field

_INJECTION_PATTERNS: dict[str, re.Pattern[str]] = {
    "ignore_instructions": re.compile(
        r"\b(ignore|disregard|forget|override)\b[^.\n]{0,40}\b(previous|prior|above|earlier|all)\b[^.\n]{0,30}\b(instructions?|rules?|prompts?|guidelines?)\b",
        re.IGNORECASE,
    ),
    "role_hijack": re.compile(r"\byou are now\b|\bnew (system )?instructions?\b|\badmin mode\b|\bdeveloper mode\b", re.IGNORECASE),
    "prompt_exfiltration": re.compile(r"\b(reveal|show|print|leak)\b[^.\n]{0,30}\b(system prompt|api[_ -]?key|password|secret|credentials?)\b", re.IGNORECASE),
    "data_exfiltration": re.compile(r"\b(send|email|forward|upload|exfiltrate)\b[^.\n]{0,60}\b(database|customer data|credentials?|all data|sales data)\b", re.IGNORECASE),
    "fake_role_tag": re.compile(r"<\s*/?\s*(system|assistant|developer)\s*>", re.IGNORECASE),
}

_SECRET_PATTERNS = [
    re.compile(r"sk-[A-Za-z0-9_\-]{16,}"),
    re.compile(r"(?i)\b(api[_-]?key|secret|token|password|passwd)\b\s*[:=]\s*\S+"),
    re.compile(r"(?i)bearer\s+[A-Za-z0-9._\-]{16,}"),
]

_CONTROL_CHARS = re.compile(r"[\x00-\x08\x0b\x0c\x0e-\x1f\x7f]")

WITHHELD = "[content withheld: possible prompt injection]"


@dataclass
class ScanResult:
    text: str
    flagged: bool = False
    reasons: list[str] = field(default_factory=list)


def scan_untrusted(text: str) -> list[str]:
    """Return the names of injection heuristics that match ``text``."""
    return [name for name, pattern in _INJECTION_PATTERNS.items() if pattern.search(text or "")]


def sanitize_untrusted(text: str, max_len: int = 600) -> ScanResult:
    """Clean text that came from a document or tool. Flagged text is withheld entirely."""
    cleaned = _CONTROL_CHARS.sub("", text or "").strip()
    reasons = scan_untrusted(cleaned)
    if reasons:
        return ScanResult(text=WITHHELD, flagged=True, reasons=reasons)
    if len(cleaned) > max_len:
        cleaned = cleaned[: max_len - 1].rstrip() + "…"
    return ScanResult(text=cleaned)


def redact(text: str | None, max_len: int = 500) -> str:
    """Mask secrets and truncate before text reaches logs or the audit trail."""
    value = text or ""
    for pattern in _SECRET_PATTERNS:
        value = pattern.sub("[REDACTED]", value)
    return value if len(value) <= max_len else value[: max_len - 1] + "…"


def validate_user_request(text: str, min_len: int = 10, max_len: int = 2000) -> str:
    cleaned = _CONTROL_CHARS.sub("", text or "").strip()
    if len(cleaned) < min_len:
        raise ValueError(f"Request must be at least {min_len} characters.")
    if len(cleaned) > max_len:
        raise ValueError(f"Request must be at most {max_len} characters.")
    return cleaned
