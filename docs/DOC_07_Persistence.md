---
afad: "3.3"
version: "0.10.0"
domain: SECONDARY
updated: "2026-03-19"
route:
  keywords: [persistence, apsw, sqlite wal, reader pool, async reader, changeset, patchset, reserve bytes, store debug snapshot, wal hook, append reversal, reversal, audit log pages, iter audit log pages, read replica, read replica config, wal snapshot, checkpoint interval]
  questions: ["how does finestvx persistence work now?", "what does SqliteLedgerStore return on writes?", "how are APSW readers configured?", "what telemetry does the store expose?", "how do async reads work?", "how are reserve bytes enforced?", "how do I reverse a transaction?", "how do I stream the audit log?", "what is ReadReplica?", "how do I open a read-only connection?", "how do I configure a read replica?"]
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
- `session_id` is optional; it is copied into SQL-trigger audit rows.
- Passed as `audit_context=` to all store and runtime write methods.

---

## `PersistenceConfig`

Immutable configuration for the APSW-backed SQLite persistence boundary.

### Signature
```python
@dataclass(frozen=True, slots=True)
class PersistenceConfig:
    database_path: Path | str
    busy_timeout_ms: int = 5000
    transaction_mode: str = "IMMEDIATE"
    wal_auto_checkpoint: int = 1000
    reader_connection_count: int = 4
    reader_checkout_timeout: float = 5.0
    writer_statement_cache_size: int = 256
    reader_statement_cache_size: int = 128
    reserve_bytes: int = 0
    telemetry_buffer_size: int = 0
    vfs_name: str | None = None
    cache_config: CacheConfig = MANDATED_CACHE_CONFIG
```

### Constraints
- `database_path` is normalized to `Path`.
- `busy_timeout_ms`, `wal_auto_checkpoint`, `reader_connection_count`, and `reader_checkout_timeout` must be positive.
- `transaction_mode` must be `"DEFERRED"`, `"IMMEDIATE"`, or `"EXCLUSIVE"`.
- `writer_statement_cache_size`, `reader_statement_cache_size`, and `telemetry_buffer_size` must be non-negative.
- `reserve_bytes` must be between `0` and `255`.
- Existing databases with a different `reserve_bytes` value fail fast; no migration path exists.
- `vfs_name` is optional; blank strings are rejected.

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
- Enforces write-once cache semantics and hard-fail checksum integrity.
- Used as the default `PersistenceConfig.cache_config`.

---

## `DatabaseSnapshot`

Immutable metadata record for a completed database snapshot.

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
- `compressed` is `True` when `compression.zstd` was applied.
- `wal_frames` and `checkpointed_frames` come from APSW `wal_checkpoint()`.
- `bytes_written` is the final output file size.

---

## `AuditLogRecord`

Immutable row from the SQLite `audit_log` table.

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
- `table_name` identifies the audited source table or `"legislative_validation"`.
- `operation` is `"INSERT"` for ledger tables and `"RESULT"` for legislative audit rows.
- `row_signature` is the BLAKE2b-128 digest of `row_payload`.

---

## `StoreStatementCacheStats`

Immutable APSW statement-cache counter snapshot.

### Signature
```python
@dataclass(frozen=True, slots=True)
class StoreStatementCacheStats:
    size: int
    evictions: int
    no_cache: int
    hits: int
    misses: int
    no_vdbe: int
    too_big: int
    max_cacheable_bytes: int
```

### Constraints
- Built from `apsw.Connection.cache_stats()`.
- Exposes cache capacity, hit/miss counters, and non-cacheable statement counts.

---

## `StoreStatusCounter`

Immutable APSW connection-status measurement.

### Signature
```python
@dataclass(frozen=True, slots=True)
class StoreStatusCounter:
    name: str
    current: int
    highwater: int
```

### Constraints
- `name` is one of the store-selected APSW status counters such as cache usage or statement memory.
- `current` and `highwater` come from `apsw.Connection.status(...)`.

---

## `StoreConnectionDebugSnapshot`

Immutable telemetry snapshot for one APSW connection.

### Signature
```python
@dataclass(frozen=True, slots=True)
class StoreConnectionDebugSnapshot:
    label: str
    readonly: bool
    data_version: int
    statement_cache: StoreStatementCacheStats
    status_counters: tuple[StoreStatusCounter, ...]
```

### Constraints
- `label` identifies the writer or one pooled reader.
- `readonly` comes from `apsw.Connection.readonly("main")`.
- `data_version` comes from APSW `data_version()` and changes on local or external writes.

---

## `StoreWalCommit`

Immutable last-observed WAL commit event from the writer connection.

### Signature
```python
@dataclass(frozen=True, slots=True)
class StoreWalCommit:
    database_name: str
    pages_in_wal: int
```

### Constraints
- Populated from APSW `set_wal_hook(...)`.
- `database_name` is usually `"main"` for the FinestVX ledger.

---

## `StoreTraceEvent`

Immutable bounded SQL trace event captured from APSW.

