---
afad: "3.3"
version: "0.10.0"
domain: INDEX
updated: "2026-03-19"
route:
  keywords: [finestvx api, bookkeeping core, persistence, runtime, localization boundary, ftllexengine, export, gateway, plugin system, validation, multi book runtime, read replica, book from saft]
  questions: ["what does finestvx export?", "where is persistence documented?", "where is the plugin system documented?", "where is the localization boundary documented?", "where is the gateway facade documented?", "where is validation documented?", "how do I manage multiple books?", "how do I open a read replica?", "how do I import a SAF-T file?"]
---

# FinestVX API Reference Index

## Root Exports

### Core
```python
from finestvx import (
    Account,
    AccountCode,
    Book,
    BookCode,
    BookPeriod,
    FluentAmount,
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
```

### Validation
```python
from finestvx import (
    ValidationFinding,
    ValidationReport,
    ValidationSeverity,
    validate_book,
    validate_ftl_resource,
    validate_ftl_resource_schemas,
    validate_fx_conversion,
    validate_legislative_transaction,
    validate_transaction,
)
```

### Legislation
```python
from finestvx import (
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
```

### Persistence and Runtime
```python
from finestvx import (
    AsyncLedgerReader,
    AuditContext,
    AuditLogRecord,
    DatabaseSnapshot,
    MANDATED_CACHE_CONFIG,
    PersistenceConfig,
    ReadReplica,
    ReadReplicaConfig,
    SqliteLedgerStore,
    StoreConnectionDebugSnapshot,
    StoreDebugSnapshot,
    StoreProfileEvent,
    StoreStatementCacheStats,
    StoreStatusCounter,
    StoreTraceEvent,
    StoreWalCommit,
    StoreWriteReceipt,
    LedgerRuntime,
    MultiBookDebugSnapshot,
    MultiBookRuntime,
    MultiBookRuntimeConfig,
    RuntimeConfig,
    RuntimeDebugSnapshot,
    create_snapshot,
)
```

### Localization
FinestVX exports no localization constructors or parsing helpers from the package root.
Use FTLLexEngine directly; see [DOC_08_Localization.md](DOC_08_Localization.md).

### Export and Gateway
```python
from finestvx import (
    ExportArtifact,
    LedgerExporter,
    book_from_saft,
    FinestVXService,
    FinestVXServiceConfig,
    GatewayDebugSnapshot,
    PostedTransactionResult,
)
```

## Symbol Routing Table

