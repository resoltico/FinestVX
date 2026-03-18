"""Intensive fuzz tests excluded from normal CI runs.

All tests in this package carry ``@pytest.mark.fuzz`` and are skipped during
``test.sh``.  Run with::

    pytest -m fuzz
    ./scripts/fuzz_hypofuzz.sh --deep
"""
