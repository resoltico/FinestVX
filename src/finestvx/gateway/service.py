"""Headless service facade for FinestVX consumers.

All monetary input strings received from external sources (user input, CSV uploads,
ERP integrations) MUST be parsed via ``ftllexengine.parsing.numbers.parse_decimal(value,
locale)`` before being converted to ``FluentNumber``.  Never call ``Decimal(str(user_input))``
directly — this bypasses locale grouping-separator validation and the built-in DoS guard.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import TYPE_CHECKING, Literal

import ftllexengine

from finestvx.export import ExportArtifact, LedgerExporter
from finestvx.legislation import (
    LegislativeInterpreterRunner,
    LegislativePackRegistry,
    create_default_pack_registry,
)
from finestvx.persistence import AuditContext, DatabaseSnapshot, StoreWriteReceipt
from finestvx.runtime import LedgerRuntime, RuntimeConfig, RuntimeDebugSnapshot
from finestvx.validation import (
    ValidationReport,
    validate_legislative_transaction,
    validate_transaction,
)
from finestvx.validation.service import report_from_legislative_result

if TYPE_CHECKING:
    from pathlib import Path

    from ftllexengine.localization import FluentLocalization, LoadSummary

    from finestvx.core.models import Book, JournalTransaction
    from finestvx.legislation import LegislativeValidationResult

__all__ = [
    "FinestVXService",
    "FinestVXServiceConfig",
    "GatewayDebugSnapshot",
    "PostedTransactionResult",
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


@dataclass(frozen=True, slots=True)
class PostedTransactionResult:
    """Ledger and legislative receipts for one posted transaction."""

    ledger_write: StoreWriteReceipt
    legislative_result: LegislativeValidationResult
    legislative_write: StoreWriteReceipt


@dataclass(slots=True)
class FinestVXService:
    """High-level orchestration facade for storage, validation, and export.

    Long-running deployments should call :meth:`clear_caches` periodically
    (e.g., daily at low-traffic time or after loading large locale batches) to
    release accumulated FTLLexEngine module-level caches.
    """

    config: FinestVXServiceConfig
    registry: LegislativePackRegistry = field(default_factory=create_default_pack_registry)
    exporter: LedgerExporter = field(default_factory=LedgerExporter)
    interpreter_runner: LegislativeInterpreterRunner = field(init=False, repr=False)
    _runtime: LedgerRuntime = field(init=False, repr=False)

    def __post_init__(self) -> None:
        """Start the runtime and interpreter pool after service construction."""
        self._runtime = LedgerRuntime(self.config.runtime)
        self.interpreter_runner = LegislativeInterpreterRunner(
            pool_min_size=self.config.runtime.legislative_interpreter_pool_min_size,
            pool_max_size=self.config.runtime.legislative_interpreter_pool_max_size,
        )

    def close(self) -> None:
        """Close runtime resources and interpreter pool held by the service."""
        self._runtime.close()
        self.interpreter_runner.close()

    def create_book(self, book: Book, *, audit_context: AuditContext) -> StoreWriteReceipt:
        """Persist a new book."""
        return self._runtime.create_book(book, audit_context=audit_context)

    def post_transaction(
        self,
        book_code: str,
        transaction: JournalTransaction,
        *,
        audit_context: AuditContext,
    ) -> PostedTransactionResult:
        """Append a posted transaction and audit its isolated legislative result."""
        ledger_write = self._runtime.append_transaction(
            book_code,
            transaction,
            audit_context=audit_context,
        )
        book = self.get_book(book_code)
        result = self.interpreter_runner.validate(book.legislative_pack, book, transaction)
        legislative_audit_context = AuditContext(
            actor=audit_context.actor,
            reason=f"{audit_context.reason}:legislative-validation",
            session_id=audit_context.session_id,
        )
        legislative_write = self._runtime.append_legislative_result(
            book_code,
            transaction.reference,
            result,
            audit_context=legislative_audit_context,
        )
        return PostedTransactionResult(
            ledger_write=ledger_write,
            legislative_result=result,
            legislative_write=legislative_write,
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
        legislative_report = report_from_legislative_result(result)
        return ValidationReport(core_report.findings + legislative_report.findings)

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

    def get_pack_localization(self, pack_code: str) -> tuple[FluentLocalization, LoadSummary]:
        """Boot the strict localization runtime for a registered pack.

        Executes the full boot sequence: loads all FTL resources, verifies all
        required messages are present, validates all message variable schemas,
        and returns structured boot evidence for the audit trail.

        Args:
            pack_code: Legislative pack code identifying the pack.

        Returns:
            A two-tuple of ``(FluentLocalization, LoadSummary)``.  The
            ``LoadSummary`` must be written to the audit log by the caller.

        Raises:
            ftllexengine.integrity.IntegrityCheckFailedError: If any resource
                fails to load, a required message is absent, or a variable
                schema mismatches.
        """
        pack = self.registry.resolve(pack_code)
        config = pack.localization_boot_config()
        l10n, summary, _schema_results = config.boot()
        pack.configure_localization(l10n)
        return l10n, summary

    def clear_caches(self, components: frozenset[str] | None = None) -> None:
        """Clear FTLLexEngine module-level caches.

        Call periodically in long-running deployments (e.g., daily at low-traffic
        time) or after loading a large batch of new locale data.

        Args:
            components: Optional filter selecting which cache families to clear.
                ``None`` clears all caches.  Known components:
                ``'parsing.currency'``, ``'parsing.dates'``, ``'locale'``,
                ``'runtime.locale_context'``, ``'introspection.message'``,
                ``'introspection.iso'``.
        """
        ftllexengine.clear_module_caches(components)

    def debug_snapshot(self) -> GatewayDebugSnapshot:
        """Return a non-invasive snapshot for service-level introspection."""
        return GatewayDebugSnapshot(
            runtime=self._runtime.debug_snapshot(),
            registered_pack_codes=self.registry.available_pack_codes(),
        )
