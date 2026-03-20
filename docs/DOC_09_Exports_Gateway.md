---
afad: "3.3"
version: "0.10.0"
domain: SECONDARY
updated: "2026-03-19"
route:
  keywords: [export artifact, ledger exporter, runtime config, ledger runtime, posted transaction result, service facade, gateway debug snapshot, runtime debug snapshot, interpreter pool, clear caches, localization boot, create reversal, post reversal, iter audit log pages, audit log streaming, book from saft, saft import, multi book runtime, multi book runtime config, read replica, open read replica]
  questions: ["how does LedgerRuntime work now?", "what does FinestVXService return on writes?", "what runtime debug data is available?", "how are artifacts exported?", "what is PostedTransactionResult?", "how do I reverse a posted transaction?", "how do I stream the audit log from the service?", "how do I import a SAF-T file?", "how do I manage multiple books?", "what is MultiBookRuntime?", "how do I open a read replica from the service?"]
---

# FinestVX Export and Gateway Reference

---

## `ExportArtifact`

Immutable named binary artifact produced by `LedgerExporter`.

### Signature
```python
@dataclass(frozen=True, slots=True)
class ExportArtifact:
    format_name: str
    media_type: str
    content: bytes
```

### Constraints
- `format_name` is one of `"json"`, `"csv"`, `"xml"`, `"pdf"`.
- `content` is deterministic for identical `Book` inputs.

---

## `LedgerExporter`

Exporter that produces deterministic JSON, CSV, XML, and PDF artifacts from a `Book`.

### Signature
```python
class LedgerExporter:
    def __init__(self) -> None: ...
    def to_json(self, book: Book) -> ExportArtifact: ...
    def to_csv(self, book: Book) -> ExportArtifact: ...
    def to_xml(self, book: Book) -> ExportArtifact: ...
    def validate_xml(self, content: bytes) -> None: ...
    def to_pdf(self, book: Book) -> ExportArtifact: ...
```

### Constraints
- `to_json()` uses stable key ordering and compact UTF-8 output.
- `to_xml()` validates against the bundled XSD.
- `to_pdf()` uses deterministic ReportLab settings.

---

## `book_from_saft`

Imports a FinestVX SAF-T XML file and returns the corresponding `Book` aggregate.

### Signature
```python
def book_from_saft(path: Path | str) -> Book:
```

### Parameters
| Name | Type | Req | Semantics |
|:-----|:-----|:----|:----------|
| `path` | `Path \| str` | Y | Filesystem path to the SAF-T XML file |

### Constraints
- Validates the file against the bundled `ledger.xsd` schema before any domain parsing.
- Raises `PersistenceIntegrityError` (from `ftllexengine.integrity`) on XML parse failure, schema violation, or domain invariant violation (e.g. invalid currency code, unknown enum value).
- Symmetric with `LedgerExporter.to_xml()`; the roundtrip `book_from_saft(exporter.to_xml(book).write(...))` reconstructs an equivalent `Book`.
- Does not write to any store; callers must persist the returned `Book` separately.

---

## `RuntimeConfig`

Immutable configuration for the `LedgerRuntime`.

### Signature
```python
@dataclass(frozen=True, slots=True)
class RuntimeConfig:
    persistence: PersistenceConfig
    read_lock_timeout: float | None = 5.0
    write_lock_timeout: float | None = 5.0
    queue_timeout: float = 5.0
    poll_interval: float = 0.1
    legislative_interpreter_pool_min_size: int = 2
    legislative_interpreter_pool_max_size: int = 8
```

### Constraints
- `queue_timeout` and `poll_interval` must be positive.
- Public runtime methods acquire `RWLock.read(timeout=read_lock_timeout)` as a lifecycle gate.
- `close()` acquires `RWLock.write(timeout=write_lock_timeout)` for exclusive shutdown.
- `legislative_interpreter_pool_min_size` and `legislative_interpreter_pool_max_size` configure the
  `InterpreterPool` used by `LegislativeInterpreterRunner`; both must be positive integers with
  `min_size <= max_size`.

---

## `RuntimeDebugSnapshot`

Immutable runtime snapshot for production introspection.

