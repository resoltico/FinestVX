"""Multi-book runtime providing per-book isolated LedgerRuntime instances."""

from __future__ import annotations

import dataclasses
from dataclasses import dataclass
from pathlib import Path
from typing import TYPE_CHECKING

from ftllexengine import require_non_empty_str
from ftllexengine.runtime import RWLock

from finestvx.runtime.service import LedgerRuntime, RuntimeConfig

if TYPE_CHECKING:
    from collections.abc import Iterator
    from typing import Self

    from finestvx.core.models import Book, JournalTransaction
    from finestvx.legislation.protocols import LegislativeValidationResult
    from finestvx.persistence import AuditContext, DatabaseSnapshot, StoreWriteReceipt
    from finestvx.persistence.config import PersistenceConfig
    from finestvx.persistence.store import AuditLogRecord
    from finestvx.runtime.service import RuntimeDebugSnapshot

__all__ = [
    "MultiBookDebugSnapshot",
    "MultiBookRuntime",
    "MultiBookRuntimeConfig",
]


@dataclass(frozen=True, slots=True)
class MultiBookRuntimeConfig:
    """Configuration for a multi-book runtime managing per-book isolated stores."""

    data_directory: Path | str
    persistence_template: PersistenceConfig
    queue_timeout: float = 5.0
    poll_interval: float = 0.1
    read_lock_timeout: float | None = 5.0
    write_lock_timeout: float | None = 5.0
    legislative_interpreter_pool_min_size: int = 2
    legislative_interpreter_pool_max_size: int = 8

    def __post_init__(self) -> None:
        """Normalize the data directory path and validate timing settings."""
        object.__setattr__(self, "data_directory", Path(self.data_directory))
        if self.queue_timeout <= 0:
            msg = "queue_timeout must be positive"
            raise ValueError(msg)
        if self.poll_interval <= 0:
            msg = "poll_interval must be positive"
            raise ValueError(msg)


@dataclass(frozen=True, slots=True)
class MultiBookDebugSnapshot:
    """Immutable multi-book runtime snapshot for observability."""

    data_directory: Path
    open_book_count: int
    books: tuple[tuple[str, RuntimeDebugSnapshot], ...]


