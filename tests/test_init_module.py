"""Tests for the FinestVX package entry point."""

from __future__ import annotations

from decimal import Decimal

from ftllexengine import (
    FluentNumber,
    ParseResult,
    make_fluent_number,
)

import finestvx
from finestvx import (
    AmountParseResult,
    LocalizationConfig,
    create_localization,
    parse_amount_input,
)


class TestPackageInit:
    """Validate the FinestVX public package API."""

    def test_version_attribute_exists(self) -> None:
        """The package exposes a version string."""
        assert isinstance(finestvx.__version__, str)
        assert finestvx.__version__

    def test_public_exports_are_accessible(self) -> None:
        """Every documented public export is reachable from the package root."""
        for export_name in finestvx.__all__:
            assert hasattr(finestvx, export_name)

    def test_create_localization_is_accessible(self) -> None:
        """create_localization remains available at the FinestVX package root."""
        assert create_localization is finestvx.create_localization
        assert LocalizationConfig is finestvx.LocalizationConfig

    def test_parse_amount_input_is_accessible(self) -> None:
        """parse_amount_input remains the FinestVX parsing boundary for FluentNumber amounts."""
        result, errors = parse_amount_input("1 234,50", "lv-LV")
        assert errors == ()
        assert result is not None
        assert result == make_fluent_number(Decimal("1234.50"))

    def test_amount_parse_result_is_parse_result_alias(self) -> None:
        """AmountParseResult is an alias of ParseResult[FluentNumber], not a duplicate type."""
        sample: AmountParseResult = (None, ())
        assert sample[0] is None

        valid_amount: AmountParseResult = (
            FluentNumber(value=Decimal("1.00"), formatted="1.00", precision=2),
            (),
        )
        assert valid_amount[0] is not None

        # ParseResult is now exported from the ftllexengine top-level package.
        assert ParseResult is not None

    def test_removed_raw_parse_aliases_are_not_exported(self) -> None:
        """FinestVX no longer re-exports raw FTLLexEngine parse helpers."""
        for removed_name in (
            "FiscalDelta",
            "MonthEndPolicy",
            "get_cldr_version",
            "LocalizationService",
            "parse_decimal_input",
            "parse_date_input",
            "parse_datetime_input",
            "parse_currency_input",
        ):
            assert removed_name not in finestvx.__all__
            assert hasattr(finestvx, removed_name) is False
