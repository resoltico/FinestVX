"""Tests for the FinestVX package entry point."""

from __future__ import annotations

import finestvx
from finestvx import LocalizationConfig, create_localization


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

    def test_removed_raw_parse_aliases_are_not_exported(self) -> None:
        """FinestVX no longer re-exports FTLLexEngine parsing or utility helpers."""
        for removed_name in (
            "AmountParseResult",
            "FiscalDelta",
            "MonthEndPolicy",
            "get_cldr_version",
            "LocalizationService",
            "parse_amount_input",
            "parse_decimal_input",
            "parse_date_input",
            "parse_datetime_input",
            "parse_currency_input",
        ):
            assert removed_name not in finestvx.__all__
            assert hasattr(finestvx, removed_name) is False
