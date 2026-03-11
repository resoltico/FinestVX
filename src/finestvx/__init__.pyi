"""Type stubs for the finestvx package.

Declares types for lazy-loaded attributes and re-exported symbols.
Mypy cannot infer types through __getattr__, so explicit declarations are required.
"""

# Core domain models
# External re-exports (ftllexengine)
from ftllexengine.introspection import get_cldr_version as get_cldr_version

from .core import Account as Account
from .core import AccountCode as AccountCode
from .core import Book as Book
from .core import BookCode as BookCode
from .core import BookPeriod as BookPeriod
from .core import FiscalDelta as FiscalDelta
from .core import FiscalPeriodState as FiscalPeriodState
from .core import JournalTransaction as JournalTransaction
from .core import LedgerEntry as LedgerEntry
from .core import LegislativePackCode as LegislativePackCode
from .core import MonthEndPolicy as MonthEndPolicy
from .core import PostingSide as PostingSide
from .core import TransactionReference as TransactionReference
from .core import TransactionState as TransactionState
from .core import validate_chart_of_accounts as validate_chart_of_accounts
from .core import validate_transaction_balance as validate_transaction_balance

# Export layer
from .export import ExportArtifact as ExportArtifact
from .export import LedgerExporter as LedgerExporter

# Gateway layer
from .gateway import FinestVXService as FinestVXService
from .gateway import FinestVXServiceConfig as FinestVXServiceConfig
from .gateway import GatewayDebugSnapshot as GatewayDebugSnapshot

# Legislative layer
from .legislation import ILegislativePack as ILegislativePack
from .legislation import LatviaStandard2026Pack as LatviaStandard2026Pack
from .legislation import LegislativeInterpreterRunner as LegislativeInterpreterRunner
from .legislation import LegislativeIssue as LegislativeIssue
from .legislation import LegislativePackMetadata as LegislativePackMetadata
from .legislation import LegislativePackRegistry as LegislativePackRegistry
from .legislation import LegislativeValidationResult as LegislativeValidationResult
from .legislation import create_default_pack_registry as create_default_pack_registry
from .legislation import validate_transaction_isolated as validate_transaction_isolated

# Localization layer
from .localization import AmountParseResult as AmountParseResult
from .localization import LocalizationConfig as LocalizationConfig
from .localization import LocalizationService as LocalizationService
from .localization import parse_amount_input as parse_amount_input
from .localization import parse_currency_input as parse_currency_input
from .localization import parse_date_input as parse_date_input
from .localization import parse_datetime_input as parse_datetime_input
from .localization import parse_decimal_input as parse_decimal_input

# Persistence layer
from .persistence import MANDATED_CACHE_CONFIG as MANDATED_CACHE_CONFIG
from .persistence import AuditContext as AuditContext
from .persistence import AuditLogRecord as AuditLogRecord
from .persistence import DatabaseSnapshot as DatabaseSnapshot
from .persistence import PersistenceConfig as PersistenceConfig
from .persistence import SqliteLedgerStore as SqliteLedgerStore
from .persistence import StoreDebugSnapshot as StoreDebugSnapshot
from .persistence import create_snapshot as create_snapshot

# Runtime layer
from .runtime import LedgerRuntime as LedgerRuntime
from .runtime import RuntimeConfig as RuntimeConfig
from .runtime import RuntimeDebugSnapshot as RuntimeDebugSnapshot

# Validation layer
from .validation import ValidationFinding as ValidationFinding
from .validation import ValidationReport as ValidationReport
from .validation import ValidationSeverity as ValidationSeverity
from .validation import validate_book as validate_book
from .validation import validate_ftl_resource as validate_ftl_resource
from .validation import validate_legislative_transaction as validate_legislative_transaction
from .validation import validate_transaction as validate_transaction

# Module-level metadata (not in __all__)
__version__: str


__all__: list[str] = [
    "MANDATED_CACHE_CONFIG",
    "Account",
    "AccountCode",
    "AmountParseResult",
    "AuditContext",
    "AuditLogRecord",
    "Book",
    "BookCode",
    "BookPeriod",
    "DatabaseSnapshot",
    "ExportArtifact",
    "FinestVXService",
    "FinestVXServiceConfig",
    "FiscalDelta",
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
    "LocalizationService",
    "MonthEndPolicy",
    "PersistenceConfig",
    "PostingSide",
    "RuntimeConfig",
    "RuntimeDebugSnapshot",
    "SqliteLedgerStore",
    "StoreDebugSnapshot",
    "TransactionReference",
    "TransactionState",
    "ValidationFinding",
    "ValidationReport",
    "ValidationSeverity",
    "create_default_pack_registry",
    "create_snapshot",
    "get_cldr_version",
    "parse_amount_input",
    "parse_currency_input",
    "parse_date_input",
    "parse_datetime_input",
    "parse_decimal_input",
    "validate_book",
    "validate_chart_of_accounts",
    "validate_ftl_resource",
    "validate_legislative_transaction",
    "validate_transaction",
    "validate_transaction_balance",
    "validate_transaction_isolated",
]
