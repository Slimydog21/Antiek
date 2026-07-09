"""Consumer double-run: select → install → read-back decision-tree selection."""

from __future__ import annotations

import os
import sys

_REPO = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
if _REPO not in sys.path:
    sys.path.insert(0, _REPO)

from substrate.model_registration import (  # noqa: E402
    clear_decision_tree_selection,
    get_decision_tree_model_id,
    install_decision_tree_selection,
    read_decision_tree_selection,
    settings_budget_projection_still_owned_by_settings,
)


def _once() -> dict[str, object]:
    clear_decision_tree_selection()
    r = install_decision_tree_selection(
        "launch-glm", provider_id="zhipu", ensure_registered=True
    )
    assert r.model_id == "launch-glm"
    assert get_decision_tree_model_id() == "launch-glm"
    status = read_decision_tree_selection()
    assert status["installed"] is True
    assert status["model_id"] == "launch-glm"
    budget_path = settings_budget_projection_still_owned_by_settings()
    clear_decision_tree_selection()
    assert get_decision_tree_model_id() is None
    # re-install for return snapshot after clear-cycle integrity
    install_decision_tree_selection("launch-glm", provider_id="zhipu")
    return {
        "model_id": get_decision_tree_model_id(),
        "provider": read_decision_tree_selection()["provider_id"],
        "budget_path": budget_path,
    }


def test_decision_tree_install_consumer_double_run_stable():
    a = _once()
    b = _once()
    assert a == b
    assert a["model_id"] == "launch-glm"
    assert a["provider"] == "zhipu"
    assert "settings_budget" in str(a["budget_path"])
