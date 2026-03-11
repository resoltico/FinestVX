---
afad: "3.3"
version: "0.1.0"
domain: SECONDARY
updated: "2026-03-09"
route:
  keywords: [export artifact, ledger exporter, json csv xml pdf, runtime config, ledger runtime, runtime debug snapshot, service facade, finestvx service, service config, gateway debug snapshot, post transaction, legislative audit]
  questions: ["how are finestvx artifacts exported?", "what does the service facade do?", "how does runtime orchestration work?", "what debug snapshots exist?", "how are legislative results audited after posting?", "what is RuntimeConfig?"]
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
- `format_name`: one of `"json"`, `"csv"`, `"xml"`, `"pdf"`.
- `media_type`: MIME type string (`"application/json"`, `"text/csv"`, `"application/xml"`, `"application/pdf"`).
- `content`: deterministic bytes; same inputs always produce identical output.

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
- Constructor: compiles the bundled `ledger.xsd` once; raises if schema file is missing.
- `to_json`: stable key ordering, compact separators, UTF-8.
- `to_csv`: deterministic row order following transaction and entry insertion order.
- `to_xml`: validated against the bundled XSD; raises `lxml.etree.DocumentInvalid` on violation.
- `validate_xml`: re-validates raw XML bytes against the same XSD.
- `to_pdf`: uses ReportLab `invariant=1` and `pageCompression=0` for deterministic output.

---

## `RuntimeConfig`

Immutable configuration for the single-writer `LedgerRuntime`.

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
- `read_lock_timeout` / `write_lock_timeout`: passed to `RWLock.read()` / `RWLock.write()`; `None` means no timeout.
- Explicit timeouts on all acquisition paths prevent indefinite stalls.

---

## `RuntimeDebugSnapshot`

Immutable non-invasive runtime snapshot for production introspection.

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
- `reader_count`, `writer_active`, `writers_waiting`: live `RWLock` observability fields.
- `queue_size`: number of pending write commands at snapshot time.
- `store`: embedded `StoreDebugSnapshot` from the underlying `SqliteLedgerStore`.

---

## `LedgerRuntime`

Single-writer, multi-reader runtime coordinating all store access via a dedicated write thread and `RWLock`.

### Signature
```python
class LedgerRuntime:
    def __init__(self, config: RuntimeConfig) -> None: ...
    def __enter__(self) -> LedgerRuntime: ...
    def __exit__(self, ...) -> None: ...
    def start(self) -> None: ...
    def close(self) -> None: ...
    def create_book(self, book: Book, *, audit_context: AuditContext) -> None: ...
    def append_transaction(self, book_code: str, transaction: JournalTransaction, *, audit_context: AuditContext) -> None: ...
    def append_legislative_result(self, book_code: str, transaction_reference: str, result: LegislativeValidationResult, *, audit_context: AuditContext) -> None: ...
    def get_book_snapshot(self, book_code: str) -> Book: ...
    def list_book_codes(self) -> tuple[str, ...]: ...
    def iter_audit_log(self, *, limit: int | None = None) -> tuple[AuditLogRecord, ...]: ...
    def create_snapshot(self, output_path: Path | str, *, compress: bool = True) -> DatabaseSnapshot: ...
    def debug_snapshot(self) -> RuntimeDebugSnapshot: ...
```

### Constraints
- Constructor: creates `SqliteLedgerStore`, `RWLock`, `Queue`, and calls `start()`.
- `start()`: starts the background write thread; no-op if already started.
- Supports context-manager protocol (`with LedgerRuntime(config) as runtime:`).
- Write methods (`create_book`, `append_transaction`, `append_legislative_result`): submitted via `Queue`; block until the write thread completes or `queue_timeout` expires.
- Read methods (`get_book_snapshot`, `list_book_codes`, `iter_audit_log`, `debug_snapshot`): acquire `RWLock.read` with `read_lock_timeout`.
- `create_snapshot`: acquires `RWLock.write` for the duration.
- `close`: signals the write thread to stop, joins it, closes the store.

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
- `runtime`: embedded `RuntimeDebugSnapshot`.
- `registered_pack_codes`: sorted tuple from `LegislativePackRegistry.available_pack_codes()`.

---

## `FinestVXService`

High-level orchestration facade coordinating persistence, validation, legislation, and export.

### Signature
```python
@dataclass(slots=True)
class FinestVXService:
    config: FinestVXServiceConfig
    registry: LegislativePackRegistry  # default: create_default_pack_registry()
    exporter: LedgerExporter  # default: LedgerExporter()
    interpreter_runner: LegislativeInterpreterRunner  # default: LegislativeInterpreterRunner()

    def close(self) -> None: ...
    def create_book(self, book: Book, *, audit_context: AuditContext) -> None: ...
    def post_transaction(self, book_code: str, transaction: JournalTransaction, *, audit_context: AuditContext) -> None: ...
    def get_book(self, book_code: str) -> Book: ...
    def list_book_codes(self) -> tuple[str, ...]: ...
    def validate_transaction(self, book_code: str, transaction: JournalTransaction) -> ValidationReport: ...
    def validate_transaction_isolated(self, book_code: str, transaction: JournalTransaction) -> ValidationReport: ...
    def export_book(self, book_code: str, format_name: Literal["json","csv","xml","pdf"]) -> ExportArtifact: ...
    def create_snapshot(self, output_path: Path | str, *, compress: bool = True) -> DatabaseSnapshot: ...
    def get_pack_localization(self, pack_code: str) -> LocalizationService: ...
    def debug_snapshot(self) -> GatewayDebugSnapshot: ...
```

### Constraints
- Constructor (`__post_init__`): creates and starts `LedgerRuntime`.
- `post_transaction`: persists transaction first, then runs isolated legislative validation, then appends the result to `audit_log` as `table_name == "legislative_validation"`.
- `validate_transaction`: combines core validation and in-process legislative validation.
- `validate_transaction_isolated`: combines core validation and subinterpreter legislative validation.
- `export_book`: delegates to `LedgerExporter`; format must be one of the four supported values.
- `get_pack_localization`: raises `KeyError` for unknown pack codes.
- `close`: must be called (or use as context manager) to release runtime resources.
