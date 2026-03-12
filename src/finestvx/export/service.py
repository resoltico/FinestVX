"""Deterministic export surfaces for FinestVX books."""

from __future__ import annotations

import csv
import json
from dataclasses import dataclass
from io import BytesIO, StringIO
from pathlib import Path
from typing import TYPE_CHECKING

from lxml import etree
from reportlab.lib.pagesizes import A4
from reportlab.pdfgen import canvas

from finestvx.core.serialization import book_to_mapping

if TYPE_CHECKING:
    from finestvx.core.models import Book

__all__ = [
    "ExportArtifact",
    "LedgerExporter",
]


@dataclass(frozen=True, slots=True)
class ExportArtifact:
    """Named binary artifact emitted by an exporter."""

    format_name: str
    media_type: str
    content: bytes


class LedgerExporter:
    """Export FinestVX books into deterministic JSON, CSV, XML, and PDF artifacts."""

    __slots__ = ("_xml_schema",)

    def __init__(self) -> None:
        """Compile the bundled XML schema once for reuse."""
        schema_path = Path(__file__).with_name("ledger.xsd")
        schema_doc = etree.parse(str(schema_path))
        self._xml_schema = etree.XMLSchema(schema_doc)

    def to_json(self, book: Book) -> ExportArtifact:
        """Serialize a book into deterministic UTF-8 JSON."""
        payload = book_to_mapping(book)
        content = json.dumps(
            payload,
            ensure_ascii=False,
            separators=(",", ":"),
            sort_keys=True,
        ).encode("utf-8")
        return ExportArtifact("json", "application/json", content)

    def to_csv(self, book: Book) -> ExportArtifact:
        """Serialize book entries into a deterministic CSV ledger."""
        buffer = StringIO(newline="")
        writer = csv.writer(buffer, lineterminator="\n")
        writer.writerow(
            (
                "book_code",
                "transaction_reference",
                "posted_at",
                "account_code",
                "side",
                "amount",
                "currency",
                "description",
                "tax_rate",
            )
        )
        for transaction in book.transactions:
            for entry in transaction.entries:
                writer.writerow(
                    (
                        book.code,
                        transaction.reference,
                        transaction.posted_at.isoformat(),
                        entry.account_code,
                        entry.side.value,
                        format(entry.decimal_value, "f"),
                        entry.currency,
                        entry.description or "",
                        "" if entry.tax_rate is None else format(entry.tax_rate, "f"),
                    )
                )
        return ExportArtifact("csv", "text/csv", buffer.getvalue().encode("utf-8"))

    def to_xml(self, book: Book) -> ExportArtifact:
        """Serialize a book into schema-validated ledger XML."""
        root = etree.Element("ledger-book")
        root.set("code", book.code)
        root.set("name", book.name)
        root.set("base-currency", book.base_currency)
        root.set("legislative-pack", book.legislative_pack)
        root.set("fiscal-start-month", str(book.fiscal_calendar.start_month))

        accounts_el = etree.SubElement(root, "accounts")
        for account in book.accounts:
            account_el = etree.SubElement(accounts_el, "account")
            account_el.set("code", account.code)
            account_el.set("name", account.name)
            account_el.set("normal-side", account.normal_side.value)
            account_el.set("currency", account.currency)
            if account.parent_code is not None:
                account_el.set("parent-code", account.parent_code)
            account_el.set("allow-posting", str(account.allow_posting).lower())
            account_el.set("active", str(account.active).lower())

        periods_el = etree.SubElement(root, "periods")
        for period in book.periods:
            period_el = etree.SubElement(periods_el, "period")
            period_el.set("fiscal-year", str(period.period.fiscal_year))
            period_el.set("quarter", str(period.period.quarter))
            period_el.set("month", str(period.period.month))
            period_el.set("start-date", period.start_date.isoformat())
            period_el.set("end-date", period.end_date.isoformat())
            period_el.set("state", period.state.value)

        transactions_el = etree.SubElement(root, "transactions")
        for transaction in book.transactions:
            transaction_el = etree.SubElement(transactions_el, "transaction")
            transaction_el.set("reference", transaction.reference)
            transaction_el.set("posted-at", transaction.posted_at.isoformat())
            transaction_el.set("state", transaction.state.value)
            transaction_el.set("description", transaction.description)
            if transaction.reversal_of is not None:
                transaction_el.set("reversal-of", transaction.reversal_of)
            if transaction.period is not None:
                transaction_el.set("period-fiscal-year", str(transaction.period.fiscal_year))
                transaction_el.set("period-quarter", str(transaction.period.quarter))
                transaction_el.set("period-month", str(transaction.period.month))
            for entry in transaction.entries:
                entry_el = etree.SubElement(transaction_el, "entry")
                entry_el.set("account-code", entry.account_code)
                entry_el.set("side", entry.side.value)
                entry_el.set("amount", format(entry.decimal_value, "f"))
                entry_el.set("currency", entry.currency)
                if entry.description is not None:
                    entry_el.set("description", entry.description)
                if entry.tax_rate is not None:
                    entry_el.set("tax-rate", format(entry.tax_rate, "f"))

        self._xml_schema.assertValid(root)
        content = etree.tostring(
            root,
            encoding="utf-8",
            xml_declaration=True,
            pretty_print=False,
        )
        return ExportArtifact("xml", "application/xml", content)

    def validate_xml(self, content: bytes) -> None:
        """Validate exported ledger XML against the bundled XSD."""
        document = etree.fromstring(content)
        self._xml_schema.assertValid(document)

    def to_pdf(self, book: Book) -> ExportArtifact:
        """Render a deterministic PDF summary for the book."""
        buffer = BytesIO()
        pdf = canvas.Canvas(buffer, pagesize=A4, invariant=1, pageCompression=0)
        pdf.setAuthor("FinestVX")
        pdf.setCreator("FinestVX")
        pdf.setTitle(f"Ledger {book.code}")
        pdf.setSubject("Deterministic ledger export")

        x_origin = 48
        y = 800
        line_height = 16
        pdf.setFont("Helvetica-Bold", 14)
        pdf.drawString(x_origin, y, f"FinestVX Book: {book.code}")
        y -= line_height * 2
        pdf.setFont("Helvetica", 10)
        for line in (
            f"Name: {book.name}",
            f"Base currency: {book.base_currency}",
            f"Legislative pack: {book.legislative_pack}",
            f"Accounts: {len(book.accounts)}",
            f"Periods: {len(book.periods)}",
            f"Transactions: {len(book.transactions)}",
        ):
            pdf.drawString(x_origin, y, line)
            y -= line_height
        y -= line_height
        for transaction in book.transactions:
            pdf.setFont("Helvetica-Bold", 10)
            pdf.drawString(
                x_origin,
                y,
                f"{transaction.reference} {transaction.posted_at.isoformat()}",
            )
            y -= line_height
            pdf.setFont("Helvetica", 9)
            pdf.drawString(x_origin + 12, y, transaction.description)
            y -= line_height
            for entry in transaction.entries:
                pdf.drawString(
                    x_origin + 24,
                    y,
                    (
                        f"{entry.side.value} {entry.account_code} "
                        f"{format(entry.decimal_value, 'f')} {entry.currency}"
                    ),
                )
                y -= line_height
            y -= 4
            if y < 80:
                pdf.showPage()
                pdf.setFont("Helvetica", 10)
                y = 800
        pdf.save()
        return ExportArtifact("pdf", "application/pdf", buffer.getvalue())
