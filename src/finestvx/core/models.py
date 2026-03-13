"""Immutable domain models for the FinestVX bookkeeping core."""

from __future__ import annotations

from collections import defaultdict
from dataclasses import dataclass, field, replace
from datetime import date, datetime
from decimal import Decimal
from itertools import pairwise
from typing import TYPE_CHECKING, Final

from ftllexengine import FiscalCalendar, FiscalPeriod, FluentNumber
from ftllexengine.analysis import detect_cycles, make_cycle_key
from ftllexengine.introspection import (
    CurrencyCode,
    get_currency_decimal_digits,
    is_valid_currency_code,
)

from .enums import FiscalPeriodState, PostingSide, TransactionState

if TYPE_CHECKING:
    from collections.abc import Sequence

    from .types import AccountCode, BookCode, LegislativePackCode, TransactionReference

__all__ = [
    "Account",
    "Book",
    "BookPeriod",
    "JournalTransaction",
    "LedgerEntry",
]

_ZERO: Final[Decimal] = Decimal(0)
_DEFAULT_PACK_CODE: Final[LegislativePackCode] = "lv.standard.2026"


def _is_known_currency_code(value: str) -> bool:
    """Return ``True`` when the string is a known ISO 4217 currency code."""
    return bool(is_valid_currency_code(value))


def _require_non_empty_text(value: object, field_name: str) -> str:
    """Validate and normalize a required text field.

    Args:
        value: Candidate text value.
        field_name: Field name for diagnostics.

    Returns:
        Stripped text value.

    Raises:
        TypeError: If the value is not a string.
        ValueError: If the value is empty after trimming.
    """
    if not isinstance(value, str):
        msg = f"{field_name} must be str, got {type(value).__name__}"
        raise TypeError(msg)
    normalized = value.strip()
    if not normalized:
        msg = f"{field_name} must not be empty"
        raise ValueError(msg)
    return normalized


def _normalize_optional_text(value: object, field_name: str) -> str | None:
    """Normalize an optional text field.

    Args:
        value: Candidate text value.
        field_name: Field name for diagnostics.

    Returns:
        Stripped text value or ``None``.
    """
    if value is None:
        return None
    return _require_non_empty_text(value, field_name)


def _normalize_currency(value: object, field_name: str) -> CurrencyCode:
    """Validate and normalize an ISO 4217 currency code."""
    normalized = _require_non_empty_text(value, field_name).upper()
    if not _is_known_currency_code(normalized):
        msg = f"{field_name} must be a valid ISO 4217 currency code, got {value!r}"
        raise ValueError(msg)
    return normalized


def _require_decimal_ratio(value: object, field_name: str) -> Decimal | None:
    """Validate an optional decimal ratio constrained to the inclusive range 0..1."""
    if value is None:
        return None
    if isinstance(value, bool):
        msg = f"{field_name} must be Decimal, not bool"
        raise TypeError(msg)
    if not isinstance(value, Decimal):
        msg = f"{field_name} must be Decimal, got {type(value).__name__}"
        raise TypeError(msg)
    if not value.is_finite():
        msg = f"{field_name} must be finite"
        raise ValueError(msg)
    if not _ZERO <= value <= Decimal(1):
        msg = f"{field_name} must be between 0 and 1 inclusive"
        raise ValueError(msg)
    return value


def _coerce_tuple[T](value: object, field_name: str) -> tuple[T, ...]:
    """Accept list or tuple input and normalize to tuple storage."""
    if isinstance(value, tuple):
        return value
    if isinstance(value, list):
        return tuple(value)
    msg = f"{field_name} must be tuple or list, got {type(value).__name__}"
    raise TypeError(msg)


def _amount_as_decimal(amount: object) -> Decimal:
    """Convert a ``FluentNumber`` amount into a decimal value for balancing."""
    if not isinstance(amount, FluentNumber):
        msg = f"amount must be FluentNumber, got {type(amount).__name__}"
        raise TypeError(msg)
    match amount.value:
        case int() as integer_value:
            return Decimal(integer_value)
        case Decimal() as decimal_value:
            if not decimal_value.is_finite():
                msg = "amount value must be finite"
                raise ValueError(msg)
            return decimal_value


def _require_posting_side(value: object, field_name: str) -> PostingSide:
    """Validate a posting-side enum value."""
    if not isinstance(value, PostingSide):
        msg = f"{field_name} must be PostingSide, got {type(value).__name__}"
        raise TypeError(msg)
    return value


def _require_transaction_state(value: object, field_name: str) -> TransactionState:
    """Validate a transaction-state enum value."""
    if not isinstance(value, TransactionState):
        msg = f"{field_name} must be TransactionState, got {type(value).__name__}"
        raise TypeError(msg)
    return value


