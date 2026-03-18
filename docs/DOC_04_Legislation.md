---
afad: "3.3"
version: "0.7.0"
domain: SECONDARY
updated: "2026-03-18"
route:
  keywords: [legislative pack, pack protocol, pack registry, pack metadata, legislative issue, legislative result, subinterpreters, latvia 2026, function registry isolation, localization boot config, configure localization, interpreter pool]
  questions: ["how does the finestvx plugin system work?", "what is an ILegislativePack?", "how are packs isolated at runtime?", "how is the Latvia pack implemented?", "how do i add a jurisdiction pack?"]
---

# FinestVX Legislation Reference

---

## `LegislativePackMetadata`

Immutable static descriptor for a legislative-pack implementation.

### Signature
```python
@dataclass(frozen=True, slots=True)
class LegislativePackMetadata:
    pack_code: LegislativePackCode
    territory_code: TerritoryCode
    tax_year: int
    default_locale: str
    currencies: tuple[CurrencyCode, ...] | list[CurrencyCode]
```

### Constraints
- `pack_code` must be non-empty.
- `territory_code` must be a valid ISO 3166-1 alpha-2 code via `ftllexengine.introspection.is_valid_territory_code()`.
- `tax_year` must be an `int` in `1..9999`; `bool` is rejected.
- `default_locale` is normalized to the canonical lowercase POSIX locale form via `ftllexengine.core.locale_utils.require_locale_code()`.
- `currencies` must be non-empty; each element must be a valid ISO 4217 code; stored as tuple.

---

## `LegislativeIssue`

Immutable structured finding emitted by a legislative pack validation.

### Signature
```python
@dataclass(frozen=True, slots=True)
class LegislativeIssue:
    code: str
    message: str
    entry_index: int | None = None
```

### Constraints
- `code` and `message` must be non-empty strings.
- `entry_index`, when present, must be a non-negative `int`; `bool` is rejected.
- Identifies which ledger entry triggered the issue, or `None` for transaction-level findings.

---

## `LegislativeValidationResult`

Immutable container of `LegislativeIssue` values produced by a pack.

### Signature
```python
@dataclass(frozen=True, slots=True)
class LegislativeValidationResult:
    pack_code: LegislativePackCode
    issues: tuple[LegislativeIssue, ...] | list[LegislativeIssue] = ()

    @property
    def accepted(self) -> bool: ...

    def require_valid(self) -> None: ...
```

### Constraints
- `pack_code` must be non-empty; `issues` are stored as tuple.
- `accepted`: `True` when `issues` is empty.
- `require_valid`: raises `ftllexengine.integrity.IntegrityCheckFailedError` when `not accepted`.

---

## `ILegislativePack`

Protocol defining the contract every legislative pack must satisfy.

### Signature
```python
class ILegislativePack(Protocol):
    @property
    def metadata(self) -> LegislativePackMetadata: ...

    @property
    def function_registry(self) -> FunctionRegistry: ...

    def validate_transaction(
        self,
        book: Book,
        transaction: JournalTransaction,
    ) -> LegislativeValidationResult: ...

    def localization_boot_config(self) -> LocalizationBootConfig: ...
    def configure_localization(self, l10n: FluentLocalization) -> None: ...
```

### Constraints
- `metadata` must be immutable.
- `function_registry` must be a pack-local unfrozen copy of the shared FTLLexEngine registry.
- `validate_transaction`: business-rule validation; returns result, never raises on rule failures.
- `localization_boot_config`: returns a `LocalizationBootConfig` with pack-local `required_messages`
  and `message_schemas` declared; callers execute `.boot()` to obtain `(FluentLocalization, LoadSummary, ...)`.
- `configure_localization`: called by the gateway immediately after `localization_boot_config().boot()`
  to register pack-specific custom Fluent functions via `FluentLocalization.add_function()`; packs
  without custom functions may implement as a no-op.

---

## `LegislativePackRegistry`

Mutable registry mapping pack codes to `ILegislativePack` implementations.

### Signature
```python
class LegislativePackRegistry:
    def register(self, pack: ILegislativePack) -> None: ...
    def resolve(self, pack_code: LegislativePackCode) -> ILegislativePack: ...
    def available_pack_codes(self) -> tuple[LegislativePackCode, ...]: ...
```