### Signature
```python
@dataclass(frozen=True, slots=True)
class RuntimeDebugSnapshot:
    started: bool
    writer_thread_name: str
    writer_thread_alive: bool
    queue_size: int
    reader_count: int
    writer_active: bool
    writers_waiting: int
    store: StoreDebugSnapshot
```

### Constraints
- `reader_count`, `writer_active`, and `writers_waiting` describe the lifecycle `RWLock`.
- `queue_size` is the pending writer-command count.
- `store` embeds the full persistence-layer telemetry snapshot.

---

## `LedgerRuntime`

Single-writer runtime that queues mutations and serves reads from the store reader pool.

### Signature
```python
class LedgerRuntime:
    def __init__(self, config: RuntimeConfig) -> None: ...
    def __enter__(self) -> LedgerRuntime: ...
    def __exit__(self, ...) -> None: ...
    def start(self) -> None: ...
    def close(self) -> None: ...
    def create_book(self, book: Book, *, audit_context: AuditContext) -> StoreWriteReceipt: ...
    def append_transaction(self, book_code: str, transaction: JournalTransaction, *, audit_context: AuditContext) -> StoreWriteReceipt: ...
    def create_reversal(self, book_code: str, original_ref: str, reversal_ref: str, *, audit_context: AuditContext) -> StoreWriteReceipt: ...
    def append_legislative_result(self, book_code: str, transaction_reference: str, result: LegislativeValidationResult, *, audit_context: AuditContext) -> StoreWriteReceipt: ...
    def get_book_snapshot(self, book_code: str) -> Book: ...
    def list_book_codes(self) -> tuple[str, ...]: ...
    def iter_audit_log(self, *, limit: int | None = None) -> tuple[AuditLogRecord, ...]: ...
    def iter_audit_log_pages(self, *, page_size: int = 500, start_seq: int = 0) -> Iterator[tuple[AuditLogRecord, ...]]: ...
    def create_snapshot(self, output_path: Path | str, *, compress: bool = True) -> DatabaseSnapshot: ...
    def debug_snapshot(self) -> RuntimeDebugSnapshot: ...
```

### Constraints
- Constructor creates `SqliteLedgerStore`, `RWLock`, `Queue`, and starts the writer thread.
- Write methods enqueue typed command dataclasses and return `StoreWriteReceipt`.
- Read methods use `SqliteLedgerStore` read-only connections while holding only the lifecycle read lock.
- `create_snapshot()` is also queued to the writer thread; it is not a direct caller-side write lock.
- `close()` stops the writer thread, joins it, and closes the store.
- `create_reversal()` enqueues a `_CreateReversalCommand` on the writer thread. Error semantics mirror `SqliteLedgerStore.append_reversal()`.
- `iter_audit_log_pages()` delegates directly to `SqliteLedgerStore.iter_audit_log_pages()`; page semantics are identical.

---

## `MultiBookRuntimeConfig`

Immutable configuration for the `MultiBookRuntime`.

### Signature
```python
@dataclass(frozen=True, slots=True)
class MultiBookRuntimeConfig:
    data_directory: Path | str
    persistence_template: PersistenceConfig
    queue_timeout: float = 5.0
    poll_interval: float = 0.1
    read_lock_timeout: float | None = 5.0
    write_lock_timeout: float | None = 5.0
    legislative_interpreter_pool_min_size: int = 2
    legislative_interpreter_pool_max_size: int = 8
```

### Constraints
- `data_directory` is normalized to `Path`; created on first `create_book()` call.
- `queue_timeout` and `poll_interval` must be positive.
- `persistence_template` provides all `PersistenceConfig` defaults; `database_path` is overridden to `data_directory / f"{book_code}.sqlite3"` per opened book.

---

## `MultiBookDebugSnapshot`

Immutable non-invasive snapshot of all open book runtimes in a `MultiBookRuntime`.

### Signature
```python
@dataclass(frozen=True, slots=True)
class MultiBookDebugSnapshot:
    data_directory: Path
    open_book_count: int
    books: tuple[tuple[str, RuntimeDebugSnapshot], ...]
```

### Constraints
- Each `books` element is a `(book_code, RuntimeDebugSnapshot)` pair.
- `books` is sorted by `book_code`.
- Captured under the multi-book `RWLock.read()`.

