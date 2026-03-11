"""Tests for the FinestVX headless service facade."""

from __future__ import annotations

from pathlib import Path

from finestvx.gateway import FinestVXService, FinestVXServiceConfig
from finestvx.persistence import AuditContext, PersistenceConfig
from finestvx.runtime import RuntimeConfig
from tests.support.book_factory import build_posted_transaction, build_sample_book


class TestFinestVXService:
    """Service-level storage, export, and localization checks."""

    def test_service_orchestrates_storage_export_and_localization(self, tmp_path: Path) -> None:
        """The facade coordinates runtime, exporter, and pack localization services."""
        service = FinestVXService(
            FinestVXServiceConfig(RuntimeConfig(PersistenceConfig(tmp_path / "service.sqlite3")))
        )
        book = build_sample_book()

        service.create_book(book, audit_context=AuditContext(actor="tester", reason="bootstrap"))
        service.post_transaction(
            book.code,
            build_posted_transaction(reference="TX-2026-0020"),
            audit_context=AuditContext(actor="tester", reason="post"),
        )
        artifact = service.export_book(book.code, "json")
        localization = service.get_pack_localization(book.legislative_pack)
        text, errors = localization.format_value("latvia-pack-name")

        assert artifact.media_type == "application/json"
        assert b'"code":"demo-book"' in artifact.content
        assert text == "Latvijas standarta pakotne 2026"
        assert errors == ()

        service.close()
