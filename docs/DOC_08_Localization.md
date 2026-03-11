---
afad: "3.3"
version: "0.1.0"
domain: SECONDARY
updated: "2026-03-09"
route:
  keywords: [localization config, localization service, fluentlocalization, pathresourceloader, fallback events, strict boot, localized parsing, amount parse result, parse decimal, parse date, parse currency, parse amount, cache stats]
  questions: ["how does finestvx localization work?", "how are FTL resources validated at boot?", "what fallback data is exposed?", "how are localized values parsed back in?", "how do i format a message?", "what is AmountParseResult?"]
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
```

### Constraints
- `locales` and `resource_ids` are stored as tuples; empty collections are rejected.
- `base_path` is normalized to `Path`.
- `strict=True` causes `FormattingIntegrityError` on any resolution failure or missing message.
- `require_all_clean=True` enforces `LoadSummary.all_clean` at boot (Junk entries fail, not just I/O errors).
- `cache` defaults to `MANDATED_CACHE_CONFIG`.

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

    def get_cache_stats(self) -> LocalizationCacheStats | None: ...

    @staticmethod
    def clear_module_caches() -> None: ...
```

### Constraints
- Constructor: loads all FTL resources eagerly; raises `SyntaxIntegrityError` on Junk entries when `require_all_clean=True`; raises `IntegrityCheckFailedError` on I/O failures.
- `summary`: the `LoadSummary` produced at initialization; immutable post-construction.
- `fallback_events`: accumulated `FallbackInfo` records for every locale fallback resolution since boot.
- `on_fallback`: optional callback invoked synchronously on each fallback; also recorded in `fallback_events`.
- `format_value` / `format_pattern`: delegate to `FluentLocalization`; return `(formatted_string, errors)`.
- `get_cache_stats`: returns `LocalizationCacheStats | None`; `None` when caching is not active.
- `clear_module_caches`: clears all FTLLexEngine bounded module-level caches.

---

## `AmountParseResult`

Type alias for the return type of `parse_amount_input`.

### Definition
```python
type AmountParseResult = ParseResult[FluentNumber]
```

### Constraints
- Purpose: names `ParseResult[FluentNumber]` from `ftllexengine.parsing` — the result of localized decimal parsing into the `FluentNumber` amount type.
- First element: parsed `FluentNumber` or `None` on failure.
- Second element: `tuple[FrozenFluentError, ...]`; empty on success.
- `ParseResult[T]` is the canonical FTLLexEngine generic type for all parsing function returns.

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
