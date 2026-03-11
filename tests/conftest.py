"""Pytest configuration: Hypothesis profiles, fuzz markers, and skip reporting."""

from __future__ import annotations

import pytest
from hypothesis import HealthCheck, Phase, Verbosity, settings

# ---------------------------------------------------------------------------
# Hypothesis profiles
# ---------------------------------------------------------------------------
settings.register_profile(
    "dev",
    max_examples=500,
    deadline=200,
    phases=list(Phase),
)

settings.register_profile(
    "ci",
    max_examples=50,
    deadline=200,
    phases=list(Phase),
    derandomize=True,
    print_blob=True,
)

settings.register_profile(
    "verbose",
    max_examples=100,
    deadline=200,
    phases=list(Phase),
    verbosity=Verbosity.verbose,
)

settings.register_profile(
    "hypofuzz",
    max_examples=10000,
    deadline=None,
    phases=list(Phase),
    suppress_health_check=[HealthCheck.too_slow, HealthCheck.data_too_large],
)

settings.register_profile(
    "stateful_fuzz",
    max_examples=500,
    deadline=None,
    phases=list(Phase),
)

settings.load_profile("ci")


# ---------------------------------------------------------------------------
# Fuzz test skip enforcement
# ---------------------------------------------------------------------------
def pytest_collection_modifyitems(
    config: pytest.Config,  # noqa: ARG001 - required pytest hook signature
    items: list[pytest.Item],
) -> None:
    """Skip fuzz-marked tests unless the fuzz mark is explicitly selected."""
    fuzz_skip_reason = (
        "FUZZ: run with ./scripts/fuzz_hypofuzz.sh --deep or pytest -m fuzz"
    )
    for item in items:
        if item.get_closest_marker("fuzz") is not None:
            item.add_marker(pytest.mark.skip(reason=fuzz_skip_reason))


# ---------------------------------------------------------------------------
# SKIP-BREAKDOWN reporting (consumed by scripts/test.sh)
# ---------------------------------------------------------------------------
def pytest_terminal_summary(
    terminalreporter: pytest.TerminalReporter,
    exitstatus: int,  # noqa: ARG001 - required pytest hook signature
    config: pytest.Config,  # noqa: ARG001 - required pytest hook signature
) -> None:
    """Emit structured skip breakdown for agent-native test.sh parsing."""
    skipped_fuzz = 0
    skipped_other = 0
    for report in terminalreporter.stats.get("skipped", []):
        longrepr = report.longrepr
        if isinstance(longrepr, tuple) and len(longrepr) == 3:
            skip_reason = str(longrepr[2])
        else:
            skip_reason = str(longrepr)
        if "FUZZ:" in skip_reason:
            skipped_fuzz += 1
        else:
            skipped_other += 1
    terminalreporter.write_line(
        f"[SKIP-BREAKDOWN] fuzz={skipped_fuzz} other={skipped_other}"
    )
