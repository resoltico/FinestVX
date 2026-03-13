"""Pure validation helpers for FinestVX accounting primitives."""

from __future__ import annotations

from typing import TYPE_CHECKING

from ftllexengine.analysis import detect_cycles

from .enums import PostingSide
from .models import (
    Account,
    JournalTransaction,
    _totals_by_currency,
    _validate_account_collection,
    _validate_transaction_entries,
)

if TYPE_CHECKING:
    from collections.abc import Sequence
    from decimal import Decimal

    from .types import AccountCode, CurrencyCode

__all__ = [
    "account_dependency_map",
    "debit_totals_by_currency",
    "detect_account_cycles",
    "validate_chart_of_accounts",
    "validate_transaction_balance",
]


def validate_chart_of_accounts(accounts: Sequence[Account]) -> None:
    """Validate chart-of-accounts identity and hierarchy constraints."""
    _validate_account_collection(tuple(accounts))


def validate_transaction_balance(transaction: JournalTransaction) -> None:
    """Validate posted transaction balance constraints."""
    _validate_transaction_entries(transaction.entries)


def debit_totals_by_currency(transaction: JournalTransaction) -> dict[CurrencyCode, Decimal]:
    """Return debit totals by currency for the supplied transaction."""
    return _totals_by_currency(transaction.entries, side=PostingSide.DEBIT)


def account_dependency_map(accounts: Sequence[Account]) -> dict[AccountCode, set[str]]:
    """Build the account graph used for cycle detection."""
    return {
        account.code: {account.parent_code} if account.parent_code else set()
        for account in accounts
    }


def detect_account_cycles(accounts: Sequence[Account]) -> list[list[str]]:
    """Return account-cycle paths without raising on failure."""
    return detect_cycles(account_dependency_map(accounts))
