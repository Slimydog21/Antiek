"""No workflow may cancel its own run on a push to main.

Every commit on main is a release candidate — the ansible deploy pulls main
HEAD — so a run that gets cancelled leaves that commit with no verdict. A
concurrency group keyed on ``github.ref`` is the same value for every push to
main, so with ``cancel-in-progress: true`` each merge kills the previous
merge's run.

This is not hypothetical. On ci.yml it produced 32 cancelled / 8 failure /
ZERO success across 40 main runs before #3203 keyed the group by
``github.sha``. The same shape then survived in four other workflows,
including the one that emits a REQUIRED check. This test exists so the next
workflow to be added cannot reintroduce it quietly.

Coalescing on pull_request is correct and stays allowed: only the latest head
of a PR is worth checking.
"""

from __future__ import annotations

import re
from pathlib import Path

import pytest
import yaml

_ROOT = Path(__file__).resolve().parents[1]
_WORKFLOWS = _ROOT / ".github" / "workflows"


def _workflow_files() -> list[Path]:
    return sorted(_WORKFLOWS.glob("*.yml"))


def _runs_on_main_push(doc: dict) -> bool:
    # PyYAML parses the bare key `on:` as the boolean True.
    triggers = doc.get("on", doc.get(True)) or {}
    if not isinstance(triggers, dict):
        return False
    push = triggers.get("push")
    if not isinstance(push, dict):
        return bool(push)
    branches = push.get("branches") or []
    return "main" in branches or not branches


def test_workflows_exist_to_check() -> None:
    """Not vacuous: if the glob breaks, every assertion below passes silently."""
    files = _workflow_files()
    assert len(files) >= 8, f"expected the workflow set, found {len(files)}"
    assert any(f.name == "ci.yml" for f in files)


@pytest.mark.parametrize("path", _workflow_files(), ids=lambda p: p.name)
def test_no_unconditional_cancel_on_main_push(path: Path) -> None:
    doc = yaml.safe_load(path.read_text(encoding="utf-8"))
    concurrency = (doc or {}).get("concurrency")
    if not concurrency:
        return  # no group at all: nothing can cancel anything
    if not _runs_on_main_push(doc or {}):
        return  # never runs on a main push, so the hazard does not apply

    group = str(concurrency.get("group", ""))
    cancel = str(concurrency.get("cancel-in-progress", "")).strip().lower()

    if cancel in {"", "false"}:
        return  # never cancels; safe whatever the key is

    # Cancelling is only safe when the group varies per commit, or when the
    # cancel itself is gated to pull_request events.
    varies_per_commit = "github.sha" in group or "github.run_id" in group
    cancel_is_pr_only = "pull_request" in cancel

    assert varies_per_commit or cancel_is_pr_only, (
        f"{path.name} cancels in-progress runs on a group that is constant "
        f"across pushes to main (group={group!r}, cancel-in-progress={cancel!r}). "
        "Every merge would cancel the previous merge's run and main would "
        "never reach a verdict. Key the group by github.sha for push events, "
        "or gate cancel-in-progress to pull_request. See #3203."
    )


@pytest.mark.parametrize("path", _workflow_files(), ids=lambda p: p.name)
def test_concurrency_group_is_not_repository_global(path: Path) -> None:
    """A group with no variable at all serializes the whole repository."""
    doc = yaml.safe_load(path.read_text(encoding="utf-8"))
    concurrency = (doc or {}).get("concurrency")
    if not concurrency:
        return
    group = str(concurrency.get("group", ""))
    cancel = str(concurrency.get("cancel-in-progress", "")).strip().lower()
    if cancel in {"", "false"}:
        return

    assert re.search(r"\$\{\{", group), (
        f"{path.name} has a constant concurrency group ({group!r}) with "
        "cancel-in-progress enabled, so any run of this workflow cancels "
        "every other run of it — including a scheduled run killed by a manual "
        "dispatch. Add a variable to the group."
    )
