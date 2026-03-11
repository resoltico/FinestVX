"""Property-based tests for FinestVX accounting-domain invariants."""

from __future__ import annotations

from datetime import UTC, datetime

import pytest
from ftllexengine.runtime.function_bridge import FluentNumber
from hypothesis import event, given

from finestvx.core import JournalTransaction, LedgerEntry, PostingSide
from tests.strategies.accounting import currencies, fluent_amounts, transaction_references

_POSTED_AT = datetime(2026, 1, 15, 9, 30, tzinfo=UTC)


@pytest.mark.property
@pytest.mark.hypothesis
class TestJournalTransactionProperties:
    """Property checks for posted transaction balance invariants."""

    @given(
        reference=transaction_references(),
        amount=fluent_amounts(),
        currency=currencies(),
    )
    def test_balanced_pair_is_always_accepted(
        self,
        reference: str,
        amount: FluentNumber,
        currency: str,
    ) -> None:
        """Mirrored debit and credit entries always create a balanced transaction."""
        transaction = JournalTransaction(
            reference=reference,
            posted_at=_POSTED_AT,
            description="Property test",
            entries=(
                LedgerEntry(
                    account_code="1000",
                    side=PostingSide.DEBIT,
                    amount=amount,
                    currency=currency,
                ),
                LedgerEntry(
                    account_code="2000",
                    side=PostingSide.CREDIT,
                    amount=amount,
                    currency=currency,
                ),
            ),
        )

        event(f"outcome=balanced_{transaction.is_balanced}")
        assert transaction.is_balanced is True
        assert (
            transaction.debits_by_currency()[currency]
            == transaction.credits_by_currency()[currency]
        )
