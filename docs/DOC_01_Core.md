---
afad: "3.3"
version: "0.1.0"
domain: CORE
updated: "2026-03-09"
route:
  keywords: [book aggregate, journal transaction, ledger entry, chart of accounts, balance validation, fiscal period wrapper, immutable ledger]
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
- `currency` must be a valid ISO 4217 code via `ftllexengine.introspection.iso.is_valid_currency_code()`.
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
- `period` must be an `ftllexengine.core.fiscal.FiscalPeriod`.
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
- `amount` must be `ftllexengine.runtime.function_bridge.FluentNumber`.
- Underlying numeric values must be finite and non-negative; polarity lives in `side`, not in the amount sign.
- `currency` must be a valid ISO 4217 code.
- `amount` decimal precision is validated against ISO 4217 via `ftllexengine.introspection.iso.get_currency()`: amounts with more decimal places than the currency supports (e.g., JPY=0, EUR=2, KWD=3) are rejected with `ValueError`.
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
    entries: tuple[LedgerEntry, ...] | list[LedgerEntry]
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
    legislative_pack: LegislativePackCode = "lv.standard.2026"
    accounts: tuple[Account, ...] | list[Account] = ()
    periods: tuple[BookPeriod, ...] | list[BookPeriod] = ()
    transactions: tuple[JournalTransaction, ...] | list[JournalTransaction] = ()
```

### Constraints
- `base_currency` must be a valid ISO 4217 code.
- `fiscal_calendar` must be `ftllexengine.core.fiscal.FiscalCalendar`.
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

## `FiscalDelta`

Immutable fiscal period delta from `ftllexengine.core.fiscal`; re-exported from `finestvx.core` for period arithmetic.

### Signature
```python
@dataclass(frozen=True, slots=True)
class FiscalDelta:
    years: int = 0
    quarters: int = 0
    months: int = 0
    days: int = 0
    month_end_policy: MonthEndPolicy = MonthEndPolicy.PRESERVE

    def total_months(self) -> int: ...
    def add_to(self, d: date) -> date: ...
    def subtract_from(self, d: date) -> date: ...
```

### Constraints
- All numeric fields must be `int`; `bool` is rejected.
- `month_end_policy` must be a `MonthEndPolicy` member.
- Arithmetic operators `+`, `-`, unary `-`, `*` are defined; mixing `month_end_policy` values in `+`/`-` raises `ValueError`.
- `add_to` / `subtract_from`: compute target date applying month-end policy.
- Use case: computing `BookPeriod.start_date` and `BookPeriod.end_date` from `FiscalCalendar` methods.

---

## `MonthEndPolicy`

Enumeration controlling month-end date behaviour in `FiscalDelta` arithmetic; re-exported from `finestvx.core`.

### Signature
```python
class MonthEndPolicy(StrEnum):
    PRESERVE = "preserve"
    CLAMP = "clamp"
    STRICT = "strict"
```

### Members
| Member | Value | Semantics |
|:-------|:------|:----------|
| `PRESERVE` | `"preserve"` | Default. Clamp day to last-of-month if arithmetic overflows. |
| `CLAMP` | `"clamp"` | If original date was month-end, result is always month-end. |
| `STRICT` | `"strict"` | Raise `ValueError` on any day overflow. |

### Constraints
- Purpose: date arithmetic policy for `FiscalDelta`; financial period calculations must be explicit about month-end handling.
- `STRICT` is appropriate for validation mode where inexact dates are errors.

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
- Rejects account cycles using `ftllexengine.analysis.graph.detect_cycles()`.
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
