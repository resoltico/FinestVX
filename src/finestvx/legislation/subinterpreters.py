"""Subinterpreter-backed legislative validation helpers."""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import TYPE_CHECKING, cast

from ftllexengine import InterpreterPool, require_positive_int

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


@dataclass(slots=True)
class LegislativeInterpreterRunner:
    """Execute built-in legislative pack validation using a reusable interpreter pool.

    Pre-warms a bounded pool of PEP 734 subinterpreters to amortize interpreter
    creation cost across the lifetime of the service. For batch legislative
    validation, this eliminates O(n) interpreter lifecycle overhead.

    Call ``close()`` when the runner is no longer needed to release all pool
    resources. In service deployments, this is typically wired into the service
    shutdown sequence.

    Attributes:
        pool_min_size: Minimum interpreters to pre-warm at construction time.
        pool_max_size: Maximum total interpreters (idle + checked out).
    """

    pool_min_size: int = 2
    pool_max_size: int = 8
    _pool: InterpreterPool = field(init=False, repr=False)

    def __post_init__(self) -> None:
        """Validate pool bounds and initialize the interpreter pool."""
        require_positive_int(self.pool_min_size, "pool_min_size")
        if self.pool_max_size < self.pool_min_size:
            msg = "pool_max_size must be >= pool_min_size"
            raise ValueError(msg)
        self._pool = InterpreterPool(
            min_size=self.pool_min_size,
            max_size=self.pool_max_size,
        )

    def validate(
        self,
        pack_code: str,
        book: Book,
        transaction: JournalTransaction,
    ) -> LegislativeValidationResult:
        """Run legislative validation in an isolated interpreter from the pool."""
        with self._pool.acquire() as interp:
            call_result = interp.call(_validate_in_subinterpreter, pack_code, book, transaction)
        # interp.call() returns object; cast to the known return type of _validate_in_subinterpreter
        result_pack_code, raw_issues = cast(
            "tuple[str, tuple[tuple[str, str, int | None], ...]]",
            call_result,
        )
        return LegislativeValidationResult(
            result_pack_code,
            tuple(
                LegislativeIssue(code=code, message=message, entry_index=entry_index)
                for code, message, entry_index in raw_issues
            ),
        )

    def close(self) -> None:
        """Close all pool interpreters and release resources."""
        self._pool.close()


def validate_transaction_isolated(
    pack_code: str,
    book: Book,
    transaction: JournalTransaction,
) -> LegislativeValidationResult:
    """Convenience wrapper for one-shot isolated legislative validation."""
    runner = LegislativeInterpreterRunner(pool_min_size=1, pool_max_size=1)
    try:
        return runner.validate(pack_code, book, transaction)
    finally:
        runner.close()
