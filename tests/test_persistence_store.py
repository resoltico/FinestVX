"""Tests for the APSW-backed FinestVX ledger store."""

from __future__ import annotations

import asyncio
from compression import zstd
from pathlib import Path

import apsw
import pytest

from finestvx.persistence import AuditContext, PersistenceConfig, SqliteLedgerStore
from tests.support.book_factory import build_posted_transaction, build_sample_book


class TestSqliteLedgerStore:
    """Persistence, audit, concurrency, and backup behavior checks."""

    def test_round_trip_book_and_transactions_emit_receipts_and_telemetry(
        self,
        tmp_path: Path,
    ) -> None:
        """Book and transaction writes emit APSW changeset receipts and reader-pool telemetry."""
        database_path = tmp_path / "ledger.sqlite3"
        store = SqliteLedgerStore(
            PersistenceConfig(
                database_path,
                reader_connection_count=2,
                telemetry_buffer_size=8,
            )
        )
        book = build_sample_book()
        transaction = build_posted_transaction(reference="TX-2026-0002")

        create_receipt = store.create_book(
            book,
            audit_context=AuditContext(actor="tester", reason="bootstrap"),
        )
        append_receipt = store.append_transaction(
            book.code,
            transaction,
            audit_context=AuditContext(actor="tester", reason="post"),
        )

        loaded = store.load_book(book.code)

        assert loaded.code == book.code
        assert tuple(account.code for account in loaded.accounts) == ("1000", "2000")
        assert tuple(item.reference for item in loaded.transactions) == ("TX-2026-0002",)
        assert loaded.transactions[0].is_balanced is True

        audit_rows = store.iter_audit_log()
        assert len(audit_rows) == 7
        assert audit_rows[0].table_name == "books"
        assert audit_rows[-1].table_name == "entries"

        assert "books" in create_receipt.changed_tables
        assert "accounts" in create_receipt.changed_tables
        assert create_receipt.change_count >= 4
        assert create_receipt.changeset_size_bytes > 0
        assert create_receipt.patchset_size_bytes > 0

        assert "transactions" in append_receipt.changed_tables
        assert "entries" in append_receipt.changed_tables
        assert append_receipt.indirect_change_count > 0
        assert append_receipt.last_wal_commit is not None

        debug_snapshot = store.debug_snapshot()
        assert debug_snapshot.reserve_bytes == 0
        assert debug_snapshot.writer.readonly is False
        assert debug_snapshot.writer.statement_cache.size == 256
        assert len(debug_snapshot.readers) == 2
        assert all(reader.readonly for reader in debug_snapshot.readers)
        assert debug_snapshot.recent_trace_events
        assert debug_snapshot.recent_profile_events

        store.close()

    def test_append_only_triggers_reject_updates_without_store_execute(
        self,
        tmp_path: Path,
    ) -> None:
        """Ledger tables stay append-only even after removing the raw store.execute API."""
        database_path = tmp_path / "ledger.sqlite3"
        store = SqliteLedgerStore(PersistenceConfig(database_path))
        book = build_sample_book()
        store.create_book(book, audit_context=AuditContext(actor="tester", reason="bootstrap"))

        assert hasattr(store, "execute") is False

        connection = apsw.Connection(str(database_path))
        try:
            with pytest.raises(apsw.ConstraintError, match="append-only table"):
                connection.execute(
                    "UPDATE books SET name = ? WHERE book_code = ?",
                    ("Changed", book.code),
                )
        finally:
            connection.close()

        store.close()

    def test_reserve_bytes_and_async_reader_are_supported(self, tmp_path: Path) -> None:
        """The store enforces reserve-bytes policy and exposes an async read-only facade."""
        database_path = tmp_path / "ledger.sqlite3"
        config = PersistenceConfig(
            database_path,
            reader_connection_count=1,
            reserve_bytes=8,
        )
        store = SqliteLedgerStore(config)
        book = build_sample_book(include_transaction=True)
        store.create_book(book, audit_context=AuditContext(actor="tester", reason="bootstrap"))

        async def exercise_async_reader() -> None:
            reader = await store.open_async_reader()
            try:
                assert await reader.list_book_codes() == (book.code,)
                loaded = await reader.load_book(book.code)
                assert loaded.code == book.code
                assert tuple(item.reference for item in loaded.transactions) == ("TX-2026-0001",)
                debug_snapshot = await reader.debug_snapshot()
                assert debug_snapshot.readonly is True
                assert debug_snapshot.statement_cache.size == 128
            finally:
                reader.close()

        asyncio.run(exercise_async_reader())

        assert store.debug_snapshot().reserve_bytes == 8

        store.close()

    def test_zstd_snapshot_is_created(self, tmp_path: Path) -> None:
        """Snapshots are WAL-consistent and can be decompressed back to SQLite bytes."""
        database_path = tmp_path / "ledger.sqlite3"
        snapshot_path = tmp_path / "ledger-snapshot.zst"
        store = SqliteLedgerStore(PersistenceConfig(database_path))
        book = build_sample_book(include_transaction=True)
        store.create_book(book, audit_context=AuditContext(actor="tester", reason="bootstrap"))

        snapshot = store.create_snapshot(snapshot_path, compress=True)
        raw_bytes = zstd.decompress(snapshot_path.read_bytes())

        assert snapshot.output_path == snapshot_path
        assert snapshot.compressed is True
        assert snapshot.bytes_written == snapshot_path.stat().st_size
        assert raw_bytes.startswith(b"SQLite format 3\x00")

        store.close()
