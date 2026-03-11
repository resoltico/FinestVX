"""Structured validation reports for FinestVX domain and localization checks."""

from __future__ import annotations

from dataclasses import dataclass
from enum import StrEnum

from ftllexengine.integrity import IntegrityCheckFailedError, IntegrityContext

__all__ = [
    "ValidationFinding",
    "ValidationReport",
    "ValidationSeverity",
]


class ValidationSeverity(StrEnum):
    """Severity levels used by FinestVX validation reports."""

    ERROR = "error"
    WARNING = "warning"
    INFO = "info"


@dataclass(frozen=True, slots=True)
class ValidationFinding:
    """Single validation finding emitted by a FinestVX validation workflow."""

    code: str
    message: str
    severity: ValidationSeverity
    source: str


@dataclass(frozen=True, slots=True)
class ValidationReport:
    """Immutable collection of validation findings."""

    findings: tuple[ValidationFinding, ...] = ()

    @property
    def accepted(self) -> bool:
        """Return ``True`` when the report contains no error findings."""
        return all(finding.severity is not ValidationSeverity.ERROR for finding in self.findings)

    def require_valid(self, *, component: str, operation: str) -> None:
        """Raise ``IntegrityCheckFailedError`` when the report is invalid."""
        if self.accepted:
            return
        error_codes = ", ".join(
            finding.code
            for finding in self.findings
            if finding.severity is ValidationSeverity.ERROR
        )
        context = IntegrityContext(component=component, operation=operation)
        msg = f"Validation failed: {error_codes}"
        raise IntegrityCheckFailedError(msg, context=context)
