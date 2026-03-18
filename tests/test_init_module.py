"""Tests for the FinestVX package entry point."""

from __future__ import annotations

from ftllexengine import FluentNumber

import finestvx
import finestvx.core

# These module-level imports are the primary contract check: if any export is
# missing from the root facade or from finestvx.core, this module fails to load
# and every test in the file is reported as a collection error.
from finestvx import FluentAmount, validate_ftl_resource_schemas
from finestvx.core import FluentAmount as _CoreFluentAmount


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

    def test_validate_ftl_resource_schemas_in_all(self) -> None:
        """validate_ftl_resource_schemas is listed in the root __all__."""
        assert "validate_ftl_resource_schemas" in finestvx.__all__
        assert callable(validate_ftl_resource_schemas)

    def test_fluent_amount_in_root_all(self) -> None:
        """FluentAmount is listed in the root __all__."""
        assert "FluentAmount" in finestvx.__all__
        assert FluentAmount is not None

    def test_fluent_amount_in_core_all(self) -> None:
        """FluentAmount is listed in finestvx.core.__all__."""
        assert "FluentAmount" in finestvx.core.__all__
        assert _CoreFluentAmount is not None

    def test_fluent_amount_is_fluent_number(self) -> None:
        """FluentAmount.__value__ resolves to FluentNumber (PEP 695 TypeAliasType)."""
        assert FluentAmount.__value__ is FluentNumber
        assert _CoreFluentAmount.__value__ is FluentNumber
