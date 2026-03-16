"""Tests for FinestVX validation report behavior."""

from __future__ import annotations

import pytest
from ftllexengine.integrity import IntegrityCheckFailedError

from finestvx.validation import ValidationFinding, ValidationReport, ValidationSeverity


class TestValidationReport:
    """Validation report acceptance and failure behavior."""

    def test_acceptance_and_require_valid_behaviour(self) -> None:
        """Accepted reports pass, invalid reports raise integrity errors."""
        accepted = ValidationReport(
            (
                ValidationFinding(
                    code="INFO_ONLY",
                    message="Informational",
                    severity=ValidationSeverity.INFO,
                    source="tests",
                ),
            )
        )
        accepted.require_valid(component="validation", operation="noop")
        assert accepted.accepted is True

        rejected = ValidationReport(
            (
                ValidationFinding(
                    code="BROKEN_ONE",
                    message="First error",
                    severity=ValidationSeverity.ERROR,
                    source="tests",
                ),
                ValidationFinding(
                    code="BROKEN_TWO",
                    message="Second error",
                    severity=ValidationSeverity.ERROR,
                    source="tests",
                ),
            )
        )

        with pytest.raises(IntegrityCheckFailedError, match="BROKEN_ONE, BROKEN_TWO") as exc_info:
            rejected.require_valid(component="validation", operation="commit")
        assert rejected.accepted is False
        assert exc_info.value.context is not None
        assert exc_info.value.context.timestamp is not None
        assert exc_info.value.context.wall_time_unix is not None
