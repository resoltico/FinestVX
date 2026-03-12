"""Single-writer, multi-reader runtime coordination for FinestVX."""

from __future__ import annotations

from concurrent.futures import Future
from dataclasses import dataclass
from queue import Empty, Queue
from threading import Event, Thread
from typing import TYPE_CHECKING

from ftllexengine.runtime.rwlock import RWLock

from finestvx.persistence import (
    SqliteLedgerStore,
)

if TYPE_CHECKING:
    from pathlib import Path
    from typing import Self

    from finestvx.core.models import Book, JournalTransaction
    from finestvx.legislation.protocols import LegislativeValidationResult
    from finestvx.persistence import (
        AuditContext,
        DatabaseSnapshot,
        PersistenceConfig,
        StoreDebugSnapshot,
    )
    from finestvx.persistence.store import AuditLogRecord

__all__ = [
    "LedgerRuntime",
    "RuntimeConfig",
    "RuntimeDebugSnapshot",
]


@dataclass(frozen=True, slots=True)
class RuntimeConfig:
    """Timeout and store settings for the FinestVX runtime."""

    persistence: PersistenceConfig
    read_lock_timeout: float | None = 5.0
    write_lock_timeout: float | None = 5.0
    queue_timeout: float = 5.0
    poll_interval: float = 0.1

    def __post_init__(self) -> None:
        """Validate runtime timings."""
        if self.queue_timeout <= 0:
            msg = "queue_timeout must be positive"
            raise ValueError(msg)
        if self.poll_interval <= 0:
            msg = "poll_interval must be positive"
            raise ValueError(msg)


@dataclass(frozen=True, slots=True)
class _CreateBookCommand:
    """Internal queued request for immutable book creation."""

    book: Book
    audit_context: AuditContext
    future: Future[None]


@dataclass(frozen=True, slots=True)
class _AppendTransactionCommand:
    """Internal queued request for a posted transaction append."""

    book_code: str
    transaction: JournalTransaction
    audit_context: AuditContext
    future: Future[None]


@dataclass(frozen=True, slots=True)
class _AppendLegislativeResultCommand:
    """Internal queued request for a legislative audit append."""

    book_code: str
    transaction_reference: str
    result: LegislativeValidationResult
    audit_context: AuditContext
    future: Future[None]


type _WriteCommand = (
    _AppendLegislativeResultCommand | _AppendTransactionCommand | _CreateBookCommand
)


def _require_write_command(command: object) -> _WriteCommand:
    """Validate that a queued object is one of the supported write commands."""
    match command:
        case _CreateBookCommand() | _AppendTransactionCommand() | _AppendLegislativeResultCommand():
            return command
        case _:
            msg = "command must be a supported write command"
            raise TypeError(msg)


@dataclass(frozen=True, slots=True)
class RuntimeDebugSnapshot:
    """Non-invasive runtime snapshot for observability and debugging."""

    started: bool
    writer_thread_name: str
    writer_thread_alive: bool
    queue_size: int
    reader_count: int
    writer_active: bool
    writers_waiting: int
    store: StoreDebugSnapshot


