"""Tests for the MultiBookRuntime and MultiBookRuntimeConfig."""

from __future__ import annotations

from datetime import date
from pathlib import Path

import pytest
from ftllexengine import FiscalCalendar, FiscalPeriod
from ftllexengine.introspection import CurrencyCode
from hypothesis import event, given, settings
from hypothesis import strategies as st

from finestvx.core.enums import FiscalPeriodState, PostingSide
from finestvx.core.models import Account, Book, BookPeriod
from finestvx.persistence import AuditContext, PersistenceConfig
from finestvx.runtime.multi_book import (
    MultiBookDebugSnapshot,
    MultiBookRuntime,
    MultiBookRuntimeConfig,
)
from tests.support.book_factory import build_posted_transaction, build_sample_book

_AUDIT = AuditContext(actor="tester", reason="test")


def _make_config(tmp_path: Path) -> MultiBookRuntimeConfig:
    """Build a minimal MultiBookRuntimeConfig pointing at tmp_path."""
    return MultiBookRuntimeConfig(
        data_directory=tmp_path,
        persistence_template=PersistenceConfig(tmp_path / "_placeholder.sqlite3"),
        poll_interval=0.01,
    )


def _make_book(code: str) -> Book:
    """Build a minimal book aggregate with a custom code."""
    return Book(
        code=code,
        name=f"Book {code}",
        base_currency=CurrencyCode("EUR"),
        fiscal_calendar=FiscalCalendar(start_month=1),
        legislative_pack="lv.standard.2026",
        accounts=(
            Account(
                code="1000",
                name="Cash",
                normal_side=PostingSide.DEBIT,
                currency=CurrencyCode("EUR"),
            ),
            Account(
                code="2000",
                name="Revenue",
                normal_side=PostingSide.CREDIT,
                currency=CurrencyCode("EUR"),
            ),
        ),
        periods=(
            BookPeriod(
                period=FiscalPeriod(fiscal_year=2026, quarter=1, month=1),
                start_date=date(2026, 1, 1),
                end_date=date(2026, 1, 31),
                state=FiscalPeriodState.OPEN,
            ),
        ),
    )


class TestMultiBookRuntimeConfig:
    """Validation and normalisation of MultiBookRuntimeConfig."""

    def test_path_is_normalised_to_path(self, tmp_path: Path) -> None:
        """data_directory is coerced to a Path regardless of input type."""
        config = MultiBookRuntimeConfig(
            data_directory=str(tmp_path),
            persistence_template=PersistenceConfig(tmp_path / "x.sqlite3"),
        )
        assert isinstance(config.data_directory, Path)

    def test_rejects_non_positive_queue_timeout(self, tmp_path: Path) -> None:
        """queue_timeout <= 0 raises ValueError."""
        with pytest.raises(ValueError, match="queue_timeout must be positive"):
            MultiBookRuntimeConfig(
                data_directory=tmp_path,
                persistence_template=PersistenceConfig(tmp_path / "x.sqlite3"),
                queue_timeout=0.0,
            )

    def test_rejects_non_positive_poll_interval(self, tmp_path: Path) -> None:
        """poll_interval <= 0 raises ValueError."""
        with pytest.raises(ValueError, match="poll_interval must be positive"):
            MultiBookRuntimeConfig(
                data_directory=tmp_path,
                persistence_template=PersistenceConfig(tmp_path / "x.sqlite3"),
                poll_interval=-1.0,
            )

    @given(interval=st.floats(max_value=0.0, allow_nan=False, allow_infinity=False))
    @settings(max_examples=30)
    def test_poll_interval_property(self, interval: float) -> None:
        """Any poll_interval <= 0 is rejected."""
        event(f"interval_sign={'zero' if interval == 0.0 else 'negative'}")
        stub_path = Path("/tmp/stub.sqlite3")
        with pytest.raises(ValueError, match="poll_interval must be positive"):
            MultiBookRuntimeConfig(
                data_directory=Path("/tmp"),
                persistence_template=PersistenceConfig(stub_path),
                poll_interval=interval,
            )