def _require_period_state(value: object, field_name: str) -> FiscalPeriodState:
    """Validate a fiscal-period-state enum value."""
    if not isinstance(value, FiscalPeriodState):
        msg = f"{field_name} must be FiscalPeriodState, got {type(value).__name__}"
        raise TypeError(msg)
    return value


def _require_fiscal_period(value: object, field_name: str) -> FiscalPeriod:
    """Validate a fiscal-period object."""
    if not isinstance(value, FiscalPeriod):
        msg = f"{field_name} must be FiscalPeriod, got {type(value).__name__}"
        raise TypeError(msg)
    return value


def _require_date_value(value: object, field_name: str) -> date:
    """Validate a date value."""
    if not isinstance(value, date):
        msg = f"{field_name} must be date, got {type(value).__name__}"
        raise TypeError(msg)
    return value


def _require_datetime_value(value: object, field_name: str) -> datetime:
    """Validate a datetime value."""
    if not isinstance(value, datetime):
        msg = f"{field_name} must be datetime, got {type(value).__name__}"
        raise TypeError(msg)
    return value


def _require_fiscal_calendar(value: object, field_name: str) -> FiscalCalendar:
    """Validate a fiscal-calendar object."""
    if not isinstance(value, FiscalCalendar):
        msg = f"{field_name} must be FiscalCalendar, got {type(value).__name__}"
        raise TypeError(msg)
    return value


def _validate_account_collection(accounts: Sequence[object]) -> None:
    """Validate chart-of-accounts identity and topology constraints."""
    seen_codes: set[AccountCode] = set()
    dependency_map: dict[AccountCode, set[str]] = {}
    validated_accounts: list[Account] = []

    for account in accounts:
        if not isinstance(account, Account):
            msg = f"accounts must contain Account objects, got {type(account).__name__}"
            raise TypeError(msg)
        validated_accounts.append(account)
        if account.code in seen_codes:
            msg = f"Duplicate account code detected: {account.code}"
            raise ValueError(msg)
        seen_codes.add(account.code)
        dependency_map[account.code] = {account.parent_code} if account.parent_code else set()

    for account in validated_accounts:
        if account.parent_code is not None and account.parent_code not in seen_codes:
            msg = (
                f"Account {account.code} references missing parent account "
                f"{account.parent_code}"
            )
            raise ValueError(msg)

    cycles = detect_cycles(dependency_map)
    if cycles:
        msg = f"Chart of accounts contains cycle: {make_cycle_key(cycles[0])}"
        raise ValueError(msg)


def _validate_period_collection(periods: Sequence[object]) -> None:
    """Validate uniqueness and ordering constraints for book periods."""
    seen_periods: set[FiscalPeriod] = set()
    validated_periods: list[BookPeriod] = []

    for period in periods:
        if not isinstance(period, BookPeriod):
            msg = f"periods must contain BookPeriod objects, got {type(period).__name__}"
            raise TypeError(msg)
        validated_periods.append(period)
        if period.period in seen_periods:
            msg = f"Duplicate fiscal period detected: {period.period!r}"
            raise ValueError(msg)
        seen_periods.add(period.period)

    ordered_periods = sorted(
        validated_periods,
        key=lambda period: (period.start_date, period.end_date),
    )

    for previous, current in pairwise(ordered_periods):
        if current.start_date <= previous.end_date:
            msg = (
                "Book periods must not overlap: "
                f"{previous.period!r} overlaps {current.period!r}"
            )
            raise ValueError(msg)


def _totals_by_currency(
    entries: Sequence[LedgerEntry],
    *,
    side: PostingSide | None = None,
) -> dict[CurrencyCode, Decimal]:
    """Aggregate journal entries by currency and optionally by posting side."""
    totals: defaultdict[CurrencyCode, Decimal] = defaultdict(Decimal)

    for entry in entries:
        if side is not None and entry.side is not side:
            continue
        totals[entry.currency] += entry.decimal_value

    return dict(totals)


def _validate_transaction_entries(entries: Sequence[object]) -> None:
    """Validate journal-entry cardinality and balancing constraints."""
    if len(entries) < 2:
        msg = "A transaction must contain at least two entries"
        raise ValueError(msg)

    validated_entries: list[LedgerEntry] = []
    for entry in entries:
        if not isinstance(entry, LedgerEntry):
            msg = f"entries must contain LedgerEntry objects, got {type(entry).__name__}"
            raise TypeError(msg)
        validated_entries.append(entry)

    debit_totals = _totals_by_currency(validated_entries, side=PostingSide.DEBIT)
    credit_totals = _totals_by_currency(validated_entries, side=PostingSide.CREDIT)
    mismatched_currencies = [
        currency
        for currency in sorted(set(debit_totals) | set(credit_totals))
        if debit_totals.get(currency, _ZERO) != credit_totals.get(currency, _ZERO)
    ]
    if mismatched_currencies:
        currencies = ", ".join(mismatched_currencies)
        msg = f"Transaction is not balanced for currencies: {currencies}"
        raise ValueError(msg)


