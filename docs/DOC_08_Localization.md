---
afad: "3.3"
version: "0.2.0"
domain: SECONDARY
updated: "2026-03-12"
route:
  keywords: [localization config, localization service, fluentlocalization, pathresourceloader, fallback events, strict boot, localized parsing, amount parse result, parse decimal, parse date, parse currency, parse amount, cache stats, cache audit log, message variable schemas, ftl schema validation, message ast, term ast, clear cache]
  questions: ["how does finestvx localization work?", "how are FTL resources validated at boot?", "what fallback data is exposed?", "how are localized values parsed back in?", "how do i format a message?", "what is AmountParseResult?", "how do i validate FTL message variables at boot?", "how do i inspect a localized message or term AST?", "how do i retrieve localization cache audit logs?"]
---

# FinestVX Localization Reference

---

## `LocalizationConfig`

Immutable boot configuration for the localization service.

### Signature
```python
@dataclass(frozen=True, slots=True)
class LocalizationConfig:
    locales: tuple[str, ...] | list[str]
    resource_ids: tuple[str, ...] | list[str]
    base_path: Path | str
    use_isolating: bool = True
    strict: bool = True
    require_all_clean: bool = True
    cache: CacheConfig = MANDATED_CACHE_CONFIG
    message_variable_schemas: dict[str, frozenset[str]] = field(default_factory=dict)
```

### Constraints
- `locales` and `resource_ids` are stored as tuples; empty collections are rejected.
- `base_path` is normalized to `Path`.
- `strict=True` causes `FormattingIntegrityError` on any resolution failure or missing message.
- `require_all_clean=True` enforces `LoadSummary.all_clean` at boot (Junk entries fail, not just I/O errors).
- `cache` defaults to `MANDATED_CACHE_CONFIG`.
- `message_variable_schemas`: optional mapping of message IDs to expected variable sets. When non-empty, `LocalizationService` validates each message's declared FTL variables against the specified set at boot. Dict values are normalized to `frozenset` by `__post_init__`. Default: empty dict (no schema validation).

---

## `LocalizationService`

Strict multi-locale formatting service with integrity-enforced boot semantics.

### Signature
```python
class LocalizationService:
    def __init__(
        self,
        config: LocalizationConfig,
        *,
        on_fallback: Callable[[FallbackInfo], None] | None = None,
    ) -> None: ...

    @property
    def summary(self) -> LoadSummary: ...

    @property
    def fallback_events(self) -> tuple[FallbackInfo, ...]: ...

    @property
    def cache_enabled(self) -> bool: ...

    @property
    def cache_config(self) -> CacheConfig | None: ...

    def format_value(
        self,
        message_id: str,
        args: dict[str, FluentValue] | None = None,
    ) -> tuple[str, tuple[object, ...]]: ...

    def format_pattern(
        self,
        message_id: str,
        args: dict[str, FluentValue] | None = None,
        *,
        attribute: str | None = None,
    ) -> tuple[str, tuple[object, ...]]: ...

    def add_function(self, name: str, func: Callable[..., FluentValue]) -> None: ...

    def get_message(self, message_id: str) -> Message | None: ...

    def get_term(self, term_id: str) -> Term | None: ...

    def validate_message_variables(
        self,
        message_id: str,
        expected_variables: frozenset[str] | set[str],
    ) -> MessageVariableValidationResult: ...

    def clear_cache(self) -> None: ...

    def get_cache_audit_log(self) -> dict[str, tuple[WriteLogEntry, ...]] | None: ...

    def get_cache_stats(self) -> LocalizationCacheStats | None: ...

    @staticmethod
    def clear_module_caches() -> None: ...
```

### Constraints
- Constructor: loads all FTL resources eagerly; raises `SyntaxIntegrityError` on Junk entries when `require_all_clean=True`; raises `IntegrityCheckFailedError` on I/O failures.
- Constructor: when `config.message_variable_schemas` is non-empty, validates each message after the load-summary check via `FluentLocalization.get_message()` plus `ftllexengine.validate_message_variables(...)`; missing messages and any missing or extra variables fail boot.
- `summary`: the `LoadSummary` produced at initialization; immutable post-construction.
- `fallback_events`: accumulated `FallbackInfo` records for every locale fallback resolution since boot.
- `cache_enabled`: `True` when FTLLexEngine format caching is active for this service.
- `cache_config`: the active `CacheConfig`, or `None` when caching is disabled.
- `on_fallback`: optional callback invoked synchronously on each fallback; also recorded in `fallback_events`.
- `format_value` / `format_pattern`: delegate to `FluentLocalization`; return `(formatted_string, errors)`.
- `get_message` / `get_term`: expose the highest-priority fallback-chain AST node for structured inspection.
- `validate_message_variables`: returns FTLLexEngine's `MessageVariableValidationResult` for an explicit message schema check; raises `IntegrityCheckFailedError` when the message does not exist in any locale.
- `clear_cache`: clears initialized FTLLexEngine bundle format caches; use this for service-local invalidation.
- `get_cache_audit_log`: returns immutable per-locale cache audit logs for initialized bundles, or `None` when caching is disabled.
- `get_cache_stats`: returns `LocalizationCacheStats | None`; `None` when caching is not active.
- `clear_module_caches`: clears FTLLexEngine module-level caches; this is broader than `clear_cache()` and does not depend on a specific service instance.

