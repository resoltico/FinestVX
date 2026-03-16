---
afad: "3.3"
version: "0.5.0"
domain: SECONDARY
updated: "2026-03-15"
route:
  keywords: [export artifact, ledger exporter, runtime config, ledger runtime, posted transaction result, service facade, gateway debug snapshot, runtime debug snapshot]
  questions: ["how does LedgerRuntime work now?", "what does FinestVXService return on writes?", "what runtime debug data is available?", "how are artifacts exported?", "what is PostedTransactionResult?"]
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
```

### Constraints
- `queue_timeout` and `poll_interval` must be positive.
- Public runtime methods acquire `RWLock.read(timeout=read_lock_timeout)` as a lifecycle gate.
- `close()` acquires `RWLock.write(timeout=write_lock_timeout)` for exclusive shutdown.

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
    def append_legislative_result(self, book_code: str, transaction_reference: str, result: LegislativeValidationResult, *, audit_context: AuditContext) -> StoreWriteReceipt: ...
    def get_book_snapshot(self, book_code: str) -> Book: ...
    def list_book_codes(self) -> tuple[str, ...]: ...
    def iter_audit_log(self, *, limit: int | None = None) -> tuple[AuditLogRecord, ...]: ...
    def create_snapshot(self, output_path: Path | str, *, compress: bool = True) -> DatabaseSnapshot: ...
    def debug_snapshot(self) -> RuntimeDebugSnapshot: ...
```

### Constraints
- Constructor creates `SqliteLedgerStore`, `RWLock`, `Queue`, and starts the writer thread.
- Write methods enqueue typed command dataclasses and return `StoreWriteReceipt`.
- Read methods use `SqliteLedgerStore` read-only connections while holding only the lifecycle read lock.
- `create_snapshot()` is also queued to the writer thread; it is not a direct caller-side write lock.
- `close()` stops the writer thread, joins it, and closes the store.

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
    registry: LegislativePackRegistry
    exporter: LedgerExporter
    interpreter_runner: LegislativeInterpreterRunner

    def close(self) -> None: ...
    def create_book(self, book: Book, *, audit_context: AuditContext) -> StoreWriteReceipt: ...
    def post_transaction(self, book_code: str, transaction: JournalTransaction, *, audit_context: AuditContext) -> PostedTransactionResult: ...
    def get_book(self, book_code: str) -> Book: ...
    def list_book_codes(self) -> tuple[str, ...]: ...
    def validate_transaction(self, book_code: str, transaction: JournalTransaction) -> ValidationReport: ...
    def validate_transaction_isolated(self, book_code: str, transaction: JournalTransaction) -> ValidationReport: ...
    def export_book(self, book_code: str, format_name: Literal["json", "csv", "xml", "pdf"]) -> ExportArtifact: ...
    def create_snapshot(self, output_path: Path | str, *, compress: bool = True) -> DatabaseSnapshot: ...
    def get_pack_localization(self, pack_code: str) -> FluentLocalization: ...
    def debug_snapshot(self) -> GatewayDebugSnapshot: ...
```

### Constraints
- `create_book()` forwards the runtime receipt from the queued writer thread.
- `post_transaction()` persists the transaction, runs legislative validation, then appends the legislative audit row and returns `PostedTransactionResult`.
- `validate_transaction()` combines core validation with in-process legislative validation.
- `validate_transaction_isolated()` combines core validation with subinterpreter legislative validation.
- `export_book()` delegates to `LedgerExporter`.
- `get_pack_localization()` returns the pack's upstream `FluentLocalization` runtime directly.
- `close()` must be called to release runtime resources.
