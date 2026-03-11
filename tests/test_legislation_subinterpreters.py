"""Tests for isolated legislative validation."""

from __future__ import annotations

from decimal import Decimal

from finestvx.legislation import validate_transaction_isolated
from finestvx.legislation.lv import LatviaStandard2026Pack
from tests.support.book_factory import build_posted_transaction, build_sample_book


class TestLegislativeInterpreterRunner:
    """Subinterpreter isolation checks."""

    def test_isolated_validation_matches_direct_pack_validation(self) -> None:
        """Built-in pack validation returns the same issue codes in a subinterpreter."""
        pack = LatviaStandard2026Pack()
        book = build_sample_book()
        transaction = build_posted_transaction(
            reference="TX-2026-0013",
            amount=Decimal("112.00"),
            tax_rate=Decimal("0.12"),
        )

        direct = pack.validate_transaction(book, transaction)
        isolated = validate_transaction_isolated(book.legislative_pack, book, transaction)

        assert [issue.code for issue in isolated.issues] == [issue.code for issue in direct.issues]
