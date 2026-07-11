from __future__ import annotations

import subprocess
import sys
from pathlib import Path

from tools.lint.campaign_artifact_check import find_forbidden

REPO = Path(__file__).resolve().parent.parent


def test_rejects_campaign_inventory_session_and_log_artifacts() -> None:
    paths = (
        "docs/campaigns/2026-07-09/inventory-aaa.txt",
        "docs/campaigns/2026-07-09/SESSION-ARC-wave.md",
        "docs/campaigns/2026-07-09/residual-tests.log",
    )
    assert find_forbidden(paths) == tuple(sorted(paths))


def test_allows_curated_decisions_and_executable_htmlspecs() -> None:
    assert find_forbidden(
        (
            "docs/decisions/research-reading-spine-handoff.md",
            "docs/htmlspec/deep-research-loop/index.html",
            "tests/test_campaign_artifact_check.py",
        )
    ) == ()


def test_normalizes_windows_separators_and_deduplicates() -> None:
    expected = "docs/campaigns/run/inventory.txt"
    assert find_forbidden((r"docs\campaigns\run\inventory.txt", expected)) == (expected,)


def test_current_tracked_tree_is_clean() -> None:
    result = subprocess.run(
        [sys.executable, "tools/lint/campaign_artifact_check.py", str(REPO)],
        cwd=REPO,
        capture_output=True,
        text=True,
    )
    assert result.returncode == 0, result.stderr
    assert "campaign-artifact-check: clean" in result.stdout
