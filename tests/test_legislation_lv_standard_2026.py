"""Tests for the Latvia 2026 legislative-pack stub."""

from __future__ import annotations

from datetime import UTC, datetime
from decimal import Decimal

from ftllexengine import FluentNumber
from ftllexengine.introspection import CurrencyCode
from ftllexengine.runtime import get_shared_registry

from finestvx import (
    Account,
    Book,
    JournalTransaction,
    LatviaStandard2026Pack,
    LedgerEntry,
    PostingSide,
)
from finestvx.legislation.lv.standard_2026 import round_eur

_POSTED_AT = datetime(2026, 2, 1, 10, 0, tzinfo=UTC)


class TestLatviaStandard2026Pack:
    """Validate the Latvia 2026 legislative-pack baseline."""

    def test_metadata_matches_brief(self) -> None:
        """The pack advertises the expected metadata."""
        pack = LatviaStandard2026Pack()

        assert pack.metadata.pack_code == "lv.standard.2026"
        assert pack.metadata.territory_code == "LV"
        assert pack.metadata.tax_year == 2026
        assert pack.metadata.default_locale == "lv_lv"
        assert pack.metadata.currencies == ("EUR",)

    def test_function_registry_is_independent_copy(self) -> None:
        """Pack-local registry extensions do not mutate the shared frozen registry."""
        pack = LatviaStandard2026Pack()
        shared = get_shared_registry()

        def local_echo(value: str) -> str:
            return value

        pack.function_registry.register(local_echo, ftl_name="LOCAL_ECHO")

        assert pack.function_registry.has_function("LOCAL_ECHO") is True
        assert shared.has_function("LOCAL_ECHO") is False
        assert shared.frozen is True
        assert pack.function_registry.frozen is False

    def test_round_eur_function_is_registered(self) -> None:
        """The ROUND_EUR custom function is registered in the pack-local registry."""
        pack = LatviaStandard2026Pack()
        assert pack.function_registry.has_function("ROUND_EUR") is True

    def test_round_eur_quantizes_to_two_decimal_places(self) -> None:
        """ROUND_EUR rounds amounts to 2 decimal places using ROUND_HALF_UP."""
        result = round_eur(FluentNumber(value=Decimal("10.005"), formatted="10.005", precision=3))
        assert result.value == Decimal("10.01")
        assert result.precision == 2

        result_int = round_eur(FluentNumber(value=100, formatted="100", precision=0))
        assert result_int.value == Decimal("100.00")
        assert result_int.precision == 2

    def test_standard_rate_transaction_is_accepted(self) -> None:
        """Entries marked with a 21 percent VAT rate pass the stub validation."""
        pack = LatviaStandard2026Pack()
        book = Book(
            code="lv-book",
            name="Latvia Book",
            base_currency=CurrencyCode("EUR"),
            legislative_pack="lv.standard.2026",
            accounts=(
                Account(
                    code="1000",
                    name="Cash",
                    normal_side=PostingSide.DEBIT,
                    currency=CurrencyCode("EUR"),
                ),
                Account(
                    code="2000",
                    name="Revenue",
                    normal_side=PostingSide.CREDIT,
                    currency=CurrencyCode("EUR"),
                ),
            ),
        )
        transaction = JournalTransaction(
            reference="LV-0001",
            posted_at=_POSTED_AT,
            description="Latvia VAT transaction",
            entries=(
                LedgerEntry(
                    account_code="1000",
                    side=PostingSide.DEBIT,
                    amount=FluentNumber(value=Decimal("121.00"), formatted="121.00", precision=2),
                    currency=CurrencyCode("EUR"),
                    tax_rate=Decimal("0.21"),
                ),
                LedgerEntry(
                    account_code="2000",
                    side=PostingSide.CREDIT,
                    amount=FluentNumber(value=Decimal("121.00"), formatted="121.00", precision=2),
                    currency=CurrencyCode("EUR"),
                    tax_rate=Decimal("0.21"),
                ),
            ),
        )

        result = pack.validate_transaction(book, transaction)

        assert result.accepted is True
        assert result.issues == ()

    def test_non_standard_rate_transaction_is_flagged(self) -> None:
        """Entries with non-21-percent VAT rates are reported by the stub validator."""
        pack = LatviaStandard2026Pack()
        book = Book(
            code="lv-book",
            name="Latvia Book",
            base_currency=CurrencyCode("EUR"),
            legislative_pack="lv.standard.2026",
            accounts=(
                Account(
                    code="1000",
                    name="Cash",
                    normal_side=PostingSide.DEBIT,
                    currency=CurrencyCode("EUR"),
                ),
                Account(
                    code="2000",
                    name="Revenue",
                    normal_side=PostingSide.CREDIT,
                    currency=CurrencyCode("EUR"),
                ),
            ),
        )
        transaction = JournalTransaction(
            reference="LV-0002",
            posted_at=_POSTED_AT,
            description="Latvia reduced-rate transaction",
            entries=(
                LedgerEntry(
                    account_code="1000",
                    side=PostingSide.DEBIT,
                    amount=FluentNumber(value=Decimal("112.00"), formatted="112.00", precision=2),
                    currency=CurrencyCode("EUR"),
                    tax_rate=Decimal("0.12"),
                ),
                LedgerEntry(
                    account_code="2000",
                    side=PostingSide.CREDIT,
                    amount=FluentNumber(value=Decimal("112.00"), formatted="112.00", precision=2),
                    currency=CurrencyCode("EUR"),
                    tax_rate=Decimal("0.12"),
                ),
            ),
        )

        result = pack.validate_transaction(book, transaction)

        assert result.accepted is False
        assert [issue.code for issue in result.issues] == [
            "LV_STANDARD_VAT_RATE_MISMATCH",
            "LV_STANDARD_VAT_RATE_MISMATCH",
        ]

    def test_pack_code_mismatch_is_reported(self) -> None:
        """Validation includes a finding when the book uses a different legislative pack."""
        pack = LatviaStandard2026Pack()
        book = Book(
            code="lv-book",
            name="Latvia Book",
            base_currency=CurrencyCode("EUR"),
            legislative_pack="other.pack",
            accounts=(
                Account(
                    code="1000",
                    name="Cash",
                    normal_side=PostingSide.DEBIT,
                    currency=CurrencyCode("EUR"),
                ),
                Account(
                    code="2000",
                    name="Revenue",
                    normal_side=PostingSide.CREDIT,
                    currency=CurrencyCode("EUR"),
                ),
            ),
        )
        transaction = JournalTransaction(
            reference="LV-0003",
            posted_at=_POSTED_AT,
            description="Pack mismatch",
            entries=(
                LedgerEntry(
                    account_code="1000",
                    side=PostingSide.DEBIT,
                    amount=FluentNumber(value=Decimal("10.00"), formatted="10.00", precision=2),
                    currency=CurrencyCode("EUR"),
                ),
                LedgerEntry(
                    account_code="2000",
                    side=PostingSide.CREDIT,
                    amount=FluentNumber(value=Decimal("10.00"), formatted="10.00", precision=2),
                    currency=CurrencyCode("EUR"),
                ),
            ),
        )

        result = pack.validate_transaction(book, transaction)

        assert result.accepted is False
        assert [issue.code for issue in result.issues] == ["LV_PACK_CODE_MISMATCH"]
