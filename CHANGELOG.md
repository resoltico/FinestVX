---
afad: "3.3"
version: "0.1.0"
domain: CHANGELOG
updated: "2026-03-12"
route:
  keywords: [changelog, release notes, version history, breaking changes, migration, fixed, what's new]
  questions: ["what changed in version X?", "what are the breaking changes?", "what was fixed in the latest release?", "what is the release history?"]
---

# Changelog

Notable changes to this project are documented in this file. The format is based on [Keep a Changelog](https://keepachangelog.com/en/1.1.0/),
and this project adheres to [Semantic Versioning](https://semver.org/spec/v2.0.0.html).

## [Unreleased]

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
