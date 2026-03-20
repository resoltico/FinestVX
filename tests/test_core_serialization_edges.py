"""Additional tests for FinestVX serialization helpers."""

from __future__ import annotations

from datetime import UTC, date, datetime
from decimal import Decimal

import pytest
from ftllexengine import FiscalCalendar, FiscalPeriod, make_fluent_number
from ftllexengine.introspection import CurrencyCode

import finestvx.core.serialization as serialization_module
from finestvx.core import Account, Book, BookPeriod, JournalTransaction, LedgerEntry, PostingSide
from finestvx.core.enums import FiscalPeriodState, TransactionState
from finestvx.core.serialization import (
    book_from_mapping,
    book_to_mapping,
    transaction_from_mapping,
    transaction_to_mapping,
)

_POSTED_AT = datetime(2026, 1, 15, 9, 30, tzinfo=UTC)


class TestSerializationHelpers:
    """Coverage for deterministic mapping serialization and validation helpers."""

    def test_round_trip_preserves_optional_fields(self) -> None:
        """Round-tripping a rich book payload preserves normalized values."""
        period = FiscalPeriod(fiscal_year=2026, quarter=1, month=1)
        transaction = JournalTransaction(
            reference="TX-2026-2000",
            posted_at=_POSTED_AT,
            description="Round-trip",
            period=period,
            reversal_of="TX-2026-1999",
            state=TransactionState.POSTED,
            entries=(
                LedgerEntry(
                    account_code="1100",
                    side=PostingSide.DEBIT,
                    amount=make_fluent_number(Decimal("12.34"), formatted="12,34"),
                    currency=CurrencyCode("EUR"),
                    description="Debit line",
                    tax_rate=Decimal("0.21"),
                ),
                LedgerEntry(
                    account_code="2100",
                    side=PostingSide.CREDIT,
                    amount=make_fluent_number(Decimal("12.34")),
                    currency=CurrencyCode("EUR"),
                ),
            ),
        )
        book = Book(
            code="demo-book",
            name="Demo Book",
            base_currency=CurrencyCode("EUR"),
            fiscal_calendar=FiscalCalendar(start_month=4),
            legislative_pack="lv.standard.2026",
            accounts=(
                Account(
                    code="1000",
                    name="Assets",
                    normal_side=PostingSide.DEBIT,
                    currency=CurrencyCode("EUR"),
                ),
                Account(
                    code="1100",
                    name="Cash",
                    normal_side=PostingSide.DEBIT,
                    currency=CurrencyCode("EUR"),
                    parent_code="1000",
                ),
                Account(
                    code="2100",
                    name="Revenue",
                    normal_side=PostingSide.CREDIT,
                    currency=CurrencyCode("EUR"),
                ),
            ),
            periods=(
                BookPeriod(
                    period=period,
                    start_date=date(2026, 1, 1),
                    end_date=date(2026, 1, 31),
                    state=FiscalPeriodState.CLOSED,
                ),
            ),
            transactions=(transaction,),
        )

        transaction_mapping = transaction_to_mapping(transaction)
        restored_transaction = transaction_from_mapping(transaction_mapping)
        book_mapping = book_to_mapping(book)
        restored_book = book_from_mapping(book_mapping)

        assert restored_transaction.reversal_of == "TX-2026-1999"
        assert restored_transaction.period == period
        assert restored_book.code == book.code
        assert restored_book.fiscal_calendar.start_month == 4
        assert restored_book.accounts[1].parent_code == "1000"
        assert restored_book.transactions[0].entries[0].decimal_value == Decimal("12.34")
        assert restored_book.transactions[0].entries[0].description == "Debit line"

    def test_private_input_validators_reject_malformed_payloads(self) -> None:
        """Low-level serialization validators reject wrong runtime shapes."""
        with pytest.raises(TypeError, match="payload must be a mapping"):
            serialization_module._require_mapping([], "payload")
        with pytest.raises(TypeError, match="entries must be a sequence"):
            serialization_module._require_sequence("bad", "entries")
        with pytest.raises(TypeError, match=r"entry\.description must be str"):
            serialization_module._entry_from_mapping(
                {"account_code": "1000", "side": "Dr", "amount": "1.00",
                 "currency": "EUR", "description": 1}
            )
        with pytest.raises(ValueError, match=r"entry\.description cannot be blank"):
            serialization_module._entry_from_mapping(
                {"account_code": "1000", "side": "Dr", "amount": "1.00",
                 "currency": "EUR", "description": "  "}
            )
        with pytest.raises(TypeError, match="start_date must be ISO date text"):
            serialization_module._require_date(1, "start_date")
        with pytest.raises(TypeError, match="posted_at must be ISO datetime text"):
            serialization_module._require_datetime(1, "posted_at")
        with pytest.raises(TypeError, match=r"period\.fiscal_year must be int"):
            serialization_module._period_from_mapping(
                {"fiscal_year": True, "quarter": 1, "month": 1}, "period"
            )
        with pytest.raises(TypeError, match="amount must be decimal text"):
            serialization_module._require_decimal(1, "amount")

    def test_public_deserializers_report_type_mismatches(self) -> None:
        """Public mapping loaders surface field-level typing errors."""
        with pytest.raises(TypeError, match="book must be a mapping"):
            book_from_mapping([])
        with pytest.raises(TypeError, match=r"transaction\.entries must be a sequence"):
            transaction_from_mapping(
                {
                    "reference": "TX-2026-2001",
                    "posted_at": _POSTED_AT.isoformat(),
                    "description": "Bad sequence",
                    "entries": "bad",
                    "period": None,
                    "state": "draft",
                    "reversal_of": None,
                }
            )
        with pytest.raises(TypeError, match=r"transaction\.reference must be str"):
            transaction_from_mapping(
                {
                    "reference": 1,
                    "posted_at": _POSTED_AT.isoformat(),
                    "description": "Bad ref",
                    "entries": (),
                    "period": None,
                    "state": "draft",
                    "reversal_of": None,
                }
            )
