"""Deterministic export surfaces for FinestVX books."""

from __future__ import annotations

import csv
import json
import time
from dataclasses import dataclass
from datetime import date, datetime
from decimal import Decimal
from io import BytesIO, StringIO
from pathlib import Path

from ftllexengine import FiscalCalendar, FiscalPeriod, make_fluent_number
from ftllexengine.integrity import IntegrityContext, PersistenceIntegrityError
from ftllexengine.introspection import CurrencyCode
from lxml import etree
from reportlab.lib.pagesizes import A4
from reportlab.pdfgen import canvas

from finestvx.core.enums import FiscalPeriodState, PostingSide, TransactionState
from finestvx.core.models import Account, Book, BookPeriod, JournalTransaction, LedgerEntry
from finestvx.core.serialization import book_to_mapping

__all__ = [
    "ExportArtifact",
    "LedgerExporter",
    "book_from_saft",
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


def _parse_entry(entry_el: etree._Element) -> LedgerEntry:
    """Parse a single ``<entry>`` element into a LedgerEntry."""
    tax_rate_str = entry_el.get("tax-rate")
    return LedgerEntry(
        account_code=entry_el.get("account-code", ""),
        side=PostingSide(entry_el.get("side", "")),
        amount=make_fluent_number(Decimal(entry_el.get("amount", "0"))),
        currency=CurrencyCode(entry_el.get("currency", "")),
        description=entry_el.get("description"),
        tax_rate=Decimal(tax_rate_str) if tax_rate_str is not None else None,
    )


def _parse_transaction(tx_el: etree._Element) -> JournalTransaction:
    """Parse a single ``<transaction>`` element into a JournalTransaction."""
    period: FiscalPeriod | None = None
    if tx_el.get("period-fiscal-year") is not None:
        period = FiscalPeriod(
            fiscal_year=int(tx_el.get("period-fiscal-year", "0")),
            quarter=int(tx_el.get("period-quarter", "0")),
            month=int(tx_el.get("period-month", "0")),
        )
    return JournalTransaction(
        reference=tx_el.get("reference", ""),
        posted_at=datetime.fromisoformat(tx_el.get("posted-at", "")),
        state=TransactionState(tx_el.get("state", "")),
        description=tx_el.get("description", ""),
        entries=tuple(_parse_entry(e) for e in tx_el),
        reversal_of=tx_el.get("reversal-of"),
        period=period,
    )


def _book_from_element(root: etree._Element) -> Book:
    """Parse a validated ``<ledger-book>`` element into a Book aggregate."""
    fiscal_calendar = FiscalCalendar(start_month=int(root.get("fiscal-start-month", "1")))

    accounts_el = root.find("accounts")
    accounts = (
        [
            Account(
                code=account_el.get("code", ""),
                name=account_el.get("name", ""),
                normal_side=PostingSide(account_el.get("normal-side", "")),
                currency=CurrencyCode(account_el.get("currency", "")),
                parent_code=account_el.get("parent-code"),
                allow_posting=account_el.get("allow-posting", "true") == "true",
                active=account_el.get("active", "true") == "true",
            )
            for account_el in accounts_el
        ]
        if accounts_el is not None
        else []
    )

    periods_el = root.find("periods")
    periods = (
        [
            BookPeriod(
                period=FiscalPeriod(
                    fiscal_year=int(period_el.get("fiscal-year", "0")),
                    quarter=int(period_el.get("quarter", "0")),
                    month=int(period_el.get("month", "0")),
                ),
                start_date=date.fromisoformat(period_el.get("start-date", "")),
                end_date=date.fromisoformat(period_el.get("end-date", "")),
                state=FiscalPeriodState(period_el.get("state", "")),
            )
            for period_el in periods_el
        ]
        if periods_el is not None
        else []
    )

    transactions_el = root.find("transactions")
    transactions = (
        [_parse_transaction(tx_el) for tx_el in transactions_el]
        if transactions_el is not None
        else []
    )

    return Book(
        code=root.get("code", ""),
        name=root.get("name", ""),
        base_currency=CurrencyCode(root.get("base-currency", "")),
        legislative_pack=root.get("legislative-pack", ""),
        fiscal_calendar=fiscal_calendar,
        accounts=tuple(accounts),
        periods=tuple(periods),
        transactions=tuple(transactions),
    )


def book_from_saft(path: Path | str) -> Book:
    """Import a FinestVX SAF-T XML file and return the corresponding Book aggregate.

    Validates the file against the bundled XSD schema before parsing. Raises
    :class:`~ftllexengine.integrity.PersistenceIntegrityError` on any parse,
    schema, or domain invariant failure.

    Args:
        path: Filesystem path to the SAF-T XML file.

    Returns:
        The reconstructed :class:`~finestvx.core.models.Book` aggregate.

    Raises:
        PersistenceIntegrityError: If the file cannot be parsed, fails schema
            validation, or contains data that violates domain invariants.
    """
    source_path = Path(path)
    integrity_context = IntegrityContext(
        component="export.saft",
        operation="book_from_saft",
        key=str(source_path),
        timestamp=time.monotonic(),
    )
    schema_path = Path(__file__).with_name("ledger.xsd")
    schema_doc = etree.parse(str(schema_path))
    xml_schema = etree.XMLSchema(schema_doc)
    try:
        document = etree.parse(str(source_path))
    except etree.XMLSyntaxError as error:
        msg = f"SAF-T XML parse failed: {error}"
        raise PersistenceIntegrityError(msg, integrity_context) from error
    try:
        xml_schema.assertValid(document)
    except etree.DocumentInvalid as error:
        msg = f"SAF-T XML schema validation failed: {error}"
        raise PersistenceIntegrityError(msg, integrity_context) from error
    try:
        return _book_from_element(document.getroot())
    except (ValueError, TypeError) as error:
        msg = f"SAF-T import domain invariant violation: {error}"
        raise PersistenceIntegrityError(msg, integrity_context) from error
