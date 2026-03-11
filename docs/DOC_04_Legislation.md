---
afad: "3.3"
version: "0.1.0"
domain: SECONDARY
updated: "2026-03-09"
route:
  keywords: [legislative pack, pack protocol, pack registry, pack metadata, legislative issue, legislative result, subinterpreters, latvia 2026, function registry isolation]
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
- `territory_code` must be a valid ISO 3166-1 alpha-2 code via `ftllexengine.introspection.iso.is_valid_territory_code()`.
- `tax_year` must be an `int` in `1..9999`; `bool` is rejected.
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
- `require_valid`: raises `ValueError` when `not accepted`.

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

    def create_localization(self) -> LocalizationService: ...
```

### Constraints
- `metadata` must be immutable.
- `function_registry` must be a pack-local unfrozen copy of the shared FTLLexEngine registry.
- `validate_transaction`: business-rule validation; returns result, never raises on rule failures.
- `create_localization`: returns a strict `LocalizationService` for pack-local FTL resources.

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
- `create_localization` loads FTL assets from `locales/lv-LV/` and `locales/en-US/` with strict boot.
- Custom FTL function `ROUND_EUR` is registered via `@fluent_function`; quantizes financial amounts to 2 decimal places using `ROUND_HALF_UP`. FTL usage: `{ ROUND_EUR($amount) }`.
- FTL messages: `latvia-pack-name`, `vat-standard-rate`, `vat-amount`.

---

## `LegislativeInterpreterRunner`

Stateless runner that executes pack validation in a fresh PEP 734 subinterpreter.

### Signature
```python
class LegislativeInterpreterRunner:
    def validate(
        self,
        pack_code: str,
        book: Book,
        transaction: JournalTransaction,
    ) -> LegislativeValidationResult:
```

### Parameters
| Name | Type | Req | Semantics |
|:-----|:-----|:----|:----------|
| `pack_code` | `str` | Y | Pack to resolve from the default registry |
| `book` | `Book` | Y | Book context |
| `transaction` | `JournalTransaction` | Y | Transaction to validate |

### Constraints
- Creates and destroys one `interpreters.Interpreter` per call.
- Pack crashes are isolated; they cannot corrupt the core runtime.
- Return type is reconstructed from primitive round-trip data (no live objects cross interpreter boundary).

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
- Delegates to `LegislativeInterpreterRunner().validate(...)`.
- Raises: `KeyError` when `pack_code` is not in the default registry.
