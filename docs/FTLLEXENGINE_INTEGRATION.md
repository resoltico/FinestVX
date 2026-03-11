---
afad: "3.3"
version: "0.1.0"
domain: AUXILIARY
updated: "2026-03-10"
route:
  keywords: [ftllexengine dependency map, fiscal calendar, fiscal delta, iso validation, fluentlocalization, parsing, parse result, cache config, rwlock, graph validation, fluent function]
  questions: ["what exactly does finestvx use from ftllexengine?", "why does finestvx depend on ftllexengine?", "which upstream primitives are active?", "what security boundaries come from ftllexengine?"]
---

# FTLLexEngine Integration Guide

FinestVX uses FTLLexEngine as an upstream platform dependency, not as copied production code.

## Active Upstream Dependencies

### Runtime and Concurrency
- `RWLock`
- `FluentNumber`
- `FluentValue`
- `FunctionRegistry`
- `fluent_function` decorator
- shared registry bootstrap via `get_shared_registry()`
- `CacheConfig`

Why:
- bounded writer-preference locking;
- float-free value boundaries;
- `FluentValue` is the type for localization call arguments (`dict[str, FluentValue]`);
- `fluent_function` is the decorator for locale-aware custom FTL functions (e.g., `ROUND_EUR` in Latvia pack);
- safe plugin function registration;
- shared cache policy expression.

### Fiscal and ISO Boundaries
- `FiscalCalendar`, `FiscalPeriod`
- `FiscalDelta`, `MonthEndPolicy`
- `CurrencyCode`, `TerritoryCode`
- `CurrencyInfo`, `get_currency()`
- `is_valid_currency_code()`, `is_valid_territory_code()`
- `get_cldr_version()`

Why:
- FinestVX does not duplicate fiscal arithmetic or ISO reference tables;
- `FiscalDelta`/`MonthEndPolicy` provide period arithmetic for `BookPeriod` date computation; re-exported from `finestvx.core` and the root `finestvx` package;
- `TerritoryCode` types `LegislativePackMetadata.territory_code`; `is_valid_territory_code()` validates it at construction;
- `get_currency()` → `CurrencyInfo.decimal_digits` enforces ISO 4217 decimal precision in `LedgerEntry` construction (e.g., JPY=0, EUR=2, KWD=3);
- `get_cldr_version()` surfaces the active CLDR data version for compliance auditing; re-exported from the root `finestvx` package.

### Validation and Diagnostics
- `validate_resource()`
- `WarningSeverity`
- `IntegrityCheckFailedError`, `SyntaxIntegrityError`
- `IntegrityContext`
- `FrozenFluentError`

Why:
- FinestVX reuses the six-pass FTL validation pipeline and upstream integrity semantics;
- `IntegrityContext` structures error payloads for `IntegrityCheckFailedError` and `SyntaxIntegrityError`;
- `FrozenFluentError` is the error type returned by all localized parsing functions.

### Localization and Parsing
- `PathResourceLoader`
- `FluentLocalization`
- `LocalizationCacheStats`
- `FallbackInfo`
- `LoadSummary`
- `ParseResult[T]`
- `parse_decimal()`, `parse_date()`, `parse_datetime()`, `parse_currency()`
- `clear_module_caches()`

Why:
- strict multi-locale formatting;
- `LoadSummary` drives boot-time integrity checks (`all_clean` assertion);
- `ParseResult[T]` is the canonical generic type for all parsing function returns; `AmountParseResult = ParseResult[FluentNumber]`;
- `parse_datetime()` supports localized parsing of `JournalTransaction.posted_at` datetime fields;
- locale-aware reverse parsing;
- cache lifecycle coordination;
- fallback observability.

### Graph Analysis
- `detect_cycles()`
- `make_cycle_key()`

Why:
- bounded account-cycle detection without separate graph machinery.

## Re-exported via FinestVX Public API

The following FTLLexEngine symbols are accessible directly from `finestvx`:

| Symbol | FinestVX import |
|:-------|:----------------|
| `FiscalDelta` | `from finestvx import FiscalDelta` |
| `MonthEndPolicy` | `from finestvx import MonthEndPolicy` |
| `get_cldr_version` | `from finestvx import get_cldr_version` |

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
The local `tmp-dir-FTLLexEngine` path is a reference source only.
