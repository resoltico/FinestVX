"""Tests for isolated legislative validation."""

from __future__ import annotations

from decimal import Decimal

import pytest

from finestvx.legislation import validate_transaction_isolated
from finestvx.legislation.lv import LatviaStandard2026Pack
from finestvx.legislation.subinterpreters import LegislativeInterpreterRunner
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

    def test_pool_min_size_zero_is_rejected(self) -> None:
        """pool_min_size=0 is rejected by require_positive_int."""
        with pytest.raises(ValueError, match="pool_min_size must be positive"):
            LegislativeInterpreterRunner(pool_min_size=0)

    def test_pool_max_size_less_than_min_size_is_rejected(self) -> None:
        """pool_max_size < pool_min_size is rejected."""
        with pytest.raises(ValueError, match="pool_max_size must be >= pool_min_size"):
            LegislativeInterpreterRunner(pool_min_size=4, pool_max_size=2)