---

## `MultiBookRuntime`

Per-book isolated runtime managing a pool of `LedgerRuntime` instances, one per SQLite file.

### Signature
```python
class MultiBookRuntime:
    def __init__(self, config: MultiBookRuntimeConfig) -> None: ...
    def __enter__(self) -> MultiBookRuntime: ...
    def __exit__(self, ...) -> None: ...
    def create_book(self, book: Book, *, audit_context: AuditContext) -> StoreWriteReceipt: ...
    def open_book(self, book_code: str) -> None: ...
    def close_book(self, book_code: str) -> None: ...
    def list_book_codes(self) -> tuple[str, ...]: ...
    def list_available_book_codes(self) -> tuple[str, ...]: ...
    def append_transaction(self, book_code: str, transaction: JournalTransaction, *, audit_context: AuditContext) -> StoreWriteReceipt: ...
    def create_reversal(self, book_code: str, original_ref: str, reversal_ref: str, *, audit_context: AuditContext) -> StoreWriteReceipt: ...
    def append_legislative_result(self, book_code: str, transaction_reference: str, result: LegislativeValidationResult, *, audit_context: AuditContext) -> StoreWriteReceipt: ...
    def get_book(self, book_code: str) -> Book: ...
    def iter_audit_log(self, book_code: str, *, limit: int | None = None) -> tuple[AuditLogRecord, ...]: ...
    def iter_audit_log_pages(self, book_code: str, *, page_size: int = 500, start_seq: int = 0) -> Iterator[tuple[AuditLogRecord, ...]]: ...
    def create_snapshot(self, book_code: str, output_path: Path | str, *, compress: bool = True) -> DatabaseSnapshot: ...
    def debug_snapshot(self) -> MultiBookDebugSnapshot: ...
    def close(self) -> None: ...
```

### Constraints
- Each book occupies its own SQLite file: `data_directory / f"{book_code}.sqlite3"`.
- The open-book dict is guarded by a single `RWLock`; structural mutations (`create_book`, `open_book`, `close_book`, `close`) hold the write lock.
- Write serialization is per-book; each open `LedgerRuntime` has its own dedicated writer thread.
- `create_book()` creates `data_directory` if absent, instantiates a `LedgerRuntime`, persists the book, then stores the runtime. Raises `ValueError` if the code is already open.
- `open_book()` raises `KeyError` if no `.sqlite3` file exists for `book_code`; is a no-op if the book is already open.
- `close_book()` is a no-op if `book_code` is not open; calls `runtime.close()` outside the write lock to avoid blocking readers.
- `list_book_codes()` returns sorted codes of currently open books.
- `list_available_book_codes()` scans `.sqlite3` files in `data_directory`; returns an empty tuple if the directory does not exist.
- All per-book routing methods (`append_transaction`, `create_reversal`, etc.) raise `KeyError("No open book: ...")` if `book_code` is not currently open.
- `close()` atomically drains the open-book dict under the write lock and then shuts down all runtimes outside the lock.
- Implements the context-manager protocol: `with MultiBookRuntime(config) as runtime:` calls `close()` on exit.

---

## `FinestVXServiceConfig`

Immutable configuration for the `FinestVXService` facade.

### Signature
```python
@dataclass(frozen=True, slots=True)
class FinestVXServiceConfig:
    runtime: RuntimeConfig
```

### Constraints
- `runtime` is required and drives the underlying `LedgerRuntime`.

---

## `GatewayDebugSnapshot`

Immutable service-level debug snapshot combining runtime state and pack registry info.

### Signature
```python
@dataclass(frozen=True, slots=True)
class GatewayDebugSnapshot:
    runtime: RuntimeDebugSnapshot
    registered_pack_codes: tuple[str, ...]
```

### Constraints
- `runtime` is the embedded runtime snapshot.
- `registered_pack_codes` comes from `LegislativePackRegistry.available_pack_codes()`.

---

## `PostedTransactionResult`

Immutable service-level write result for one posted transaction.

