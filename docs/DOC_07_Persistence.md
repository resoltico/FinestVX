---
afad: "3.3"
version: "0.1.0"
domain: SECONDARY
updated: "2026-03-09"
route:
  keywords: [persistence, apsw, sqlite strict, audit context, audit log record, persistence config, database snapshot, ledger store, store debug snapshot, pep 750, sql templates, zstd backup, cache config]
  questions: ["how does finestvx persistence work?", "what schema rules are enforced?", "how are snapshots created?", "what is the mandated cache config?", "how is the audit trail structured?", "what is AuditLogRecord?"]
---

# FinestVX Persistence Reference

---

## `AuditContext`

Immutable write-context descriptor passed to every ledger mutation.

### Signature
```python
@dataclass(frozen=True, slots=True)
class AuditContext:
    actor: str
    reason: str
    session_id: str | None = None
```

### Constraints
- `actor` and `reason` must be non-empty after stripping whitespace.
- `session_id` is optional; surfaced in audit rows for session-level correlation.
- Passed as `audit_context=` keyword argument to all write methods on `SqliteLedgerStore` and `LedgerRuntime`.

---

## `PersistenceConfig`

Immutable configuration for the APSW-backed SQLite store.

### Signature
```python
@dataclass(frozen=True, slots=True)
class PersistenceConfig:
    database_path: Path | str
    busy_timeout_ms: int = 5000
    transaction_mode: str = "IMMEDIATE"
    wal_auto_checkpoint: int = 1000
    cache_config: CacheConfig = MANDATED_CACHE_CONFIG
```

### Constraints
- `database_path` is normalized to `Path` at construction.
- `busy_timeout_ms` must be positive.
- `transaction_mode` must be one of `"DEFERRED"`, `"IMMEDIATE"`, `"EXCLUSIVE"`.
- `wal_auto_checkpoint` must be positive.
- `cache_config` defaults to `MANDATED_CACHE_CONFIG`.

---

## `MANDATED_CACHE_CONFIG`

Constant defining the FinestVX-mandated FTLLexEngine cache policy.

### Definition
```python
MANDATED_CACHE_CONFIG: CacheConfig = CacheConfig(
    write_once=True,
    integrity_strict=True,
    enable_audit=True,
    max_audit_entries=50000,
)
```

### Constraints
- Purpose: enforces financial-grade cache semantics: write-once audit, hard-fail on BLAKE2b checksum mismatch, full audit trail.
- Used as the default in `PersistenceConfig.cache_config` and `LocalizationConfig.cache`.

---

## `DatabaseSnapshot`

Immutable metadata record for a completed database snapshot operation.

### Signature
```python
@dataclass(frozen=True, slots=True)
class DatabaseSnapshot:
    output_path: Path
    compressed: bool
    wal_frames: int
    checkpointed_frames: int
    bytes_written: int
```

### Constraints
- `output_path`: destination path of the snapshot file.
- `compressed`: `True` when `compression.zstd` was used.
- `wal_frames` / `checkpointed_frames`: WAL frame counts at checkpoint time.
- `bytes_written`: byte length of the written file.

---

## `AuditLogRecord`

Immutable single row from the `audit_log` SQLite table.

### Signature
```python
@dataclass(frozen=True, slots=True)
class AuditLogRecord:
    seq: int
    table_name: str
    operation: str
    row_pk: str
    actor: str
    reason: str
    session_id: str | None
    monotonic_ms: int
    row_signature: str
    row_payload: str
```

### Constraints
- `seq`: auto-incremented primary key; monotonically increasing.
- `table_name`: the audited table (`"books"`, `"accounts"`, `"transactions"`, `"entries"`, `"legislative_validation"`).
- `operation`: `"INSERT"` for ledger tables; `"RESULT"` for legislative validation rows.
- `row_signature`: BLAKE2b-128 hex digest of `row_payload` JSON.
- `row_payload`: JSON object of the inserted row's columns.
- `monotonic_ms`: `time.monotonic_ns() // 1_000_000` at insertion time.

---

