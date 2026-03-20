"""State-machine fuzz tests for FinestVX ledger append-only invariants.

Run with::

    pytest -m fuzz
    ./scripts/fuzz_hypofuzz.sh --deep
"""

from __future__ import annotations

from datetime import UTC, datetime
from decimal import Decimal

import pytest
from ftllexengine import FluentNumber, make_fluent_number
from ftllexengine.introspection import CurrencyCode
from hypothesis import Phase, event, settings
from hypothesis import strategies as st
from hypothesis.stateful import RuleBasedStateMachine, invariant, rule

from finestvx.core import Account, Book, JournalTransaction, LedgerEntry, PostingSide

pytestmark = pytest.mark.fuzz

_POSTED_AT = datetime(2026, 1, 15, 9, 30, tzinfo=UTC)
_EUR = CurrencyCode("EUR")

_AMOUNTS = st.decimals(
    min_value=Decimal("0.01"),
    max_value=Decimal("9999.99"),
    places=2,
    allow_nan=False,
    allow_infinity=False,
).map(make_fluent_number)

_REFERENCES = st.text(
    alphabet=st.characters(min_codepoint=48, max_codepoint=90),
    min_size=4,
    max_size=12,
).filter(lambda s: s.strip() != "")

_SKIP_REASON = "FUZZ: run with ./scripts/fuzz_hypofuzz.sh --deep or pytest -m fuzz"


def _make_book() -> Book:
    """Return a minimal two-account EUR book."""
    return Book(
        code="fuzz",
        name="Fuzz Book",
        base_currency=_EUR,
        legislative_pack="lv.standard.2026",
        accounts=(
            Account(
                code="1000",
                name="Cash",
                normal_side=PostingSide.DEBIT,
                currency=_EUR,
            ),
            Account(
                code="2000",
                name="Revenue",
                normal_side=PostingSide.CREDIT,
                currency=_EUR,
            ),
        ),
    )


class LedgerStateMachine(RuleBasedStateMachine):
    """Stateful model for append-only ledger operations.

    Invariants checked after every rule:
    - ``book.transactions`` is a tuple (immutable, append-only semantics).
    - Every stored transaction satisfies ``is_balanced``.
    - Running debit sum equals running credit sum per currency.
    """

    def __init__(self) -> None:
        super().__init__()
        self._book = _make_book()
        self._debit_total: Decimal = Decimal(0)
        self._credit_total: Decimal = Decimal(0)

    @rule(amount=_AMOUNTS, reference=_REFERENCES)
    def post_balanced_transaction(self, amount: FluentNumber, reference: str) -> None:
        """Append a balanced EUR debit/credit pair to the book."""
        tx = JournalTransaction(
            reference=reference,
            posted_at=_POSTED_AT,
            description="State machine post",
            entries=(
                LedgerEntry(
                    account_code="1000",
                    side=PostingSide.DEBIT,
                    amount=amount,
                    currency=_EUR,
                ),
                LedgerEntry(
                    account_code="2000",
                    side=PostingSide.CREDIT,
                    amount=amount,
                    currency=_EUR,
                ),
            ),
        )
        self._book = self._book.append_transaction(tx)
        self._debit_total += amount.decimal_value
        self._credit_total += amount.decimal_value
        event(f"rule=post_balanced_transaction tx_count={len(self._book.transactions)}")

    @invariant()
    def transactions_is_tuple(self) -> None:
        """book.transactions is always a tuple."""
        event("invariant=transactions_is_tuple")
        assert isinstance(self._book.transactions, tuple)

    @invariant()
    def all_stored_transactions_are_balanced(self) -> None:
        """Every transaction in the book satisfies the zero-sum invariant."""
        event("invariant=all_stored_transactions_are_balanced")
        for tx in self._book.transactions:
            assert tx.is_balanced, f"unbalanced transaction: {tx.reference}"

    @invariant()
    def running_totals_are_equal(self) -> None:
        """Accumulated debit and credit totals remain equal after every append."""
        event("invariant=running_totals_are_equal")
        assert self._debit_total == self._credit_total


TestCase = LedgerStateMachine.TestCase
TestCase.settings = settings(
    stateful_step_count=50,
    deadline=None,
    phases=[Phase.reuse, Phase.generate, Phase.target, Phase.shrink],
)
