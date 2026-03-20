"""Tests for FinestVX deterministic exporters."""

from __future__ import annotations

from pathlib import Path

import pytest
from ftllexengine.integrity import PersistenceIntegrityError

from finestvx.export import LedgerExporter, book_from_saft
from tests.support.book_factory import build_sample_book


class TestLedgerExporter:
    """Determinism and schema checks for exported artifacts."""

    def test_json_csv_xml_pdf_exports_are_deterministic(self) -> None:
        """Repeated exports of the same book produce stable bytes."""
        exporter = LedgerExporter()
        book = build_sample_book(include_transaction=True)

        json_first = exporter.to_json(book)
        json_second = exporter.to_json(book)
        csv_artifact = exporter.to_csv(book)
        xml_first = exporter.to_xml(book)
        xml_second = exporter.to_xml(book)
        pdf_first = exporter.to_pdf(book)
        pdf_second = exporter.to_pdf(book)

        assert json_first.content == json_second.content
        assert csv_artifact.content.startswith(b"book_code,transaction_reference")
        exporter.validate_xml(xml_first.content)
        assert xml_first.content == xml_second.content
        assert pdf_first.content == pdf_second.content


class TestBookFromSaft:
    """Roundtrip, schema validation, and error handling for book_from_saft."""

    def test_saft_roundtrip_minimal_book(self, tmp_path: Path) -> None:
        """A book without transactions survives to_xml → book_from_saft intact."""
        exporter = LedgerExporter()
        book = build_sample_book()
        artifact = exporter.to_xml(book)
        xml_path = tmp_path / "ledger.xml"
        xml_path.write_bytes(artifact.content)

        imported = book_from_saft(xml_path)

        assert imported.code == book.code
        assert imported.name == book.name
        assert imported.base_currency == book.base_currency
        assert imported.legislative_pack == book.legislative_pack
        assert imported.fiscal_calendar.start_month == book.fiscal_calendar.start_month
        assert len(imported.accounts) == len(book.accounts)
        assert len(imported.periods) == len(book.periods)
        assert len(imported.transactions) == 0

    def test_saft_roundtrip_with_transaction(self, tmp_path: Path) -> None:
        """A book with a posted transaction roundtrips correctly."""
        exporter = LedgerExporter()
        book = build_sample_book(include_transaction=True)
        artifact = exporter.to_xml(book)
        xml_path = tmp_path / "ledger_tx.xml"
        xml_path.write_bytes(artifact.content)

        imported = book_from_saft(xml_path)

        assert len(imported.transactions) == 1
        original_tx = book.transactions[0]
        imported_tx = imported.transactions[0]
        assert imported_tx.reference == original_tx.reference
        assert imported_tx.state == original_tx.state
        assert imported_tx.description == original_tx.description
        assert len(imported_tx.entries) == len(original_tx.entries)

    def test_saft_roundtrip_entry_amounts_preserved(self, tmp_path: Path) -> None:
        """Entry amounts and sides survive the XML roundtrip."""
        exporter = LedgerExporter()
        book = build_sample_book(include_transaction=True)
        artifact = exporter.to_xml(book)
        xml_path = tmp_path / "ledger_amounts.xml"
        xml_path.write_bytes(artifact.content)

        imported = book_from_saft(xml_path)

        orig_entries = book.transactions[0].entries
        imp_entries = imported.transactions[0].entries
        for orig, imp in zip(orig_entries, imp_entries, strict=True):
            assert imp.side == orig.side
            assert imp.currency == orig.currency
            assert imp.decimal_value == orig.decimal_value

    def test_book_from_saft_accepts_path_string(self, tmp_path: Path) -> None:
        """book_from_saft accepts a str path in addition to Path."""
        exporter = LedgerExporter()
        book = build_sample_book()
        xml_path = tmp_path / "ledger_str.xml"
        xml_path.write_bytes(exporter.to_xml(book).content)

        imported = book_from_saft(str(xml_path))
        assert imported.code == book.code

    def test_book_from_saft_invalid_xml_raises(self, tmp_path: Path) -> None:
        """Malformed XML raises PersistenceIntegrityError."""
        bad_xml = tmp_path / "bad.xml"
        bad_xml.write_bytes(b"<not valid xml")
        with pytest.raises(PersistenceIntegrityError, match="SAF-T XML parse failed"):
            book_from_saft(bad_xml)

    def test_book_from_saft_schema_violation_raises(self, tmp_path: Path) -> None:
        """XML that parses but fails XSD validation raises PersistenceIntegrityError."""
        bad_xml = tmp_path / "schema_fail.xml"
        bad_xml.write_bytes(
            b'<?xml version=\'1.0\' encoding=\'utf-8\'?>'
            b'<ledger-book code="x" name="y"/>'
        )
        with pytest.raises(PersistenceIntegrityError, match="SAF-T XML schema validation failed"):
            book_from_saft(bad_xml)