class LedgerRuntime:
    """Dedicated write-thread runtime with RWLock-protected read snapshots."""

    __slots__ = (
        "_config",
        "_lock",
        "_queue",
        "_started",
        "_stop_event",
        "_store",
        "_thread",
    )

    def __init__(self, config: RuntimeConfig) -> None:
        """Create the runtime and start its dedicated write thread."""
        self._config = config
        self._store = SqliteLedgerStore(config.persistence)
        self._lock = RWLock()
        self._queue: Queue[_WriteCommand | None] = Queue()
        self._stop_event = Event()
        self._thread = Thread(
            target=self._writer_loop,
            name="finestvx-write-thread",
            daemon=True,
        )
        self._started = False
        self.start()

    def start(self) -> None:
        """Start the background write thread if it is not already running."""
        if self._started:
            return
        self._thread.start()
        self._started = True

    def close(self) -> None:
        """Stop the write thread and close the persistence store."""
        if not self._started:
            self._store.close()
            return
        self._stop_event.set()
        self._queue.put(None, timeout=self._config.queue_timeout)
        self._thread.join(timeout=self._config.queue_timeout)
        self._store.close()
        self._started = False

    def __enter__(self) -> Self:
        """Enter context-manager scope."""
        return self

    def __exit__(self, exc_type: object, exc: object, traceback: object) -> None:
        """Close the runtime at the end of a context-manager scope."""
        self.close()

    def _dispatch_command(self, command: _WriteCommand) -> None:
        """Execute one write command under the exclusive lock and resolve its Future.

        Catches all exceptions — including unexpected ones — and forwards them to
        the command's Future. This prevents the write thread from dying silently:
        every failure surfaces to the caller via Future.result() rather than
        being swallowed in a background thread.
        """
        try:
            with self._lock.write(timeout=self._config.write_lock_timeout):
                match command:
                    case _CreateBookCommand(book=book, audit_context=audit_context):
                        self._store.create_book(
                            book,
                            audit_context=audit_context,
                        )
                    case _AppendTransactionCommand(
                        book_code=book_code,
                        transaction=transaction,
                        audit_context=audit_context,
                    ):
                        self._store.append_transaction(
                            book_code,
                            transaction,
                            audit_context=audit_context,
                        )
                    case _AppendLegislativeResultCommand(
                        book_code=book_code,
                        transaction_reference=transaction_reference,
                        result=result,
                        audit_context=audit_context,
                    ):
                        self._store.append_legislative_result(
                            book_code,
                            transaction_reference,
                            result,
                            audit_context=audit_context,
                        )
            command.future.set_result(None)
        except Exception as error:
            # Future-based dispatch: any exception from a write operation must become
            # Future.set_exception() so the caller receives it via Future.result(),
            # rather than leaving the write thread dead and the error silently dropped.
            command.future.set_exception(error)

    def _writer_loop(self) -> None:
        """Serialize all write requests through one dedicated thread."""
        while not self._stop_event.is_set() or not self._queue.empty():
            try:
                command = self._queue.get(timeout=self._config.poll_interval)
            except Empty:
                continue
            if command is None:
                continue
            self._dispatch_command(command)

    def _submit(
        self,
        command: object,
    ) -> None:
        """Submit a write request and wait for completion."""
        queued_command = _require_write_command(command)
        self._queue.put(
            queued_command,
            timeout=self._config.queue_timeout,
        )
        queued_command.future.result(
            timeout=self._config.queue_timeout + self._config.poll_interval
        )

    def create_book(self, book: Book, *, audit_context: AuditContext) -> None:
        """Persist a new book through the dedicated write thread."""
        self._submit(
            _CreateBookCommand(
                book=book,
                audit_context=audit_context,
                future=Future(),
            )
        )

    def append_transaction(
        self,
        book_code: str,
        transaction: JournalTransaction,
        *,
        audit_context: AuditContext,
    ) -> None:
        """Append a posted transaction through the dedicated write thread."""
        self._submit(
            _AppendTransactionCommand(
                book_code=book_code,
                transaction=transaction,
                audit_context=audit_context,
                future=Future(),
            )
        )

    def append_legislative_result(
        self,
        book_code: str,
        transaction_reference: str,
        result: LegislativeValidationResult,
        *,
        audit_context: AuditContext,
    ) -> None:
        """Append a post-commit legislative result through the dedicated write thread."""
        self._submit(
            _AppendLegislativeResultCommand(
                book_code=book_code,
                transaction_reference=transaction_reference,
                result=result,
                audit_context=audit_context,
                future=Future(),
            )
        )

    def get_book_snapshot(self, book_code: str) -> Book:
        """Read a complete immutable book snapshot under a shared lock."""
        with self._lock.read(timeout=self._config.read_lock_timeout):
            return self._store.load_book(book_code)

    def list_book_codes(self) -> tuple[str, ...]:
        """List all persisted books under a shared lock."""
        with self._lock.read(timeout=self._config.read_lock_timeout):
            return self._store.list_book_codes()

    def iter_audit_log(self, *, limit: int | None = None) -> tuple[AuditLogRecord, ...]:
        """Read audit log rows under a shared lock."""
        with self._lock.read(timeout=self._config.read_lock_timeout):
            return self._store.iter_audit_log(limit=limit)

    def create_snapshot(
        self,
        output_path: Path | str,
        *,
        compress: bool = True,
    ) -> DatabaseSnapshot:
        """Create a WAL-consistent snapshot under an exclusive write lock."""
        with self._lock.write(timeout=self._config.write_lock_timeout):
            return self._store.create_snapshot(output_path, compress=compress)

    def debug_snapshot(self) -> RuntimeDebugSnapshot:
        """Return a non-invasive runtime snapshot for production introspection."""
        with self._lock.read(timeout=self._config.read_lock_timeout):
            return RuntimeDebugSnapshot(
                started=self._started,
                writer_thread_name=self._thread.name,
                writer_thread_alive=self._thread.is_alive(),
                queue_size=self._queue.qsize(),
                reader_count=self._lock.reader_count,
                writer_active=self._lock.writer_active,
                writers_waiting=self._lock.writers_waiting,
                store=self._store.debug_snapshot(),
            )
