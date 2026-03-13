---
afad: "3.3"
version: "0.4.0"
domain: AUXILIARY
updated: "2026-03-13"
route:
  keywords: [ftllexengine dependency map, fluentlocalization, require locale code, validate message variables, make fluent number, parse fluent number, normalized locale code, cache config, rwlock, graph validation, fluent function, cache audit log]
  questions: ["what exactly does finestvx use from ftllexengine?", "why does finestvx depend on ftllexengine?", "which upstream primitives are active?", "what security boundaries come from ftllexengine?", "what functionality did finestvx delete in favor of ftllexengine?"]
---

# FTLLexEngine Integration Guide

FinestVX uses FTLLexEngine as an upstream platform dependency, not as copied production code.

## Active Upstream Dependencies

### Runtime and Concurrency
- `RWLock`
- `FluentNumber`
- `make_fluent_number()`
- `FunctionRegistry`
- `fluent_function` decorator
- shared registry bootstrap via `get_shared_registry()`
- `CacheConfig`
- `CacheAuditLogEntry`

Why:
- bounded writer-preference locking via the public `ftllexengine.runtime` facade;
- float-free value boundaries;
- canonical `FluentNumber` construction without local precision helpers;
- `fluent_function` is the decorator for locale-aware custom FTL functions (e.g., `ROUND_EUR` in Latvia pack);
- safe plugin function registration;
- shared cache policy expression;
- public cache audit-log typing without internal imports.

### Fiscal and ISO Boundaries
- `FiscalCalendar`, `FiscalPeriod`
- `CurrencyCode`, `TerritoryCode`
- `get_currency_decimal_digits()`
- `is_valid_currency_code()`, `is_valid_territory_code()`
- `require_locale_code()`

Why:
- FinestVX does not duplicate fiscal arithmetic or ISO reference tables;
- `TerritoryCode` types `LegislativePackMetadata.territory_code`; `is_valid_territory_code()` validates it at construction;
- locale-bearing FinestVX metadata/config is validated and canonicalized with `require_locale_code()`;
- `get_currency_decimal_digits()` enforces ISO 4217 decimal precision in `LedgerEntry` construction (e.g., JPY=0, EUR=2, KWD=3).

### Validation and Diagnostics
- `validate_resource()`
- `validate_message_variables()`
- `MessageVariableValidationResult`
- `WarningSeverity`
- `IntegrityCheckFailedError`, `SyntaxIntegrityError`
- `IntegrityContext`
- `FrozenFluentError`

Why:
- FinestVX reuses the six-pass FTL validation pipeline and upstream integrity semantics;
- FinestVX now delegates strict boot validation to `FluentLocalization.require_clean()`,
  `FluentLocalization.validate_message_variables()`, and
  `FluentLocalization.validate_message_schemas()` instead of maintaining local summary/schema glue;
- strict parse failures still surface as `SyntaxIntegrityError` during eager resource loading;
- `IntegrityContext` structures error payloads for `IntegrityCheckFailedError`;
- `FrozenFluentError` is the error type returned by all localized parsing functions.

### Localization and Parsing
- `PathResourceLoader`
- `FluentLocalization`
- `FluentLocalization.require_clean()`
- `FluentLocalization.validate_message_variables()`
- `FluentLocalization.validate_message_schemas()`
- `FluentLocalization.get_message()`, `FluentLocalization.get_term()`
- `FluentLocalization.get_cache_audit_log()`
- `LocalizationCacheStats`
- `CacheAuditLogEntry`
- `FallbackInfo`
- `LoadSummary`
- `ParseResult[T]`
- `parse_decimal()`, `parse_fluent_number()`, `parse_date()`, `parse_datetime()`, `parse_currency()`

Why:
- strict multi-locale formatting;
- `require_clean()` is the strict boot-time load-integrity gate;
- `validate_message_variables()` and `validate_message_schemas()` are the strict boot-time message-contract gates;
- `FluentLocalization.get_message()`/`get_term()` expose AST nodes for schema validation and
  explicit localization inspection;
- `FluentLocalization.get_cache_audit_log()` exposes immutable per-locale cache audit trails for
  initialized bundles without leaking raw cache objects;
- `CacheAuditLogEntry` is the public audit-log entry type returned by those cache APIs;
- `ParseResult[T]` is the canonical generic type for all parsing function returns;
- FinestVX no longer wraps reverse parsing; callers import `parse_fluent_number()` and the raw
  decimal/date/datetime/currency parsing functions directly from `ftllexengine.parsing`;
- locale-aware reverse parsing;
- cache lifecycle coordination;
- fallback observability.

## Integrity and Security Boundaries

- `PathResourceLoader` rejects path traversal in locale codes and resource identifiers, then
  resolves paths before enforcing the root-directory boundary.
- `IntegrityCache` is the active format-cache model behind FinestVX localization: BLAKE2b-backed
  entry checksums, key-binding verification, write-once conflict detection, strict corruption
  failures, and bounded audit logging.
- `CacheAuditLogEntry` audit records are now reachable through the FTLLexEngine facade APIs, so
  FinestVX can consume immutable cache-audit evidence without touching private cache internals.
- FinestVX hard-codes `CacheConfig(write_once=True, integrity_strict=True, enable_audit=True,
  max_audit_entries=50000)` as `MANDATED_CACHE_CONFIG` and uses it as the default localization and
  persistence-adjacent FTLLexEngine cache policy.
- APSW-side durability and FTLLexEngine-side cache integrity are intentionally complementary:
  SQLite WAL, reserve-bytes enforcement, audit triggers, and changesets protect persisted ledger
  state, while FTLLexEngine protects localized formatting state against silent cache corruption.

### Graph Analysis
- `detect_cycles()`
- `make_cycle_key()`

Why:
- bounded account-cycle detection without separate graph machinery.

## Public Boundary Rule

FinestVX no longer re-exports FTLLexEngine symbols from its own public API.
Callers import upstream primitives directly from `ftllexengine`.

## Functionality FinestVX Deleted in Favor of FTLLexEngine

- local `FluentNumber` construction helpers were removed in favor of `make_fluent_number()`;
- local locale-boundary validation helpers were removed in favor of `require_locale_code()`;
- local localization wrapper classes were removed in favor of returning `FluentLocalization`;
- local one-message and bulk schema wrappers were removed in favor of
  `validate_message_variables()` and `validate_message_schemas()`;
- local `parse_amount_input` and `AmountParseResult` were removed; callers use
  `ftllexengine.parsing.parse_fluent_number()` directly;
- duplicate raw parse aliases were removed; callers use `ftllexengine.parsing` directly.

## Why FinestVX Uses FTLLexEngine

FTLLexEngine is the source of truth for:
- fiscal primitives and period arithmetic;
- locale and FTL handling;
- float-free numeric values;
- concurrency primitives;
- ISO validation and currency precision;
- static FTL validation and integrity exceptions.

That keeps FinestVX focused on bookkeeping, persistence, runtime orchestration,
and service composition instead of rebuilding those foundational systems.

## Reference Tree Rule

FinestVX production code must import FTLLexEngine from PyPI.
The local `.tmp-dir-FTLLexEngine-src` path is a reference source only.
