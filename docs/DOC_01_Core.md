---
afad: "3.3"
version: "0.7.0"
domain: CORE
updated: "2026-03-17"
route:
  keywords: [book aggregate, journal transaction, ledger entry, chart of accounts, balance validation, immutable ledger, currency precision]
  questions: ["how is a book modeled?", "what invariants does a journal transaction enforce?", "how are ledger entries represented?", "how do i validate a chart of accounts?", "what is the current FinestVX core API?"]
---

# FinestVX Core Reference

---

## `Account`

`Account` is the immutable chart-of-accounts node used by the current FinestVX core.

### Signature
```python
@dataclass(frozen=True, slots=True)
class Account:
    code: AccountCode
    name: str
    normal_side: PostingSide
    currency: CurrencyCode
    parent_code: AccountCode | None = None
    allow_posting: bool = True
    active: bool = True
```

### Constraints
- `code` and `name` are required non-empty strings.
- `normal_side` must be `PostingSide.DEBIT` or `PostingSide.CREDIT`.
- `currency` must be a valid ISO 4217 code via `ftllexengine.introspection.is_valid_currency_code()`.
- `parent_code`, when present, must be non-empty and cannot equal `code`.
- Mutability is prohibited; modifications require constructing a new object.

---

## `BookPeriod`

`BookPeriod` is the current wrapper that binds an FTLLexEngine `FiscalPeriod` to concrete calendar dates and a FinestVX lifecycle state.

### Signature
```python
@dataclass(frozen=True, slots=True, order=True)
class BookPeriod:
    period: FiscalPeriod
    start_date: date
    end_date: date
    state: FiscalPeriodState = FiscalPeriodState.OPEN
```

### Constraints
- `period` must be an `ftllexengine.FiscalPeriod`.
- `start_date` and `end_date` must be `date` values.
- `state` must be a `FiscalPeriodState` enum member.
- `end_date` must be on or after `start_date`.
- Ordering is enabled for deterministic period sorting.

---

## `LedgerEntry`

`LedgerEntry` is the single debit or credit posting line inside a journal transaction.

### Signature
```python
@dataclass(frozen=True, slots=True)
class LedgerEntry:
    account_code: AccountCode
    side: PostingSide
    amount: FluentNumber
    currency: CurrencyCode
    description: str | None = None
    tax_rate: Decimal | None = None
```

### Constraints
- `amount` must be `ftllexengine.FluentNumber`.
- Underlying numeric values must be finite and non-negative; polarity lives in `side`, not in the amount sign.
- `currency` must be a valid ISO 4217 code.
- `amount` decimal precision is validated against ISO 4217 via `ftllexengine.introspection.get_currency_decimal_digits()`: amounts with more decimal places than the currency supports (e.g., JPY=0, EUR=2, KWD=3) are rejected with `ValueError`.
- `tax_rate`, when present, must be a finite `Decimal` in the inclusive range `0..1`.
- `decimal_value` exposes the balancing value as `Decimal`.

---

## `JournalTransaction`

`JournalTransaction` is the immutable transaction object for posted ledger movements.

### Signature
```python
@dataclass(frozen=True, slots=True)
class JournalTransaction:
    reference: TransactionReference
    posted_at: datetime
    description: str
    entries: Sequence[LedgerEntry]
    period: FiscalPeriod | None = None
    state: TransactionState = TransactionState.POSTED
    reversal_of: TransactionReference | None = None
```

### Constraints
- `reference` and `description` are required non-empty strings.
- `posted_at` must be a `datetime`.
- `entries` are normalized to an internal tuple.
- Posted transactions require at least two entries.
- Posted transactions must balance per currency: debit totals must equal credit totals for every currency present.
- `reversal_of`, when present, must reference another transaction, not itself.
- `is_balanced`: `True` when debit and credit totals match for every currency; `False` otherwise (non-raising property).
- `debits_by_currency()`, `credits_by_currency()`, `totals_by_currency(side?)`: return `dict[CurrencyCode, Decimal]` aggregates.

---

## `Book`

`Book` is the root aggregate for the current FinestVX slice.

### Signature
```python
@dataclass(frozen=True, slots=True)
class Book:
    code: BookCode
    name: str
    base_currency: CurrencyCode
    fiscal_calendar: FiscalCalendar = field(default_factory=FiscalCalendar)
    legislative_pack: LegislativePackCode = ""
    accounts: Sequence[Account] = ()
    periods: Sequence[BookPeriod] = ()
    transactions: Sequence[JournalTransaction] = ()
```

### Constraints
- `base_currency` must be a valid ISO 4217 code.
- `legislative_pack` has an empty-string syntactic default that is always rejected at `__post_init__`; callers must supply a non-empty value.
- `fiscal_calendar` must be `ftllexengine.FiscalCalendar`.
- `accounts`, `periods`, and `transactions` are normalized to tuples.
- Account codes must be unique.
- Account parent references must resolve within the same book.
- Account hierarchies must be acyclic.
- Period identifiers must be unique and non-overlapping.
- Transactions stored in a book must be posted.
- Every transaction entry account code must exist in the book chart.
- Transaction periods, when present, must exist in the book period set.
- `account_map()`: returns `dict[AccountCode, Account]` keyed by code.
- `period_set()`: returns `frozenset[FiscalPeriod]` of all known periods.
- `append_account(account)`: returns a new `Book` with the account appended; does not mutate.
- `append_transaction(transaction)`: returns a new `Book` with the transaction appended; does not mutate.

---

## `validate_chart_of_accounts`

`validate_chart_of_accounts()` is the public pure validator for account-identity and account-hierarchy rules.

### Signature
```python
def validate_chart_of_accounts(accounts: Sequence[Account]) -> None:
```

### Constraints
- Rejects non-`Account` members.
- Rejects duplicate account codes.
- Rejects missing parent references.
- Rejects account cycles using an internal O(V) ancestor-walk.
- Returns `None` on success and raises `TypeError` or `ValueError` on failure.

---

## `validate_transaction_balance`

`validate_transaction_balance()` is the public pure validator for posted transaction balance rules.

### Signature
```python
def validate_transaction_balance(transaction: JournalTransaction) -> None:
```

### Constraints
- Rejects transactions with fewer than two entries.
- Rejects non-`LedgerEntry` members.
- Rejects debit-credit mismatches per currency.
- Returns `None` on success and raises `ValueError` on failure.
