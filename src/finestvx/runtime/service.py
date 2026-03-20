"""Single-writer runtime coordination for FinestVX."""

from __future__ import annotations

from concurrent.futures import Future
from dataclasses import dataclass
from queue import Empty, Queue
from threading import Event, Thread
from typing import TYPE_CHECKING, cast

from ftllexengine import require_positive_int
from ftllexengine.runtime import RWLock

from finestvx.persistence import DatabaseSnapshot, SqliteLedgerStore, StoreWriteReceipt

if TYPE_CHECKING:
    from collections.abc import Iterator
    from pathlib import Path
    from typing import Self

    from finestvx.core.models import Book, JournalTransaction
    from finestvx.legislation.protocols import LegislativeValidationResult
    from finestvx.persistence import (
        AuditContext,
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
    legislative_interpreter_pool_min_size: int = 2
    legislative_interpreter_pool_max_size: int = 8

    def __post_init__(self) -> None:
        """Validate runtime timings and pool bounds."""
        if self.queue_timeout <= 0:
            msg = "queue_timeout must be positive"
            raise ValueError(msg)
        if self.poll_interval <= 0:
            msg = "poll_interval must be positive"
            raise ValueError(msg)
        require_positive_int(
            self.legislative_interpreter_pool_min_size,
            "legislative_interpreter_pool_min_size",
        )
        if self.legislative_interpreter_pool_max_size < self.legislative_interpreter_pool_min_size:
            msg = (
                "legislative_interpreter_pool_max_size must be >= "
                "legislative_interpreter_pool_min_size"
            )
            raise ValueError(msg)


@dataclass(frozen=True, slots=True)
class _CreateBookCommand:
    """Internal queued request for immutable book creation."""

    book: Book
    audit_context: AuditContext
    future: Future[StoreWriteReceipt]


@dataclass(frozen=True, slots=True)
class _AppendTransactionCommand:
    """Internal queued request for a posted transaction append."""

    book_code: str
    transaction: JournalTransaction
    audit_context: AuditContext
    future: Future[StoreWriteReceipt]


@dataclass(frozen=True, slots=True)
class _AppendLegislativeResultCommand:
    """Internal queued request for a legislative audit append."""

    book_code: str
    transaction_reference: str
    result: LegislativeValidationResult
    audit_context: AuditContext
    future: Future[StoreWriteReceipt]


@dataclass(frozen=True, slots=True)
class _CreateReversalCommand:
    """Internal queued request for an atomic transaction reversal."""

    book_code: str
    original_ref: str
    reversal_ref: str
    audit_context: AuditContext
    future: Future[StoreWriteReceipt]


@dataclass(frozen=True, slots=True)
class _CreateSnapshotCommand:
    """Internal queued request for a WAL-consistent snapshot."""

    output_path: Path | str
    compress: bool
    future: Future[DatabaseSnapshot]


type _RuntimeCommand = (
    _AppendLegislativeResultCommand
    | _AppendTransactionCommand
    | _CreateBookCommand
    | _CreateReversalCommand
    | _CreateSnapshotCommand
)


def _require_runtime_command(command: object) -> _RuntimeCommand:
    """Validate that a queued object is one of the supported runtime commands."""
    match command:
        case (
            _CreateBookCommand()
            | _AppendTransactionCommand()
            | _AppendLegislativeResultCommand()
            | _CreateReversalCommand()
            | _CreateSnapshotCommand()
        ):
            return command
        case _:
            msg = "command must be a supported runtime command"
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
    """Dedicated write-thread runtime with lifecycle locking and WAL-concurrent reads."""

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
        self._queue: Queue[_RuntimeCommand | None] = Queue()
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
        with self._lock.write(timeout=self._config.write_lock_timeout):
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

    def _dispatch_command(self, command: _RuntimeCommand) -> None:
        """Execute one writer command and resolve its Future.

        Catches all exceptions and forwards them to the command Future so the
        background writer thread never dies silently.
        """
        try:
            match command:
                case _CreateBookCommand(
                    book=book,
                    audit_context=audit_context,
                    future=future,
                ):
                    future.set_result(
                        self._store.create_book(
                            book,
                            audit_context=audit_context,
                        )
                    )
                case _AppendTransactionCommand(
                    book_code=book_code,
                    transaction=transaction,
                    audit_context=audit_context,
                    future=future,
                ):
                    future.set_result(
                        self._store.append_transaction(
                            book_code,
                            transaction,
                            audit_context=audit_context,
                        )
                    )
                case _AppendLegislativeResultCommand(
                    book_code=book_code,
                    transaction_reference=transaction_reference,
                    result=result,
                    audit_context=audit_context,
                    future=future,
                ):
                    future.set_result(
                        self._store.append_legislative_result(
                            book_code,
                            transaction_reference,
                            result,
                            audit_context=audit_context,
                        )
                    )
                case _CreateReversalCommand(
                    book_code=book_code,
                    original_ref=original_ref,
                    reversal_ref=reversal_ref,
                    audit_context=audit_context,
                    future=future,
                ):
                    future.set_result(
                        self._store.append_reversal(
                            book_code,
                            original_ref,
                            reversal_ref,
                            audit_context=audit_context,
                        )
                    )
                case _CreateSnapshotCommand(
                    output_path=output_path,
                    compress=compress,
                    future=future,
                ):
                    future.set_result(
                        self._store.create_snapshot(
                            output_path,
                            compress=compress,
                        )
                    )
        except Exception as error:
            # Future-based dispatch: any exception from a store operation must become
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

    def _submit(self, command: object) -> StoreWriteReceipt | DatabaseSnapshot:
        """Submit a runtime command and wait for completion."""
        queued_command = _require_runtime_command(command)
        self._queue.put(
            queued_command,
            timeout=self._config.queue_timeout,
        )
        return queued_command.future.result(
            timeout=self._config.queue_timeout + self._config.poll_interval
        )

    def create_book(self, book: Book, *, audit_context: AuditContext) -> StoreWriteReceipt:
        """Persist a new book through the dedicated write thread."""
        future: Future[StoreWriteReceipt] = Future()
        with self._lock.read(timeout=self._config.read_lock_timeout):
            return cast(
                "StoreWriteReceipt",
                self._submit(
                    _CreateBookCommand(
                        book=book,
                        audit_context=audit_context,
                        future=future,
                    )
                ),
            )

    def append_transaction(
        self,
        book_code: str,
        transaction: JournalTransaction,
        *,
        audit_context: AuditContext,
    ) -> StoreWriteReceipt:
        """Append a posted transaction through the dedicated write thread."""
        future: Future[StoreWriteReceipt] = Future()
        with self._lock.read(timeout=self._config.read_lock_timeout):
            return cast(
                "StoreWriteReceipt",
                self._submit(
                    _AppendTransactionCommand(
                        book_code=book_code,
                        transaction=transaction,
                        audit_context=audit_context,
                        future=future,
                    )
                ),
            )

    def append_legislative_result(
        self,
        book_code: str,
        transaction_reference: str,
        result: LegislativeValidationResult,
        *,
        audit_context: AuditContext,
    ) -> StoreWriteReceipt:
        """Append a post-commit legislative result through the dedicated write thread."""
        future: Future[StoreWriteReceipt] = Future()
        with self._lock.read(timeout=self._config.read_lock_timeout):
            return cast(
                "StoreWriteReceipt",
                self._submit(
                    _AppendLegislativeResultCommand(
                        book_code=book_code,
                        transaction_reference=transaction_reference,
                        result=result,
                        audit_context=audit_context,
                        future=future,
                    )
                ),
            )

    def get_book_snapshot(self, book_code: str) -> Book:
        """Read a complete immutable book snapshot from the reader pool."""
        with self._lock.read(timeout=self._config.read_lock_timeout):
            return self._store.load_book(book_code)

    def list_book_codes(self) -> tuple[str, ...]:
        """List all persisted books from the reader pool."""
        with self._lock.read(timeout=self._config.read_lock_timeout):
            return self._store.list_book_codes()

    def create_reversal(
        self,
        book_code: str,
        original_ref: str,
        reversal_ref: str,
        *,
        audit_context: AuditContext,
    ) -> StoreWriteReceipt:
        """Atomically reverse an existing posted transaction.

        Loads the original transaction, inverts every entry (debit ↔ credit),
        and writes the reversal in a single SQLite transaction.

        Args:
            book_code: Target book containing the original transaction.
            original_ref: Reference of the transaction to reverse.
            reversal_ref: Reference to assign to the new reversal transaction.
            audit_context: Actor, reason, and session metadata for the write.

        Returns:
            A :class:`StoreWriteReceipt` for the completed reversal write.

        Raises:
            KeyError: If ``book_code`` is not found.
            ValueError: If ``original_ref`` is not found, ``reversal_ref`` is
                already in use, or the original transaction is already reversed.
        """
        future: Future[StoreWriteReceipt] = Future()
        with self._lock.read(timeout=self._config.read_lock_timeout):
            return cast(
                "StoreWriteReceipt",
                self._submit(
                    _CreateReversalCommand(
                        book_code=book_code,
                        original_ref=original_ref,
                        reversal_ref=reversal_ref,
                        audit_context=audit_context,
                        future=future,
                    )
                ),
            )

    def iter_audit_log(self, *, limit: int | None = None) -> tuple[AuditLogRecord, ...]:
        """Read audit log rows from the reader pool."""
        with self._lock.read(timeout=self._config.read_lock_timeout):
            return self._store.iter_audit_log(limit=limit)

    def iter_audit_log_pages(
        self,
        *,
        page_size: int = 500,
        start_seq: int = 0,
    ) -> Iterator[tuple[AuditLogRecord, ...]]:
        """Yield pages of audit log rows without materializing the full result set.

        Args:
            page_size: Maximum number of rows per page.
            start_seq: Sequence number lower bound (exclusive).

        Yields:
            Non-empty tuples of :class:`AuditLogRecord` ordered by ``seq``.
        """
        yield from self._store.iter_audit_log_pages(
            page_size=page_size,
            start_seq=start_seq,
        )

    def create_snapshot(
        self,
        output_path: Path | str,
        *,
        compress: bool = True,
    ) -> DatabaseSnapshot:
        """Create a WAL-consistent snapshot through the dedicated write thread."""
        future: Future[DatabaseSnapshot] = Future()
        with self._lock.read(timeout=self._config.read_lock_timeout):
            return cast(
                "DatabaseSnapshot",
                self._submit(
                    _CreateSnapshotCommand(
                        output_path=output_path,
                        compress=compress,
                        future=future,
                    )
                ),
            )

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
