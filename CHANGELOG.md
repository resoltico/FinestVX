---
afad: "3.3"
version: "0.4.0"
domain: CHANGELOG
updated: "2026-03-13"
route:
  keywords: [changelog, release notes, version history, breaking changes, migration, fixed, what's new]
  questions: ["what changed in version X?", "what are the breaking changes?", "what was fixed in the latest release?", "what is the release history?"]
---

# Changelog

Notable changes to this project are documented in this file. The format is based on [Keep a Changelog](https://keepachangelog.com/en/1.1.0/),
and this project adheres to [Semantic Versioning](https://semver.org/spec/v2.0.0.html).

## [Unreleased]

## [0.4.0] - 2026-03-13

### Changed

- **FTLLexEngine v0.152.0 is now the direct localization platform boundary**:
  - `LocalizationService` was removed entirely; FinestVX now returns upstream
    `FluentLocalization` instances directly and keeps only `LocalizationConfig` plus
    `create_localization(...)` as the boot-policy seam
  - `create_localization(...)` now delegates one-message and bulk message-contract enforcement to
    `FluentLocalization.validate_message_variables()` and
    `FluentLocalization.validate_message_schemas()` without local wrapper logic
  - locale-boundary validation now uses `ftllexengine.core.locale_utils.require_locale_code()`
    directly; FinestVX no longer carries a duplicate locale canonicalization helper
  - FTLLexEngine imports now use the public facades exposed in v0.152.0, including
    `ftllexengine.FluentNumber`, `ftllexengine.runtime.fluent_function`,
    `ftllexengine.localization.LocalizationCacheStats`, and `CacheAuditLogEntry`
  - Latvia pack locale assets remain under canonical directory names (`lv_lv`, `en_us`) so pack
    metadata, loader substitution, cache keys, and fallback telemetry all use one normalized locale
    model end to end

### Removed

- **Duplicate raw parsing exports deleted from FinestVX**:
  - `parse_decimal_input`, `parse_date_input`, `parse_datetime_input`, and `parse_currency_input`
    were removed from `finestvx.localization` and the package root
  - callers now import raw reverse-parsing functions directly from `ftllexengine.parsing`
  - `parse_amount_input` remains as the only FinestVX parsing adapter because it returns the
    bookkeeping engine's `FluentNumber` amount type

- **Pure FTLLexEngine proxy exports deleted from FinestVX**:
  - `FiscalDelta`, `MonthEndPolicy`, and `get_cldr_version` are no longer exported from
    `finestvx` or `finestvx.core`
  - callers now import those upstream primitives directly from `ftllexengine`
  - FinestVX no longer proxies FTLLexEngine symbols through its own public API surface

### Fixed

- **FTLLexEngine integration backlog resolved end to end**:
  - upstream enhancement items for locale-boundary validation, single-message localization schema
    validation, public runtime extension exports, and public localization telemetry exports are now
    adopted downstream and removed from the FTLLexEngine tracker
  - the localization-wrapper simplification item and the stale `get_currency()` documentation drift
    were both resolved in FinestVX source and docs

## [0.3.0] - 2026-03-12

### Added

- **`persistence`: APSW async reader and typed telemetry surface**:
  - Added `AsyncLedgerReader` for explicit APSW `as_async(...)` read-only access to book snapshots,
    audit rows, and connection telemetry
  - Added typed APSW observability records: `StoreStatementCacheStats`,
    `StoreStatusCounter`, `StoreConnectionDebugSnapshot`, `StoreWalCommit`,
    `StoreTraceEvent`, and `StoreProfileEvent`
  - Added `StoreWriteReceipt` so every persisted mutation carries APSW `changeset` and `patchset`
    bytes plus changed-table metadata

- **`localization.LocalizationService`: structured schema and cache-control helpers**:
  - Added `cache_enabled`, `cache_config`, and `clear_cache()` so callers can inspect and control
    the live FTLLexEngine format-cache boundary directly
  - Added `get_message()` and `get_term()` to surface fallback-chain AST nodes for explicit schema
    inspection and FTL debugging
  - Added `validate_message_variables()` to expose FTLLexEngine's structured
    `MessageVariableValidationResult` at the FinestVX service layer
  - Added `get_cache_audit_log()` so callers can retrieve immutable per-locale FTLLexEngine cache
    audit trails through the FinestVX service facade

### Changed

- **`persistence.PersistenceConfig`: APSW topology and integrity policy expanded**:
  - Added explicit reader-pool and telemetry controls:
    `reader_connection_count`, `reader_checkout_timeout`,
    `writer_statement_cache_size`, `reader_statement_cache_size`,
    `reserve_bytes`, `telemetry_buffer_size`, and optional `vfs_name`
  - Existing databases now hard-fail on `reserve_bytes` mismatch; no backward-compatibility
    shims or migrations are provided

- **`persistence.SqliteLedgerStore`: single connection replaced with writer plus read-only reader pool**:
  - Reads now run through pooled APSW read-only connections while writes remain serialized on one
    writer connection, enabling actual WAL read concurrency instead of multi-threading one shared
    connection
  - Applied APSW hardening and telemetry features directly: modern `set_busy_timeout()`,
    DQS disablement, query-planner optimize hooks, SQLite log forwarding, WAL hook capture,
    `cache_stats()`, and `status()`
  - Removed the raw `execute()` escape hatch entirely; callers now use typed store APIs only

- **`runtime.LedgerRuntime`: lifecycle locking separated from database concurrency**:
  - The runtime `RWLock` now gates API lifecycle and shutdown only; it no longer serializes all
    database reads behind writer-thread store access
  - Write mutations and snapshots are queued as typed command dataclasses and still execute on the
    dedicated writer thread
  - `create_book()`, `append_transaction()`, and `append_legislative_result()` now return
    `StoreWriteReceipt`

- **`gateway.FinestVXService`: write methods now surface receipt data**:
  - `create_book()` now returns the underlying `StoreWriteReceipt`
  - `post_transaction()` now returns `PostedTransactionResult`, containing the ledger write receipt,
    the legislative validation result, and the legislative audit write receipt

- **FTLLexEngine v0.150.0 integration is now fully adopted in FinestVX**:
  - `LocalizationService` boot-time message schema enforcement now uses
    `FluentLocalization.get_message()` plus `ftllexengine.validate_message_variables(...)` instead
    of manual set arithmetic over `get_message_variables()`
  - `LocalizationService.get_cache_audit_log()` now delegates to
    `FluentLocalization.get_cache_audit_log()`, exposing immutable `WriteLogEntry` trails for
    initialized locale bundles
  - `AmountParseResult` now imports the canonical `ParseResult` alias from the FTLLexEngine
    top-level package, matching the upstream diagnostics move
  - `FiscalDelta`, `MonthEndPolicy`, and `get_cldr_version` are now wired through FTLLexEngine's
    top-level exports in the FinestVX core and package root

### Fixed

- **APSW compatibility and observability alignment**:
  - Replaced the legacy APSW alias `setbusytimeout()` with `set_busy_timeout()`
  - Moved WAL commit capture to the post-WAL configuration point so write receipts and debug
    snapshots expose stable `StoreWalCommit` data
  - Updated the persistence, runtime, gateway, and package-edge tests to cover the new reader-pool,
    async-reader, reserve-bytes, receipt, and queued-snapshot architecture

- **Localization integration regression coverage expanded**:
  - Added a Hypothesis property test for structured FTL variable-schema validation, including
    semantic `event()` emission for declared/expected variable counts and valid/invalid outcomes
  - Extended localization edge tests to cover cache controls, direct message/term AST access, and
    per-locale cache audit-log retrieval

## [0.2.0] - 2026-03-12

### Added

- **`localization.LocalizationConfig`: `message_variable_schemas` field for boot-time FTL contract
  enforcement**:
  - `LocalizationConfig` now accepts an optional `message_variable_schemas: dict[str, frozenset[str]]`
    field (default: empty dict); when non-empty, `LocalizationService` validates each listed message's
    declared FTL variables against the expected set immediately after the load-summary check at boot
  - Validation uses `FluentLocalization.get_message_variables(message_id)` to read declared variables
    and raises `IntegrityCheckFailedError` for two failure modes: message not found in any locale, or
    declared variable set does not match expected set exactly (both missing and extra variables fail)
  - Enables callers to enforce FTL message contracts at service construction time rather than at
    first format call, surfacing schema drift in CI

### Changed

- **`core.models.LedgerEntry`: currency decimal precision now uses
  `get_currency_decimal_digits(code)` instead of `get_currency(code).decimal_digits`**:
  - `ftllexengine.introspection.iso.get_currency_decimal_digits(code: str) -> int | None` added in
    FTLLexEngine v0.148.0 returns the ISO 4217 decimal digit count directly without constructing a
    `CurrencyInfo` object or requiring a locale parameter; decimal precision is locale-independent
  - Import updated from `get_currency` to `get_currency_decimal_digits`; validation logic simplified
    by one intermediate variable; external behavior is identical

- **`__init__`: `get_cldr_version` lazy-loaded from `ftllexengine` top-level package**:
  - FTLLexEngine v0.148.0 exports `get_cldr_version` from `ftllexengine.__all__`; the `TYPE_CHECKING`
    import and `_EXPORT_MAP` entry updated to route through `ftllexengine` directly instead of
    `ftllexengine.introspection`

- **`runtime.LedgerRuntime`: private write-queue transport now uses typed command dataclasses**:
  - Internal queue items are now `_CreateBookCommand`, `_AppendTransactionCommand`, and
    `_AppendLegislativeResultCommand` instead of a string `kind` plus heterogeneous payload union
  - Dispatch now pattern-matches directly on command objects, removing stringly-typed branching and
    tightening the single-writer runtime around explicit command shapes
  - `_submit()` now validates queue ingress through `_require_write_command()` and rejects unsupported
    private command objects immediately with `TypeError`

### Fixed

- **`localization.parsing.parse_date_input`: CLDR locale date patterns with 4-digit years now
  accepted**:
  - FTLLexEngine v0.148.0 fixed `parse_date`/`parse_datetime` to generate a `%Y` (4-digit) variant
    alongside every CLDR `%y` (2-digit) pattern; inputs such as `"15.01.2026"` with locale `lv-LV`
    (CLDR short pattern `dd.MM.yy`) now parse correctly — previously returned `(None, errors)` with
    "No matching date pattern found"; fix applies to all locales using `yy` in any CLDR style

- **Ruff strict-mode alignment for production code and stubs**:
  - Type-only imports now live behind `TYPE_CHECKING` across the affected core, export, gateway,
    legislation, localization, persistence, runtime, and validation modules, preserving runtime
    imports only where values are constructed or matched at execution time
  - `src/finestvx/__init__.pyi` no longer carries a module docstring, matching stub-file rules, and
    the runtime test suite now targets the typed private command objects introduced by the runtime
    refactor
  - `persistence.store` and `validation.service` replaced loop-driven list building with direct
    comprehensions or `extend(...)`, eliminating Ruff `PERF401` findings without changing behavior

## [0.1.0] - 2026-03-11

### Added

- Initial release

[0.2.0]: https://github.com/resoltico/ftllexengine/releases/tag/v0.2.0
[0.1.0]: https://github.com/resoltico/ftllexengine/releases/tag/v0.1.0
