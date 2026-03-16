"""Latvia legislative-pack stub for the 2026 tax year."""

from __future__ import annotations

from dataclasses import dataclass, field
from decimal import ROUND_HALF_UP as _ROUND_HALF_UP
from decimal import Decimal
from pathlib import Path
from typing import TYPE_CHECKING

from ftllexengine import FluentNumber, make_fluent_number
from ftllexengine.localization import LocalizationBootConfig
from ftllexengine.runtime import FunctionRegistry, fluent_function, get_shared_registry

from finestvx.legislation.protocols import (
    LegislativeIssue,
    LegislativePackMetadata,
    LegislativeValidationResult,
)
from finestvx.persistence import MANDATED_CACHE_CONFIG

if TYPE_CHECKING:
    from ftllexengine.localization import FluentLocalization

    from finestvx.core.models import Book, JournalTransaction

__all__ = ["LatviaStandard2026Pack"]

_STANDARD_VAT_RATE = Decimal("0.21")
_EUR_QUANTIZE = Decimal("0.01")


@fluent_function
def round_eur(value: FluentNumber) -> FluentNumber:
    """Quantize a financial amount to two decimal places using banking ROUND_HALF_UP.

    FTL usage: { ROUND_EUR($amount) }

    Ensures EUR amounts always carry exactly two decimal places for display in
    Latvian tax documents and VAT summaries.
    """
    decimal_value = value.decimal_value
    if not decimal_value.is_finite():
        return value
    quantized = decimal_value.quantize(_EUR_QUANTIZE, rounding=_ROUND_HALF_UP)
    return make_fluent_number(quantized)


def _build_metadata() -> LegislativePackMetadata:
    """Create metadata for the Latvia standard 2026 pack."""
    return LegislativePackMetadata(
        pack_code="lv.standard.2026",
        territory_code="LV",
        tax_year=2026,
        default_locale="lv-LV",
        currencies=("EUR",),
    )


def _build_registry() -> FunctionRegistry:
    """Return an unfrozen copy of the shared registry with Latvia-specific functions."""
    registry = get_shared_registry().copy()
    registry.register(round_eur)
    return registry


@dataclass(frozen=True, slots=True)
class LatviaStandard2026Pack:
    """Initial Latvia pack with a single standard-rate VAT validation hook."""

    metadata: LegislativePackMetadata = field(default_factory=_build_metadata)
    function_registry: FunctionRegistry = field(default_factory=_build_registry)

    def create_localization(self) -> FluentLocalization:
        """Create the strict pack-local localization runtime."""
        base_path = Path(__file__).with_name("locales") / "{locale}"
        localization = LocalizationBootConfig.from_path(
            locales=(self.metadata.default_locale, "en_us"),
            resource_ids=("legislation.ftl",),
            base_path=base_path,
            cache=MANDATED_CACHE_CONFIG,
        ).boot()
        shared_registry = get_shared_registry()
        for function_name in self.function_registry:
            if shared_registry.has_function(function_name):
                continue
            function = self.function_registry.get_callable(function_name)
            if function is not None:
                localization.add_function(function_name, function)
        return localization

    def validate_transaction(
        self,
        book: Book,
        transaction: JournalTransaction,
    ) -> LegislativeValidationResult:
        """Validate transaction VAT rates against the initial Latvia stub rules.

        Args:
            book: Book context owning the transaction.
            transaction: Posted transaction to validate.

        Returns:
            Validation result containing zero or more legislative issues.
        """
        issues: list[LegislativeIssue] = []
        for index, entry in enumerate(transaction.entries):
            if entry.tax_rate is None:
                continue
            if entry.tax_rate != _STANDARD_VAT_RATE:
                issues.append(
                    LegislativeIssue(
                        code="LV_STANDARD_VAT_RATE_MISMATCH",
                        message=(
                            "Latvia standard 2026 stub currently accepts only a "
                            "21 percent VAT rate on explicitly taxed entries."
                        ),
                        entry_index=index,
                    )
                )
        if book.legislative_pack != self.metadata.pack_code:
            issues.append(
                LegislativeIssue(
                    code="LV_PACK_CODE_MISMATCH",
                    message=(
                        "Book legislative_pack must match the Latvia standard 2026 "
                        "pack code when this pack validates the transaction."
                    ),
                )
            )
        return LegislativeValidationResult(self.metadata.pack_code, tuple(issues))
