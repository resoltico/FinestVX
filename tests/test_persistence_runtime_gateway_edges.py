"""Additional tests for FinestVX persistence, runtime, gateway, and package edges."""

from __future__ import annotations

import importlib
import importlib.metadata
import sys
from decimal import Decimal
from pathlib import Path
from typing import Any, cast

import pytest

import finestvx
import finestvx.persistence as persistence_module
from finestvx import JournalTransaction, LedgerEntry, PostingSide, TransactionState
from finestvx.gateway import FinestVXService, FinestVXServiceConfig
from finestvx.legislation.subinterpreters import _validate_in_subinterpreter
from finestvx.persistence import AuditContext, PersistenceConfig, SqliteLedgerStore
from finestvx.persistence.backup import create_snapshot as create_snapshot_wrapper
from finestvx.runtime import LedgerRuntime, RuntimeConfig
from finestvx.runtime.service import LedgerRuntime as LedgerRuntimeClass
from tests.support.book_factory import build_posted_transaction, build_sample_book


class _FakeStore:
    """Minimal store used to exercise runtime shutdown branches."""

    def __init__(self) -> None:
        """Initialize close tracking."""
        self.closed = False

    def close(self) -> None:
        """Record that the fake store was closed."""
        self.closed = True


class TestPersistenceAndRuntimeEdges:
    """Coverage for edge branches across store and runtime layers."""

    def test_audit_context_and_persistence_config_validation(self, tmp_path: Path) -> None:
        """Configuration dataclasses reject invalid values."""
        with pytest.raises(ValueError, match="actor cannot be blank"):
            AuditContext(actor=" ", reason="bootstrap")
        with pytest.raises(ValueError, match="reason cannot be blank"):
            AuditContext(actor="tester", reason=" ")
        with pytest.raises(ValueError, match="busy_timeout_ms must be positive"):
            PersistenceConfig(tmp_path / "db.sqlite3", busy_timeout_ms=0)
        with pytest.raises(ValueError, match="wal_auto_checkpoint must be positive"):
            PersistenceConfig(tmp_path / "db.sqlite3", wal_auto_checkpoint=0)
        with pytest.raises(ValueError, match="transaction_mode must be one of"):
            PersistenceConfig(tmp_path / "db.sqlite3", transaction_mode="WRONG")
        with pytest.raises(ValueError, match="reader_connection_count must be positive"):
            PersistenceConfig(tmp_path / "db.sqlite3", reader_connection_count=0)
        with pytest.raises(ValueError, match="reader_checkout_timeout must be positive"):
            PersistenceConfig(tmp_path / "db.sqlite3", reader_checkout_timeout=0)
        with pytest.raises(ValueError, match="writer_statement_cache_size must be non-negative"):
            PersistenceConfig(tmp_path / "db.sqlite3", writer_statement_cache_size=-1)
        with pytest.raises(ValueError, match="reader_statement_cache_size must be non-negative"):
            PersistenceConfig(tmp_path / "db.sqlite3", reader_statement_cache_size=-1)
        with pytest.raises(ValueError, match="reserve_bytes must be between 0 and 255 inclusive"):
            PersistenceConfig(tmp_path / "db.sqlite3", reserve_bytes=256)
        with pytest.raises(ValueError, match="telemetry_buffer_size must be non-negative"):
            PersistenceConfig(tmp_path / "db.sqlite3", telemetry_buffer_size=-1)
        with pytest.raises(ValueError, match="vfs_name must not be blank"):
            PersistenceConfig(tmp_path / "db.sqlite3", vfs_name="   ")
        with pytest.raises(ValueError, match="queue_timeout must be positive"):
            RuntimeConfig(PersistenceConfig(tmp_path / "db.sqlite3"), queue_timeout=0)
        with pytest.raises(ValueError, match="poll_interval must be positive"):
            RuntimeConfig(PersistenceConfig(tmp_path / "db.sqlite3"), poll_interval=0)

    def test_store_error_paths_payload_export_and_snapshot_wrapper(self, tmp_path: Path) -> None:
        """Store helpers cover unknown references, payload export, and uncompressed backups."""
        database_path = tmp_path / "ledger.sqlite3"
        store = SqliteLedgerStore(PersistenceConfig(database_path))
        book = build_sample_book()
        audit_context = AuditContext(actor="tester", reason="bootstrap", session_id="sess-1")
        store.create_book(book, audit_context=audit_context)

        assert store.database_path == database_path
        assert store.export_book_payload(book.code)["code"] == book.code
        assert store.iter_audit_log(limit=1)[0].session_id == "sess-1"

        with pytest.raises(KeyError, match="Unknown book"):
            store.load_book("missing-book")
        with pytest.raises(KeyError, match="Unknown book"):
            store.append_transaction(
                "missing-book",
                build_posted_transaction(reference="TX-2026-4000"),
                audit_context=AuditContext(actor="tester", reason="post"),
            )
        draft_transaction = JournalTransaction(
            reference="TX-2026-4001",
            posted_at=build_posted_transaction(reference="TX-2026-4001").posted_at,
            description="Draft",
            state=TransactionState.DRAFT,
            entries=build_posted_transaction(reference="TX-2026-4001").entries,
        )
        with pytest.raises(ValueError, match="Only posted transactions"):
            store.append_transaction(
                book.code,
                draft_transaction,
                audit_context=AuditContext(actor="tester", reason="post"),
            )
        base_transaction = build_posted_transaction(reference="TX-2026-4002")
        unknown_account_transaction = JournalTransaction(
            reference="TX-2026-4002",
            posted_at=base_transaction.posted_at,
            description="Unknown account",
            entries=(
                base_transaction.entries[0],
                LedgerEntry(
                    account_code="9999",
                    side=PostingSide.CREDIT,
                    amount=base_transaction.entries[1].amount,
                    currency="EUR",
                ),
            ),
        )
        with pytest.raises(ValueError, match="Unknown account code"):
            store.append_transaction(
                book.code,
                unknown_account_transaction,
                audit_context=AuditContext(actor="tester", reason="post"),
            )

        snapshot_path = tmp_path / "ledger.sqlite3.snapshot"
        snapshot = create_snapshot_wrapper(store, snapshot_path, compress=False)

        assert snapshot.compressed is False
        assert snapshot.bytes_written == snapshot_path.stat().st_size
        debug_snapshot = store.debug_snapshot()
        assert debug_snapshot.book_count == 1
        assert debug_snapshot.transaction_count == 0
        assert debug_snapshot.entry_count == 0
        assert debug_snapshot.audit_row_count >= 4
        assert debug_snapshot.writer.statement_cache.size == 256
        assert len(debug_snapshot.readers) == 4

        store.close()

        with pytest.raises(ValueError, match="reserve_bytes mismatch"):
            SqliteLedgerStore(PersistenceConfig(database_path, reserve_bytes=8))

    def test_runtime_context_manager_start_idempotence_and_invalid_submissions(
        self,
        tmp_path: Path,
    ) -> None:
        """Runtime paths cover idempotent start, context management, and payload guards."""
        config = RuntimeConfig(PersistenceConfig(tmp_path / "runtime.sqlite3"), poll_interval=0.01)
        with LedgerRuntime(config) as runtime:
            runtime.start()
            create_receipt = runtime.create_book(
                build_sample_book(),
                audit_context=AuditContext(actor="tester", reason="bootstrap"),
            )
            runtime.create_snapshot(tmp_path / "runtime-snapshot.zst")
            runtime_snapshot = runtime.debug_snapshot()
            assert runtime_snapshot.writer_thread_alive is True
            assert runtime_snapshot.store.book_count == 1
            assert runtime_snapshot.store.audit_row_count >= 4
            assert "books" in create_receipt.changed_tables
            with pytest.raises(TypeError, match="command must be a supported runtime command"):
                runtime._submit(("demo-book", build_posted_transaction(reference="TX-2026-4003")))
            with pytest.raises(TypeError, match="command must be a supported runtime command"):
                runtime._submit(object())

        runtime = object.__new__(LedgerRuntimeClass)
        runtime._started = False
        fake_store = _FakeStore()
        runtime._store = cast("Any", fake_store)
        LedgerRuntimeClass.close(runtime)
        assert fake_store.closed is True


