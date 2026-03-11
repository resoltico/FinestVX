"""Tests for FinestVX localized input parsing helpers."""

from __future__ import annotations

from datetime import datetime
from decimal import Decimal

from ftllexengine.parsing import (
    parse_currency,
    parse_date,
    parse_datetime,
    parse_decimal,
)

from finestvx.localization import (
    parse_amount_input,
    parse_currency_input,
    parse_date_input,
    parse_datetime_input,
    parse_decimal_input,
)


class TestLocalizedParsing:
    """Boundary parsing checks for localized user input."""

    def test_decimal_and_amount_parsing_use_locale_rules(self) -> None:
        """Localized decimal input is parsed back into Decimal and FluentNumber values."""
        decimal_value, decimal_errors = parse_decimal_input("1 234,50", "lv-LV")
        amount_value, amount_errors = parse_amount_input("1 234,50", "lv-LV")

        assert decimal_errors == ()
        assert amount_errors == ()
        assert decimal_value == Decimal("1234.50")
        assert amount_value is not None
        assert amount_value.value == Decimal("1234.50")

    def test_currency_parsing_recovers_amount_and_code(self) -> None:
        """Localized currency input is parsed into amount/code pairs."""
        parsed, errors = parse_currency_input("EUR 1 234,50", "lv-LV")

        assert errors == ()
        assert parsed == (Decimal("1234.50"), "EUR")

    def test_date_parsing_accepts_iso_format(self) -> None:
        """parse_date_input parses ISO 8601 dates as locale-independent input."""
        result, errors = parse_date_input("2026-01-15", "lv-LV")
        assert errors == ()
        assert result is not None
        assert result.year == 2026
        assert result.month == 1
        assert result.day == 15

    def test_datetime_parsing_accepts_iso_format(self) -> None:
        """parse_datetime_input parses ISO 8601 datetimes as locale-independent input."""
        result, errors = parse_datetime_input("2026-01-15 09:30:00", "en-US")
        assert errors == ()
        assert result is not None
        assert isinstance(result, datetime)
        assert result.year == 2026
        assert result.month == 1

    def test_parse_functions_return_errors_on_invalid_input(self) -> None:
        """Parsing failures return (None, errors) rather than raising."""
        decimal_value, errors = parse_decimal_input("not-a-number", "en-US")
        assert decimal_value is None
        assert len(errors) > 0

        amount_value, errors = parse_amount_input("not-a-number", "en-US")
        assert amount_value is None
        assert len(errors) > 0

    def test_parse_functions_are_ftllexengine_aliases(self) -> None:
        """The four alias functions are the exact same callables as ftllexengine's."""
        assert parse_decimal_input is parse_decimal
        assert parse_date_input is parse_date
        assert parse_datetime_input is parse_datetime
        assert parse_currency_input is parse_currency