### Signature
```python
@dataclass(frozen=True, slots=True)
class StoreTraceEvent:
    connection_label: str
    code: str
    statement_id: int | None
    sql: str | None
    trigger: bool
    total_changes: int | None
```

### Constraints
- Emitted only when `PersistenceConfig.telemetry_buffer_size > 0`.
- `code` is a symbolic APSW trace code such as `SQLITE_TRACE_STMT`.
- `trigger` distinguishes trigger SQL from top-level statements.

---

## `StoreProfileEvent`

Immutable bounded SQL profile event captured from APSW.

### Signature
```python
@dataclass(frozen=True, slots=True)
class StoreProfileEvent:
    connection_label: str
    sql: str
    nanoseconds: int
```

### Constraints
- Emitted only when `PersistenceConfig.telemetry_buffer_size > 0`.
- Built from APSW `set_profile(...)`.

---

## `StoreWriteReceipt`

Immutable APSW changeset receipt for one committed write operation.

### Signature
```python
@dataclass(frozen=True, slots=True)
class StoreWriteReceipt:
    data_version: int
    changed_tables: tuple[str, ...]
    change_count: int
    indirect_change_count: int
    changeset: bytes
    patchset: bytes
    changeset_size_bytes: int
    patchset_size_bytes: int
    memory_used_bytes: int
    last_wal_commit: StoreWalCommit | None
```

### Constraints
- Returned by all mutating `SqliteLedgerStore` methods.
- `changeset` and `patchset` come from APSW `Session`.
- `indirect_change_count` includes trigger-generated rows such as `audit_log` inserts.
- `last_wal_commit` is `None` only when SQLite did not emit a WAL hook event for that write.

---

## `StoreDebugSnapshot`

Immutable non-invasive store snapshot combining counts and APSW telemetry.

### Signature
```python
@dataclass(frozen=True, slots=True)
class StoreDebugSnapshot:
    database_path: Path
    reserve_bytes: int
    book_count: int
    transaction_count: int
    entry_count: int
    audit_row_count: int
    writer: StoreConnectionDebugSnapshot
    readers: tuple[StoreConnectionDebugSnapshot, ...]
    last_wal_commit: StoreWalCommit | None
    recent_trace_events: tuple[StoreTraceEvent, ...]
    recent_profile_events: tuple[StoreProfileEvent, ...]
```

### Constraints
- Counts come from live read-only queries.
- `writer` is collected under the internal writer lock.
- `readers` contains one entry per pooled read-only connection.
- `recent_trace_events` and `recent_profile_events` are bounded by `telemetry_buffer_size`.

---

## `AsyncLedgerReader`

Async read-only APSW facade over the FinestVX persistence store.

### Signature
```python
class AsyncLedgerReader:
    @classmethod
    async def open(cls, config: PersistenceConfig) -> AsyncLedgerReader: ...
    async def list_book_codes(self) -> tuple[str, ...]: ...
    async def load_book(self, book_code: str) -> Book: ...
    async def iter_audit_log(self, *, limit: int | None = None) -> tuple[AuditLogRecord, ...]: ...
    async def iter_audit_log_pages(self, *, page_size: int = 500, start_seq: int = 0) -> AsyncIterator[tuple[AuditLogRecord, ...]]: ...
    async def debug_snapshot(self) -> StoreConnectionDebugSnapshot: ...
    def close(self) -> None: ...
```

### Constraints
- Opens APSW `as_async(...)` with `SQLITE_OPEN_READONLY`.
- Enforces `reserve_bytes` and read-only invariants at open time.
- Exposes the same immutable read model as the synchronous reader pool.
- `iter_audit_log_pages()` is an async generator; pages are `tuple[AuditLogRecord, ...]`, each at most `page_size` records.
- `start_seq` skips all rows with `seq <= start_seq`; useful for resumable streaming from a known cursor position.

---

## `SqliteLedgerStore`

APSW-backed append-only ledger store with one writer connection and a read-only reader pool.

### Signature
```python
class SqliteLedgerStore:
    def __init__(self, config: PersistenceConfig) -> None: ...
    @property
    def database_path(self) -> Path: ...
    def create_book(self, book: Book, *, audit_context: AuditContext) -> StoreWriteReceipt: ...
    def append_transaction(self, book_code: str, transaction: JournalTransaction, *, audit_context: AuditContext) -> StoreWriteReceipt: ...
    def append_reversal(self, book_code: str, original_ref: str, reversal_ref: str, *, audit_context: AuditContext) -> StoreWriteReceipt: ...
    def append_legislative_result(self, book_code: str, transaction_reference: str, result: LegislativeValidationResult, *, audit_context: AuditContext) -> StoreWriteReceipt: ...
    def load_book(self, book_code: str) -> Book: ...
    def list_book_codes(self) -> tuple[str, ...]: ...
    def export_book_payload(self, book_code: str) -> dict[str, object]: ...
    def iter_audit_log(self, *, limit: int | None = None) -> tuple[AuditLogRecord, ...]: ...
    def iter_audit_log_pages(self, *, page_size: int = 500, start_seq: int = 0) -> Iterator[tuple[AuditLogRecord, ...]]: ...
    def create_snapshot(self, output_path: Path | str, *, compress: bool = True) -> DatabaseSnapshot: ...
    async def open_async_reader(self) -> AsyncLedgerReader: ...
    def debug_snapshot(self) -> StoreDebugSnapshot: ...
    def close(self) -> None: ...
```

