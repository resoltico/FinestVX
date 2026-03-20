"""Property-based tests for FinestVX accounting-domain invariants."""

from __future__ import annotations

from datetime import UTC, datetime
from decimal import Decimal

import pytest
from ftllexengine import FluentNumber
from ftllexengine.introspection import CurrencyCode
from hypothesis import event, given

from finestvx.core import JournalTransaction, LedgerEntry, PostingSide
from tests.strategies.accounting import (
    currencies,
    fluent_amounts,
    optional_descriptions,
    tax_rates_in_range,
    tax_rates_out_of_range,
    transaction_references,
)

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
                    currency=CurrencyCode(currency),
                ),
                LedgerEntry(
                    account_code="2000",
                    side=PostingSide.CREDIT,
                    amount=amount,
                    currency=CurrencyCode(currency),
                ),
            ),
        )

        event(f"outcome=balanced_{transaction.is_balanced}")
        assert transaction.is_balanced is True
        assert (
            transaction.debits_by_currency()[CurrencyCode(currency)]
            == transaction.credits_by_currency()[CurrencyCode(currency)]
        )

    @given(
        amount=fluent_amounts(),
        currency=currencies(),
        tax_rate=tax_rates_in_range(),
    )
    def test_tax_rate_in_range_is_accepted(
        self,
        amount: FluentNumber,
        currency: str,
        tax_rate: Decimal,
    ) -> None:
        """LedgerEntry accepts any tax rate within [0, 1]."""
        entry = LedgerEntry(
            account_code="1000",
            side=PostingSide.DEBIT,
            amount=amount,
            currency=CurrencyCode(currency),
            tax_rate=tax_rate,
        )

        event(f"outcome=accepted_tax_rate_{tax_rate}")
        assert entry.tax_rate == tax_rate

    @given(
        amount=fluent_amounts(),
        currency=currencies(),
        tax_rate=tax_rates_out_of_range(),
    )
    def test_tax_rate_out_of_range_is_rejected(
        self,
        amount: FluentNumber,
        currency: str,
        tax_rate: Decimal,
    ) -> None:
        """LedgerEntry rejects any tax rate outside [0, 1]."""
        event(f"outcome=rejected_tax_rate_{tax_rate}")
        with pytest.raises(ValueError, match=r"in range \[0, 1\]"):
            LedgerEntry(
                account_code="1000",
                side=PostingSide.DEBIT,
                amount=amount,
                currency=CurrencyCode(currency),
                tax_rate=tax_rate,
            )

    @given(
        amount=fluent_amounts(),
        currency=currencies(),
        description=optional_descriptions(),
    )
    def test_description_whitespace_is_stripped(
        self,
        amount: FluentNumber,
        currency: str,
        description: str | None,
    ) -> None:
        """LedgerEntry strips whitespace from descriptions and passes through None."""
        entry = LedgerEntry(
            account_code="1000",
            side=PostingSide.DEBIT,
            amount=amount,
            currency=CurrencyCode(currency),
            description=description,
        )

        if description is None:
            event("outcome=description_none")
            assert entry.description is None
        else:
            event("outcome=description_stripped")
            assert entry.description == description.strip()
            assert entry.description is not None
            assert entry.description == entry.description.strip()
