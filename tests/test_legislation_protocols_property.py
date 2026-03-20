"""Property-based tests for FinestVX legislative protocol invariants."""

from __future__ import annotations

import pytest
from ftllexengine.introspection import CurrencyCode, TerritoryCode
from hypothesis import event, given

from finestvx.legislation import LegislativePackMetadata
from tests.strategies.config import (
    invalid_tax_years,
    valid_tax_years,
)


@pytest.mark.property
@pytest.mark.hypothesis
class TestLegislativePackMetadataProperties:
    """Property checks for LegislativePackMetadata tax-year invariants."""

    @given(tax_year=valid_tax_years())
    def test_valid_tax_year_is_accepted(self, tax_year: int) -> None:
        """LegislativePackMetadata accepts any tax year within [1, 9999]."""
        metadata = LegislativePackMetadata(
            pack_code="lv.standard.test",
            territory_code=TerritoryCode("LV"),
            tax_year=tax_year,
            default_locale="lv-LV",
            currencies=(CurrencyCode("EUR"),),
        )

        event(f"outcome=accepted_tax_year={tax_year}")
        assert metadata.tax_year == tax_year

    @given(tax_year=invalid_tax_years())
    def test_invalid_tax_year_is_rejected(self, tax_year: int) -> None:
        """LegislativePackMetadata rejects any tax year outside [1, 9999]."""
        event(f"outcome=rejected_tax_year={tax_year}")
        with pytest.raises(ValueError, match=r"tax_year must be in range \[1, 9999\]"):
            LegislativePackMetadata(
                pack_code="lv.standard.test",
                territory_code=TerritoryCode("LV"),
                tax_year=tax_year,
                default_locale="lv-LV",
                currencies=(CurrencyCode("EUR"),),
            )
