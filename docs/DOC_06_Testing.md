---
afad: "3.3"
version: "0.5.0"
domain: TESTING
updated: "2026-03-15"
route:
  keywords: [pytest, hypothesis, mypy, pylint, ruff, lint.sh, test.sh, coverage, bash 5, quality gates, conftest, hypothesis profiles]
  questions: ["how do i run finestvx tests?", "what quality tools are configured?", "do the shared scripts pass?", "what coverage threshold is enforced?", "what test categories exist now?", "what hypothesis profiles are available?"]
---

# FinestVX Testing Reference

## Current Test Categories

| Category | Location | Purpose |
|:---------|:---------|:--------|
| Unit | `tests/test_*.py` | Deterministic behavior checks for domain, persistence, localization, export, runtime, gateway, and legislation. |
| Property | `tests/test_*_property.py` | Invariant checks using Hypothesis. Strategies emit `hypothesis.event()` for semantic fuzzer guidance. |
| Strategy Support | `tests/strategies/` | Shared generators for property tests (factory functions; all emit `event()` calls). |
| Test Support | `tests/support/` | Deterministic builders and fixtures. |

## Shared Scripts

### Invocation

Bash 5.0+ is a hard requirement. The scripts enforce this with an immediate `exit 1` if Bash < 5 is detected.

```bash
PY_VERSION=3.14 ./scripts/lint.sh
PY_VERSION=3.14 ./scripts/test.sh
```

On macOS, ensure Homebrew bash is first in `$PATH` or invoke via the shebang (`./`):
```bash
brew install bash          # once
PY_VERSION=3.14 ./scripts/lint.sh
```

## Hypothesis Profiles

Profiles are defined in `tests/conftest.py` and loaded automatically.

| Profile | max_examples | deadline | Use Case |
|:--------|:-------------|:---------|:---------|
| `ci` | 50 | 200ms | CI (default; `derandomize=True`, `print_blob=True`) |
| `dev` | 500 | 200ms | Local development |
| `verbose` | 100 | 200ms | Debugging with progress output |
| `hypofuzz` | 10000 | None | Coverage-guided fuzzing |
| `stateful_fuzz` | 500 | None | State machine fuzzing |

Override at the command line:
```bash
HYPOTHESIS_PROFILE=dev PYTHONPATH=src .venv-3.14/bin/pytest tests/test_core_models_property.py
```

## Current Gate Status

Repository-level status:
- `scripts/lint.sh`: pass
- `scripts/test.sh`: pass

Full-suite status:
- tests: `67 passed`
- coverage threshold: `>=95%`
- current coverage: `>=97%`

## Direct Tooling Commands

```bash
PYTHONPATH=src .venv-3.14/bin/pytest
PYTHONPATH=src .venv-3.14/bin/ruff check src tests
PYTHONPATH=src .venv-3.14/bin/mypy src tests
PYTHONPATH=src .venv-3.14/bin/pylint src/finestvx
cd tests && PYTHONPATH=../src ../.venv-3.14/bin/pylint --rcfile=.pylintrc .
```

## Configuration Files

| File | Responsibility |
|:-----|:---------------|
| `pyproject.toml` | pytest options, coverage, mypy, Ruff, production Pylint settings |
| `tests/conftest.py` | Hypothesis profiles, fuzz skip enforcement, `[SKIP-BREAKDOWN]` reporting |
| `tests/mypy.ini` | pragmatic mypy policy for tests |
| `tests/.pylintrc` | pragmatic Pylint policy for tests |

## Test Discipline

- production code remains strict;
- tests use pragmatic casts and fakes only where type-checkers cannot model failure-path testing cleanly;
- all `@given` tests emit at least one `hypothesis.event()` call for semantic fuzzer guidance;
- coverage validates implemented behavior, not excuses missing behavior.