### Constraints
- `register`: raises `ValueError` on duplicate pack codes.
- `resolve`: raises `KeyError` when the pack code is not registered.
- `available_pack_codes`: deterministic sorted tuple.
- Implements `__contains__`, `__iter__`, and `__len__`.

---

## `create_default_pack_registry`

Function that returns a registry pre-loaded with the Latvia 2026 stub pack.

### Signature
```python
def create_default_pack_registry() -> LegislativePackRegistry:
```

### Constraints
- Return: `LegislativePackRegistry` containing `LatviaStandard2026Pack`.
- Creates a fresh registry on each call; instances are independent.

---

## `LatviaStandard2026Pack`

Immutable legislative pack stub for Latvia, tax year 2026.

### Signature
```python
@dataclass(frozen=True, slots=True)
class LatviaStandard2026Pack:
    metadata: LegislativePackMetadata  # default_factory
    function_registry: FunctionRegistry  # default_factory
```

### Constraints
- `metadata.pack_code == "lv.standard.2026"`, `territory_code == "LV"`, `tax_year == 2026`, `currencies == ("EUR",)`.
- Validation rule: any ledger entry with a non-`None` `tax_rate` not equal to `Decimal("0.21")` is flagged.
- Validation rule: `book.legislative_pack != "lv.standard.2026"` is flagged.
- `localization_boot_config()` returns a `LocalizationBootConfig` with declared `required_messages`
  and `message_schemas`; loads FTL assets from `locales/lv_lv/` and `locales/en_us/` applying
  `MANDATED_CACHE_CONFIG`.
- `configure_localization(l10n)` registers `ROUND_EUR` and all other pack functions into the booted
  `FluentLocalization` via `l10n.add_function()`.
- Custom FTL function `ROUND_EUR` quantizes financial amounts to 2 decimal places using `ROUND_HALF_UP`. FTL usage: `{ ROUND_EUR($amount) }`.
- FTL messages: `latvia-pack-name`, `vat-standard-rate`, `vat-amount`.

---

## `LegislativeInterpreterRunner`

Stateful runner that dispatches pack validation through a bounded `InterpreterPool` of reusable PEP 734 subinterpreters.

### Signature
```python
@dataclass(slots=True)
class LegislativeInterpreterRunner:
    pool_min_size: int = 2
    pool_max_size: int = 8
    _pool: InterpreterPool  # init=False; constructed from pool_min_size/pool_max_size

    def validate(
        self,
        pack_code: str,
        book: Book,
        transaction: JournalTransaction,
    ) -> LegislativeValidationResult: ...

    def close(self) -> None: ...
```

### Parameters
| Name | Type | Req | Semantics |
|:-----|:-----|:----|:----------|
| `pack_code` | `str` | Y | Pack to resolve from the default registry |
| `book` | `Book` | Y | Book context |
| `transaction` | `JournalTransaction` | Y | Transaction to validate |

### Constraints
- Holds a bounded `InterpreterPool` (default: `min_size=2`, `max_size=8`); interpreters are reused
  across calls, amortizing PEP 734 interpreter startup cost.
- `validate()` acquires one interpreter via context manager, executes `_validate_in_subinterpreter`,
  and releases it back to the pool.
- Pack crashes are isolated; they cannot corrupt the core runtime.
- Return type is reconstructed from primitive round-trip data (no live objects cross interpreter boundary).
- `close()` must be called on shutdown to release all pool interpreters; `FinestVXService.close()`
  handles this automatically.

---

## `validate_transaction_isolated`

Convenience function for one-shot subinterpreter legislative validation.

### Signature
```python
def validate_transaction_isolated(
    pack_code: str,
    book: Book,
    transaction: JournalTransaction,
) -> LegislativeValidationResult:
```

### Parameters
| Name | Type | Req | Semantics |
|:-----|:-----|:----|:----------|
| `pack_code` | `str` | Y | Pack to resolve |
| `book` | `Book` | Y | Book context |
| `transaction` | `JournalTransaction` | Y | Transaction to validate |

### Constraints
- Creates `LegislativeInterpreterRunner(pool_min_size=1, pool_max_size=1)` for a single call, then closes it.
- Raises: `KeyError` when `pack_code` is not in the default registry.