### Constraints
- Writer connection: APSW `transaction_mode`, `set_busy_timeout()`, DQS hardening, WAL pragmas, reserve-bytes enforcement, SQL audit functions, WAL hook.
- Reader pool: `reader_connection_count` read-only APSW connections; checkout waits at most `reader_checkout_timeout`.
- Write methods return `StoreWriteReceipt`; the raw `execute()` escape hatch does not exist.
- `create_snapshot()` runs on the writer connection after WAL checkpoint truncation.
- `load_book()` raises `KeyError` for unknown `book_code`.
- `load_book()` raises `LedgerInvariantError` (`ftllexengine.integrity`) when a loaded book fails an accounting invariant (unbalanced posted transaction, duplicate account code); indicates storage corruption or a write-path bug.
- `load_book()` raises `PersistenceIntegrityError` (`ftllexengine.integrity`) when deserialization produces a value that cannot satisfy domain model invariants (unknown currency code, precision violation); indicates schema migration gap or storage tampering.
- Both integrity exceptions carry `IntegrityContext` for structured audit trail correlation.
- Direct reads can run concurrently with writes; writer operations remain serialized by the internal writer lock.
- `append_reversal()` atomically loads `original_ref`, inverts all entry sides (DEBIT↔CREDIT), sets `reversal_of=original_ref` on the new transaction, and writes it in a single SQLite transaction. Raises `KeyError` for unknown `book_code`, `ValueError("not found")` when `original_ref` does not exist, `ValueError("already reversed")` when `original_ref` is already marked reversed, and `ValueError("already in use")` when `reversal_ref` duplicates an existing transaction reference.
- `iter_audit_log_pages()` is a synchronous generator yielding pages of `tuple[AuditLogRecord, ...]`; each page is at most `page_size` records. Uses `WHERE seq > ? ORDER BY seq LIMIT ?` cursor pagination — never materializes the full result set. `start_seq` resumes from a known cursor position.

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
| `output_path` | `Path \| str` | Y | Destination path |
| `compress` | `bool` | N | zstd when `True` |

### Constraints
- Return: `DatabaseSnapshot` with final byte count and WAL statistics.
- Delegates to `store.create_snapshot(...)`.

---

## `ReadReplicaConfig`

Immutable configuration for a periodically refreshed read-only WAL connection.

### Signature
```python
@dataclass(frozen=True, slots=True)
class ReadReplicaConfig:
    database_path: Path | str
    checkpoint_interval: float = 1.0
    reader_statement_cache_size: int = 128
    reserve_bytes: int = 0
```

### Constraints
- `database_path` is normalized to `Path`.
- `checkpoint_interval` must be positive; determines how often `ReadReplica` reconnects to release held WAL snapshot frames.
- `reader_statement_cache_size` must be non-negative.
- `reserve_bytes` must be between `0` and `255`; must match the target database's configured value.

---

## `ReadReplica`

Async read-only facade that reconnects its underlying APSW connection periodically so the writer can checkpoint WAL frames.

### Signature
```python
class ReadReplica:
    @classmethod
    async def open(cls, config: ReadReplicaConfig) -> ReadReplica: ...
    async def refresh(self) -> None: ...
    async def list_book_codes(self) -> tuple[str, ...]: ...
    async def load_book(self, book_code: str) -> Book: ...
    async def iter_audit_log(self, *, limit: int | None = None) -> tuple[AuditLogRecord, ...]: ...
    async def iter_audit_log_pages(self, *, page_size: int = 500, start_seq: int = 0) -> AsyncIterator[tuple[AuditLogRecord, ...]]: ...
    def close(self) -> None: ...
```

### Constraints
- `open()` opens an `AsyncLedgerReader` over `config.database_path` and records `time.monotonic()` as the refresh baseline.
- Before each read method, `_maybe_refresh()` checks whether `time.monotonic() - _last_refresh >= checkpoint_interval`; if so, reconnects and resets the baseline.
- `refresh()` forces an immediate reconnect regardless of elapsed time.
- All read methods delegate to the underlying `AsyncLedgerReader` after the refresh check.
- `iter_audit_log_pages()` is an async generator; semantics are identical to `AsyncLedgerReader.iter_audit_log_pages()`.
- `close()` closes the underlying `AsyncLedgerReader`; must be called when the replica is no longer needed.
- Opened via `FinestVXService.open_read_replica(config)` for service-level deployments.

---

## Schema Rules

SQLite schema rules enforced by FinestVX persistence.

### Constraints
- Core tables are `STRICT`.
- `UPDATE` and `DELETE` are rejected on ledger tables by append-only triggers.
- `AFTER INSERT` audit triggers write `audit_log` rows for all core table inserts.
- WAL mode, `foreign_keys=1`, and `synchronous=FULL` are mandatory.
