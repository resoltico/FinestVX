---
afad: "3.3"
version: "0.2.0"
domain: PRIMARY
updated: "2026-03-12"
route:
  keywords: [validation report, validation finding, validation severity, validate book, validate transaction, ftl resource validation, legislative validation]
  questions: ["how do i validate a transaction?", "what is a ValidationReport?", "how does finestvx report validation errors?", "how do i validate an ftl resource?", "how do i validate against a legislative pack?"]
---

# FinestVX Validation Reference

---

## `ValidationSeverity`

Enumeration of diagnostic severity levels in a validation report.

### Signature
```python
class ValidationSeverity(StrEnum):
    ERROR = "error"
    WARNING = "warning"
    INFO = "info"
```

### Members
| Member | Value | Semantics |
|:-------|:------|:----------|
| `ERROR` | `"error"` | Blocking failure; `ValidationReport.accepted` returns `False` |
| `WARNING` | `"warning"` | Non-blocking advisory |
| `INFO` | `"info"` | Informational; never blocks acceptance |

### Constraints
- Purpose: severity classification for `ValidationFinding` instances.
- Type: `StrEnum`; string-comparable and JSON-serializable.

---

## `ValidationFinding`

Immutable single finding emitted by a validation workflow.

### Signature
```python
@dataclass(frozen=True, slots=True)
class ValidationFinding:
    code: str
    message: str
    severity: ValidationSeverity
    source: str
```

### Constraints
- All fields are required non-empty strings, except `severity` which must be `ValidationSeverity`.
- `source` identifies the originating subsystem (e.g. `"core.transaction"`, `"ftl.resource"`, `"legislation.lv.standard.2026"`).
- Immutable; no mutation after construction.

---

## `ValidationReport`

Immutable collection of `ValidationFinding` instances produced by a validation pass.

### Signature
```python
@dataclass(frozen=True, slots=True)
class ValidationReport:
    findings: tuple[ValidationFinding, ...] = ()

    @property
    def accepted(self) -> bool: ...

    def require_valid(self, *, component: str, operation: str) -> None: ...
```

### Constraints
- `findings` defaults to an empty tuple; an empty report is always accepted.
- `accepted`: `True` when no finding carries `ValidationSeverity.ERROR`; warnings and info do not block.
- `require_valid`: raises `ftllexengine.integrity.IntegrityCheckFailedError` when `not accepted`; used at hard-fail boundaries.
- Combining reports: `ValidationReport(report_a.findings + report_b.findings)`.

---

## `validate_book`

Function that validates chart-of-accounts and transaction invariants across a full book aggregate.

### Signature
```python
def validate_book(book: Book) -> ValidationReport:
```

### Parameters
| Name | Type | Req | Semantics |
|:-----|:-----|:----|:----------|
| `book` | `Book` | Y | Root aggregate to validate |

### Constraints
- Return: `ValidationReport` with zero or more findings; never raises on validation failures.
- Runs `validate_chart_of_accounts` and then `validate_transaction` for each transaction.
- Account-reference violations in transactions are collected as separate `ERROR` findings.
- Raises: `TypeError` only if `book` is not a `Book` instance (structural precondition).

---

## `validate_transaction`

Function that validates a single journal transaction within the context of a book.

### Signature
```python
def validate_transaction(book: Book, transaction: JournalTransaction) -> ValidationReport:
```

### Parameters
| Name | Type | Req | Semantics |
|:-----|:-----|:----|:----------|
| `book` | `Book` | Y | Provides the known account set |
| `transaction` | `JournalTransaction` | Y | Transaction to validate |

### Constraints
- Return: `ValidationReport`; never raises.
- Validates balance via `validate_transaction_balance`; unknown account codes collected as findings.
- Balance failures are returned as an `ERROR` finding, not raised.

---

## `validate_ftl_resource`

Function that runs FTLLexEngine's six-pass static validation pipeline on an FTL source string.

### Signature
```python
def validate_ftl_resource(
    source: str,
    *,
    known_messages: frozenset[str] | None = None,
    known_terms: frozenset[str] | None = None,
    known_msg_deps: Mapping[str, frozenset[str]] | None = None,
    known_term_deps: Mapping[str, frozenset[str]] | None = None,
) -> ValidationReport:
```

### Parameters
| Name | Type | Req | Semantics |
|:-----|:-----|:----|:----------|
| `source` | `str` | Y | Raw FTL source text |
| `known_messages` | `frozenset[str] \| None` | N | Message IDs already in bundle for cross-resource checks |
| `known_terms` | `frozenset[str] \| None` | N | Term IDs already in bundle |
| `known_msg_deps` | `Mapping[...] \| None` | N | Existing message dependency maps |
| `known_term_deps` | `Mapping[...] \| None` | N | Existing term dependency maps |

### Constraints
- Return: `ValidationReport`; delegates to `ftllexengine.validation.validate_resource`.
- Covers all six passes: syntax, structural duplicates, undefined refs, circular refs, chain depth, semantic compliance.
- Can be used independently of a `FluentBundle` instance; suitable for CI/CD pipelines.

---

## `validate_legislative_transaction`

Function that validates a posted transaction against its book's configured legislative pack.

### Signature
```python
def validate_legislative_transaction(
    registry: LegislativePackRegistry,
    book: Book,
    transaction: JournalTransaction,
) -> ValidationReport:
```

### Parameters
| Name | Type | Req | Semantics |
|:-----|:-----|:----|:----------|
| `registry` | `LegislativePackRegistry` | Y | Pack registry used to resolve the book's pack code |
| `book` | `Book` | Y | Supplies `book.legislative_pack` |
| `transaction` | `JournalTransaction` | Y | Transaction to validate |

### Constraints
- Return: `ValidationReport`; legislative issues map to `ERROR` findings with `source = "legislation.<pack_code>"`.
- Raises: `KeyError` when `book.legislative_pack` is not registered.
- Runs in-process (not isolated); for subinterpreter isolation use `FinestVXService.validate_transaction_isolated`.