## `StoreDebugSnapshot`

Immutable non-invasive debug snapshot of store-level counters.

### Signature
```python
@dataclass(frozen=True, slots=True)
class StoreDebugSnapshot:
    database_path: Path
    book_count: int
    transaction_count: int
    entry_count: int
    audit_row_count: int
```

### Constraints
- Read-only; does not mutate store state.
- Counts are live SQLite `COUNT(*)` queries at snapshot time.

---

## `SqliteLedgerStore`

APSW-backed append-only ledger store with WAL, STRICT tables, and SQL audit triggers.

### Signature
```python
class SqliteLedgerStore:
    def __init__(self, config: PersistenceConfig) -> None: ...
    @property
    def database_path(self) -> Path: ...
    def create_book(self, book: Book, *, audit_context: AuditContext) -> None: ...
    def append_transaction(self, book_code: str, transaction: JournalTransaction, *, audit_context: AuditContext) -> None: ...
    def load_book(self, book_code: str) -> Book: ...
    def list_book_codes(self) -> tuple[str, ...]: ...
    def iter_audit_log(self, *, limit: int | None = None) -> tuple[AuditLogRecord, ...]: ...
    def append_legislative_result(self, book_code: str, transaction_reference: str, result: LegislativeValidationResult, *, audit_context: AuditContext) -> None: ...
    def execute(self, sql: str, bindings: Iterable[SQLiteBinding] = ()) -> apsw.Cursor: ...
    def create_snapshot(self, output_path: Path | str, *, compress: bool = True) -> DatabaseSnapshot: ...
    def debug_snapshot(self) -> StoreDebugSnapshot: ...
    def close(self) -> None: ...
```

### Constraints
- Constructor: opens the SQLite connection, registers scalar functions, applies WAL pragmas, installs schema and triggers.
- `create_book`: validates chart before inserting; runs inside an APSW transaction.
- `append_transaction`: validates balance and account membership; append-only.
- `load_book`: raises `KeyError` for unknown `book_code`.
- `iter_audit_log`: ordered by `seq`; `limit` caps the row count.
- `database_path`: returns the on-disk `Path` from `config.database_path`.
- `execute(sql, bindings)`: raw SQL escape hatch; returns `apsw.Cursor`; no audit context applied; use only for queries that cannot be expressed through the typed methods.
- `create_snapshot`: WAL-consistent copy via APSW backup API; optionally zstd-compressed.
- Thread: not thread-safe; concurrent access is coordinated by `LedgerRuntime` via `RWLock`.

---

## `create_snapshot`

Function that creates a WAL-consistent snapshot from a `SqliteLedgerStore`.

### Signature
```python
def create_snapshot(
    store: SqliteLedgerStore,
    output_path: Path | str,
    *,
    compress: bool = True,
) -> DatabaseSnapshot:
```

### Parameters
| Name | Type | Req | Semantics |
|:-----|:-----|:----|:----------|
| `store` | `SqliteLedgerStore` | Y | Source store |
| `output_path` | `Path \| str` | Y | Destination file path |
| `compress` | `bool` | N | Use `compression.zstd` when `True` (default) |

### Constraints
- Return: `DatabaseSnapshot` with byte count and WAL statistics.
- Delegates to `store.create_snapshot(output_path, compress=compress)`.

---

## Schema Rules

The SQLite schema enforces:
- `STRICT` typing on all core tables.
- Append-only: `BEFORE UPDATE` and `BEFORE DELETE` triggers raise `ABORT` on all core tables.
- `CHECK` constraints: posting side (`Dr`/`Cr`), non-negative amount text, consistent period columns.
- Audit inserts: `AFTER INSERT` triggers write to `audit_log` for every core table row.

## SQL Template Rendering

`finestvx.persistence.sql.render_sql` renders PEP 750 template strings into validated SQL.

Supported format specs:
- `identifier` — validates and double-quotes a SQLite identifier.
- `literal` — single-quotes a static scalar value.
- `raw` — passes a pre-validated string fragment unchanged.

Used in `schema.py` for append-only trigger generation.