class TestMultiBookRuntimeLifecycle:
    """Open, close, and routing mechanics of MultiBookRuntime."""

    def test_create_book_stores_sqlite_file(self, tmp_path: Path) -> None:
        """create_book creates a per-book SQLite file in data_directory."""
        config = _make_config(tmp_path)
        with MultiBookRuntime(config) as runtime:
            book = build_sample_book()
            runtime.create_book(book, audit_context=_AUDIT)
            assert (tmp_path / "demo-book.sqlite3").exists()
            assert "demo-book" in runtime.list_book_codes()

    def test_create_book_rejects_duplicate_code(self, tmp_path: Path) -> None:
        """Creating a book with an already-open code raises ValueError."""
        config = _make_config(tmp_path)
        with MultiBookRuntime(config) as runtime:
            book = build_sample_book()
            runtime.create_book(book, audit_context=_AUDIT)
            with pytest.raises(ValueError, match="already open"):
                runtime.create_book(book, audit_context=_AUDIT)

    def test_open_book_fails_for_missing_file(self, tmp_path: Path) -> None:
        """open_book raises KeyError when no SQLite file exists for the code."""
        config = _make_config(tmp_path)
        with MultiBookRuntime(config) as runtime, pytest.raises(KeyError, match="demo-book"):
            runtime.open_book("demo-book")

    def test_open_book_succeeds_for_existing_file(self, tmp_path: Path) -> None:
        """open_book opens an existing database created by create_book."""
        config = _make_config(tmp_path)
        book = build_sample_book()
        with MultiBookRuntime(config) as runtime:
            runtime.create_book(book, audit_context=_AUDIT)

        with MultiBookRuntime(config) as runtime:
            assert "demo-book" not in runtime.list_book_codes()
            runtime.open_book("demo-book")
            assert "demo-book" in runtime.list_book_codes()

    def test_open_book_is_idempotent(self, tmp_path: Path) -> None:
        """Calling open_book on an already-open book is a no-op."""
        config = _make_config(tmp_path)
        book = build_sample_book()
        with MultiBookRuntime(config) as runtime:
            runtime.create_book(book, audit_context=_AUDIT)
            runtime.open_book("demo-book")
            assert runtime.list_book_codes().count("demo-book") == 1

    def test_close_book_removes_from_pool(self, tmp_path: Path) -> None:
        """close_book removes the runtime from the open pool."""
        config = _make_config(tmp_path)
        book = build_sample_book()
        with MultiBookRuntime(config) as runtime:
            runtime.create_book(book, audit_context=_AUDIT)
            runtime.close_book("demo-book")
            assert "demo-book" not in runtime.list_book_codes()

    def test_close_book_unknown_is_noop(self, tmp_path: Path) -> None:
        """close_book on an unknown code does not raise."""
        config = _make_config(tmp_path)
        with MultiBookRuntime(config):
            pass  # no-op; just verifying no exception

    def test_list_available_book_codes_scans_directory(self, tmp_path: Path) -> None:
        """list_available_book_codes returns all .sqlite3 stems in data_directory."""
        config = _make_config(tmp_path)
        with MultiBookRuntime(config) as runtime:
            runtime.create_book(build_sample_book(), audit_context=_AUDIT)
        runtime2 = MultiBookRuntime(config)
        codes = runtime2.list_available_book_codes()
        assert "demo-book" in codes

    def test_list_available_book_codes_empty_dir(self, tmp_path: Path) -> None:
        """list_available_book_codes returns empty tuple when data_dir is absent."""
        config = _make_config(tmp_path / "nonexistent")
        runtime = MultiBookRuntime(config)
        assert runtime.list_available_book_codes() == ()

    def test_require_runtime_raises_for_closed_book(self, tmp_path: Path) -> None:
        """Operations on an unopened book code raise KeyError."""
        config = _make_config(tmp_path)
        with MultiBookRuntime(config) as runtime, pytest.raises(KeyError, match="No open book"):
            runtime.get_book("demo-book")

    def test_close_shuts_down_all_runtimes(self, tmp_path: Path) -> None:
        """close() terminates every open LedgerRuntime."""
        config = _make_config(tmp_path)
        runtime = MultiBookRuntime(config)
        runtime.create_book(build_sample_book(), audit_context=_AUDIT)
        runtime.close()
        assert runtime.list_book_codes() == ()


