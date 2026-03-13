"""Tests for FinestVX validation-report and legislative protocol dataclasses."""

from __future__ import annotations

from typing import Any, cast

import pytest
from ftllexengine.integrity import IntegrityCheckFailedError

from finestvx.legislation import (
    LegislativeIssue,
    LegislativePackMetadata,
    LegislativeValidationResult,
)
from finestvx.validation import ValidationFinding, ValidationReport, ValidationSeverity


class TestValidationReport:
    """Validation report acceptance and failure behavior."""

    def test_acceptance_and_require_valid_behaviour(self) -> None:
        """Accepted reports pass, invalid reports raise integrity errors."""
        accepted = ValidationReport(
            (
                ValidationFinding(
                    code="INFO_ONLY",
                    message="Informational",
                    severity=ValidationSeverity.INFO,
                    source="tests",
                ),
            )
        )
        accepted.require_valid(component="validation", operation="noop")
        assert accepted.accepted is True

        rejected = ValidationReport(
            (
                ValidationFinding(
                    code="BROKEN_ONE",
                    message="First error",
                    severity=ValidationSeverity.ERROR,
                    source="tests",
                ),
                ValidationFinding(
                    code="BROKEN_TWO",
                    message="Second error",
                    severity=ValidationSeverity.ERROR,
                    source="tests",
                ),
            )
        )

        with pytest.raises(IntegrityCheckFailedError, match="BROKEN_ONE, BROKEN_TWO"):
            rejected.require_valid(component="validation", operation="commit")
        assert rejected.accepted is False


class TestLegislativeProtocolDataclasses:
    """Validation of legislative metadata, issues, and results."""

    def test_metadata_normalizes_values_and_validates_bounds(self) -> None:
        """Metadata accepts valid identifiers and rejects malformed values."""
        metadata = LegislativePackMetadata(
            pack_code="lv.standard.2026",
            territory_code="lv",
            tax_year=2026,
            default_locale="lv-LV",
            currencies=["eur"],
        )

        assert metadata.territory_code == "LV"
        assert metadata.default_locale == "lv_lv"
        assert metadata.currencies == ("EUR",)

        with pytest.raises(TypeError, match="pack_code must be str"):
            LegislativePackMetadata(
                pack_code=cast("Any", 1),
                territory_code="LV",
                tax_year=2026,
                default_locale="lv-LV",
                currencies=("EUR",),
            )
        with pytest.raises(ValueError, match="territory_code must be a valid ISO 3166-1"):
            LegislativePackMetadata(
                pack_code="lv.standard.2026",
                territory_code="LVA",
                tax_year=2026,
                default_locale="lv-LV",
                currencies=("EUR",),
            )
        with pytest.raises(TypeError, match="tax_year must be int"):
            LegislativePackMetadata(
                pack_code="lv.standard.2026",
                territory_code="LV",
                tax_year=True,
                default_locale="lv-LV",
                currencies=("EUR",),
            )
        with pytest.raises(ValueError, match="tax_year must be between 1 and 9999"):
            LegislativePackMetadata(
                pack_code="lv.standard.2026",
                territory_code="LV",
                tax_year=10_000,
                default_locale="lv-LV",
                currencies=("EUR",),
            )
        with pytest.raises(ValueError, match="currencies must not be empty"):
            LegislativePackMetadata(
                pack_code="lv.standard.2026",
                territory_code="LV",
                tax_year=2026,
                default_locale="lv-LV",
                currencies=(),
            )
        with pytest.raises(ValueError, match="invalid ISO 4217 code"):
            LegislativePackMetadata(
                pack_code="lv.standard.2026",
                territory_code="LV",
                tax_year=2026,
                default_locale="lv-LV",
                currencies=("ZZZ1",),
            )
        with pytest.raises(TypeError, match="currencies must be tuple or list"):
            LegislativePackMetadata(
                pack_code="lv.standard.2026",
                territory_code="LV",
                tax_year=2026,
                default_locale="lv-LV",
                currencies=cast("Any", {"EUR"}),
            )
        with pytest.raises(ValueError, match="Invalid default_locale"):
            LegislativePackMetadata(
                pack_code="lv.standard.2026",
                territory_code="LV",
                tax_year=2026,
                default_locale="lv/LV",
                currencies=("EUR",),
            )

    def test_issue_and_validation_result_enforce_shape(self) -> None:
        """Issue and result objects validate indices and failure signalling."""
        issue = LegislativeIssue(code="VAT_MISMATCH", message="Wrong rate", entry_index=0)
        result = LegislativeValidationResult("lv.standard.2026", [issue])

        assert result.accepted is False
        with pytest.raises(ValueError, match="VAT_MISMATCH"):
            result.require_valid()

        accepted_result = LegislativeValidationResult("lv.standard.2026")
        accepted_result.require_valid()
        assert accepted_result.accepted is True

        with pytest.raises(TypeError, match="code must be str"):
            LegislativeIssue(code=cast("Any", 1), message="Wrong rate")
        with pytest.raises(ValueError, match="message must not be empty"):
            LegislativeIssue(code="VAT_MISMATCH", message=" ")
        with pytest.raises(TypeError, match="entry_index must be int"):
            LegislativeIssue(code="VAT_MISMATCH", message="Wrong rate", entry_index=True)
        with pytest.raises(ValueError, match="entry_index must be non-negative"):
            LegislativeIssue(code="VAT_MISMATCH", message="Wrong rate", entry_index=-1)
