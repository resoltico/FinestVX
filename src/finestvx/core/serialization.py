"""Deterministic serialization helpers for FinestVX domain models."""

from __future__ import annotations

from collections.abc import Mapping, Sequence
from datetime import date, datetime
from decimal import Decimal

from ftllexengine import FiscalCalendar, FiscalPeriod, make_fluent_number

from ._validators import normalize_optional_text, require_non_empty_text
from .enums import FiscalPeriodState, PostingSide, TransactionState
from .models import Account, Book, BookPeriod, JournalTransaction, LedgerEntry

__all__ = [
    "book_from_mapping",
    "book_to_mapping",
    "transaction_from_mapping",
    "transaction_to_mapping",
]


def _require_mapping(value: object, field_name: str) -> Mapping[str, object]:
    """Validate that the supplied value is a mapping."""
    if not isinstance(value, Mapping):
        msg = f"{field_name} must be a mapping, got {type(value).__name__}"
        raise TypeError(msg)
    return value


def _require_sequence(value: object, field_name: str) -> Sequence[object]:
    """Validate that the supplied value is a sequence excluding strings."""
    if isinstance(value, str) or not isinstance(value, Sequence):
        msg = f"{field_name} must be a sequence, got {type(value).__name__}"
        raise TypeError(msg)
    return value


def _require_date(value: object, field_name: str) -> date:
    """Parse an ISO 8601 date string."""
    if not isinstance(value, str):
        msg = f"{field_name} must be ISO date text, got {type(value).__name__}"
        raise TypeError(msg)
    return date.fromisoformat(value)


def _require_datetime(value: object, field_name: str) -> datetime:
    """Parse an ISO 8601 datetime string."""
    if not isinstance(value, str):
        msg = f"{field_name} must be ISO datetime text, got {type(value).__name__}"
        raise TypeError(msg)
    return datetime.fromisoformat(value)


def _require_int(value: object, field_name: str) -> int:
    """Validate an integer field."""
    if isinstance(value, bool) or not isinstance(value, int):
        msg = f"{field_name} must be int, got {type(value).__name__}"
        raise TypeError(msg)
    return value


def _require_decimal(value: object, field_name: str) -> Decimal:
    """Parse a decimal value from its text representation."""
    if not isinstance(value, str):
        msg = f"{field_name} must be decimal text, got {type(value).__name__}"
        raise TypeError(msg)
    return Decimal(value)


def _period_to_mapping(period: FiscalPeriod) -> dict[str, int]:
    """Serialize a fiscal period."""
    return {
        "fiscal_year": period.fiscal_year,
        "quarter": period.quarter,
        "month": period.month,
    }


def _period_from_mapping(payload: object, field_name: str) -> FiscalPeriod:
    """Deserialize a fiscal period from a mapping."""
    data = _require_mapping(payload, field_name)
    return FiscalPeriod(
        fiscal_year=_require_int(data["fiscal_year"], f"{field_name}.fiscal_year"),
        quarter=_require_int(data["quarter"], f"{field_name}.quarter"),
        month=_require_int(data["month"], f"{field_name}.month"),
    )


def _entry_to_mapping(entry: LedgerEntry) -> dict[str, object]:
    """Serialize a ledger entry."""
    return {
        "account_code": entry.account_code,
        "side": entry.side.value,
        "amount": format(entry.decimal_value, "f"),
        "currency": entry.currency,
        "description": entry.description,
        "tax_rate": None if entry.tax_rate is None else format(entry.tax_rate, "f"),
    }


def _entry_from_mapping(payload: object) -> LedgerEntry:
    """Deserialize a ledger entry."""
    data = _require_mapping(payload, "entry")
    amount = _require_decimal(data["amount"], "entry.amount")
    tax_rate = data.get("tax_rate")
    return LedgerEntry(
        account_code=require_non_empty_text(data["account_code"], "entry.account_code"),
        side=PostingSide(require_non_empty_text(data["side"], "entry.side")),
        amount=make_fluent_number(amount),
        currency=require_non_empty_text(data["currency"], "entry.currency"),
        description=normalize_optional_text(data.get("description"), "entry.description"),
        tax_rate=None if tax_rate is None else _require_decimal(tax_rate, "entry.tax_rate"),
    )


def transaction_to_mapping(transaction: JournalTransaction) -> dict[str, object]:
    """Serialize a journal transaction."""
    return {
        "reference": transaction.reference,
        "posted_at": transaction.posted_at.isoformat(),
        "description": transaction.description,
        "entries": [_entry_to_mapping(entry) for entry in transaction.entries],
        "period": None if transaction.period is None else _period_to_mapping(transaction.period),
        "state": transaction.state.value,
        "reversal_of": transaction.reversal_of,
    }


