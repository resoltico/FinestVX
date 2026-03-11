"""Localized input parsing helpers for FinestVX bookkeeping boundaries."""

from __future__ import annotations

from ftllexengine.parsing import (
    ParseResult,
    parse_currency,
    parse_date,
    parse_datetime,
    parse_decimal,
)
from ftllexengine.runtime.function_bridge import FluentNumber

from finestvx.core.serialization import fluent_number_from_decimal

__all__ = [
    "AmountParseResult",
    "parse_amount_input",
    "parse_currency_input",
    "parse_date_input",
    "parse_datetime_input",
    "parse_decimal_input",
]

type AmountParseResult = ParseResult[FluentNumber]
"""Return type for localized amount parsing into ``FluentNumber`` values."""

# Direct re-exports of FTLLexEngine parsing functions under FinestVX input naming.
# These are aliases, not wrappers: no implementation overhead, full signature fidelity.
parse_decimal_input = parse_decimal
parse_date_input = parse_date
parse_datetime_input = parse_datetime
parse_currency_input = parse_currency


def parse_amount_input(value: str, locale_code: str) -> AmountParseResult:
    """Parse localized decimal input into the engine's ``FluentNumber`` type."""
    parsed, errors = parse_decimal(value, locale_code)
    if parsed is None:
        return (None, errors)
    return (fluent_number_from_decimal(parsed), errors)
