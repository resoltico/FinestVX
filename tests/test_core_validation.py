"""Tests for FinestVX pure validation helpers."""

from __future__ import annotations

from datetime import UTC, datetime
from decimal import Decimal

import pytest
from ftllexengine.runtime.function_bridge import FluentNumber

from finestvx.core import (
    Account,
    JournalTransaction,
    LedgerEntry,
    PostingSide,
    TransactionState,
)
from finestvx.core.validation import (
    account_dependency_map,
    detect_account_cycles,
    validate_chart_of_accounts,
    validate_transaction_balance,
)

_POSTED_AT = datetime(2026, 1, 15, 9, 30, tzinfo=UTC)


class TestValidationHelpers:
    """Validate helper-level domain checks."""

    def test_validate_chart_of_accounts_accepts_valid_tree(self) -> None:
        """A valid account tree passes helper validation."""
        accounts = (
            Account(
                code="1000",
                name="Assets",
                normal_side=PostingSide.DEBIT,
                currency="EUR",
            ),
            Account(
                code="1100",
                name="Cash",
                normal_side=PostingSide.DEBIT,
                currency="EUR",
                parent_code="1000",
            ),
        )

        validate_chart_of_accounts(accounts)
        assert account_dependency_map(accounts) == {
            "1000": set(),
            "1100": {"1000"},
        }
        assert detect_account_cycles(accounts) == []

    def test_validate_transaction_balance_rejects_unbalanced_entries(self) -> None:
        """The helper rejects non-zero-sum transaction postings."""
        transaction = JournalTransaction(
            reference="TX-VAL-0001",
            posted_at=_POSTED_AT,
            description="Validation failure",
            state=TransactionState.DRAFT,
            entries=(
                LedgerEntry(
                    account_code="1000",
                    side=PostingSide.DEBIT,
                    amount=FluentNumber(value=Decimal("10.00"), formatted="10.00", precision=2),
                    currency="EUR",
                ),
                LedgerEntry(
                    account_code="2000",
                    side=PostingSide.CREDIT,
                    amount=FluentNumber(value=Decimal("9.00"), formatted="9.00", precision=2),
                    currency="EUR",
                ),
            ),
        )

        with pytest.raises(ValueError, match="not balanced"):
            validate_transaction_balance(transaction)
