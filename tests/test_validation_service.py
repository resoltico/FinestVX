"""Tests for FinestVX validation service wrappers."""

from __future__ import annotations

from decimal import Decimal

from finestvx.legislation import create_default_pack_registry
from finestvx.validation import (
    validate_book,
    validate_ftl_resource,
    validate_legislative_transaction,
)
from tests.support.book_factory import build_posted_transaction, build_sample_book


class TestValidationService:
    """Validation aggregation checks."""

    def test_validate_book_accepts_clean_book(self) -> None:
        """A valid book produces an accepted report."""
        report = validate_book(build_sample_book())

        assert report.accepted is True
        assert report.findings == ()

    def test_validate_ftl_resource_reports_invalid_references(self) -> None:
        """FTL static validation failures are surfaced as findings."""
        report = validate_ftl_resource("hello = { -missing-term }\n")

        assert report.accepted is False
        assert any(finding.source == "ftl.resource" for finding in report.findings)

    def test_validate_legislative_transaction_reports_pack_issues(self) -> None:
        """Legislative validation findings are bridged into a unified report."""
        registry = create_default_pack_registry()
        book = build_sample_book()
        transaction = build_posted_transaction(
            reference="TX-2026-0012",
            amount=Decimal("112.00"),
            tax_rate=Decimal("0.12"),
        )

        report = validate_legislative_transaction(registry, book, transaction)

        assert report.accepted is False
        assert [finding.code for finding in report.findings] == [
            "LV_STANDARD_VAT_RATE_MISMATCH",
            "LV_STANDARD_VAT_RATE_MISMATCH",
        ]
