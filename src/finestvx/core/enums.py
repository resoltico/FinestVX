"""Enum types for the FinestVX accounting domain."""

from __future__ import annotations

from enum import StrEnum

__all__ = [
    "FiscalPeriodState",
    "PostingSide",
    "TransactionState",
]


class PostingSide(StrEnum):
    """Debit or credit side for accounts and journal entries."""

    DEBIT = "Dr"
    CREDIT = "Cr"


class FiscalPeriodState(StrEnum):
    """Lifecycle state for a fiscal period exposed by a book."""

    OPEN = "open"
    CLOSED = "closed"
    LOCKED = "locked"


class TransactionState(StrEnum):
    """Lifecycle state for a journal transaction."""

    DRAFT = "draft"
    POSTED = "posted"
    REVERSED = "reversed"
