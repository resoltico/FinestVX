"""Tests for FinestVX localized amount parsing."""

from __future__ import annotations

from decimal import Decimal

from ftllexengine import make_fluent_number
from ftllexengine.parsing import parse_decimal

from finestvx.localization import (
    parse_amount_input,
)


class TestLocalizationParsing:
    """Boundary parsing checks for FinestVX's FluentNumber amount adapter."""

    def test_amount_parsing_uses_upstream_locale_rules(self) -> None:
        """Localized decimal parsing is delegated to FTLLexEngine and wrapped once."""
        decimal_value, decimal_errors = parse_decimal("1 234,50", "lv-LV")
        amount_value, amount_errors = parse_amount_input("1 234,50", "lv-LV")

        assert decimal_errors == ()
        assert amount_errors == ()
        assert decimal_value == Decimal("1234.50")
        assert amount_value is not None
        assert amount_value == make_fluent_number(Decimal("1234.50"))

    def test_parse_functions_return_errors_on_invalid_input(self) -> None:
        """Amount parsing failures return (None, errors) rather than raising."""
        amount_value, errors = parse_amount_input("not-a-number", "en-US")
        assert amount_value is None
        assert len(errors) > 0