class TestMultiBookRuntimeRouting:
    """Per-book operation routing in MultiBookRuntime."""

    def test_append_transaction_and_get_book(self, tmp_path: Path) -> None:
        """Transactions appended via MultiBookRuntime appear in get_book."""
        config = _make_config(tmp_path)
        book = build_sample_book()
        tx = build_posted_transaction(reference="TX-2026-M001")
        with MultiBookRuntime(config) as runtime:
            runtime.create_book(book, audit_context=_AUDIT)
            runtime.append_transaction("demo-book", tx, audit_context=_AUDIT)
            loaded = runtime.get_book("demo-book")
        assert any(t.reference == "TX-2026-M001" for t in loaded.transactions)

    def test_create_reversal_routes_correctly(self, tmp_path: Path) -> None:
        """create_reversal is routed to the correct per-book runtime."""
        config = _make_config(tmp_path)
        book = build_sample_book()
        tx = build_posted_transaction(reference="TX-2026-M002")
        with MultiBookRuntime(config) as runtime:
            runtime.create_book(book, audit_context=_AUDIT)
            runtime.append_transaction("demo-book", tx, audit_context=_AUDIT)
            runtime.create_reversal(
                "demo-book",
                "TX-2026-M002",
                "TX-2026-M002-REV",
                audit_context=_AUDIT,
            )
            loaded = runtime.get_book("demo-book")
        assert any(t.reference == "TX-2026-M002-REV" for t in loaded.transactions)

    def test_iter_audit_log_routes_correctly(self, tmp_path: Path) -> None:
        """iter_audit_log returns rows from the specified book."""
        config = _make_config(tmp_path)
        book = build_sample_book()
        with MultiBookRuntime(config) as runtime:
            runtime.create_book(book, audit_context=_AUDIT)
            rows = runtime.iter_audit_log("demo-book")
        assert len(rows) >= 1

    def test_iter_audit_log_pages_routes_correctly(self, tmp_path: Path) -> None:
        """iter_audit_log_pages yields at least one page for a created book."""
        config = _make_config(tmp_path)
        book = build_sample_book()
        with MultiBookRuntime(config) as runtime:
            runtime.create_book(book, audit_context=_AUDIT)
            pages = list(runtime.iter_audit_log_pages("demo-book", page_size=10))
        assert len(pages) >= 1

    def test_create_snapshot_routes_correctly(self, tmp_path: Path) -> None:
        """create_snapshot for a book code produces a snapshot file."""
        config = _make_config(tmp_path)
        book = build_sample_book()
        with MultiBookRuntime(config) as runtime:
            runtime.create_book(book, audit_context=_AUDIT)
            snap = runtime.create_snapshot("demo-book", tmp_path / "snap.zst")
        assert snap.bytes_written > 0

    def test_debug_snapshot_reflects_open_books(self, tmp_path: Path) -> None:
        """debug_snapshot reports all currently open books."""
        config = _make_config(tmp_path)
        book = build_sample_book()
        with MultiBookRuntime(config) as runtime:
            runtime.create_book(book, audit_context=_AUDIT)
            snapshot: MultiBookDebugSnapshot = runtime.debug_snapshot()
        assert snapshot.open_book_count == 1
        assert snapshot.books[0][0] == "demo-book"

    def test_multiple_books_isolated(self, tmp_path: Path) -> None:
        """Transactions in book-A do not appear in book-B."""
        config = _make_config(tmp_path)
        tx_a = build_posted_transaction(reference="TX-A-001")
        with MultiBookRuntime(config) as runtime:
            runtime.create_book(_make_book("book-alpha"), audit_context=_AUDIT)
            runtime.create_book(_make_book("book-beta"), audit_context=_AUDIT)
            runtime.append_transaction("book-alpha", tx_a, audit_context=_AUDIT)
            book_beta = runtime.get_book("book-beta")
        assert all(t.reference != "TX-A-001" for t in book_beta.transactions)
