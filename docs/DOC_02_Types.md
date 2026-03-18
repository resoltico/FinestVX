---
afad: "3.3"
version: "0.7.0"
domain: TYPES
updated: "2026-03-17"
route:
  keywords: [posting side, transaction state, fiscal period state, account code, book code, legislative pack code, transaction reference, fluent amount, type aliases, fluent number alias]
  questions: ["what enums does finestvx define?", "what type aliases exist in the accounting core?", "how are posting directions represented?", "what lifecycle states exist for transactions?", "what lifecycle states exist for fiscal periods?", "what is FluentAmount?"]
---

# FinestVX Types Reference

---

## `PostingSide`

Enumeration of the two accounting posting directions.

### Signature
```python
class PostingSide(StrEnum):
    DEBIT = "Dr"
    CREDIT = "Cr"
```

### Members
| Member | Value | Semantics |
|:-------|:------|:----------|
| `DEBIT` | `"Dr"` | Debit posting; increases asset and expense accounts |
| `CREDIT` | `"Cr"` | Credit posting; increases liability, equity, and revenue accounts |

### Constraints
- Purpose: polarity carrier for `Account.normal_side` and `LedgerEntry.side`.
- Type: `StrEnum`; string-comparable and SQLite-serializable.
- Amounts remain non-negative; sign lives entirely in the side.

---

## `FiscalPeriodState`

Enumeration of lifecycle states for a `BookPeriod`.

### Signature
```python
class FiscalPeriodState(StrEnum):
    OPEN = "open"
    CLOSED = "closed"
    LOCKED = "locked"
```

### Members
| Member | Value | Semantics |
|:-------|:------|:----------|
| `OPEN` | `"open"` | Default; period accepts new transactions |
| `CLOSED` | `"closed"` | Period closed for routine posting |
| `LOCKED` | `"locked"` | Period locked; no modifications permitted |

### Constraints
- Purpose: lifecycle classification for `BookPeriod.state`.
- Type: `StrEnum`; persisted as text in the `periods` SQLite table.
- Policy enforcement beyond identity-level is the caller's responsibility.

---

## `TransactionState`

Enumeration of lifecycle states for a `JournalTransaction`.

### Signature
```python
class TransactionState(StrEnum):
    DRAFT = "draft"
    POSTED = "posted"
    REVERSED = "reversed"
```

### Members
| Member | Value | Semantics |
|:-------|:------|:----------|
| `DRAFT` | `"draft"` | Pre-commit; not yet balance-validated |
| `POSTED` | `"posted"` | Default; balance-validated and immutable |
| `REVERSED` | `"reversed"` | Reversed by a contra-transaction |

### Constraints
- Purpose: lifecycle carrier for `JournalTransaction.state`.
- Type: `StrEnum`; persisted as text in the `transactions` SQLite table.
- `Book` and `SqliteLedgerStore` store only `POSTED` transactions.
- `DRAFT` is valid for pre-commit validation scenarios only.

---

## `AccountCode`

Type alias for chart-of-accounts node identifiers.

### Definition
```python
type AccountCode = str
```

### Constraints
- Purpose: distinguishes account identifiers from arbitrary strings at the type level.
- Narrowing: validated as non-empty at all domain boundaries.

---

## `BookCode`

Type alias for book aggregate identifiers.

### Definition
```python
type BookCode = str
```

### Constraints
- Purpose: distinguishes book identifiers from arbitrary strings.
- Narrowing: validated as non-empty at all domain boundaries.

---

## `LegislativePackCode`

Type alias for legislative-pack registration keys.

### Definition
```python
type LegislativePackCode = str
```

### Constraints
- Purpose: identifies which legislative pack governs a book.
- `Book` has an empty-string syntactic default that `__post_init__` always rejects; callers must supply a non-empty value.
- Narrowing: validated as non-empty at domain and registry boundaries.

---

## `TransactionReference`

Type alias for immutable transaction reference strings.

### Definition
```python
type TransactionReference = str
```

### Constraints
- Purpose: external or internal transaction identifier; referenced by `reversal_of`.
- Narrowing: validated as non-empty; self-referential `reversal_of` is rejected by `JournalTransaction`.

---

## `FluentAmount`

Type alias for monetary amounts throughout the FinestVX accounting domain.

### Definition
```python
type FluentAmount = FluentNumber
```

### Constraints
- `FluentAmount` is an alias for `ftllexengine.FluentNumber`; the two names are interchangeable at the type level.
- Exported from `finestvx.core` and `finestvx` for use in type annotations that should clearly signal financial-amount semantics rather than generic `FluentNumber` usage.
- Underlying value must be backed by `int | Decimal`; `float` and `bool` are rejected at `FluentNumber.__post_init__`.
