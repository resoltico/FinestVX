"""Periodically refreshed read-only facade for WAL-consistent book reads."""

from __future__ import annotations

import time
from typing import TYPE_CHECKING

from finestvx.persistence.config import PersistenceConfig, ReadReplicaConfig
from finestvx.persistence.store import AsyncLedgerReader

if TYPE_CHECKING:
    from collections.abc import AsyncIterator
    from typing import Self

    from finestvx.core.models import Book
    from finestvx.persistence.store import AuditLogRecord

__all__ = ["ReadReplica"]


class ReadReplica:
    """Read-only async facade that refreshes its APSW connection periodically.

    Reconnects the underlying async APSW connection at most every
    ``config.checkpoint_interval`` seconds, releasing any lingering WAL snapshot
    hold so the writer can checkpoint WAL frames.  All read methods delegate to
    :class:`~finestvx.persistence.store.AsyncLedgerReader`.
    """

    __slots__ = ("_config", "_last_refresh", "_persistence_config", "_reader")

    def __init__(
        self,
        config: ReadReplicaConfig,
        reader: AsyncLedgerReader,
    ) -> None:
        """Construct a ReadReplica wrapping an already-opened AsyncLedgerReader."""
        self._config = config
        self._reader = reader
        self._last_refresh = time.monotonic()
        self._persistence_config = PersistenceConfig(
            database_path=config.database_path,
            reader_connection_count=1,
            reader_statement_cache_size=config.reader_statement_cache_size,
            reserve_bytes=config.reserve_bytes,
        )

    @classmethod
    async def open(cls, config: ReadReplicaConfig) -> Self:
        """Open an async read-only connection and return a new ReadReplica."""
        persistence_config = PersistenceConfig(
            database_path=config.database_path,
            reader_connection_count=1,
            reader_statement_cache_size=config.reader_statement_cache_size,
            reserve_bytes=config.reserve_bytes,
        )
        reader = await AsyncLedgerReader.open(persistence_config)
        return cls(config, reader)

    async def _maybe_refresh(self) -> None:
        """Reconnect the underlying reader if the checkpoint interval has elapsed."""
        if time.monotonic() - self._last_refresh >= self._config.checkpoint_interval:
            await self.refresh()

    async def refresh(self) -> None:
        """Force an immediate reconnect of the underlying async APSW connection.

        Closes the current connection and opens a fresh one.  This releases any
        held WAL snapshot so the writer can checkpoint WAL frames.
        """
        old_reader = self._reader
        self._reader = await AsyncLedgerReader.open(self._persistence_config)
        self._last_refresh = time.monotonic()
        old_reader.close()

    async def list_book_codes(self) -> tuple[str, ...]:
        """Return all known book codes in deterministic order."""
        await self._maybe_refresh()
        return await self._reader.list_book_codes()

    async def load_book(self, book_code: str) -> Book:
        """Load a complete book aggregate."""
        await self._maybe_refresh()
        return await self._reader.load_book(book_code)

    async def iter_audit_log(
        self,
        *,
        limit: int | None = None,
    ) -> tuple[AuditLogRecord, ...]:
        """Return audit log rows ordered by sequence number."""
        await self._maybe_refresh()
        return await self._reader.iter_audit_log(limit=limit)

    async def iter_audit_log_pages(
        self,
        *,
        page_size: int = 500,
        start_seq: int = 0,
    ) -> AsyncIterator[tuple[AuditLogRecord, ...]]:
        """Yield pages of audit log rows without materializing the full result set."""
        await self._maybe_refresh()
        async for page in self._reader.iter_audit_log_pages(
            page_size=page_size,
            start_seq=start_seq,
        ):
            yield page

    def close(self) -> None:
        """Close the underlying async APSW connection."""
        self._reader.close()
