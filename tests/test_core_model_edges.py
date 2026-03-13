"""Additional edge-case tests for FinestVX core models."""

from __future__ import annotations

from datetime import UTC, date, datetime
from decimal import Decimal
from typing import Any, cast

import pytest
from ftllexengine import FluentNumber, make_fluent_number
from ftllexengine.core.fiscal import FiscalCalendar, FiscalPeriod

import finestvx.core.models as models_module
from finestvx.core import Account, Book, BookPeriod, JournalTransaction, LedgerEntry, PostingSide
from finestvx.core.enums import TransactionState

_POSTED_AT = datetime(2026, 1, 15, 9, 30, tzinfo=UTC)


class TestCoreModelHelpers:
    """Direct checks for private validation helpers."""

    def test_text_ratio_and_tuple_helpers_reject_invalid_values(self) -> None:
        """Primitive validators reject invalid scalar inputs with clear errors."""
        with pytest.raises(TypeError, match="field must be str"):
            models_module._require_non_empty_text(1, "field")
        with pytest.raises(ValueError, match="field must not be empty"):
            models_module._require_non_empty_text("   ", "field")
        assert models_module._normalize_optional_text(None, "field") is None
        assert models_module._normalize_optional_text(" value ", "field") == "value"

        with pytest.raises(TypeError, match="tax_rate must be Decimal, not bool"):
            models_module._require_decimal_ratio(True, "tax_rate")
        with pytest.raises(TypeError, match="tax_rate must be Decimal"):
            models_module._require_decimal_ratio("0.21", "tax_rate")
        with pytest.raises(ValueError, match="tax_rate must be finite"):
            models_module._require_decimal_ratio(Decimal("NaN"), "tax_rate")

        assert models_module._coerce_tuple([1, 2], "items") == (1, 2)
        with pytest.raises(TypeError, match="items must be tuple or list"):
            models_module._coerce_tuple({1, 2}, "items")

    def test_amount_and_enum_helpers_reject_invalid_values(self) -> None:
        """Amount coercion and enum validators defend against bad runtime types."""
        with pytest.raises(TypeError, match="amount must be FluentNumber"):
            models_module._amount_as_decimal("1.00")

        integer_amount = FluentNumber(value=10, formatted="10", precision=0)
        assert models_module._amount_as_decimal(integer_amount) == Decimal(10)

        with pytest.raises(ValueError, match="amount value must be finite"):
            models_module._amount_as_decimal(
                FluentNumber(value=Decimal("Infinity"), formatted="Infinity", precision=0)
            )

        with pytest.raises(TypeError, match="side must be PostingSide"):
            models_module._require_posting_side("Dr", "side")
        with pytest.raises(TypeError, match="state must be TransactionState"):
            models_module._require_transaction_state("posted", "state")
        with pytest.raises(TypeError, match="state must be FiscalPeriodState"):
            models_module._require_period_state("open", "state")
        with pytest.raises(TypeError, match="period must be FiscalPeriod"):
            models_module._require_fiscal_period("2026-Q1", "period")
        with pytest.raises(TypeError, match="start_date must be date"):
            models_module._require_date_value("2026-01-01", "start_date")
        with pytest.raises(TypeError, match="posted_at must be datetime"):
            models_module._require_datetime_value("2026-01-01", "posted_at")
        with pytest.raises(TypeError, match="calendar must be FiscalCalendar"):
            models_module._require_fiscal_calendar("jan", "calendar")

    def test_collection_validators_reject_inconsistent_graphs(self) -> None:
        """Collection validators reject malformed account, period, and transaction sets."""
        cash = Account(
            code="1000",
            name="Cash",
            normal_side=PostingSide.DEBIT,
            currency="EUR",
        )
        revenue = Account(
            code="2000",
            name="Revenue",
            normal_side=PostingSide.CREDIT,
            currency="EUR",
        )
        valid_period = BookPeriod(
            period=FiscalPeriod(fiscal_year=2026, quarter=1, month=1),
            start_date=date(2026, 1, 1),
            end_date=date(2026, 1, 31),
        )
        later_period = BookPeriod(
            period=FiscalPeriod(fiscal_year=2026, quarter=1, month=2),
            start_date=date(2026, 2, 1),
            end_date=date(2026, 2, 28),
        )

        with pytest.raises(TypeError, match="Account objects"):
            models_module._validate_account_collection((object(),))
        with pytest.raises(ValueError, match="references missing parent account"):
            models_module._validate_account_collection(
                (
                    Account(
                        code="3000",
                        name="Receivable",
                        normal_side=PostingSide.DEBIT,
                        currency="EUR",
                        parent_code="9999",
                    ),
                )
            )

        with pytest.raises(TypeError, match="BookPeriod objects"):
            models_module._validate_period_collection((object(),))
        with pytest.raises(ValueError, match="Duplicate fiscal period"):
            models_module._validate_period_collection((valid_period, valid_period))
        with pytest.raises(ValueError, match="must not overlap"):
            models_module._validate_period_collection(
                (
                    valid_period,
                    BookPeriod(
                        period=FiscalPeriod(fiscal_year=2026, quarter=1, month=3),
                        start_date=date(2026, 1, 20),
                        end_date=date(2026, 2, 5),
                    ),
                )
            )

        one_entry = LedgerEntry(
            account_code="1000",
            side=PostingSide.DEBIT,
            amount=make_fluent_number(Decimal("1.00")),
            currency="EUR",
        )
        with pytest.raises(ValueError, match="at least two entries"):
            models_module._validate_transaction_entries((one_entry,))
        with pytest.raises(TypeError, match="LedgerEntry objects"):
            models_module._validate_transaction_entries((object(), object()))
        with pytest.raises(TypeError, match="JournalTransaction objects"):
            models_module._validate_transactions_against_accounts((object(),), {"1000"})

        draft_transaction = JournalTransaction(
            reference="TX-DRAFT-001",
            posted_at=_POSTED_AT,
            description="Draft",
            state=TransactionState.DRAFT,
            entries=(
                one_entry,
                LedgerEntry(
                    account_code="2000",
                    side=PostingSide.CREDIT,
                    amount=make_fluent_number(Decimal("1.00")),
                    currency="EUR",
                ),
            ),
        )
        with pytest.raises(ValueError, match="only contain posted transactions"):
            models_module._validate_transactions_against_accounts(
                (draft_transaction,),
                {"1000", "2000"},
            )

        posted_transaction = JournalTransaction(
            reference="TX-POSTED-001",
            posted_at=_POSTED_AT,
            description="Posted",
            entries=(
                one_entry,
                LedgerEntry(
                    account_code="2000",
                    side=PostingSide.CREDIT,
                    amount=make_fluent_number(Decimal("1.00")),
                    currency="EUR",
                ),
            ),
        )
        with pytest.raises(ValueError, match="references unknown account 2000"):
            models_module._validate_transactions_against_accounts((posted_transaction,), {"1000"})

        book = Book(
            code="demo-book",
            name="Demo Book",
            base_currency="EUR",
            fiscal_calendar=FiscalCalendar(start_month=1),
            accounts=(cash, revenue),
            periods=(valid_period, later_period),
        )
        assert book.account_map() == {"1000": cash, "2000": revenue}
        assert book.period_set() == frozenset({valid_period.period, later_period.period})
        updated_book = book.append_account(
            Account(
                code="3000",
                name="VAT",
                normal_side=PostingSide.CREDIT,
                currency="EUR",
            )
        )
        assert len(updated_book.accounts) == 3
        assert len(book.accounts) == 2