class MultiBookRuntime:
    """Per-book isolated runtime managing a pool of LedgerRuntime instances.

    Each book is backed by its own SQLite file under ``config.data_directory``.
    Write serialization is per-book; each open book has its own dedicated write
    thread.  All public methods that take a ``book_code`` argument route to the
    matching open :class:`~finestvx.runtime.service.LedgerRuntime`.
    """

    __slots__ = ("_config", "_lock", "_runtimes")

    def __init__(self, config: MultiBookRuntimeConfig) -> None:
        """Create the multi-book runtime; no books are opened automatically."""
        self._config = config
        self._runtimes: dict[str, LedgerRuntime] = {}
        self._lock = RWLock()

    def __enter__(self) -> Self:
        """Enter context-manager scope."""
        return self

    def __exit__(self, exc_type: object, exc: object, traceback: object) -> None:
        """Close all open book runtimes at the end of a context-manager scope."""
        self.close()

    def _runtime_config_for(self, book_code: str) -> RuntimeConfig:
        """Build a per-book RuntimeConfig with the correct database path."""
        db_path = Path(self._config.data_directory) / f"{book_code}.sqlite3"
        persistence = dataclasses.replace(
            self._config.persistence_template, database_path=db_path
        )
        return RuntimeConfig(
            persistence=persistence,
            queue_timeout=self._config.queue_timeout,
            poll_interval=self._config.poll_interval,
            read_lock_timeout=self._config.read_lock_timeout,
            write_lock_timeout=self._config.write_lock_timeout,
            legislative_interpreter_pool_min_size=self._config.legislative_interpreter_pool_min_size,
            legislative_interpreter_pool_max_size=self._config.legislative_interpreter_pool_max_size,
        )

    def _require_runtime(self, book_code: str) -> LedgerRuntime:
        """Return the open runtime for *book_code* or raise KeyError."""
        with self._lock.read(timeout=self._config.read_lock_timeout):
            try:
                return self._runtimes[book_code]
            except KeyError:
                msg = f"No open book: {book_code!r}"
                raise KeyError(msg) from None

    def create_book(self, book: Book, *, audit_context: AuditContext) -> StoreWriteReceipt:
        """Create a new book backed by its own SQLite file and start its runtime.

        Args:
            book: The book aggregate to persist.
            audit_context: Actor, reason, and session metadata for the write.

        Returns:
            A :class:`~finestvx.persistence.StoreWriteReceipt` for the write.

        Raises:
            ValueError: If a book with the same code is already open.
        """
        book_code = book.code
        with self._lock.write(timeout=self._config.write_lock_timeout):
            if book_code in self._runtimes:
                msg = f"Book {book_code!r} is already open"
                raise ValueError(msg)
            Path(self._config.data_directory).mkdir(parents=True, exist_ok=True)
            runtime = LedgerRuntime(self._runtime_config_for(book_code))
            receipt = runtime.create_book(book, audit_context=audit_context)
            self._runtimes[book_code] = runtime
        return receipt

    def open_book(self, book_code: str) -> None:
        """Open an existing book database from the data directory.

        Args:
            book_code: Identifies the SQLite file ``<data_directory>/<book_code>.sqlite3``.

        Raises:
            KeyError: If no database file exists for *book_code*.
        """
        require_non_empty_str(book_code, "book_code")
        with self._lock.write(timeout=self._config.write_lock_timeout):
            if book_code in self._runtimes:
                return
            db_path = Path(self._config.data_directory) / f"{book_code}.sqlite3"
            if not db_path.exists():
                msg = f"No database file for book {book_code!r}"
                raise KeyError(msg)
            self._runtimes[book_code] = LedgerRuntime(self._runtime_config_for(book_code))

    def close_book(self, book_code: str) -> None:
        """Close one book's runtime and remove it from the open pool.

        Args:
            book_code: Code of the book to close.  No-op if not currently open.
        """
        require_non_empty_str(book_code, "book_code")
        with self._lock.write(timeout=self._config.write_lock_timeout):
            runtime = self._runtimes.pop(book_code, None)
        if runtime is not None:
            runtime.close()

    def list_book_codes(self) -> tuple[str, ...]:
        """Return codes for all currently open books in sorted order."""
        with self._lock.read(timeout=self._config.read_lock_timeout):
            return tuple(sorted(self._runtimes))

    def list_available_book_codes(self) -> tuple[str, ...]:
        """Return codes derived from all .sqlite3 files in the data directory."""
        data_dir = Path(self._config.data_directory)
        if not data_dir.exists():
            return ()
        return tuple(sorted(p.stem for p in data_dir.glob("*.sqlite3")))

    def append_transaction(
        self,
        book_code: str,
        transaction: JournalTransaction,
        *,
        audit_context: AuditContext,
    ) -> StoreWriteReceipt:
        """Append a posted transaction to the specified book.

        Args:
            book_code: Target book code.
            transaction: Posted transaction to append.
            audit_context: Actor, reason, and session metadata for the write.

        Returns:
            A :class:`~finestvx.persistence.StoreWriteReceipt` for the write.

        Raises:
            KeyError: If *book_code* is not currently open.
        """
        return self._require_runtime(book_code).append_transaction(
            book_code,
            transaction,
            audit_context=audit_context,
        )

    def create_reversal(
        self,
        book_code: str,
        original_ref: str,
        reversal_ref: str,
        *,
        audit_context: AuditContext,
    ) -> StoreWriteReceipt:
        """Atomically reverse an existing posted transaction in the specified book.

        Args:
            book_code: Target book containing the original transaction.
            original_ref: Reference of the transaction to reverse.
            reversal_ref: Reference to assign to the new reversal transaction.
            audit_context: Actor, reason, and session metadata for the write.

        Returns:
            A :class:`~finestvx.persistence.StoreWriteReceipt` for the reversal.

        Raises:
            KeyError: If *book_code* is not currently open or *original_ref* is absent.
            ValueError: If *original_ref* is already reversed or *reversal_ref* is in use.
        """
        return self._require_runtime(book_code).create_reversal(
            book_code,
            original_ref,
            reversal_ref,
            audit_context=audit_context,
        )

    def append_legislative_result(
        self,
        book_code: str,
        transaction_reference: str,
        result: LegislativeValidationResult,
        *,
        audit_context: AuditContext,
    ) -> StoreWriteReceipt:
        """Append a legislative validation result to the specified book.

        Args:
            book_code: Target book code.
            transaction_reference: Reference of the validated transaction.
            result: Legislative validation result to persist.
            audit_context: Actor, reason, and session metadata for the write.

        Returns:
            A :class:`~finestvx.persistence.StoreWriteReceipt` for the write.

        Raises:
            KeyError: If *book_code* is not currently open.
        """
        return self._require_runtime(book_code).append_legislative_result(
            book_code,
            transaction_reference,
            result,
            audit_context=audit_context,
        )

    def get_book(self, book_code: str) -> Book:
        """Load a complete immutable book snapshot from the specified book's store.

        Args:
            book_code: Code of the book to load.

        Returns:
            The current :class:`~finestvx.core.models.Book` aggregate.

        Raises:
            KeyError: If *book_code* is not currently open.
        """
        return self._require_runtime(book_code).get_book_snapshot(book_code)

    def iter_audit_log(
        self,
        book_code: str,
        *,
        limit: int | None = None,
    ) -> tuple[AuditLogRecord, ...]:
        """Return audit log rows for the specified book.

        Args:
            book_code: Code of the book whose audit log to read.
            limit: Maximum number of rows to return; ``None`` returns all rows.

        Returns:
            Tuple of :class:`~finestvx.persistence.store.AuditLogRecord` ordered by ``seq``.

        Raises:
            KeyError: If *book_code* is not currently open.
        """
        return self._require_runtime(book_code).iter_audit_log(limit=limit)

    def iter_audit_log_pages(
        self,
        book_code: str,
        *,
        page_size: int = 500,
        start_seq: int = 0,
    ) -> Iterator[tuple[AuditLogRecord, ...]]:
        """Yield cursor-paginated audit log rows for the specified book.

        Args:
            book_code: Code of the book whose audit log to stream.
            page_size: Maximum number of rows per page.
            start_seq: Sequence number lower bound (exclusive).

        Yields:
            Non-empty tuples of :class:`~finestvx.persistence.store.AuditLogRecord`.

        Raises:
            KeyError: If *book_code* is not currently open.
        """
        yield from self._require_runtime(book_code).iter_audit_log_pages(
            page_size=page_size,
            start_seq=start_seq,
        )

    def create_snapshot(
        self,
        book_code: str,
        output_path: Path | str,
        *,
        compress: bool = True,
    ) -> DatabaseSnapshot:
        """Create a WAL-consistent snapshot for the specified book.

        Args:
            book_code: Code of the book to snapshot.
            output_path: Destination file path.
            compress: Apply zstd compression when ``True``.

        Returns:
            A :class:`~finestvx.persistence.DatabaseSnapshot` with write statistics.

        Raises:
            KeyError: If *book_code* is not currently open.
        """
        return self._require_runtime(book_code).create_snapshot(
            output_path,
            compress=compress,
        )

    def debug_snapshot(self) -> MultiBookDebugSnapshot:
        """Return a non-invasive snapshot of all open book runtimes."""
        with self._lock.read(timeout=self._config.read_lock_timeout):
            books = tuple(
                (code, runtime.debug_snapshot())
                for code, runtime in sorted(self._runtimes.items())
            )
        return MultiBookDebugSnapshot(
            data_directory=Path(self._config.data_directory),
            open_book_count=len(books),
            books=books,
        )

    def close(self) -> None:
        """Close all open book runtimes and release their resources."""
        with self._lock.write(timeout=self._config.write_lock_timeout):
            runtimes = list(self._runtimes.values())
            self._runtimes.clear()
        for runtime in runtimes:
            runtime.close()