### Signature
```python
@dataclass(frozen=True, slots=True)
class PostedTransactionResult:
    ledger_write: StoreWriteReceipt
    legislative_result: LegislativeValidationResult
    legislative_write: StoreWriteReceipt
```

### Constraints
- `ledger_write` is the receipt for the transaction insert.
- `legislative_result` is the validation result produced after the ledger write committed.
- `legislative_write` is the receipt for the follow-up audit-log insert.

---

## `FinestVXService`

High-level orchestration facade for persistence, validation, legislation, and export.

### Signature
```python
@dataclass(slots=True)
class FinestVXService:
    config: FinestVXServiceConfig
    registry: LegislativePackRegistry  # default_factory=create_default_pack_registry
    exporter: LedgerExporter  # default_factory=LedgerExporter
    interpreter_runner: LegislativeInterpreterRunner  # init=False; constructed from config pool-size settings

    def __enter__(self) -> FinestVXService: ...
    def __exit__(self, *args: object) -> None: ...
    def close(self) -> None: ...
    def create_book(self, book: Book, *, audit_context: AuditContext) -> StoreWriteReceipt: ...
    def post_transaction(self, book_code: str, transaction: JournalTransaction, *, audit_context: AuditContext) -> PostedTransactionResult: ...
    def post_reversal(self, book_code: str, original_ref: str, *, reversal_ref: str, audit_context: AuditContext) -> PostedTransactionResult: ...
    def get_book(self, book_code: str) -> Book: ...
    def list_book_codes(self) -> tuple[str, ...]: ...
    def validate_transaction(self, book_code: str, transaction: JournalTransaction) -> ValidationReport: ...
    def validate_transaction_isolated(self, book_code: str, transaction: JournalTransaction) -> ValidationReport: ...
    def export_book(self, book_code: str, format_name: Literal["json", "csv", "xml", "pdf"]) -> ExportArtifact: ...
    def create_snapshot(self, output_path: Path | str, *, compress: bool = True) -> DatabaseSnapshot: ...
    def iter_audit_log_pages(self, *, page_size: int = 500, start_seq: int = 0) -> Iterator[tuple[AuditLogRecord, ...]]: ...
    def get_pack_localization(self, pack_code: str) -> tuple[FluentLocalization, LoadSummary]: ...
    def clear_caches(self, components: frozenset[str] | None = None) -> None: ...
    async def open_read_replica(self, config: ReadReplicaConfig) -> ReadReplica: ...
    def debug_snapshot(self) -> GatewayDebugSnapshot: ...
```

### Constraints
- `create_book()` forwards the runtime receipt from the queued writer thread.
- `post_transaction()` persists the transaction, runs legislative validation, then appends the legislative audit row and returns `PostedTransactionResult`.
- `post_reversal()` calls `LedgerRuntime.create_reversal()`, loads the resulting book snapshot, runs isolated legislative validation on the reversal transaction, appends the legislative audit row, and returns `PostedTransactionResult`. Error semantics for unknown books, missing originals, double-reversals, and duplicate reversal references mirror `SqliteLedgerStore.append_reversal()`.
- `validate_transaction()` combines core validation with in-process legislative validation.
- `validate_transaction_isolated()` combines core validation with subinterpreter legislative validation.
- `export_book()` delegates to `LedgerExporter`.
- `iter_audit_log_pages()` delegates to `LedgerRuntime.iter_audit_log_pages()`; page semantics are identical to `SqliteLedgerStore.iter_audit_log_pages()`.
- `get_pack_localization()` boots the pack and returns `(FluentLocalization, LoadSummary)`; calls
  `pack.configure_localization(l10n)` immediately after boot to register pack-specific custom Fluent functions.
- `clear_caches(components=None)` forwards to `ftllexengine.clear_module_caches(components=components)`;
  pass a `frozenset[str]` of component names (e.g., `frozenset({"introspection.iso"})`) to clear selectively.
- `open_read_replica(config)` lazily imports and opens a `ReadReplica` for the service's underlying database; the caller must call `ReadReplica.close()` when the replica is no longer needed.
- `close()` must be called to release runtime and interpreter pool resources.
- Implements the context-manager protocol: `with FinestVXService(...) as svc:` calls `close()` on exit; prefer this over explicit `try/finally`.
