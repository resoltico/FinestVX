"""Tests for FinestVX immutable accounting-domain models."""

from __future__ import annotations

from datetime import UTC, date, datetime
from decimal import Decimal

import pytest
from ftllexengine import FiscalCalendar, FiscalPeriod, FluentNumber
from ftllexengine.introspection import CurrencyCode

from finestvx.core import (
    Account,
    Book,
    BookPeriod,
    JournalTransaction,
    LedgerEntry,
    PostingSide,
    TransactionState,
)

_POSTED_AT = datetime(2026, 1, 15, 9, 30, tzinfo=UTC)


class TestAccount:
    """Tests for account invariants."""

    def test_rejects_invalid_currency(self) -> None:
        """Account rejects invalid ISO currency codes."""
        with pytest.raises(ValueError, match="ISO 4217"):
            Account(
                code="1000",
                name="Cash",
                normal_side=PostingSide.DEBIT,
                currency=CurrencyCode("ZZZ1"),
            )

    def test_rejects_self_parent(self) -> None:
        """Account cannot point at itself as parent."""
        with pytest.raises(ValueError, match="own parent"):
            Account(
                code="1000",
                name="Cash",
                normal_side=PostingSide.DEBIT,
                currency=CurrencyCode("EUR"),
                parent_code="1000",
            )


class TestBookPeriod:
    """Tests for fiscal period wrappers."""

    def test_rejects_end_before_start(self) -> None:
        """BookPeriod rejects inverted date ranges."""
        with pytest.raises(ValueError, match="on or after"):
            BookPeriod(
                period=FiscalPeriod(fiscal_year=2026, quarter=1, month=1),
                start_date=date(2026, 3, 31),
                end_date=date(2026, 1, 1),
            )


class TestLedgerEntry:
    """Tests for ledger-entry invariants."""

    def test_rejects_negative_amount(self) -> None:
        """LedgerEntry rejects negative amounts because side encodes polarity."""
        with pytest.raises(ValueError, match="non-negative"):
            LedgerEntry(
                account_code="1000",
                side=PostingSide.DEBIT,
                amount=FluentNumber(value=Decimal("-1.00"), formatted="-1.00", precision=2),
                currency=CurrencyCode("EUR"),
            )

    def test_rejects_tax_rate_outside_ratio_range(self) -> None:
        """LedgerEntry rejects tax rates outside the inclusive 0..1 interval."""
        with pytest.raises(ValueError, match="between 0 and 1"):
            LedgerEntry(
                account_code="1000",
                side=PostingSide.DEBIT,
                amount=FluentNumber(value=Decimal("1.00"), formatted="1.00", precision=2),
                currency=CurrencyCode("EUR"),
                tax_rate=Decimal("1.21"),
            )


class TestJournalTransaction:
    """Tests for transaction balancing."""

    def test_balanced_transaction_is_accepted(self) -> None:
        """Balanced debit and credit totals construct successfully."""
        transaction = JournalTransaction(
            reference="TX-2026-0001",
            posted_at=_POSTED_AT,
            description="Invoice payment",
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

        assert transaction.is_balanced is True
        assert transaction.debits_by_currency() == {"EUR": Decimal("10.00")}
        assert transaction.credits_by_currency() == {"EUR": Decimal("10.00")}

    def test_unbalanced_transaction_is_rejected(self) -> None:
        """Posted transactions must remain zero-sum per currency."""
        with pytest.raises(ValueError, match="not balanced"):
            JournalTransaction(
                reference="TX-2026-0002",
                posted_at=_POSTED_AT,
                description="Unbalanced posting",
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
                        amount=FluentNumber(value=Decimal("9.99"), formatted="9.99", precision=2),
                        currency=CurrencyCode("EUR"),
                    ),
                ),
            )

    def test_multi_currency_transaction_balances_per_currency(self) -> None:
        """A transaction may contain several currencies when each currency balances."""
        transaction = JournalTransaction(
            reference="TX-2026-0003",
            posted_at=_POSTED_AT,
            description="Mixed currency settlement",
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
                LedgerEntry(
                    account_code="3000",
                    side=PostingSide.DEBIT,
                    amount=FluentNumber(value=Decimal("5.00"), formatted="5.00", precision=2),
                    currency=CurrencyCode("USD"),
                ),
                LedgerEntry(
                    account_code="4000",
                    side=PostingSide.CREDIT,
                    amount=FluentNumber(value=Decimal("5.00"), formatted="5.00", precision=2),
                    currency=CurrencyCode("USD"),
                ),
            ),
        )

        assert transaction.is_balanced is True
        assert transaction.debits_by_currency() == {
            "EUR": Decimal("10.00"),
            "USD": Decimal("5.00"),
        }


