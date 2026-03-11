"""Tests for the FinestVX single-writer runtime."""

from __future__ import annotations

from concurrent.futures import Future
from pathlib import Path
from unittest.mock import MagicMock

import pytest

from finestvx.persistence import AuditContext, PersistenceConfig
from finestvx.runtime import LedgerRuntime, RuntimeConfig
from finestvx.runtime.service import _WriteCommand
from tests.support.book_factory import build_posted_transaction, build_sample_book


class TestLedgerRuntime:
    """Read/write coordination and audit visibility checks."""

    def test_runtime_serializes_writes_and_serves_snapshots(self, tmp_path: Path) -> None:
        """The runtime accepts queued writes and exposes read-side snapshots."""
        config = RuntimeConfig(PersistenceConfig(tmp_path / "runtime.sqlite3"))
        runtime = LedgerRuntime(config)
        book = build_sample_book()

        runtime.create_book(book, audit_context=AuditContext(actor="tester", reason="bootstrap"))
        runtime.append_transaction(
            book.code,
            build_posted_transaction(reference="TX-2026-0009"),
            audit_context=AuditContext(actor="tester", reason="post"),
        )

        snapshot = runtime.get_book_snapshot(book.code)

        assert runtime.list_book_codes() == (book.code,)
        assert tuple(item.reference for item in snapshot.transactions) == ("TX-2026-0009",)
        assert runtime.iter_audit_log(limit=1)[0].table_name == "books"

        runtime.close()

    def test_dispatch_command_forwards_unexpected_exception_to_future(
        self, tmp_path: Path
    ) -> None:
        """Unexpected exceptions in _dispatch_command are forwarded to the command Future.

        Exercises the broad-exception-caught path: the write thread must never die
        silently. Any exception from store operations must reach the caller via
        Future.result(), not crash the thread.
        """
        config = RuntimeConfig(PersistenceConfig(tmp_path / "dispatch.sqlite3"))
        runtime = LedgerRuntime(config)

        mock_book = build_sample_book()
        injected_error = RuntimeError("injected unexpected failure")

        mock_store = MagicMock()
        mock_store.create_book.side_effect = injected_error
        runtime._store = mock_store

        future: Future[None] = Future()
        command = _WriteCommand(
            kind="create_book",
            payload=mock_book,
            audit_context=AuditContext(actor="tester", reason="inject"),
            future=future,
        )

        runtime._dispatch_command(command)

        assert future.done()
        with pytest.raises(RuntimeError, match="injected unexpected failure"):
            future.result()

        runtime.close()