def transaction_from_mapping(payload: object) -> JournalTransaction:
    """Deserialize a journal transaction."""
    data = _require_mapping(payload, "transaction")
    period = data.get("period")
    return JournalTransaction(
        reference=require_non_empty_text(data["reference"], "transaction.reference"),
        posted_at=_require_datetime(data["posted_at"], "transaction.posted_at"),
        description=require_non_empty_text(data["description"], "transaction.description"),
        entries=tuple(
            _entry_from_mapping(item)
            for item in _require_sequence(data["entries"], "transaction.entries")
        ),
        period=None if period is None else _period_from_mapping(period, "transaction.period"),
        state=TransactionState(require_non_empty_text(data["state"], "transaction.state")),
        reversal_of=normalize_optional_text(data.get("reversal_of"), "transaction.reversal_of"),
    )


def _account_to_mapping(account: Account) -> dict[str, object]:
    """Serialize an account."""
    return {
        "code": account.code,
        "name": account.name,
        "normal_side": account.normal_side.value,
        "currency": account.currency,
        "parent_code": account.parent_code,
        "allow_posting": account.allow_posting,
        "active": account.active,
    }


def _account_from_mapping(payload: object) -> Account:
    """Deserialize an account."""
    data = _require_mapping(payload, "account")
    return Account(
        code=require_non_empty_text(data["code"], "account.code"),
        name=require_non_empty_text(data["name"], "account.name"),
        normal_side=PostingSide(require_non_empty_text(data["normal_side"], "account.normal_side")),
        currency=require_non_empty_text(data["currency"], "account.currency"),
        parent_code=normalize_optional_text(data.get("parent_code"), "account.parent_code"),
        allow_posting=bool(data.get("allow_posting", True)),
        active=bool(data.get("active", True)),
    )


def _book_period_to_mapping(period: BookPeriod) -> dict[str, object]:
    """Serialize a book period."""
    return {
        "period": _period_to_mapping(period.period),
        "start_date": period.start_date.isoformat(),
        "end_date": period.end_date.isoformat(),
        "state": period.state.value,
    }


def _book_period_from_mapping(payload: object) -> BookPeriod:
    """Deserialize a book period."""
    data = _require_mapping(payload, "book_period")
    return BookPeriod(
        period=_period_from_mapping(data["period"], "book_period.period"),
        start_date=_require_date(data["start_date"], "book_period.start_date"),
        end_date=_require_date(data["end_date"], "book_period.end_date"),
        state=FiscalPeriodState(require_non_empty_text(data["state"], "book_period.state")),
    )


def book_to_mapping(book: Book) -> dict[str, object]:
    """Serialize a book into a deterministic mapping."""
    return {
        "code": book.code,
        "name": book.name,
        "base_currency": book.base_currency,
        "fiscal_calendar": {"start_month": book.fiscal_calendar.start_month},
        "legislative_pack": book.legislative_pack,
        "accounts": [_account_to_mapping(account) for account in book.accounts],
        "periods": [_book_period_to_mapping(period) for period in book.periods],
        "transactions": [transaction_to_mapping(transaction) for transaction in book.transactions],
    }


def book_from_mapping(payload: object) -> Book:
    """Deserialize a book mapping into a domain object."""
    data = _require_mapping(payload, "book")
    fiscal_calendar = _require_mapping(data["fiscal_calendar"], "book.fiscal_calendar")
    return Book(
        code=require_non_empty_text(data["code"], "book.code"),
        name=require_non_empty_text(data["name"], "book.name"),
        base_currency=require_non_empty_text(data["base_currency"], "book.base_currency"),
        fiscal_calendar=FiscalCalendar(
            start_month=_require_int(
                fiscal_calendar["start_month"],
                "book.fiscal_calendar.start_month",
            )
        ),
        legislative_pack=require_non_empty_text(data["legislative_pack"], "book.legislative_pack"),
        accounts=tuple(
            _account_from_mapping(item)
            for item in _require_sequence(data["accounts"], "book.accounts")
        ),
        periods=tuple(
            _book_period_from_mapping(item)
            for item in _require_sequence(data["periods"], "book.periods")
        ),
        transactions=tuple(
            transaction_from_mapping(item)
            for item in _require_sequence(data["transactions"], "book.transactions")
        ),
    )
