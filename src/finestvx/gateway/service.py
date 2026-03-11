"""Headless service facade for FinestVX consumers."""

from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path
from typing import Literal

from finestvx.core.models import Book, JournalTransaction
from finestvx.export import ExportArtifact, LedgerExporter
from finestvx.legislation import (
    LegislativeInterpreterRunner,
    LegislativePackRegistry,
    create_default_pack_registry,
)
from finestvx.localization import LocalizationService
from finestvx.persistence import AuditContext, DatabaseSnapshot
from finestvx.runtime import LedgerRuntime, RuntimeConfig, RuntimeDebugSnapshot
from finestvx.validation import (
    ValidationFinding,
    ValidationReport,
    ValidationSeverity,
    validate_legislative_transaction,
    validate_transaction,
)

__all__ = [
    "FinestVXService",
    "FinestVXServiceConfig",
    "GatewayDebugSnapshot",
]

ExportFormat = Literal["json", "csv", "xml", "pdf"]


@dataclass(frozen=True, slots=True)
class FinestVXServiceConfig:
    """Configuration for the FinestVX headless service facade."""

    runtime: RuntimeConfig


@dataclass(frozen=True, slots=True)
class GatewayDebugSnapshot:
    """Non-invasive service snapshot for runtime and plugin observability."""

    runtime: RuntimeDebugSnapshot
    registered_pack_codes: tuple[str, ...]


@dataclass(slots=True)
class FinestVXService:
    """High-level orchestration facade for storage, validation, and export."""

    config: FinestVXServiceConfig
    registry: LegislativePackRegistry = field(default_factory=create_default_pack_registry)
    exporter: LedgerExporter = field(default_factory=LedgerExporter)
    interpreter_runner: LegislativeInterpreterRunner = field(
        default_factory=LegislativeInterpreterRunner
    )
    _runtime: LedgerRuntime = field(init=False, repr=False)

    def __post_init__(self) -> None:
        """Start the runtime after service construction."""
        self._runtime = LedgerRuntime(self.config.runtime)

    def close(self) -> None:
        """Close runtime resources held by the service."""
        self._runtime.close()

    def create_book(self, book: Book, *, audit_context: AuditContext) -> None:
        """Persist a new book."""
        self._runtime.create_book(book, audit_context=audit_context)

    def post_transaction(
        self,
        book_code: str,
        transaction: JournalTransaction,
        *,
        audit_context: AuditContext,
    ) -> None:
        """Append a posted transaction and audit its isolated legislative result."""
        self._runtime.append_transaction(book_code, transaction, audit_context=audit_context)
        book = self.get_book(book_code)
        result = self.interpreter_runner.validate(book.legislative_pack, book, transaction)
        legislative_audit_context = AuditContext(
            actor=audit_context.actor,
            reason=f"{audit_context.reason}:legislative-validation",
            session_id=audit_context.session_id,
        )
        self._runtime.append_legislative_result(
            book_code,
            transaction.reference,
            result,
            audit_context=legislative_audit_context,
        )

    def get_book(self, book_code: str) -> Book:
        """Load a stored book snapshot."""
        return self._runtime.get_book_snapshot(book_code)

    def list_book_codes(self) -> tuple[str, ...]:
        """Return all stored book codes."""
        return self._runtime.list_book_codes()

    def validate_transaction(
        self,
        book_code: str,
        transaction: JournalTransaction,
    ) -> ValidationReport:
        """Run core and in-process legislative validation for a transaction."""
        book = self.get_book(book_code)
        core_report = validate_transaction(book, transaction)
        legislative_report = validate_legislative_transaction(self.registry, book, transaction)
        return ValidationReport(core_report.findings + legislative_report.findings)

    def validate_transaction_isolated(
        self,
        book_code: str,
        transaction: JournalTransaction,
    ) -> ValidationReport:
        """Run legislative validation inside a subinterpreter."""
        book = self.get_book(book_code)
        core_report = validate_transaction(book, transaction)
        result = self.interpreter_runner.validate(book.legislative_pack, book, transaction)
        legislative_findings = tuple(
            ValidationFinding(
                code=issue.code,
                message=issue.message,
                severity=ValidationSeverity.ERROR,
                source=f"legislation.{result.pack_code}",
            )
            for issue in result.issues
        )
        return ValidationReport(core_report.findings + legislative_findings)

    def export_book(self, book_code: str, format_name: ExportFormat) -> ExportArtifact:
        """Export a stored book into the selected deterministic artifact format."""
        book = self.get_book(book_code)
        match format_name:
            case "json":
                return self.exporter.to_json(book)
            case "csv":
                return self.exporter.to_csv(book)
            case "xml":
                return self.exporter.to_xml(book)
            case "pdf":
                return self.exporter.to_pdf(book)

    def create_snapshot(
        self,
        output_path: Path | str,
        *,
        compress: bool = True,
    ) -> DatabaseSnapshot:
        """Create a database snapshot from the underlying runtime store."""
        return self._runtime.create_snapshot(output_path, compress=compress)

    def get_pack_localization(self, pack_code: str) -> LocalizationService:
        """Create the strict localization service for a registered pack."""
        pack = self.registry.resolve(pack_code)
        return pack.create_localization()

    def debug_snapshot(self) -> GatewayDebugSnapshot:
        """Return a non-invasive snapshot for service-level introspection."""
        return GatewayDebugSnapshot(
            runtime=self._runtime.debug_snapshot(),
            registered_pack_codes=self.registry.available_pack_codes(),
        )
