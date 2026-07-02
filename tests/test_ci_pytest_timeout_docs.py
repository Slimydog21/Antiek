"""CI pytest throughput decision must match the live workflow."""

from __future__ import annotations

import re
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
CI = ROOT / ".github" / "workflows" / "ci.yml"
DECISION = ROOT / "docs" / "decisions" / "ci-pytest-timeout.md"


def _pytest_job_block() -> str:
    text = CI.read_text(encoding="utf-8")
    match = re.search(
        r"^  pytest:\n(?P<body>.*?)(?:\n  [a-zA-Z0-9_-]+:\n|\Z)",
        text,
        re.MULTILINE | re.DOTALL,
    )
    assert match is not None, "pytest job not found in ci.yml"
    return match.group("body")


def test_ci_pytest_job_stays_on_xdist_with_reduced_timeout() -> None:
    job = _pytest_job_block()

    assert "timeout-minutes: 20" in job
    assert "timeout-minutes: 40" not in job
    assert "python -m pytest tests/ -q -m \"not integration\"" in job
    assert "-n auto --dist loadscope --tb=short" in job
    assert "5859 passed" in job
    assert "worker-order flakiness" in job


def test_ci_timeout_decision_records_same_xdist_contract() -> None:
    doc = DECISION.read_text(encoding="utf-8")
    compact = " ".join(doc.split())

    assert "2026-06-30 — xdist validation attempt, then wired" in doc
    assert "python -m pytest tests/ -q -m \"not integration\" -n auto --dist loadscope" in doc
    assert "drops the pytest job timeout to 20 minutes" in compact
    assert "5859 passed, 14 skipped, 25 warnings" in doc
    assert "the workflow now runs the full suite with xdist" in compact.lower()
