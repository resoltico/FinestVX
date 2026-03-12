"""Validation workflows that connect FinestVX domain rules to FTLLexEngine."""

from __future__ import annotations

from typing import TYPE_CHECKING

from ftllexengine.diagnostics.validation import WarningSeverity
from ftllexengine.validation import validate_resource

from finestvx.core.validation import validate_chart_of_accounts, validate_transaction_balance

from .reports import ValidationFinding, ValidationReport, ValidationSeverity

if TYPE_CHECKING:
    from collections.abc import Mapping

    from finestvx.core.models import Book, JournalTransaction
    from finestvx.legislation.protocols import LegislativeValidationResult
    from finestvx.legislation.registry import LegislativePackRegistry

__all__ = [
    "validate_book",
    "validate_ftl_resource",
    "validate_legislative_transaction",
    "validate_transaction",
]


def _report_from_exception(code: str, message: str, source: str) -> ValidationReport:
    """Convert a domain exception into a single-finding report."""
    return ValidationReport(
        (
            ValidationFinding(
                code=code,
                message=message,
                severity=ValidationSeverity.ERROR,
                source=source,
            ),
        )
    )


def validate_book(book: Book) -> ValidationReport:
    """Validate chart and transaction invariants for a full book aggregate."""
    try:
        validate_chart_of_accounts(book.accounts)
    except (TypeError, ValueError) as error:
        return _report_from_exception("BOOK_CHART_INVALID", str(error), "core.book")

    findings: list[ValidationFinding] = []
    account_codes = {account.code for account in book.accounts}
    for transaction in book.transactions:
        report = validate_transaction(book, transaction)
        findings.extend(report.findings)
        findings.extend(
            [
                ValidationFinding(
                    code="BOOK_UNKNOWN_ACCOUNT_REFERENCE",
                    message=(
                        f"Transaction {transaction.reference} references unknown account "
                        f"{entry.account_code}"
                    ),
                    severity=ValidationSeverity.ERROR,
                    source="core.book",
                )
                for entry in transaction.entries
                if entry.account_code not in account_codes
            ]
        )
    return ValidationReport(tuple(findings))


def validate_transaction(book: Book, transaction: JournalTransaction) -> ValidationReport:
    """Validate a transaction within the context of a book."""
    try:
        validate_transaction_balance(transaction)
    except (TypeError, ValueError) as error:
        return _report_from_exception(
            "TRANSACTION_BALANCE_INVALID",
            str(error),
            "core.transaction",
        )

    known_accounts = {account.code for account in book.accounts}
    findings: list[ValidationFinding] = [
        ValidationFinding(
            code="TRANSACTION_UNKNOWN_ACCOUNT",
            message=f"Unknown account code: {entry.account_code}",
            severity=ValidationSeverity.ERROR,
            source="core.transaction",
        )
        for entry in transaction.entries
        if entry.account_code not in known_accounts
    ]
    return ValidationReport(tuple(findings))


def _severity_from_warning(severity: WarningSeverity) -> ValidationSeverity:
    """Map FTLLexEngine warning severities into FinestVX severities."""
    match severity:
        case WarningSeverity.CRITICAL:
            return ValidationSeverity.ERROR
        case WarningSeverity.WARNING:
            return ValidationSeverity.WARNING
        case WarningSeverity.INFO:
            return ValidationSeverity.INFO


def validate_ftl_resource(
    source: str,
    *,
    known_messages: frozenset[str] | None = None,
    known_terms: frozenset[str] | None = None,
    known_msg_deps: Mapping[str, frozenset[str]] | None = None,
    known_term_deps: Mapping[str, frozenset[str]] | None = None,
) -> ValidationReport:
    """Run FTLLexEngine's six-pass static validation pipeline for an FTL resource."""
    result = validate_resource(
        source,
        known_messages=known_messages,
        known_terms=known_terms,
        known_msg_deps=known_msg_deps,
        known_term_deps=known_term_deps,
    )
    findings: list[ValidationFinding] = [
        ValidationFinding(
            code=error.code.name,
            message=error.message,
            severity=ValidationSeverity.ERROR,
            source="ftl.resource",
        )
        for error in result.errors
    ]
    findings.extend(
        [
            ValidationFinding(
                code=warning.code.name,
                message=warning.message,
                severity=_severity_from_warning(warning.severity),
                source="ftl.resource",
            )
            for warning in result.warnings
        ]
    )
    findings.extend(
        [
            ValidationFinding(
                code="PARSE_JUNK",
                message=annotation.message,
                severity=ValidationSeverity.ERROR,
                source="ftl.resource",
            )
            for annotation in result.annotations
        ]
    )
    return ValidationReport(tuple(findings))


def _pack_result_to_report(result: LegislativeValidationResult) -> ValidationReport:
    """Convert legislative issues into a FinestVX validation report."""
    return ValidationReport(
        tuple(
            ValidationFinding(
                code=issue.code,
                message=issue.message,
                severity=ValidationSeverity.ERROR,
                source=f"legislation.{result.pack_code}",
            )
            for issue in result.issues
        )
    )


def validate_legislative_transaction(
    registry: LegislativePackRegistry,
    book: Book,
    transaction: JournalTransaction,
) -> ValidationReport:
    """Validate a transaction against its configured legislative pack."""
    pack = registry.resolve(book.legislative_pack)
    result = pack.validate_transaction(book, transaction)
    return _pack_result_to_report(result)
