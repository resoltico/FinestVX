---
afad: "3.3"
version: "0.3.0"
domain: SECONDARY
updated: "2026-03-13"
route:
  keywords: [localization config, create localization, fluentlocalization, pathresourceloader, fallback callback, strict boot, amount parse result, parse amount, cache stats, cache audit log, message variable schemas, validate message variables, normalized locale codes]
  questions: ["how does finestvx localization work?", "how are FTL resources validated at boot?", "how do i create a localization runtime?", "how are localized amounts parsed back in?", "how do i validate message schemas?", "how do i inspect a localized message or term AST?", "how do i retrieve localization cache audit logs?"]
---

# FinestVX Localization Reference

---

## `LocalizationConfig`

Immutable boot configuration for FinestVX localization construction.

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
- `locales` are validated and canonicalized with `ftllexengine.core.locale_utils.require_locale_code()`.
- Locale codes must be unique after normalization.
- `resource_ids` are stored as tuples; empty collections are rejected.
- `base_path` is normalized to `Path`.
- `strict=True` hard-fails formatting errors and missing messages.
- `require_all_clean=True` delegates boot validation to `FluentLocalization.require_clean()`.
- `cache` defaults to `MANDATED_CACHE_CONFIG`.
- `message_variable_schemas` values are normalized to `frozenset`.
- Resource directories behind `base_path` must use the normalized locale names.

---

## `create_localization`

Function that constructs the strict FTLLexEngine localization runtime used by FinestVX.

### Signature
```python
def create_localization(
    config: LocalizationConfig,
    *,
    on_fallback: Callable[[FallbackInfo], None] | None = None,
) -> FluentLocalization:
```

### Parameters
| Name | Type | Req | Semantics |
|:-----|:-----|:----|:----------|
| `config` | `LocalizationConfig` | Y | Boot policy and resource paths |
| `on_fallback` | `Callable[[FallbackInfo], None] \| None` | N | Callback for fallback events |

### Constraints
- Builds `PathResourceLoader` from `config.base_path`.
- Returns the upstream `FluentLocalization` object directly; FinestVX does not wrap it.
- `require_all_clean=True` calls `FluentLocalization.require_clean()` during construction.
- `message_variable_schemas` uses `FluentLocalization.validate_message_schemas()` during construction.
- Fallback observability is callback-based; FinestVX does not store a parallel event log.
- Summary, cache statistics, cache audit logs, AST access, and one-message schema validation all come from `FluentLocalization`.

### Example
```python
localization = create_localization(
    LocalizationConfig(
        locales=("lv_lv", "en_us"),
        resource_ids=("invoices.ftl",),
        base_path=Path("locales/{locale}"),
    )
)
```

---

## `AmountParseResult`

Type alias for the return type of `parse_amount_input`.

### Definition
```python
type AmountParseResult = ParseResult[FluentNumber]
```

### Constraints
- First element: parsed `FluentNumber` or `None`.
- Second element: `tuple[FrozenFluentError, ...]`.
- `ParseResult[T]` is the canonical FTLLexEngine generic parse result.

---

## `parse_amount_input`

Function that parses localized decimal text into a `FluentNumber`.

### Signature
```python
def parse_amount_input(value: str, locale_code: str) -> AmountParseResult:
```

### Parameters
| Name | Type | Req | Semantics |
|:-----|:-----|:----|:----------|
| `value` | `str` | Y | Localized decimal text |
| `locale_code` | `str` | Y | Locale for reverse parsing |

### Constraints
- Delegates numeric parsing to `ftllexengine.parsing.parse_decimal`.
- Delegates `FluentNumber` construction to `ftllexengine.make_fluent_number`.
- Return: `(FluentNumber, ())` on success; `(None, errors)` on failure.
- FinestVX no longer re-exports raw decimal/date/datetime/currency parsers; import those directly from `ftllexengine.parsing`.
