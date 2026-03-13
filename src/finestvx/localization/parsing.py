"""Localized input parsing helpers for FinestVX bookkeeping boundaries."""

from __future__ import annotations

from ftllexengine import FluentNumber, ParseResult, make_fluent_number
from ftllexengine.parsing import parse_decimal

__all__ = [
    "AmountParseResult",
    "parse_amount_input",
]

type AmountParseResult = ParseResult[FluentNumber]
"""Return type for localized amount parsing into ``FluentNumber`` values."""


def parse_amount_input(value: str, locale_code: str) -> AmountParseResult:
    """Parse localized decimal input into the engine's ``FluentNumber`` type."""
    parsed, errors = parse_decimal(value, locale_code)
    if parsed is None:
        return (None, errors)
    return (make_fluent_number(parsed), errors)
