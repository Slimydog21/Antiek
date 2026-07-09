"""Real-path tests: Settings decision-tree install → process registry."""

from __future__ import annotations

import os
import sys

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

_REPO = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
if _REPO not in sys.path:
    sys.path.insert(0, _REPO)

from interfaces.research.api.settings_budget import (  # noqa: E402
    register_settings_budget_routes,
)
from substrate.model_registration import (  # noqa: E402
    clear_decision_tree_selection,
    get_decision_tree_model_id,
    get_decision_tree_registry,
    install_decision_tree_selection,
    read_decision_tree_selection,
    settings_budget_projection_still_owned_by_settings,
)


@pytest.fixture(autouse=True)
def _clear_registry():
    clear_decision_tree_selection()
    yield
    clear_decision_tree_selection()


def test_install_and_read_back():
    result = install_decision_tree_selection(
        "glm-5.2", provider_id="zhipu", ensure_registered=True
    )
    assert result.installed is True
    assert result.model_id == "glm-5.2"
    assert result.provider_id == "zhipu"
    assert get_decision_tree_model_id() == "glm-5.2"
    reg = get_decision_tree_registry()
    assert reg is not None
    assert reg.selected_model_id == "glm-5.2"
    status = read_decision_tree_selection()
    assert status["installed"] is True
    assert status["model_id"] == "glm-5.2"


def test_clear_resets_selection():
    install_decision_tree_selection("composer-2.5", provider_id="xai")
    cleared = clear_decision_tree_selection()
    assert cleared["installed"] is False
    assert get_decision_tree_model_id() is None
    assert get_decision_tree_registry() is None


def test_install_requires_provider_for_new_model():
    with pytest.raises(ValueError, match="provider_id"):
        install_decision_tree_selection("brand-new", ensure_registered=True)


def test_settings_api_install_and_clear():
    app = FastAPI()
    register_settings_budget_routes(app)
    client = TestClient(app)
    empty = client.get("/settings/decision-tree")
    assert empty.status_code == 200
    assert empty.json()["installed"] is False

    inst = client.post(
        "/settings/decision-tree",
        json={"model_id": "glm-5.2", "provider_id": "zhipu"},
    )
    assert inst.status_code == 200
    body = inst.json()
    assert body["installed"] is True
    assert body["model_id"] == "glm-5.2"
    assert body["provider_id"] == "zhipu"
    assert get_decision_tree_model_id() == "glm-5.2"

    again = client.get("/settings/decision-tree")
    assert again.json()["model_id"] == "glm-5.2"

    cleared = client.delete("/settings/decision-tree")
    assert cleared.status_code == 200
    assert cleared.json()["installed"] is False
    assert get_decision_tree_model_id() is None


def test_budget_projection_still_settings_owned():
    path = settings_budget_projection_still_owned_by_settings()
    assert "settings_budget" in path
    assert "estimate_prompt_cost" in path