### Example: FTL variable schema validation at boot
```python
service = LocalizationService(
    LocalizationConfig(
        locales=("lv-LV",),
        resource_ids=("invoices.ftl",),
        base_path=Path("locales/{locale}"),
        message_variable_schemas={
            "invoice-total": frozenset({"amount", "currency"}),
            "greeting": frozenset({"name"}),
        },
    )
)
# Raises IntegrityCheckFailedError at boot if any declared FTL variable set
# does not match the schema exactly (missing or extra variables both fail).
```

### Example: Structured Schema Inspection
```python
result = service.validate_message_variables(
    "invoice-total",
    frozenset({"amount", "currency"}),
)
assert result.is_valid
```

### Example: Cache Audit Log Access
```python
audit_log = service.get_cache_audit_log()
assert audit_log is not None
assert "lv-LV" in audit_log
```

---

## `AmountParseResult`

Type alias for the return type of `parse_amount_input`.

### Definition
```python
type AmountParseResult = ParseResult[FluentNumber]
```

### Constraints
- Purpose: names `ParseResult[FluentNumber]` — the result of localized decimal parsing into the `FluentNumber` amount type.
- First element: parsed `FluentNumber` or `None` on failure.
- Second element: `tuple[FrozenFluentError, ...]`; empty on success.
- `ParseResult[T]` is the canonical FTLLexEngine generic type for all parsing function returns; importable as `from ftllexengine import ParseResult`.

---

## `parse_decimal_input`

Direct alias of `ftllexengine.parsing.parse_decimal`; parses a localized decimal string into a financial `Decimal`.

### Signature
```python
parse_decimal_input = parse_decimal  # alias
# Effective signature:
def parse_decimal_input(value: str, locale_code: str) -> ParseResult[Decimal]: ...
```

### Parameters
| Name | Type | Req | Semantics |
|:-----|:-----|:----|:----------|
| `value` | `str` | Y | Localized decimal string |
| `locale_code` | `str` | Y | BCP 47 locale code |

### Constraints
- Return: `(Decimal, ())` on success; `(None, errors)` on failure.
- Direct alias — no wrapper overhead; identical behavior to `ftllexengine.parsing.parse_decimal`.

---

## `parse_date_input`

Direct alias of `ftllexengine.parsing.parse_date`; parses a localized date string using CLDR-backed patterns.

### Signature
```python
parse_date_input = parse_date  # alias
# Effective signature:
def parse_date_input(value: str, locale_code: str) -> ParseResult[date]: ...
```

### Parameters
| Name | Type | Req | Semantics |
|:-----|:-----|:----|:----------|
| `value` | `str` | Y | ISO 8601 or locale-format date string |
| `locale_code` | `str` | Y | BCP 47 locale code |

### Constraints
- Return: `(date, ())` on success; `(None, errors)` on failure.
- ISO 8601 format (`YYYY-MM-DD`) is always accepted regardless of locale.
- CLDR locale-specific patterns are accepted for all supported locales, including both the CLDR-defined 2-digit year form and the 4-digit year variant. For example, lv-LV accepts `"15.01.26"` (CLDR short `dd.MM.yy`) and `"15.01.2026"` (4-digit year).

---

## `parse_datetime_input`

Direct alias of `ftllexengine.parsing.parse_datetime`; parses a localized datetime string using CLDR-backed patterns.

### Signature
```python
parse_datetime_input = parse_datetime  # alias
# Effective signature:
def parse_datetime_input(value: str, locale_code: str) -> ParseResult[datetime]: ...
```

### Parameters
| Name | Type | Req | Semantics |
|:-----|:-----|:----|:----------|
| `value` | `str` | Y | ISO 8601 or locale-format datetime string |
| `locale_code` | `str` | Y | BCP 47 locale code |

### Constraints
- Return: `(datetime, ())` on success; `(None, errors)` on failure.
- ISO 8601 format (`YYYY-MM-DD HH:MM:SS`) is always accepted regardless of locale.
- Used to parse the `JournalTransaction.posted_at` field from user input.

---

## `parse_currency_input`

Direct alias of `ftllexengine.parsing.parse_currency`; parses a localized currency string into an amount and code pair.

### Signature
```python
parse_currency_input = parse_currency  # alias
# Effective signature:
def parse_currency_input(value: str, locale_code: str) -> ParseResult[tuple[Decimal, str]]: ...
```

### Parameters
| Name | Type | Req | Semantics |
|:-----|:-----|:----|:----------|
| `value` | `str` | Y | Localized currency string |
| `locale_code` | `str` | Y | BCP 47 locale code |

### Constraints
- Return: `((Decimal, currency_code), ())` on success; `(None, errors)` on failure.

---

## `parse_amount_input`

Function that parses a localized decimal string into a `FluentNumber` amount.

### Signature
```python
def parse_amount_input(value: str, locale_code: str) -> AmountParseResult:
```

### Parameters
| Name | Type | Req | Semantics |
|:-----|:-----|:----|:----------|
| `value` | `str` | Y | Localized decimal string |
| `locale_code` | `str` | Y | BCP 47 locale code |

### Constraints
- Return: `(FluentNumber, ())` on success; `(None, errors)` on failure.
- Wraps `parse_decimal_input` and converts the `Decimal` result into `FluentNumber` via `fluent_number_from_decimal`.
