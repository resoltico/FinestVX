"""Runtime strategy metrics for FinestVX Hypothesis strategies.

Tracks expected events, strategy families, and intended weight distributions.
Activated during deep fuzz runs::

    ./scripts/fuzz_hypofuzz.sh --deep --metrics

Three constants are consumed by the metrics collection infrastructure:

- ``EXPECTED_EVENTS``: all strategy-level event strings emitted by
  ``tests/strategies/``.  Update when a new strategy variant is added.
- ``STRATEGY_CATEGORIES``: maps event prefix to a human-readable family name
  for grouped reporting.
- ``INTENDED_WEIGHTS``: expected per-variant fraction within each strategy
  family.  Used to detect skewed generation (threshold: 0.15 deviation).
"""

from __future__ import annotations

# ---------------------------------------------------------------------------
# Events emitted by tests/strategies/accounting.py
#
# currencies(): strategy=currency_{code} for each sampled currency
# transaction_references(): strategy=reference_len_{n} for n in 4..12
# fluent_amounts(): strategy=amount_precision_{n}; always 2 since places=2
# ---------------------------------------------------------------------------

EXPECTED_EVENTS: frozenset[str] = frozenset(
    {
        "strategy=currency_EUR",
        "strategy=currency_USD",
        *(f"strategy=reference_len_{n}" for n in range(4, 13)),
        "strategy=amount_precision_2",
    }
)

STRATEGY_CATEGORIES: dict[str, str] = {
    "strategy=currency_": "Currency selection",
    "strategy=reference_len_": "Transaction reference length",
    "strategy=amount_precision_": "Ledger amount decimal precision",
}

# Expected fraction of each variant within its family (must sum to ~1.0).
# A deviation > 0.15 from any entry signals a weight skew in generation.
INTENDED_WEIGHTS: dict[str, float] = {
    # currencies: uniform 50/50 across EUR and USD
    "strategy=currency_EUR": 0.5,
    "strategy=currency_USD": 0.5,
    # reference lengths: uniform across 4..12 (9 values)
    **{f"strategy=reference_len_{n}": 1 / 9 for n in range(4, 13)},
    # amounts: places=2 forces all generated values to have exactly 2 decimal places
    "strategy=amount_precision_2": 1.0,
}