def _validate_transactions_against_accounts(
    transactions: Sequence[object],
    account_codes: set[AccountCode],
) -> None:
    """Ensure posted transactions only reference known account codes."""
    for transaction in transactions:
        if not isinstance(transaction, JournalTransaction):
            msg = (
                "transactions must contain JournalTransaction objects, "
                f"got {type(transaction).__name__}"
            )
            raise TypeError(msg)
        if transaction.state is not TransactionState.POSTED:
            msg = "Book can only contain posted transactions"
            raise ValueError(msg)
        for entry in transaction.entries:
            if entry.account_code not in account_codes:
                msg = (
                    f"Transaction {transaction.reference} references unknown account "
                    f"{entry.account_code}"
                )
                raise ValueError(msg)


@dataclass(frozen=True, slots=True)
class Account:
    """Chart-of-accounts node definition."""

    code: AccountCode
    name: str
    normal_side: PostingSide
    currency: CurrencyCode
    parent_code: AccountCode | None = None
    allow_posting: bool = True
    active: bool = True

    def __post_init__(self) -> None:
        """Validate and normalize account fields."""
        object.__setattr__(self, "code", _require_non_empty_text(self.code, "code"))
        object.__setattr__(self, "name", _require_non_empty_text(self.name, "name"))
        object.__setattr__(self, "currency", _normalize_currency(self.currency, "currency"))
        object.__setattr__(
            self,
            "parent_code",
            _normalize_optional_text(self.parent_code, "parent_code"),
        )
        object.__setattr__(
            self,
            "normal_side",
            _require_posting_side(self.normal_side, "normal_side"),
        )
        if self.parent_code == self.code:
            msg = "Account cannot be its own parent"
            raise ValueError(msg)


@dataclass(frozen=True, slots=True, order=True)
class BookPeriod:
    """Open, closed, or locked fiscal period exposed by a book."""

    period: FiscalPeriod
    start_date: date
    end_date: date
    state: FiscalPeriodState = FiscalPeriodState.OPEN

    def __post_init__(self) -> None:
        """Validate the period date range."""
        object.__setattr__(self, "period", _require_fiscal_period(self.period, "period"))
        object.__setattr__(
            self,
            "start_date",
            _require_date_value(self.start_date, "start_date"),
        )
        object.__setattr__(self, "end_date", _require_date_value(self.end_date, "end_date"))
        object.__setattr__(self, "state", _require_period_state(self.state, "state"))
        if self.end_date < self.start_date:
            msg = "end_date must be on or after start_date"
            raise ValueError(msg)


@dataclass(frozen=True, slots=True)
class LedgerEntry:
    """Single debit or credit posting within a journal transaction."""

    account_code: AccountCode
    side: PostingSide
    amount: FluentNumber
    currency: CurrencyCode
    description: str | None = None
    tax_rate: Decimal | None = None

    def __post_init__(self) -> None:
        """Validate ledger-entry invariants."""
        object.__setattr__(
            self,
            "account_code",
            _require_non_empty_text(self.account_code, "account_code"),
        )
        object.__setattr__(self, "side", _require_posting_side(self.side, "side"))
        decimal_value = _amount_as_decimal(self.amount)
        if decimal_value < _ZERO:
            msg = "amount must be non-negative"
            raise ValueError(msg)
        object.__setattr__(self, "currency", _normalize_currency(self.currency, "currency"))
        max_decimal_places = get_currency_decimal_digits(self.currency)
        if max_decimal_places is not None:
            exponent = decimal_value.as_tuple().exponent
            if isinstance(exponent, int):
                amount_decimal_places = max(-exponent, 0)
                if amount_decimal_places > max_decimal_places:
                    msg = (
                        f"amount has {amount_decimal_places} decimal places but "
                        f"{self.currency} supports at most {max_decimal_places}"
                    )
                    raise ValueError(msg)
        object.__setattr__(
            self,
            "description",
            _normalize_optional_text(self.description, "description"),
        )
        object.__setattr__(self, "tax_rate", _require_decimal_ratio(self.tax_rate, "tax_rate"))

    @property
    def decimal_value(self) -> Decimal:
        """Return the numeric value used for balancing calculations."""
        return _amount_as_decimal(self.amount)


