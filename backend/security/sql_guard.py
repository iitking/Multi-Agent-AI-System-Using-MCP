"""Validation for model-/user-supplied SQL. Defence in depth on top of read-only credentials."""
from __future__ import annotations

import re

MAX_SQL_LENGTH = 2000

_FORBIDDEN = re.compile(
    r"\b(insert|update|delete|drop|alter|create|attach|detach|pragma|replace|truncate|grant|"
    r"revoke|copy|vacuum|call|exec|execute|merge|into|set)\b",
    re.IGNORECASE,
)
_TABLE_REF = re.compile(r"\b(?:from|join)\s+([A-Za-z_][\w\.\"]*)", re.IGNORECASE)


class SQLGuardError(ValueError):
    """Raised when a query is not an allowed single read-only SELECT."""


def validate_readonly_sql(sql: str, allowed_tables: set[str]) -> str:
    """Return the cleaned SQL or raise :class:`SQLGuardError`.

    Rules: one ``SELECT`` statement, no comments, no ``:`` (bind/cast tricks), no write or
    admin keywords, and every ``FROM``/``JOIN`` target must be in ``allowed_tables``.
    """
    if not isinstance(sql, str) or not sql.strip():
        raise SQLGuardError("Query is empty.")
    cleaned = sql.strip().rstrip(";").strip()
    if len(cleaned) > MAX_SQL_LENGTH:
        raise SQLGuardError(f"Query is longer than {MAX_SQL_LENGTH} characters.")
    if ";" in cleaned:
        raise SQLGuardError("Only a single statement is allowed.")
    if "--" in cleaned or "/*" in cleaned or "*/" in cleaned:
        raise SQLGuardError("SQL comments are not allowed.")
    if ":" in cleaned:
        raise SQLGuardError("The ':' character is not allowed.")
    if not re.match(r"^select\b", cleaned, re.IGNORECASE):
        raise SQLGuardError("Only SELECT statements are allowed.")
    forbidden = _FORBIDDEN.search(cleaned)
    if forbidden:
        raise SQLGuardError(f"Keyword not allowed: {forbidden.group(1).upper()}.")
    for table in _TABLE_REF.findall(cleaned):
        name = table.replace('"', "").split(".")[-1].lower()
        if name not in allowed_tables:
            raise SQLGuardError(f"Table '{name}' is not approved for analytics queries.")
    return cleaned
