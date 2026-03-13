"""FinestVX public package API."""

from __future__ import annotations

from importlib import import_module
from importlib.metadata import PackageNotFoundError
from importlib.metadata import version as _get_version
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from .core import (
        Account,
        AccountCode,
        Book,
        BookCode,
        BookPeriod,
        FiscalPeriodState,
        JournalTransaction,
        LedgerEntry,
        LegislativePackCode,
        PostingSide,
        TransactionReference,
        TransactionState,
        validate_chart_of_accounts,
        validate_transaction_balance,
    )
    from .export import ExportArtifact, LedgerExporter
    from .gateway import (
        FinestVXService,
        FinestVXServiceConfig,
        GatewayDebugSnapshot,
        PostedTransactionResult,
    )
    from .legislation import (
        ILegislativePack,
        LatviaStandard2026Pack,
        LegislativeInterpreterRunner,
        LegislativeIssue,
        LegislativePackMetadata,
        LegislativePackRegistry,
        LegislativeValidationResult,
        create_default_pack_registry,
        validate_transaction_isolated,
    )
    from .localization import (
        AmountParseResult,
        LocalizationConfig,
        create_localization,
        parse_amount_input,
    )
    from .persistence import (
        MANDATED_CACHE_CONFIG,
        AsyncLedgerReader,
        AuditContext,
        AuditLogRecord,
        DatabaseSnapshot,
        PersistenceConfig,
        SqliteLedgerStore,
        StoreConnectionDebugSnapshot,
        StoreDebugSnapshot,
        StoreProfileEvent,
        StoreStatementCacheStats,
        StoreStatusCounter,
        StoreTraceEvent,
        StoreWalCommit,
        StoreWriteReceipt,
        create_snapshot,
    )
    from .runtime import LedgerRuntime, RuntimeConfig, RuntimeDebugSnapshot
    from .validation import (
        ValidationFinding,
        ValidationReport,
        ValidationSeverity,
        validate_book,
        validate_ftl_resource,
        validate_legislative_transaction,
        validate_transaction,
    )

# Version information - auto-populated from package metadata.
# SINGLE SOURCE OF TRUTH: pyproject.toml [project] version
try:
    __version__ = _get_version("finestvx")
except PackageNotFoundError:
    # Development mode: package not installed yet.
    # Run: uv sync
    __version__ = "0.0.0+dev"

__all__ = [
    "MANDATED_CACHE_CONFIG",
    "Account",
    "AccountCode",
    "AmountParseResult",
    "AsyncLedgerReader",
    "AuditContext",
    "AuditLogRecord",
    "Book",
    "BookCode",
    "BookPeriod",
    "DatabaseSnapshot",
    "ExportArtifact",
    "FinestVXService",
    "FinestVXServiceConfig",
    "FiscalPeriodState",
    "GatewayDebugSnapshot",
    "ILegislativePack",
    "JournalTransaction",
    "LatviaStandard2026Pack",
    "LedgerEntry",
    "LedgerExporter",
    "LedgerRuntime",
    "LegislativeInterpreterRunner",
    "LegislativeIssue",
    "LegislativePackCode",
    "LegislativePackMetadata",
    "LegislativePackRegistry",
    "LegislativeValidationResult",
    "LocalizationConfig",
    "PersistenceConfig",
    "PostedTransactionResult",
    "PostingSide",
    "RuntimeConfig",
    "RuntimeDebugSnapshot",
    "SqliteLedgerStore",
    "StoreConnectionDebugSnapshot",
    "StoreDebugSnapshot",
    "StoreProfileEvent",
    "StoreStatementCacheStats",
    "StoreStatusCounter",
    "StoreTraceEvent",
    "StoreWalCommit",
    "StoreWriteReceipt",
    "TransactionReference",
    "TransactionState",
    "ValidationFinding",
    "ValidationReport",
    "ValidationSeverity",
    "create_default_pack_registry",
    "create_localization",
    "create_snapshot",
    "parse_amount_input",
    "validate_book",
    "validate_chart_of_accounts",
    "validate_ftl_resource",
    "validate_legislative_transaction",
    "validate_transaction",
    "validate_transaction_balance",
    "validate_transaction_isolated",
]