class TestBook:
    """Tests for book aggregate invariants."""

    def test_rejects_duplicate_account_codes(self) -> None:
        """Book rejects duplicate account codes."""
        account = Account(
            code="1000",
            name="Cash",
            normal_side=PostingSide.DEBIT,
            currency=CurrencyCode("EUR"),
        )

        with pytest.raises(ValueError, match="Duplicate account code"):
            Book(
                code="demo",
                name="Demo Book",
                base_currency=CurrencyCode("EUR"),
                legislative_pack="lv.standard.2026",
                accounts=(account, account),
            )

    def test_rejects_account_cycles(self) -> None:
        """Book rejects cyclic account hierarchies."""
        with pytest.raises(ValueError, match="contains cycle"):
            Book(
                code="demo",
                name="Demo Book",
                base_currency=CurrencyCode("EUR"),
                legislative_pack="lv.standard.2026",
                accounts=(
                    Account(
                        code="1000",
                        name="Cash",
                        normal_side=PostingSide.DEBIT,
                        currency=CurrencyCode("EUR"),
                        parent_code="2000",
                    ),
                    Account(
                        code="2000",
                        name="Receivables",
                        normal_side=PostingSide.DEBIT,
                        currency=CurrencyCode("EUR"),
                        parent_code="1000",
                    ),
                ),
            )

    def test_rejects_unknown_transaction_account(self) -> None:
        """Book rejects transactions referencing unknown accounts."""
        transaction = JournalTransaction(
            reference="TX-2026-0004",
            posted_at=_POSTED_AT,
            description="Unknown account",
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

        with pytest.raises(ValueError, match="unknown account 2000"):
            Book(
                code="demo",
                name="Demo Book",
                base_currency=CurrencyCode("EUR"),
                legislative_pack="lv.standard.2026",
                accounts=(
                    Account(
                        code="1000",
                        name="Cash",
                        normal_side=PostingSide.DEBIT,
                        currency=CurrencyCode("EUR"),
                    ),
                ),
                transactions=(transaction,),
            )

    def test_rejects_transactions_outside_known_periods(self) -> None:
        """Book requires transaction periods to exist in the book period set."""
        transaction = JournalTransaction(
            reference="TX-2026-0005",
            posted_at=_POSTED_AT,
            description="Outside known periods",
            period=FiscalPeriod(fiscal_year=2026, quarter=2, month=4),
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

        with pytest.raises(ValueError, match="unknown fiscal period"):
            Book(
                code="demo",
                name="Demo Book",
                base_currency=CurrencyCode("EUR"),
                fiscal_calendar=FiscalCalendar(start_month=1),
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
                periods=(
                    BookPeriod(
                        period=FiscalPeriod(fiscal_year=2026, quarter=1, month=1),
                        start_date=date(2026, 1, 1),
                        end_date=date(2026, 3, 31),
                    ),
                ),
                transactions=(transaction,),
            )

    def test_append_transaction_returns_new_book(self) -> None:
        """Book append helpers preserve immutability semantics."""
        book = Book(
            code="demo",
            name="Demo Book",
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
            reference="TX-2026-0006",
            posted_at=_POSTED_AT,
            description="Immutable append",
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

        updated = book.append_transaction(transaction)

        assert book.transactions == ()
        assert updated.transactions == (transaction,)

    def test_rejects_draft_transactions_inside_book(self) -> None:
        """Book stores only posted transactions."""
        draft_transaction = JournalTransaction(
            reference="TX-2026-0007",
            posted_at=_POSTED_AT,
            description="Draft transaction",
            state=TransactionState.DRAFT,
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

        with pytest.raises(ValueError, match="only contain posted transactions"):
            Book(
                code="demo",
                name="Demo Book",
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
                transactions=(draft_transaction,),
            )
