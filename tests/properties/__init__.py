"""Hypothesis property tests for substrate.

Tests skip gracefully if ``hypothesis`` is not installed in the venv.
``hypothesis`` is deliberately not in pyproject direct deps (the
invariants-pointer discipline); the operator opts it in by ``pip install
hypothesis`` when ready.
"""
