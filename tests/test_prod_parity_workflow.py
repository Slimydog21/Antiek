"""Contract tests for the scheduled production-parity alarm."""

from pathlib import Path

import yaml

ROOT = Path(__file__).resolve().parents[1]
WORKFLOW_PATH = ROOT / ".github" / "workflows" / "prod_parity.yml"


def _workflow_text() -> str:
    return WORKFLOW_PATH.read_text(encoding="utf-8")


def test_workflow_is_schedule_or_manual_only() -> None:
    document = yaml.safe_load(_workflow_text())
    triggers = document.get("on", document.get(True))

    assert set(triggers) == {"schedule", "workflow_dispatch"}


def test_probe_propagates_blocking_checker_failures() -> None:
    text = _workflow_text()
    document = yaml.safe_load(text)
    probe = document["jobs"]["probe"]
    run = probe["steps"][-1]["run"]

    assert "continue-on-error" not in probe
    assert "tools/prod_parity/check.py" in run
    assert "||" not in run
    assert "::warning" not in run
    assert "continue-on-error" not in text
