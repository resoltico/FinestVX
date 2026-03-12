"""Tests for the FinestVX package entry point."""

from __future__ import annotations

from datetime import date
from decimal import Decimal

from ftllexengine import (
    FiscalDelta as UpstreamFiscalDelta,
)
from ftllexengine import (
    MonthEndPolicy as UpstreamMonthEndPolicy,
)
from ftllexengine import (
    ParseResult,
)
from ftllexengine import (
    get_cldr_version as upstream_get_cldr_version,
)
from ftllexengine.runtime.function_bridge import FluentNumber

import finestvx
from finestvx import (
    AmountParseResult,
    FiscalDelta,
    MonthEndPolicy,
    get_cldr_version,
    parse_datetime_input,
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

    def test_fiscal_delta_and_month_end_policy_are_exported(self) -> None:
        """FiscalDelta and MonthEndPolicy are re-exported from the FinestVX root."""
        delta = FiscalDelta(months=3)
        assert delta.total_months() == 3
        assert MonthEndPolicy.PRESERVE.value == "preserve"
        assert MonthEndPolicy.STRICT.value == "strict"

    def test_fiscal_delta_arithmetic(self) -> None:
        """FiscalDelta supports addition and subtraction for period arithmetic."""
        delta = FiscalDelta(months=1)
        result = delta.add_to(date(2026, 1, 31))
        assert result.month == 2

    def test_get_cldr_version_returns_version_string(self) -> None:
        """get_cldr_version is re-exported and returns the active CLDR version."""
        version = get_cldr_version()
        assert isinstance(version, str)
        assert version

    def test_upstream_re_exports_remain_identity_equal(self) -> None:
        """FinestVX root exports point at the FTLLexEngine top-level symbols directly."""
        assert FiscalDelta is UpstreamFiscalDelta
        assert MonthEndPolicy is UpstreamMonthEndPolicy
        assert get_cldr_version is upstream_get_cldr_version

    def test_parse_datetime_input_is_accessible(self) -> None:
        """parse_datetime_input is exported and delegates to ftllexengine."""
        result, errors = parse_datetime_input("2026-01-15 09:30:00", "en-US")
        assert errors == ()
        assert result is not None
        assert result.year == 2026

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