class TestLedgerEntryCurrencyPrecision:
    """Currency decimal precision enforcement via ISO 4217 via ftllexengine.introspection.iso."""

    def test_eur_rejects_three_decimal_places(self) -> None:
        """EUR supports 2 decimal places; 3-decimal amounts are rejected."""
        with pytest.raises(ValueError, match="decimal places but EUR supports at most 2"):
            LedgerEntry(
                account_code="1000",
                side=PostingSide.DEBIT,
                amount=make_fluent_number(Decimal("10.001")),
                currency="EUR",
            )

    def test_eur_accepts_two_decimal_places(self) -> None:
        """EUR amounts with exactly 2 decimal places are accepted."""
        entry = LedgerEntry(
            account_code="1000",
            side=PostingSide.DEBIT,
            amount=make_fluent_number(Decimal("10.00")),
            currency="EUR",
        )
        assert entry.decimal_value == Decimal("10.00")

    def test_jpy_rejects_fractional_amounts(self) -> None:
        """JPY supports 0 decimal places; any fractional amount is rejected."""
        with pytest.raises(ValueError, match="decimal places but JPY supports at most 0"):
            LedgerEntry(
                account_code="1000",
                side=PostingSide.DEBIT,
                amount=make_fluent_number(Decimal("100.5")),
                currency="JPY",
            )

    def test_jpy_accepts_integer_amounts(self) -> None:
        """JPY amounts with zero decimal places are accepted."""
        entry = LedgerEntry(
            account_code="1000",
            side=PostingSide.DEBIT,
            amount=make_fluent_number(Decimal(1000)),
            currency="JPY",
        )
        assert entry.decimal_value == Decimal(1000)

    def test_kwd_accepts_three_decimal_places(self) -> None:
        """KWD (Kuwaiti Dinar) supports 3 decimal places."""
        entry = LedgerEntry(
            account_code="1000",
            side=PostingSide.DEBIT,
            amount=make_fluent_number(Decimal("1.234")),
            currency="KWD",
        )
        assert entry.decimal_value == Decimal("1.234")


