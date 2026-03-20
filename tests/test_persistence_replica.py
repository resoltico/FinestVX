"""Tests for ReadReplicaConfig and the ReadReplica async facade."""

from __future__ import annotations

import asyncio
import time
from pathlib import Path

import pytest

from finestvx.persistence import AuditContext, PersistenceConfig, SqliteLedgerStore
from finestvx.persistence.config import ReadReplicaConfig
from finestvx.persistence.replica import ReadReplica
from tests.support.book_factory import build_sample_book


class TestReadReplicaConfig:
    """Validation and normalisation of ReadReplicaConfig."""

    def test_path_is_normalised_to_path(self, tmp_path: Path) -> None:
        """database_path is coerced to a Path regardless of input type."""
        config = ReadReplicaConfig(database_path=str(tmp_path / "db.sqlite3"))
        assert isinstance(config.database_path, Path)

    def test_rejects_non_positive_checkpoint_interval(self, tmp_path: Path) -> None:
        """checkpoint_interval <= 0 raises ValueError."""
        with pytest.raises(ValueError, match="checkpoint_interval must be positive"):
            ReadReplicaConfig(database_path=tmp_path / "db.sqlite3", checkpoint_interval=0.0)

    def test_rejects_negative_checkpoint_interval(self, tmp_path: Path) -> None:
        """Negative checkpoint_interval raises ValueError."""
        with pytest.raises(ValueError, match="checkpoint_interval must be positive"):
            ReadReplicaConfig(
                database_path=tmp_path / "db.sqlite3", checkpoint_interval=-5.0
            )

    def test_rejects_negative_reader_statement_cache_size(self, tmp_path: Path) -> None:
        """reader_statement_cache_size < 0 raises ValueError."""
        with pytest.raises(ValueError, match="reader_statement_cache_size must be non-negative"):
            ReadReplicaConfig(
                database_path=tmp_path / "db.sqlite3", reader_statement_cache_size=-1
            )

    def test_rejects_reserve_bytes_out_of_range(self, tmp_path: Path) -> None:
        """reserve_bytes outside 0..255 raises ValueError."""
        with pytest.raises(ValueError, match=r"reserve_bytes must be in range \[0, 255\]"):
            ReadReplicaConfig(database_path=tmp_path / "db.sqlite3", reserve_bytes=256)

    def test_accepts_valid_defaults(self, tmp_path: Path) -> None:
        """Default ReadReplicaConfig values are accepted without error."""
        config = ReadReplicaConfig(database_path=tmp_path / "db.sqlite3")
        assert config.checkpoint_interval == 1.0
        assert config.reader_statement_cache_size == 128
        assert config.reserve_bytes == 0


class TestReadReplica:
    """Async facade over WAL-consistent read-only connections."""

    def _populate_store(self, db_path: Path) -> None:
        """Create and close a store with one book for replica tests."""
        store = SqliteLedgerStore(PersistenceConfig(db_path))
        book = build_sample_book()
        store.create_book(book, audit_context=AuditContext(actor="tester", reason="seed"))
        store.close()

    def test_open_and_list_book_codes(self, tmp_path: Path) -> None:
        """ReadReplica.open returns a functional replica that lists book codes."""
        db_path = tmp_path / "ledger.sqlite3"
        self._populate_store(db_path)

        async def _run() -> tuple[str, ...]:
            replica = await ReadReplica.open(ReadReplicaConfig(database_path=db_path))
            try:
                return await replica.list_book_codes()
            finally:
                replica.close()

        codes = asyncio.run(_run())
        assert "demo-book" in codes

    def test_load_book_returns_correct_aggregate(self, tmp_path: Path) -> None:
        """load_book returns the stored book with the correct code."""
        db_path = tmp_path / "ledger.sqlite3"
        self._populate_store(db_path)

        async def _run() -> str:
            replica = await ReadReplica.open(ReadReplicaConfig(database_path=db_path))
            try:
                book = await replica.load_book("demo-book")
                return book.code
            finally:
                replica.close()

        assert asyncio.run(_run()) == "demo-book"

    def test_iter_audit_log_returns_rows(self, tmp_path: Path) -> None:
        """iter_audit_log returns at least one row for a seeded book."""
        db_path = tmp_path / "ledger.sqlite3"
        self._populate_store(db_path)

        async def _run() -> int:
            replica = await ReadReplica.open(ReadReplicaConfig(database_path=db_path))
            try:
                rows = await replica.iter_audit_log()
                return len(rows)
            finally:
                replica.close()

        assert asyncio.run(_run()) >= 1

    def test_iter_audit_log_pages_yields_pages(self, tmp_path: Path) -> None:
        """iter_audit_log_pages yields at least one page for a seeded book."""
        db_path = tmp_path / "ledger.sqlite3"
        self._populate_store(db_path)

        async def _run() -> int:
            replica = await ReadReplica.open(ReadReplicaConfig(database_path=db_path))
            pages: list[object] = []
            try:
                async for page in replica.iter_audit_log_pages(page_size=10):
                    pages.append(page)
            finally:
                replica.close()
            return len(pages)

        assert asyncio.run(_run()) >= 1

    def test_refresh_reconnects_without_error(self, tmp_path: Path) -> None:
        """refresh() completes without raising and the replica remains functional."""
        db_path = tmp_path / "ledger.sqlite3"
        self._populate_store(db_path)

        async def _run() -> tuple[str, ...]:
            replica = await ReadReplica.open(ReadReplicaConfig(database_path=db_path))
            try:
                await replica.refresh()
                return await replica.list_book_codes()
            finally:
                replica.close()

        codes = asyncio.run(_run())
        assert "demo-book" in codes

    def test_maybe_refresh_triggers_when_interval_elapsed(self, tmp_path: Path) -> None:
        """_maybe_refresh reconnects when checkpoint_interval has elapsed."""
        db_path = tmp_path / "ledger.sqlite3"
        self._populate_store(db_path)

        async def _run() -> tuple[str, ...]:
            config = ReadReplicaConfig(database_path=db_path, checkpoint_interval=0.001)
            replica = await ReadReplica.open(config)
            try:
                # Force last_refresh to be old enough to trigger reconnect
                object.__setattr__(replica, "_last_refresh", time.monotonic() - 1.0)
                await replica._maybe_refresh()
                return await replica.list_book_codes()
            finally:
                replica.close()

        codes = asyncio.run(_run())
        assert "demo-book" in codes
