"""Subinterpreter-backed legislative validation helpers."""

from __future__ import annotations

from concurrent import interpreters
from typing import TYPE_CHECKING

from .protocols import LegislativeIssue, LegislativeValidationResult
from .registry import create_default_pack_registry

if TYPE_CHECKING:
    from finestvx.core.models import Book, JournalTransaction

__all__ = [
    "LegislativeInterpreterRunner",
    "validate_transaction_isolated",
]


def _validate_in_subinterpreter(
    pack_code: str,
    book: Book,
    transaction: JournalTransaction,
) -> tuple[str, tuple[tuple[str, str, int | None], ...]]:
    """Resolve a built-in legislative pack and validate within a subinterpreter."""
    pack = create_default_pack_registry().resolve(pack_code)
    result = pack.validate_transaction(book, transaction)
    return (
        result.pack_code,
        tuple((issue.code, issue.message, issue.entry_index) for issue in result.issues),
    )


class LegislativeInterpreterRunner:
    """Execute built-in legislative pack validation inside a fresh subinterpreter."""

    __slots__ = ()

    def validate(
        self,
        pack_code: str,
        book: Book,
        transaction: JournalTransaction,
    ) -> LegislativeValidationResult:
        """Run legislative validation in an isolated interpreter."""
        interpreter = interpreters.create()
        try:
            result_pack_code, raw_issues = interpreter.call(
                _validate_in_subinterpreter,
                pack_code,
                book,
                transaction,
            )
        finally:
            interpreter.close()
        return LegislativeValidationResult(
            result_pack_code,
            tuple(
                LegislativeIssue(code=code, message=message, entry_index=entry_index)
                for code, message, entry_index in raw_issues
            ),
        )


def validate_transaction_isolated(
    pack_code: str,
    book: Book,
    transaction: JournalTransaction,
) -> LegislativeValidationResult:
    """Convenience wrapper for one-shot isolated legislative validation."""
    return LegislativeInterpreterRunner().validate(pack_code, book, transaction)
