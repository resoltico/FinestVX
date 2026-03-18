---
afad: "3.3"
version: "0.7.0"
domain: CHANGELOG
updated: "2026-03-17"
route:
  keywords: [changelog, release notes, version history, breaking changes, migration, fixed, what's new]
  questions: ["what changed in version X?", "what are the breaking changes?", "what was fixed in the latest release?", "what is the release history?"]
---

# Changelog

Notable changes to this project are documented in this file. The format is based on [Keep a Changelog](https://keepachangelog.com/en/1.1.0/),
and this project adheres to [Semantic Versioning](https://semver.org/spec/v2.0.0.html).

## [Unreleased]

## [0.7.0] - 2026-03-18

### Breaking Changes

- **`ILegislativePack.create_localization()` removed** — replaced by
  `localization_boot_config() -> LocalizationBootConfig`; callers must now execute
  `pack.localization_boot_config().boot()` and capture the returned
  `(FluentLocalization, LoadSummary, ...)` evidence tuple
- **`FinestVXService.get_pack_localization()` return type changed** — now returns
  `(FluentLocalization, LoadSummary)` instead of bare `FluentLocalization`; callers must
  write the `LoadSummary` to the audit log
- **`FinestVXService.interpreter_runner` no longer accepts a custom factory** — the field
  is now `init=False` and constructed from `RuntimeConfig` pool size settings
- **`RuntimeConfig` gains `legislative_interpreter_pool_min_size: int = 2` and
  `legislative_interpreter_pool_max_size: int = 8`** — existing `RuntimeConfig` constructions
  without these fields continue to work (defaults are sane); override to tune pool size
- **`LegislativeInterpreterRunner` is now a stateful dataclass** — `close()` must be called
  on shutdown to release interpreter pool resources; `FinestVXService.close()` handles this
  automatically when using the service facade
- **`Book.legislative_pack` no longer has a default value** — previously defaulted to
  `"lv.standard.2026"` (Latvian pack); now required at construction; every `Book()` call must
  provide an explicit `legislative_pack=` argument

### Added

- **`FinestVXService.clear_caches(components=None)`** — clears FTLLexEngine module-level
  caches; accepts an optional `frozenset[str]` to clear only named component families; for
  use in long-running deployments to reclaim locale/CLDR cache memory
- **`validate_ftl_resource_schemas(source, expected_schemas)`** (`finestvx.validation`) —
  validates FTL message variable contracts against declared expected variable sets; returns a
  `ValidationReport` with `FTL_SCHEMA_MISMATCH` or `FTL_SCHEMA_MESSAGE_MISSING` findings;
  exported from `finestvx.validation`
- **`ILegislativePack.configure_localization(l10n)` protocol method** — called by
  `FinestVXService.get_pack_localization()` immediately after boot to register pack-specific
  custom Fluent functions (e.g., `ROUND_EUR`) into the booted `FluentLocalization`; packs
  without custom functions implement it as a no-op
- **`LedgerInvariantError` and `PersistenceIntegrityError` on storage load** — `load_book`
  now raises structured integrity exceptions from `ftllexengine.integrity` when stored data
  fails domain invariants (balance, chart-of-accounts) or cannot be deserialized; previously
  raised bare `ValueError`/`TypeError`
- **`tests/fuzz/` directory** — placeholder package for intensive fuzz-only tests carrying
  `@pytest.mark.fuzz`; excluded from CI test runs
- **`tests/strategy_metrics.py`** — `EXPECTED_EVENTS`, `STRATEGY_CATEGORIES`, and
  `INTENDED_WEIGHTS` constants for runtime strategy coverage metrics during `--deep` fuzz runs
- **Crash recording hook** (`tests/conftest.py`) — `pytest_runtest_makereport` writes
  portable reproduction scripts and JSON metadata to `.hypothesis/crashes/` on test failure

### Changed

- **FTLLexEngine 0.156.0 is now the required minimum** — raises the lower bound from
  `>=0.155.0` to `>=0.156.0`; required for `InterpreterPool`, `LedgerInvariantError`,
  `PersistenceIntegrityError`, the `LocalizationBootConfig.boot()` API inversion, and
  `clear_module_caches(components=...)` selective cache clearing
- **`LegislativeInterpreterRunner` uses `InterpreterPool`** — replaces per-call interpreter
  creation/destruction with a bounded reusable pool (default: `min_size=2`, `max_size=8`);
  amortizes interpreter startup cost across the service lifetime
- **`_load_book_from_connection` wraps deserialization and invariant checks** — structural
  deserialization failures raise `PersistenceIntegrityError`; balance and chart-of-accounts
  violations raise `LedgerInvariantError`; both carry `IntegrityContext` for audit trails
- **`_wal_checkpoint_stats` deleted** — APSW 3.51.3.0+ stubs correctly type `wal_checkpoint()`
  as `tuple[int, int]`; the helper existed solely to contain the `# type: ignore[index]`
  suppression; with that suppression gone the method became a dead-weight single-call wrapper
  around a write/side-effect operation; the `wal_checkpoint(mode=TRUNCATE)` call is inlined
  directly into `create_snapshot`, which is the only call site
- **`LatviaStandard2026Pack`** implements `localization_boot_config()` with declared
  `required_messages` and `message_schemas` contracts for financial-grade boot validation
- **`finestvx.core._validators`** — shared `require_non_empty_text` / `normalize_optional_text`
  extracted to eliminate triplication across `core/models.py`, `core/serialization.py`, and
  `legislation/protocols.py`
- **Account cycle detection** (`core/models.py`) — replaced `ftllexengine.analysis.detect_cycles`
  (general DFS, O(V*E)) with `_find_account_cycle()` (O(V) ancestor walk), removing the
  coupling to FTL graph constants tuned for FTL resource graphs, not chart-of-accounts sizes

### Fixed

- **`validate_ftl_resource_schemas` now accessible from root `finestvx` package** — the
  function was exported from `finestvx.validation` but absent from `finestvx.__all__` and
  `_EXPORT_MAP`; `from finestvx import validate_ftl_resource_schemas` previously raised
  `AttributeError` at runtime
- **`FluentAmount` now exported from `finestvx.core` and root `finestvx`** — the type alias
  `FluentAmount = FluentNumber` was declared in `finestvx.core.types` and present in
  `finestvx.core.types.__all__` but not re-exported through `finestvx.core.__init__` or the
  root facade; `from finestvx.core import FluentAmount` and `from finestvx import FluentAmount`
  both previously raised `ImportError`

## [0.6.0] - 2026-03-16

### Changed

- **FTLLexEngine 0.155.0 is now the direct localization and numeric platform boundary**:
  - removed the `finestvx.localization` package and the package-root `LocalizationConfig` /
    `create_localization` exports; FinestVX no longer carries a local localization boot wrapper
  - `LatviaStandard2026Pack.create_localization()` now boots directly with
    `ftllexengine.localization.LocalizationBootConfig.from_path(...).boot()` and applies
    `MANDATED_CACHE_CONFIG` at that upstream boundary
  - `LedgerEntry` validation and the Latvia pack `ROUND_EUR` function now use
    `FluentNumber.decimal_value` directly instead of reconstructing `Decimal` locally
  - isolated legislative validation now reuses one centralized
    `LegislativeValidationResult -> ValidationReport` projection helper

### Fixed

- **Integrity now matches the new platform boundary**:
  - `ValidationReport.require_valid()` now captures both monotonic and wall-clock timestamps in
    `IntegrityContext`, matching FTLLexEngine's dual-clock integrity evidence model

## [0.5.0] - 2026-03-13

### Changed

- **FTLLexEngine v0.153.0 is now adopted as the direct parsing and concurrency platform boundary**:
  - removed `AmountParseResult` and `parse_amount_input` from `finestvx.localization` and the
    package root; callers now use `ftllexengine.parsing.parse_fluent_number()` directly
  - `LedgerRuntime` now imports `RWLock` from the stable public `ftllexengine.runtime` facade
    instead of the internal `runtime.rwlock` module path
  - FinestVX core modules now import FTLLexEngine fiscal and graph primitives from public facades
    instead of deeper implementation paths, matching the platform-first boundary in both source and
    tests

### Fixed

- **FTLLexEngine and incidental integration backlogs are fully resolved downstream**:
  - adopted the upstream `parse_fluent_number()` and public `runtime.RWLock` exports, clearing the
    FTLLexEngine tracker
  - resolved the remaining incidental deep-import observations by switching the affected FinestVX
    modules and test helpers to public FTLLexEngine facades
  - updated reference docs to describe the current API surface only; the localization reference now
    points reverse-parsing callers to FTLLexEngine directly instead of documenting a removed
    FinestVX wrapper

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
