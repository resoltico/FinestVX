"""Tests for the FinestVX single-writer runtime."""

from __future__ import annotations

from concurrent.futures import Future
from pathlib import Path
from threading import Event, Thread
from unittest.mock import MagicMock

import pytest

from finestvx.core.models import JournalTransaction
from finestvx.persistence import (
    AuditContext,
    PersistenceConfig,
    SqliteLedgerStore,
    StoreWriteReceipt,
)
from finestvx.runtime import LedgerRuntime, RuntimeConfig
from finestvx.runtime.service import _CreateBookCommand
from tests.support.book_factory import build_posted_transaction, build_sample_book


class TestLedgerRuntime:
    """Read/write coordination and audit visibility checks."""

    def test_runtime_serializes_writes_serves_snapshots_and_returns_receipts(
        self,
        tmp_path: Path,
    ) -> None:
        """The runtime accepts queued writes, exposes concurrent reads, and returns receipts."""
        config = RuntimeConfig(
            PersistenceConfig(
                tmp_path / "runtime.sqlite3",
                reader_connection_count=2,
                telemetry_buffer_size=4,
            )
        )
        runtime = LedgerRuntime(config)
        book = build_sample_book()

        create_receipt = runtime.create_book(
            book,
            audit_context=AuditContext(actor="tester", reason="bootstrap"),
        )
        append_receipt = runtime.append_transaction(
            book.code,
            build_posted_transaction(reference="TX-2026-0009"),
            audit_context=AuditContext(actor="tester", reason="post"),
        )

        snapshot = runtime.get_book_snapshot(book.code)

        assert runtime.list_book_codes() == (book.code,)
        assert tuple(item.reference for item in snapshot.transactions) == ("TX-2026-0009",)
        assert runtime.iter_audit_log(limit=1)[0].table_name == "books"
        assert "books" in create_receipt.changed_tables
        assert "transactions" in append_receipt.changed_tables
        runtime_snapshot = runtime.debug_snapshot()
        assert runtime_snapshot.store.writer.readonly is False
        assert len(runtime_snapshot.store.readers) == 2

        runtime.close()

    def test_runtime_reads_continue_while_writer_command_is_in_flight(
        self,
        tmp_path: Path,
        monkeypatch: pytest.MonkeyPatch,
    ) -> None:
        """Lifecycle locking does not block reader-pool calls during queued writes."""
        config = RuntimeConfig(
            PersistenceConfig(tmp_path / "runtime.sqlite3", reader_connection_count=2),
            poll_interval=0.01,
        )
        runtime = LedgerRuntime(config)
        book = build_sample_book()
        runtime.create_book(book, audit_context=AuditContext(actor="tester", reason="bootstrap"))

        started = Event()
        release = Event()
        original_append_transaction = type(runtime._store).append_transaction

        def blocked_append_transaction(
            self: SqliteLedgerStore,
            book_code: str,
            transaction: JournalTransaction,
            *,
            audit_context: AuditContext,
        ) -> StoreWriteReceipt:
            started.set()
            assert release.wait(timeout=5) is True
            return original_append_transaction(
                self,
                book_code,
                transaction,
                audit_context=audit_context,
            )

        monkeypatch.setattr(
            type(runtime._store),
            "append_transaction",
            blocked_append_transaction,
        )

        write_result: list[object] = []
        write_thread = Thread(
            target=lambda: write_result.append(
                runtime.append_transaction(
                    book.code,
                    build_posted_transaction(reference="TX-2026-0010"),
                    audit_context=AuditContext(actor="tester", reason="post"),
                )
            ),
            daemon=True,
        )
        write_thread.start()

        assert started.wait(timeout=5) is True

        read_result: list[tuple[str, ...]] = []
        read_thread = Thread(
            target=lambda: read_result.append(runtime.list_book_codes()),
            daemon=True,
        )
        read_thread.start()
        read_thread.join(timeout=1)

        assert read_thread.is_alive() is False
        assert read_result == [(book.code,)]

        release.set()
        write_thread.join(timeout=5)

        assert write_thread.is_alive() is False
        assert write_result

        runtime.close()

    def test_dispatch_command_forwards_unexpected_exception_to_future(
        self,
        tmp_path: Path,
    ) -> None:
        """Unexpected exceptions in _dispatch_command are forwarded to the command Future."""
        config = RuntimeConfig(PersistenceConfig(tmp_path / "dispatch.sqlite3"))
        runtime = LedgerRuntime(config)

        mock_book = build_sample_book()
        injected_error = RuntimeError("injected unexpected failure")

        mock_store = MagicMock()
        mock_store.create_book.side_effect = injected_error
        runtime._store = mock_store

        future: Future[StoreWriteReceipt] = Future()
        command = _CreateBookCommand(
            book=mock_book,
            audit_context=AuditContext(actor="tester", reason="inject"),
            future=future,
        )

        runtime._dispatch_command(command)

        assert future.done()
        with pytest.raises(RuntimeError, match="injected unexpected failure"):
            future.result()

        runtime.close()