_EXPORT_MAP: dict[str, tuple[str, str]] = {
    "Account": ("finestvx.core", "Account"),
    "AccountCode": ("finestvx.core", "AccountCode"),
    "AmountParseResult": ("finestvx.localization", "AmountParseResult"),
    "AsyncLedgerReader": ("finestvx.persistence", "AsyncLedgerReader"),
    "AuditContext": ("finestvx.persistence", "AuditContext"),
    "AuditLogRecord": ("finestvx.persistence", "AuditLogRecord"),
    "Book": ("finestvx.core", "Book"),
    "BookCode": ("finestvx.core", "BookCode"),
    "BookPeriod": ("finestvx.core", "BookPeriod"),
    "DatabaseSnapshot": ("finestvx.persistence", "DatabaseSnapshot"),
    "ExportArtifact": ("finestvx.export", "ExportArtifact"),
    "FiscalPeriodState": ("finestvx.core", "FiscalPeriodState"),
    "FinestVXService": ("finestvx.gateway", "FinestVXService"),
    "FinestVXServiceConfig": ("finestvx.gateway", "FinestVXServiceConfig"),
    "GatewayDebugSnapshot": ("finestvx.gateway", "GatewayDebugSnapshot"),
    "ILegislativePack": ("finestvx.legislation", "ILegislativePack"),
    "JournalTransaction": ("finestvx.core", "JournalTransaction"),
    "LedgerEntry": ("finestvx.core", "LedgerEntry"),
    "LedgerExporter": ("finestvx.export", "LedgerExporter"),
    "LedgerRuntime": ("finestvx.runtime", "LedgerRuntime"),
    "LatviaStandard2026Pack": ("finestvx.legislation", "LatviaStandard2026Pack"),
    "LegislativeInterpreterRunner": (
        "finestvx.legislation",
        "LegislativeInterpreterRunner",
    ),
    "LegislativeIssue": ("finestvx.legislation", "LegislativeIssue"),
    "LegislativePackCode": ("finestvx.core", "LegislativePackCode"),
    "LegislativePackMetadata": ("finestvx.legislation", "LegislativePackMetadata"),
    "LegislativePackRegistry": ("finestvx.legislation", "LegislativePackRegistry"),
    "LegislativeValidationResult": (
        "finestvx.legislation",
        "LegislativeValidationResult",
    ),
    "LocalizationConfig": ("finestvx.localization", "LocalizationConfig"),
    "MANDATED_CACHE_CONFIG": ("finestvx.persistence", "MANDATED_CACHE_CONFIG"),
    "PersistenceConfig": ("finestvx.persistence", "PersistenceConfig"),
    "PostedTransactionResult": ("finestvx.gateway", "PostedTransactionResult"),
    "PostingSide": ("finestvx.core", "PostingSide"),
    "RuntimeConfig": ("finestvx.runtime", "RuntimeConfig"),
    "RuntimeDebugSnapshot": ("finestvx.runtime", "RuntimeDebugSnapshot"),
    "SqliteLedgerStore": ("finestvx.persistence", "SqliteLedgerStore"),
    "StoreConnectionDebugSnapshot": ("finestvx.persistence", "StoreConnectionDebugSnapshot"),
    "StoreDebugSnapshot": ("finestvx.persistence", "StoreDebugSnapshot"),
    "StoreProfileEvent": ("finestvx.persistence", "StoreProfileEvent"),
    "StoreStatementCacheStats": ("finestvx.persistence", "StoreStatementCacheStats"),
    "StoreStatusCounter": ("finestvx.persistence", "StoreStatusCounter"),
    "StoreTraceEvent": ("finestvx.persistence", "StoreTraceEvent"),
    "StoreWalCommit": ("finestvx.persistence", "StoreWalCommit"),
    "StoreWriteReceipt": ("finestvx.persistence", "StoreWriteReceipt"),
    "TransactionReference": ("finestvx.core", "TransactionReference"),
    "TransactionState": ("finestvx.core", "TransactionState"),
    "ValidationFinding": ("finestvx.validation", "ValidationFinding"),
    "ValidationReport": ("finestvx.validation", "ValidationReport"),
    "ValidationSeverity": ("finestvx.validation", "ValidationSeverity"),
    "create_localization": ("finestvx.localization", "create_localization"),
    "create_default_pack_registry": (
        "finestvx.legislation",
        "create_default_pack_registry",
    ),
    "create_snapshot": ("finestvx.persistence", "create_snapshot"),
    "parse_amount_input": ("finestvx.localization", "parse_amount_input"),
    "validate_book": ("finestvx.validation", "validate_book"),
    "validate_chart_of_accounts": ("finestvx.core", "validate_chart_of_accounts"),
    "validate_ftl_resource": ("finestvx.validation", "validate_ftl_resource"),
    "validate_legislative_transaction": (
        "finestvx.validation",
        "validate_legislative_transaction",
    ),
    "validate_transaction": ("finestvx.validation", "validate_transaction"),
    "validate_transaction_balance": ("finestvx.core", "validate_transaction_balance"),
    "validate_transaction_isolated": (
        "finestvx.legislation",
        "validate_transaction_isolated",
    ),
}


def __getattr__(name: str) -> object:
    """Lazy-load public exports on first access."""
    try:
        module_name, attribute_name = _EXPORT_MAP[name]
    except KeyError as error:
        msg = f"module {__name__!r} has no attribute {name!r}"
        raise AttributeError(msg) from error
    module = import_module(module_name)
    value = getattr(module, attribute_name)
    globals()[name] = value
    return value