| Symbol or Topic | File | Section |
|:----------------|:-----|:--------|
| `Account`, `BookPeriod`, `LedgerEntry`, `JournalTransaction`, `Book` | [DOC_01_Core.md](DOC_01_Core.md) | Core |
| `validate_chart_of_accounts`, `validate_transaction_balance` | [DOC_01_Core.md](DOC_01_Core.md) | Core |
| `PostingSide`, `FiscalPeriodState`, `TransactionState` | [DOC_02_Types.md](DOC_02_Types.md) | Types |
| `AccountCode`, `BookCode`, `FluentAmount`, `LegislativePackCode`, `TransactionReference` | [DOC_02_Types.md](DOC_02_Types.md) | Types |
| architecture, concurrency, PEP 750/734/784 usage | [DOC_03_Architecture.md](DOC_03_Architecture.md) | Architecture |
| `ILegislativePack`, `LegislativePackMetadata`, `LegislativeIssue`, `LegislativeValidationResult` | [DOC_04_Legislation.md](DOC_04_Legislation.md) | Legislation |
| `LegislativePackRegistry`, `create_default_pack_registry`, `LatviaStandard2026Pack` | [DOC_04_Legislation.md](DOC_04_Legislation.md) | Legislation |
| `LegislativeInterpreterRunner`, `validate_transaction_isolated` | [DOC_04_Legislation.md](DOC_04_Legislation.md) | Legislation |
| error model, integrity exceptions, APSW errors, `TimeoutError` | [DOC_05_Errors.md](DOC_05_Errors.md) | Errors |
| pytest, Hypothesis, scripts, Bash 5 requirement | [DOC_06_Testing.md](DOC_06_Testing.md) | Testing |
| `AuditContext`, `AuditLogRecord`, `PersistenceConfig`, `DatabaseSnapshot` | [DOC_07_Persistence.md](DOC_07_Persistence.md) | Persistence |
| `AsyncLedgerReader`, `StoreWriteReceipt`, `StoreWalCommit`, `StoreTraceEvent`, `StoreProfileEvent` | [DOC_07_Persistence.md](DOC_07_Persistence.md) | Persistence |
| `StoreStatementCacheStats`, `StoreStatusCounter`, `StoreConnectionDebugSnapshot`, `StoreDebugSnapshot`, `SqliteLedgerStore`, `create_snapshot` | [DOC_07_Persistence.md](DOC_07_Persistence.md) | Persistence |
| `SqliteLedgerStore.append_reversal`, `SqliteLedgerStore.iter_audit_log_pages`, `AsyncLedgerReader.iter_audit_log_pages` | [DOC_07_Persistence.md](DOC_07_Persistence.md) | Persistence |
| `ReadReplicaConfig`, `ReadReplica` | [DOC_07_Persistence.md](DOC_07_Persistence.md) | Persistence |
| direct FTLLexEngine localization boot/parsing boundary | [DOC_08_Localization.md](DOC_08_Localization.md) | Localization |
| fallback callbacks, message AST access, FTL schema validation, localization cache audit logs, reverse parsing boundary | [DOC_08_Localization.md](DOC_08_Localization.md) | Localization |
| `ExportArtifact`, `LedgerExporter`, `book_from_saft` | [DOC_09_Exports_Gateway.md](DOC_09_Exports_Gateway.md) | Export and Gateway |
| `RuntimeConfig`, `LedgerRuntime`, `RuntimeDebugSnapshot` | [DOC_09_Exports_Gateway.md](DOC_09_Exports_Gateway.md) | Export and Gateway |
| `MultiBookRuntimeConfig`, `MultiBookDebugSnapshot`, `MultiBookRuntime` | [DOC_09_Exports_Gateway.md](DOC_09_Exports_Gateway.md) | Export and Gateway |
| `FinestVXServiceConfig`, `FinestVXService`, `GatewayDebugSnapshot`, `PostedTransactionResult` | [DOC_09_Exports_Gateway.md](DOC_09_Exports_Gateway.md) | Export and Gateway |
| `LedgerRuntime.create_reversal`, `LedgerRuntime.iter_audit_log_pages`, `FinestVXService.post_reversal`, `FinestVXService.iter_audit_log_pages` | [DOC_09_Exports_Gateway.md](DOC_09_Exports_Gateway.md) | Export and Gateway |
| `FinestVXService.open_read_replica` | [DOC_09_Exports_Gateway.md](DOC_09_Exports_Gateway.md) | Export and Gateway |
| `ValidationSeverity`, `ValidationFinding`, `ValidationReport` | [DOC_10_Validation.md](DOC_10_Validation.md) | Validation |
| `validate_book`, `validate_transaction`, `validate_ftl_resource`, `validate_legislative_transaction` | [DOC_10_Validation.md](DOC_10_Validation.md) | Validation |
| `validate_ftl_resource_schemas`, `validate_fx_conversion` | [DOC_10_Validation.md](DOC_10_Validation.md) | Validation |
| `LedgerInvariantError`, `PersistenceIntegrityError` (from `ftllexengine.integrity`) | [DOC_05_Errors.md](DOC_05_Errors.md) | Errors |
| `ILegislativePack.configure_localization`, `localization_boot_config` | [DOC_04_Legislation.md](DOC_04_Legislation.md) | Legislation |
| `FinestVXService.clear_caches` | [DOC_09_Exports_Gateway.md](DOC_09_Exports_Gateway.md) | Export and Gateway |
| fuzz test placement, `@pytest.mark.fuzz`, `tests/strategy_metrics.py` | [DOC_06_Testing.md](DOC_06_Testing.md) | Testing |
| FTLLexEngine dependency map and platform boundary | [FTLLEXENGINE_INTEGRATION.md](FTLLEXENGINE_INTEGRATION.md) | Integration |
| plugin extension workflow, `ROUND_EUR` custom function | [PLUGIN_SYSTEM.md](PLUGIN_SYSTEM.md) | Plugin System |

## Docs Inventory

```text
docs/
  DOC_00_Index.md
  DOC_01_Core.md
  DOC_02_Types.md
  DOC_03_Architecture.md
  DOC_04_Legislation.md
  DOC_05_Errors.md
  DOC_06_Testing.md
  DOC_07_Persistence.md
  DOC_08_Localization.md
  DOC_09_Exports_Gateway.md
  DOC_10_Validation.md
  FTLLEXENGINE_INTEGRATION.md
  PLUGIN_SYSTEM.md
```
