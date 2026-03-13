"""Shared type aliases for the FinestVX accounting domain."""

from __future__ import annotations

from ftllexengine import FluentNumber
from ftllexengine.introspection import CurrencyCode

type AccountCode = str
"""Canonical chart-of-accounts code."""

type BookCode = str
"""Canonical book identifier."""

type LegislativePackCode = str
"""Identifier for a legislative-pack implementation."""

type TransactionReference = str
"""External or internal immutable transaction reference."""

type FluentAmount = FluentNumber
"""Accounting amount type backed by FTLLexEngine's float-free number wrapper."""

__all__ = [
    "AccountCode",
    "BookCode",
    "CurrencyCode",
    "FluentAmount",
    "LegislativePackCode",
    "TransactionReference",
]
