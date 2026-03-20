"""Validation workflows that connect FinestVX domain rules to FTLLexEngine."""

from __future__ import annotations

from decimal import Decimal
from typing import TYPE_CHECKING

from ftllexengine import parse_ftl
from ftllexengine.diagnostics import WarningSeverity
from ftllexengine.introspection import get_currency_decimal_digits, validate_message_variables
from ftllexengine.syntax.ast import Message, Term
from ftllexengine.validation import validate_resource

from finestvx.core.validation import validate_chart_of_accounts, validate_transaction_balance

from .reports import ValidationFinding, ValidationReport, ValidationSeverity

if TYPE_CHECKING:
    from collections.abc import Mapping

    from ftllexengine.introspection import CurrencyCode

    from finestvx.core.models import Book, JournalTransaction
    from finestvx.legislation.protocols import LegislativeValidationResult
    from finestvx.legislation.registry import LegislativePackRegistry

_FX_SOURCE = "core.fx"

__all__ = [
    "report_from_legislative_result",
    "validate_book",
    "validate_ftl_resource",
    "validate_ftl_resource_schemas",
    "validate_fx_conversion",
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


def validate_ftl_resource_schemas(
    source: str,
    expected_schemas: Mapping[str, frozenset[str]],
) -> ValidationReport:
    """Validate FTL message variable contracts against expected schemas.

    Parses ``source`` and verifies that every message or term listed in
    ``expected_schemas`` declares exactly the expected variable set — no missing
    variables, no extra variables.  This is the pre-flight check that ensures
    all legislative pack FTL resources honour the variable contracts declared in
    the pack's ``localization_boot_config()``.

    Args:
        source: FTL source text to validate.
        expected_schemas: Mapping of message or term ID to expected variable
            names.  Example: ``{"vat-amount": frozenset({"amount"})}``.

    Returns:
        A :class:`ValidationReport` containing an ``FTL_SCHEMA_MISMATCH`` error
        finding for every message whose declared variables deviate from the
        expected set, or an empty report when all contracts are satisfied.
    """
    resource = parse_ftl(source)
    entries_by_id: dict[str, Message | Term] = {
        entry.id.name: entry
        for entry in resource.entries
        if isinstance(entry, (Message, Term))
    }
    findings: list[ValidationFinding] = []
    for message_id, expected_vars in expected_schemas.items():
        entry = entries_by_id.get(message_id)
        if entry is None:
            findings.append(
                ValidationFinding(
                    code="FTL_SCHEMA_MESSAGE_MISSING",
                    message=f"Message {message_id!r} not found in FTL source",
                    severity=ValidationSeverity.ERROR,
                    source="ftl.schema",
                )
            )
            continue
        result = validate_message_variables(entry, expected_vars)
        if not result.is_valid:
            findings.append(
                ValidationFinding(
                    code="FTL_SCHEMA_MISMATCH",
                    message=(
                        f"Message {message_id!r}: expected vars "
                        f"{sorted(expected_vars)}, "
                        f"got {sorted(result.declared_variables)}"
                        + (
                            f" (missing: {sorted(result.missing_variables)})"
                            if result.missing_variables
                            else ""
                        )
                        + (
                            f" (extra: {sorted(result.extra_variables)})"
                            if result.extra_variables
                            else ""
                        )
                    ),
                    severity=ValidationSeverity.ERROR,
                    source="ftl.schema",
                )
            )
    return ValidationReport(tuple(findings))


def validate_fx_conversion(
    transaction: JournalTransaction,
    base_currency: CurrencyCode,
    counter_currency: CurrencyCode,
    rate: Decimal,
) -> ValidationReport:
    """Validate a cross-currency FX conversion entry in a multi-currency transaction.

    Checks that the debit total in ``base_currency`` multiplied by ``rate``
    matches the credit total in ``counter_currency`` within ISO 4217 precision.
    Does not alter the core per-currency zero-sum invariant.

    Args:
        transaction: The transaction under validation.
        base_currency: Currency being sold or exchanged from.
        counter_currency: Currency being purchased or exchanged to.
        rate: Number of counter-currency units per one base-currency unit.

    Returns:
        An empty :class:`ValidationReport` when the conversion reconciles,
        or a report containing ``FX_RATE_INVALID``, ``FX_BASE_CURRENCY_ABSENT``,
        ``FX_COUNTER_CURRENCY_ABSENT``, or ``FX_RATE_MISMATCH`` findings.
    """
    if not rate.is_finite() or rate <= Decimal(0):
        return ValidationReport(
            (
                ValidationFinding(
                    code="FX_RATE_INVALID",
                    message=f"FX rate must be a positive finite Decimal, got {rate!r}",
                    severity=ValidationSeverity.ERROR,
                    source=_FX_SOURCE,
                ),
            )
        )
    base_debit = transaction.debits_by_currency().get(base_currency, Decimal(0))
    counter_credit = transaction.credits_by_currency().get(counter_currency, Decimal(0))
    findings: list[ValidationFinding] = []
    if base_debit == Decimal(0):
        findings.append(
            ValidationFinding(
                code="FX_BASE_CURRENCY_ABSENT",
                message=f"No debit entries found for base currency {base_currency}",
                severity=ValidationSeverity.ERROR,
                source=_FX_SOURCE,
            )
        )
    if counter_credit == Decimal(0):
        findings.append(
            ValidationFinding(
                code="FX_COUNTER_CURRENCY_ABSENT",
                message=f"No credit entries found for counter currency {counter_currency}",
                severity=ValidationSeverity.ERROR,
                source=_FX_SOURCE,
            )
        )
    if findings:
        return ValidationReport(tuple(findings))
    expected_counter = base_debit * rate
    counter_precision = get_currency_decimal_digits(counter_currency)
    precision_digits = counter_precision if counter_precision is not None else 2
    tolerance = Decimal(10) ** -precision_digits
    if abs(expected_counter - counter_credit) > tolerance:
        findings.append(
            ValidationFinding(
                code="FX_RATE_MISMATCH",
                message=(
                    f"FX conversion mismatch: {base_currency} {base_debit} * {rate} = "
                    f"{expected_counter}, but {counter_currency} credit total is {counter_credit}"
                ),
                severity=ValidationSeverity.ERROR,
                source=_FX_SOURCE,
            )
        )
    return ValidationReport(tuple(findings))


def report_from_legislative_result(result: LegislativeValidationResult) -> ValidationReport:
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
    return report_from_legislative_result(result)
