"""Tests for the FinestVX package entry point."""

from __future__ import annotations

import finestvx


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

    def test_removed_platform_proxy_exports_are_not_exported(self) -> None:
        """FinestVX no longer re-exports deleted platform-boundary helper symbols."""
        for removed_name in (
            "AmountParseResult",
            "FiscalDelta",
            "MonthEndPolicy",
            "get_cldr_version",
            "LocalizationConfig",
            "LocalizationService",
            "create_localization",
        ):
            assert removed_name not in finestvx.__all__
            assert hasattr(finestvx, removed_name) is False
