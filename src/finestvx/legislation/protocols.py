"""Protocols and shared data types for FinestVX legislative packs."""

from __future__ import annotations

from dataclasses import dataclass
from typing import TYPE_CHECKING, Protocol

from ftllexengine.core.locale_utils import require_locale_code
from ftllexengine.introspection import is_valid_currency_code, is_valid_territory_code

from finestvx.core._validators import require_non_empty_text

if TYPE_CHECKING:
    from ftllexengine.introspection import CurrencyCode, TerritoryCode
    from ftllexengine.localization import FluentLocalization, LocalizationBootConfig
    from ftllexengine.runtime import FunctionRegistry

    from finestvx.core.models import Book, JournalTransaction
    from finestvx.core.types import LegislativePackCode

__all__ = [
    "ILegislativePack",
    "LegislativeIssue",
    "LegislativePackMetadata",
    "LegislativeValidationResult",
]


def _is_known_territory_code(value: str) -> bool:
    """Return ``True`` when the string is a known ISO 3166-1 alpha-2 code."""
    return bool(is_valid_territory_code(value))


def _is_known_currency_code(value: str) -> bool:
    """Return ``True`` when the string is a known ISO 4217 currency code."""
    return bool(is_valid_currency_code(value))


def _require_tax_year(value: object, field_name: str) -> int:
    """Validate a tax-year integer."""
    if isinstance(value, bool) or not isinstance(value, int):
        msg = f"{field_name} must be int, got {type(value).__name__}"
        raise TypeError(msg)
    if not 1 <= value <= 9999:
        msg = f"{field_name} must be between 1 and 9999"
        raise ValueError(msg)
    return value


def _require_non_negative_int(value: object, field_name: str) -> int:
    """Validate a non-negative integer."""
    if isinstance(value, bool) or not isinstance(value, int):
        msg = f"{field_name} must be int, got {type(value).__name__}"
        raise TypeError(msg)
    if value < 0:
        msg = f"{field_name} must be non-negative"
        raise ValueError(msg)
    return value


def _coerce_tuple[T](value: object, field_name: str) -> tuple[T, ...]:
    """Accept list or tuple input and normalize to tuple storage."""
    if isinstance(value, tuple):
        return value
    if isinstance(value, list):
        return tuple(value)
    msg = f"{field_name} must be tuple or list, got {type(value).__name__}"
    raise TypeError(msg)


@dataclass(frozen=True, slots=True)
class LegislativePackMetadata:
    """Static metadata describing a legislative pack implementation."""

    pack_code: LegislativePackCode
    territory_code: TerritoryCode
    tax_year: int
    default_locale: str
    currencies: tuple[CurrencyCode, ...] | list[CurrencyCode]

    def __post_init__(self) -> None:
        """Validate metadata shape and jurisdiction identifiers."""
        object.__setattr__(
            self,
            "pack_code",
            require_non_empty_text(self.pack_code, "pack_code"),
        )
        territory_code = require_non_empty_text(self.territory_code, "territory_code").upper()
        if not _is_known_territory_code(territory_code):
            msg = f"territory_code must be a valid ISO 3166-1 alpha-2 code, got {territory_code!r}"
            raise ValueError(msg)
        object.__setattr__(self, "territory_code", territory_code)
        object.__setattr__(self, "tax_year", _require_tax_year(self.tax_year, "tax_year"))
        object.__setattr__(
            self,
            "default_locale",
            require_locale_code(self.default_locale, "default_locale"),
        )
        object.__setattr__(self, "currencies", _coerce_tuple(self.currencies, "currencies"))
        if len(self.currencies) == 0:
            msg = "currencies must not be empty"
            raise ValueError(msg)
        normalized_currencies = tuple(
            require_non_empty_text(currency, "currencies").upper()
            for currency in self.currencies
        )
        for currency in normalized_currencies:
            if not _is_known_currency_code(currency):
                msg = f"currencies contains invalid ISO 4217 code {currency!r}"
                raise ValueError(msg)
        object.__setattr__(self, "currencies", normalized_currencies)


@dataclass(frozen=True, slots=True)
class LegislativeIssue:
    """Structured legislative validation finding."""

    code: str
    message: str
    entry_index: int | None = None

    def __post_init__(self) -> None:
        """Validate issue payload structure."""
        object.__setattr__(self, "code", require_non_empty_text(self.code, "code"))
        object.__setattr__(self, "message", require_non_empty_text(self.message, "message"))
        if self.entry_index is None:
            return
        object.__setattr__(
            self,
            "entry_index",
            _require_non_negative_int(self.entry_index, "entry_index"),
        )


@dataclass(frozen=True, slots=True)
class LegislativeValidationResult:
    """Validation result emitted by a legislative pack."""

    pack_code: LegislativePackCode
    issues: tuple[LegislativeIssue, ...] | list[LegislativeIssue] = ()

    def __post_init__(self) -> None:
        """Normalize issue storage and validate issue types."""
        object.__setattr__(
            self,
            "pack_code",
            require_non_empty_text(self.pack_code, "pack_code"),
        )
        object.__setattr__(self, "issues", _coerce_tuple(self.issues, "issues"))

    @property
    def accepted(self) -> bool:
        """Return ``True`` when the result contains no issues."""
        return len(self.issues) == 0

    def require_valid(self) -> None:
        """Raise ``ValueError`` when legislative validation produced issues."""
        if self.accepted:
            return
        issue_codes = ", ".join(issue.code for issue in self.issues)
        msg = f"Legislative validation failed for {self.pack_code}: {issue_codes}"
        raise ValueError(msg)


class ILegislativePack(Protocol):
    """Protocol that all FinestVX legislative packs must implement."""

    @property
    def metadata(self) -> LegislativePackMetadata:
        """Return static metadata for the pack."""

    @property
    def function_registry(self) -> FunctionRegistry:
        """Return the pack-local function registry copy."""

    def validate_transaction(
        self,
        book: Book,
        transaction: JournalTransaction,
    ) -> LegislativeValidationResult:
        """Validate a posted transaction within the pack's legislative rules."""

    def localization_boot_config(self) -> LocalizationBootConfig:
        """Return the strict boot configuration for the pack's localization runtime.

        The caller is responsible for calling ``LocalizationBootConfig.boot()``
        and capturing the returned ``LoadSummary`` for audit trails.
        """

    def configure_localization(self, l10n: FluentLocalization) -> None:
        """Register pack-specific custom functions into an already-booted localization.

        Called by the gateway immediately after ``localization_boot_config().boot()``.
        Packs with no custom functions may leave this as a no-op.
        """
