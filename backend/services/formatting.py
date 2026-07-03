"""Shared number formatting so reports, agents and tests agree on exact strings."""
from __future__ import annotations


def fmt_money(value: float) -> str:
    return f"${value:,.2f}"


def fmt_pct(value: float, signed: bool = True) -> str:
    return f"{value:+.1f}%" if signed else f"{value:.1f}%"