@dataclass(frozen=True, slots=True)
class JournalTransaction:
    """Immutable bookkeeping transaction built from posted ledger entries."""

    reference: TransactionReference
    posted_at: datetime
    description: str
    entries: tuple[LedgerEntry, ...] | list[LedgerEntry]
    period: FiscalPeriod | None = None
    state: TransactionState = TransactionState.POSTED
    reversal_of: TransactionReference | None = None

    def __post_init__(self) -> None:
        """Validate transaction identity and balancing constraints."""
        object.__setattr__(
            self,
            "reference",
            _require_non_empty_text(self.reference, "reference"),
        )
        object.__setattr__(
            self,
            "posted_at",
            _require_datetime_value(self.posted_at, "posted_at"),
        )
        object.__setattr__(
            self,
            "description",
            _require_non_empty_text(self.description, "description"),
        )
        object.__setattr__(self, "entries", _coerce_tuple(self.entries, "entries"))
        if self.period is not None:
            object.__setattr__(self, "period", _require_fiscal_period(self.period, "period"))
        object.__setattr__(self, "state", _require_transaction_state(self.state, "state"))
        object.__setattr__(
            self,
            "reversal_of",
            _normalize_optional_text(self.reversal_of, "reversal_of"),
        )
        if self.reversal_of == self.reference:
            msg = "reversal_of must reference a different transaction"
            raise ValueError(msg)
        if self.state is TransactionState.POSTED:
            _validate_transaction_entries(self.entries)

    def totals_by_currency(self, side: PostingSide | None = None) -> dict[CurrencyCode, Decimal]:
        """Return aggregated totals by currency.

        Args:
            side: Optional posting side filter.

        Returns:
            Currency totals for the selected entry subset.
        """
        return _totals_by_currency(self.entries, side=side)

    def debits_by_currency(self) -> dict[CurrencyCode, Decimal]:
        """Return debit totals grouped by currency."""
        return self.totals_by_currency(PostingSide.DEBIT)

    def credits_by_currency(self) -> dict[CurrencyCode, Decimal]:
        """Return credit totals grouped by currency."""
        return self.totals_by_currency(PostingSide.CREDIT)

    @property
    def is_balanced(self) -> bool:
        """Return ``True`` when debit and credit totals match for every currency."""
        try:
            _validate_transaction_entries(self.entries)
        except ValueError:
            return False
        return True


@dataclass(frozen=True, slots=True)
class Book:
    """Root aggregate containing accounts, periods, and posted transactions."""

    code: BookCode
    name: str
    base_currency: CurrencyCode
    fiscal_calendar: FiscalCalendar = field(default_factory=FiscalCalendar)
    legislative_pack: LegislativePackCode = _DEFAULT_PACK_CODE
    accounts: tuple[Account, ...] | list[Account] = ()
    periods: tuple[BookPeriod, ...] | list[BookPeriod] = ()
    transactions: tuple[JournalTransaction, ...] | list[JournalTransaction] = ()

    def __post_init__(self) -> None:
        """Validate and normalize aggregate invariants."""
        object.__setattr__(self, "code", _require_non_empty_text(self.code, "code"))
        object.__setattr__(self, "name", _require_non_empty_text(self.name, "name"))
        object.__setattr__(
            self,
            "base_currency",
            _normalize_currency(self.base_currency, "base_currency"),
        )
        object.__setattr__(
            self,
            "fiscal_calendar",
            _require_fiscal_calendar(self.fiscal_calendar, "fiscal_calendar"),
        )
        object.__setattr__(
            self,
            "legislative_pack",
            _require_non_empty_text(self.legislative_pack, "legislative_pack"),
        )
        object.__setattr__(self, "accounts", _coerce_tuple(self.accounts, "accounts"))
        object.__setattr__(self, "periods", _coerce_tuple(self.periods, "periods"))
        object.__setattr__(
            self,
            "transactions",
            _coerce_tuple(self.transactions, "transactions"),
        )
        _validate_account_collection(self.accounts)
        _validate_period_collection(self.periods)
        account_codes = {account.code for account in self.accounts}
        _validate_transactions_against_accounts(self.transactions, account_codes)
        known_periods = {period.period for period in self.periods}
        for transaction in self.transactions:
            if transaction.period is not None and transaction.period not in known_periods:
                msg = (
                    f"Transaction {transaction.reference} references unknown fiscal period "
                    f"{transaction.period!r}"
                )
                raise ValueError(msg)

    def account_map(self) -> dict[AccountCode, Account]:
        """Return account definitions keyed by account code."""
        return {account.code: account for account in self.accounts}

    def period_set(self) -> frozenset[FiscalPeriod]:
        """Return the known fiscal periods for the book."""
        return frozenset(period.period for period in self.periods)

    def append_account(self, account: Account) -> Book:
        """Return a new book instance with one additional account."""
        return replace(self, accounts=(*self.accounts, account))

    def append_transaction(self, transaction: JournalTransaction) -> Book:
        """Return a new book instance with one additional posted transaction."""
        return replace(self, transactions=(*self.transactions, transaction))
