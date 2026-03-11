"""Tests for the APSW-backed FinestVX ledger store."""

from __future__ import annotations

from compression import zstd
from pathlib import Path

import apsw
import pytest

from finestvx.persistence import AuditContext, PersistenceConfig, SqliteLedgerStore
from tests.support.book_factory import build_posted_transaction, build_sample_book


class TestSqliteLedgerStore:
    """Persistence, audit, and backup behavior checks."""

    def test_round_trip_book_and_transactions(self, tmp_path: Path) -> None:
        """Book bootstrap rows and appended transactions round-trip cleanly."""
        database_path = tmp_path / "ledger.sqlite3"
        store = SqliteLedgerStore(PersistenceConfig(database_path))
        book = build_sample_book()
        transaction = build_posted_transaction(reference="TX-2026-0002")

        store.create_book(book, audit_context=AuditContext(actor="tester", reason="bootstrap"))
        store.append_transaction(
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

        store.close()

    def test_append_only_triggers_reject_updates(self, tmp_path: Path) -> None:
        """Core ledger tables are protected against UPDATE statements."""
        database_path = tmp_path / "ledger.sqlite3"
        store = SqliteLedgerStore(PersistenceConfig(database_path))
        book = build_sample_book()
        store.create_book(book, audit_context=AuditContext(actor="tester", reason="bootstrap"))

        with pytest.raises(apsw.ConstraintError, match="append-only table"):
            store.execute(
                "UPDATE books SET name = ? WHERE book_code = ?",
                ("Changed", book.code),
            )

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