class TestCoreModelConstructors:
    """Constructor-level checks for uncovered branches."""

    def test_constructors_reject_invalid_runtime_types(self) -> None:
        """Dataclass constructors enforce their runtime contracts."""
        with pytest.raises(TypeError, match="normal_side must be PostingSide"):
            Account(
                code="1000",
                name="Cash",
                normal_side=cast("Any", "Dr"),
                currency="EUR",
            )

        with pytest.raises(TypeError, match="amount must be FluentNumber"):
            LedgerEntry(
                account_code="1000",
                side=PostingSide.DEBIT,
                amount=cast("Any", "1.00"),
                currency="EUR",
            )

        with pytest.raises(TypeError, match="entries must be tuple or list"):
            JournalTransaction(
                reference="TX-2026-1000",
                posted_at=_POSTED_AT,
                description="Bad entries",
                state=TransactionState.DRAFT,
                entries=cast("Any", "not-a-sequence"),
            )

        with pytest.raises(ValueError, match="reversal_of must reference a different transaction"):
            JournalTransaction(
                reference="TX-2026-1001",
                posted_at=_POSTED_AT,
                description="Bad reversal",
                state=TransactionState.DRAFT,
                reversal_of="TX-2026-1001",
                entries=(),
            )

    def test_draft_transaction_balance_property_returns_false_for_invalid_entries(self) -> None:
        """Draft transactions expose invalid balance state without constructor rejection."""
        transaction = JournalTransaction(
            reference="TX-2026-1002",
            posted_at=_POSTED_AT,
            description="Single sided draft",
            state=TransactionState.DRAFT,
            entries=(
                LedgerEntry(
                    account_code="1000",
                    side=PostingSide.DEBIT,
                    amount=make_fluent_number(Decimal("10.00")),
                    currency="EUR",
                ),
            ),
        )

        assert transaction.is_balanced is False

    def test_book_period_and_book_validate_input_types(self) -> None:
        """Book and period wrappers reject invalid field types and states."""
        with pytest.raises(TypeError, match="period must be FiscalPeriod"):
            BookPeriod(
                period=cast("Any", "2026-Q1"),
                start_date=date(2026, 1, 1),
                end_date=date(2026, 1, 31),
            )
        with pytest.raises(TypeError, match="state must be FiscalPeriodState"):
            BookPeriod(
                period=FiscalPeriod(fiscal_year=2026, quarter=1, month=1),
                start_date=date(2026, 1, 1),
                end_date=date(2026, 1, 31),
                state=cast("Any", "open"),
            )
        with pytest.raises(TypeError, match="transactions must contain JournalTransaction objects"):
            Book(
                code="demo-book",
                name="Demo Book",
                base_currency="EUR",
                fiscal_calendar=FiscalCalendar(start_month=1),
                accounts=(),
                transactions=cast("Any", (object(),)),
            )
