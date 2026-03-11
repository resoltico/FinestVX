"""Tests for FinestVX deterministic exporters."""

from __future__ import annotations

from finestvx.export import LedgerExporter
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