class TestGatewayAndPackageEdges:
    """Coverage for the headless facade, registry helpers, and package init."""

    def test_gateway_validation_export_and_snapshot_paths(self, tmp_path: Path) -> None:
        """The facade exposes all major storage, validation, export, and snapshot operations."""
        service = FinestVXService(
            FinestVXServiceConfig(RuntimeConfig(PersistenceConfig(tmp_path / "service.sqlite3")))
        )
        book = build_sample_book()
        audit_context = AuditContext(actor="tester", reason="bootstrap")
        create_receipt = service.create_book(book, audit_context=audit_context)
        post_result = service.post_transaction(
            book.code,
            build_posted_transaction(reference="TX-2026-5000"),
            audit_context=AuditContext(actor="tester", reason="post"),
        )

        assert service.list_book_codes() == (book.code,)
        assert (
            service.validate_transaction(
                book.code,
                build_posted_transaction(reference="TX-2026-5001"),
            ).accepted
            is True
        )
        assert service.validate_transaction_isolated(
            book.code,
            build_posted_transaction(
                reference="TX-2026-5002",
                amount=Decimal("112.00"),
                tax_rate=Decimal("0.12"),
            ),
        ).accepted is False
        assert service.export_book(book.code, "csv").media_type == "text/csv"
        assert service.export_book(book.code, "xml").media_type == "application/xml"
        assert service.export_book(book.code, "pdf").media_type == "application/pdf"
        assert service.create_snapshot(tmp_path / "service-snapshot.zst").compressed is True
        _l10n, l10n_summary = service.get_pack_localization(book.legislative_pack)
        assert l10n_summary.all_clean is True
        debug_snapshot = service.debug_snapshot()
        audit_rows = service._runtime.iter_audit_log()
        assert debug_snapshot.registered_pack_codes == ("lv.standard.2026",)
        assert debug_snapshot.runtime.store.book_count == 1
        assert debug_snapshot.runtime.store.transaction_count == 1
        assert "books" in create_receipt.changed_tables
        assert "audit_log" in post_result.legislative_write.changed_tables
        assert any(row.table_name == "legislative_validation" for row in audit_rows)

        service.close()

    def test_registry_private_normalization_and_package_lazy_exports(
        self,
        monkeypatch: pytest.MonkeyPatch,
    ) -> None:
        """Registry normalization, subinterpreter helper, and package fallbacks remain stable."""
        assert tuple(iter(finestvx.create_default_pack_registry())) == ("lv.standard.2026",)
        assert len(finestvx.create_default_pack_registry()) == 1
        assert _validate_in_subinterpreter(
            "lv.standard.2026",
            build_sample_book(),
            build_posted_transaction(reference="TX-2026-5003"),
        )[0] == "lv.standard.2026"
        assert persistence_module.create_snapshot is create_snapshot_wrapper
        assert finestvx.StoreWriteReceipt is persistence_module.StoreWriteReceipt
        assert finestvx.AsyncLedgerReader is persistence_module.AsyncLedgerReader

        registry = finestvx.create_default_pack_registry()
        with pytest.raises(TypeError, match="pack_code must be str"):
            registry.resolve(cast("Any", 1))
        with pytest.raises(ValueError, match="pack_code cannot be blank"):
            registry.resolve("   ")
        with pytest.raises(AttributeError, match="has no attribute"):
            persistence_module.__getattr__("missing_export")

        module = sys.modules["finestvx"]
        monkeypatch.setattr(
            importlib.metadata,
            "version",
            lambda name: (_ for _ in ()).throw(importlib.metadata.PackageNotFoundError(name)),
        )
        reloaded = importlib.reload(module)
        assert reloaded.__version__ == "0.0.0+dev"
        monkeypatch.undo()
        importlib.reload(module)
