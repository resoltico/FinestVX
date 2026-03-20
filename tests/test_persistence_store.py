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

    def test_append_reversal_creates_inverted_transaction(self, tmp_path: Path) -> None:
        """append_reversal creates a mirror transaction with all entries inverted."""
        database_path = tmp_path / "ledger.sqlite3"
        store = SqliteLedgerStore(PersistenceConfig(database_path))
        book = build_sample_book()
        tx = build_posted_transaction(reference="TX-2026-0010")
        store.create_book(book, audit_context=AuditContext(actor="tester", reason="bootstrap"))
        store.append_transaction(
            book.code, tx, audit_context=AuditContext(actor="tester", reason="post")
        )

        receipt = store.append_reversal(
            book.code,
            "TX-2026-0010",
            "TX-2026-0010-REV",
            audit_context=AuditContext(actor="tester", reason="reversal"),
        )

        loaded = store.load_book(book.code)
        references = [t.reference for t in loaded.transactions]
        assert "TX-2026-0010" in references
        assert "TX-2026-0010-REV" in references
        reversal = next(t for t in loaded.transactions if t.reference == "TX-2026-0010-REV")
        original = next(t for t in loaded.transactions if t.reference == "TX-2026-0010")
        assert reversal.reversal_of == "TX-2026-0010"
        assert reversal.is_balanced is True
        assert len(reversal.entries) == len(original.entries)
        original_sides = [e.side for e in original.entries]
        reversal_sides = [e.side for e in reversal.entries]
        assert original_sides[0] != reversal_sides[0]
        assert original_sides[1] != reversal_sides[1]
        assert "transactions" in receipt.changed_tables

        store.close()

    def test_append_reversal_rejects_unknown_book_and_missing_transaction(
        self, tmp_path: Path
    ) -> None:
        """append_reversal raises the correct errors for invalid inputs."""
        database_path = tmp_path / "ledger.sqlite3"
        store = SqliteLedgerStore(PersistenceConfig(database_path))
        book = build_sample_book()
        store.create_book(book, audit_context=AuditContext(actor="tester", reason="bootstrap"))
        audit = AuditContext(actor="tester", reason="reversal")

        with pytest.raises(KeyError, match="unknown-book"):
            store.append_reversal("unknown-book", "TX-MISSING", "TX-REV", audit_context=audit)

        with pytest.raises(ValueError, match="not found"):
            store.append_reversal(book.code, "TX-MISSING", "TX-REV", audit_context=audit)

        store.close()

    def test_append_reversal_prevents_double_reversal(self, tmp_path: Path) -> None:
        """append_reversal raises ValueError when the original is already reversed."""
        database_path = tmp_path / "ledger.sqlite3"
        store = SqliteLedgerStore(PersistenceConfig(database_path))
        book = build_sample_book()
        tx = build_posted_transaction(reference="TX-2026-0011")
        store.create_book(book, audit_context=AuditContext(actor="tester", reason="bootstrap"))
        store.append_transaction(
            book.code, tx, audit_context=AuditContext(actor="tester", reason="post")
        )
        store.append_reversal(
            book.code,
            "TX-2026-0011",
            "TX-2026-0011-REV",
            audit_context=AuditContext(actor="tester", reason="reversal"),
        )

        with pytest.raises(ValueError, match="already reversed"):
            store.append_reversal(
                book.code,
                "TX-2026-0011",
                "TX-2026-0011-REV-2",
                audit_context=AuditContext(actor="tester", reason="second-reversal"),
            )

        store.close()

    def test_iter_audit_log_pages_yields_pages_without_full_materialization(
        self, tmp_path: Path
    ) -> None:
        """iter_audit_log_pages returns the same records as iter_audit_log split into pages."""
        database_path = tmp_path / "ledger.sqlite3"
        store = SqliteLedgerStore(PersistenceConfig(database_path))
        book = build_sample_book()
        store.create_book(book, audit_context=AuditContext(actor="tester", reason="bootstrap"))
        for i in range(3):
            store.append_transaction(
                book.code,
                build_posted_transaction(reference=f"TX-PAGE-{i:04d}"),
                audit_context=AuditContext(actor="tester", reason=f"tx-{i}"),
            )

        all_rows = store.iter_audit_log()
        pages = list(store.iter_audit_log_pages(page_size=4))

        paged_rows = tuple(row for page in pages for row in page)
        assert paged_rows == all_rows
        assert all(len(page) <= 4 for page in pages)
        assert len(pages) > 1

        store.close()

    def test_append_reversal_rejects_duplicate_reversal_ref(self, tmp_path: Path) -> None:
        """append_reversal raises ValueError when the reversal_ref is already in use."""
        database_path = tmp_path / "ledger.sqlite3"
        store = SqliteLedgerStore(PersistenceConfig(database_path))
        book = build_sample_book()
        store.create_book(book, audit_context=AuditContext(actor="tester", reason="bootstrap"))
        store.append_transaction(
            book.code,
            build_posted_transaction(reference="TX-2026-0012"),
            audit_context=AuditContext(actor="tester", reason="post"),
        )
        store.append_transaction(
            book.code,
            build_posted_transaction(reference="TX-2026-0013"),
            audit_context=AuditContext(actor="tester", reason="post"),
        )

        with pytest.raises(ValueError, match="already in use"):
            store.append_reversal(
                book.code,
                "TX-2026-0012",
                "TX-2026-0013",
                audit_context=AuditContext(actor="tester", reason="reversal"),
            )

        store.close()

    def test_iter_audit_log_pages_with_start_seq_skips_earlier_entries(
        self, tmp_path: Path
    ) -> None:
        """iter_audit_log_pages with start_seq skips rows up to and including start_seq."""
        database_path = tmp_path / "ledger.sqlite3"
        store = SqliteLedgerStore(PersistenceConfig(database_path))
        book = build_sample_book()
        store.create_book(book, audit_context=AuditContext(actor="tester", reason="bootstrap"))
        store.append_transaction(
            book.code,
            build_posted_transaction(reference="TX-SKIP-0001"),
            audit_context=AuditContext(actor="tester", reason="post"),
        )

        all_rows = store.iter_audit_log()
        cutoff_seq = all_rows[2].seq
        paged = list(store.iter_audit_log_pages(start_seq=cutoff_seq))
        paged_rows = tuple(row for page in paged for row in page)

        assert all(row.seq > cutoff_seq for row in paged_rows)

        store.close()

    def test_async_iter_audit_log_pages_yields_pages(self, tmp_path: Path) -> None:
        """AsyncLedgerReader.iter_audit_log_pages yields cursor-paginated records."""
        database_path = tmp_path / "ledger.sqlite3"
        config = PersistenceConfig(database_path, reserve_bytes=8)
        store = SqliteLedgerStore(config)
        book = build_sample_book()
        store.create_book(book, audit_context=AuditContext(actor="tester", reason="bootstrap"))
        for i in range(3):
            store.append_transaction(
                book.code,
                build_posted_transaction(reference=f"TX-ASYNC-{i:04d}"),
                audit_context=AuditContext(actor="tester", reason=f"tx-{i}"),
            )
        all_rows = store.iter_audit_log()

        async def exercise_async_pages() -> None:
            reader = await store.open_async_reader()
            try:
                pages: list[tuple[object, ...]] = []
                async for page in reader.iter_audit_log_pages(page_size=4):
                    pages.append(page)
                paged_rows = tuple(row for page in pages for row in page)
                assert len(paged_rows) == len(all_rows)
                assert all(len(page) <= 4 for page in pages)
            finally:
                reader.close()

        asyncio.run(exercise_async_pages())
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
