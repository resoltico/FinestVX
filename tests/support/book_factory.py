"""Deterministic builders for FinestVX integration tests."""

from __future__ import annotations

from datetime import UTC, date, datetime
from decimal import Decimal

from ftllexengine import make_fluent_number
from ftllexengine.core.fiscal import FiscalCalendar, FiscalPeriod

from finestvx.core.enums import FiscalPeriodState, PostingSide
from finestvx.core.models import Account, Book, BookPeriod, JournalTransaction, LedgerEntry

POSTED_AT = datetime(2026, 1, 15, 9, 30, tzinfo=UTC)

__all__ = [
    "POSTED_AT",
    "build_posted_transaction",
    "build_sample_book",
]


def build_posted_transaction(
    reference: str = "TX-2026-0001",
    *,
    amount: Decimal = Decimal("121.00"),
    tax_rate: Decimal | None = Decimal("0.21"),
) -> JournalTransaction:
    """Build a balanced posted transaction for test scenarios."""
    return JournalTransaction(
        reference=reference,
        posted_at=POSTED_AT,
        description="Sample posted transaction",
        entries=(
            LedgerEntry(
                account_code="1000",
                side=PostingSide.DEBIT,
                amount=make_fluent_number(amount),
                currency="EUR",
                tax_rate=tax_rate,
            ),
            LedgerEntry(
                account_code="2000",
                side=PostingSide.CREDIT,
                amount=make_fluent_number(amount),
                currency="EUR",
                tax_rate=tax_rate,
            ),
        ),
    )


def build_sample_book(*, include_transaction: bool = False) -> Book:
    """Build a deterministic book aggregate for integration tests."""
    transactions = (build_posted_transaction(),) if include_transaction else ()
    return Book(
        code="demo-book",
        name="Demo Book",
        base_currency="EUR",
        fiscal_calendar=FiscalCalendar(start_month=1),
        legislative_pack="lv.standard.2026",
        accounts=(
            Account(
                code="1000",
                name="Cash",
                normal_side=PostingSide.DEBIT,
                currency="EUR",
            ),
            Account(
                code="2000",
                name="Revenue",
                normal_side=PostingSide.CREDIT,
                currency="EUR",
            ),
        ),
        periods=(
            BookPeriod(
                period=FiscalPeriod(fiscal_year=2026, quarter=1, month=1),
                start_date=date(2026, 1, 1),
                end_date=date(2026, 1, 31),
                state=FiscalPeriodState.OPEN,
            ),
        ),
        transactions=transactions,
    )
