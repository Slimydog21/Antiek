"""Settings add-model product path (residual bf)."""

from __future__ import annotations

import os
import sys

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
    list_operator_models,
    register_operator_model,
)


def setup_function():
    clear_decision_tree_selection()


def test_register_operator_model_lists():
    clear_decision_tree_selection()
    out = register_operator_model(
        "glm-5.2",
        provider_id="zai",
        display_name="GLM 5.2",
        select=True,
    )
    assert out["model_id"] == "glm-5.2"
    assert out["provider_id"] == "zai"
    assert out["selected"] is True
    assert out["view_format"] == "html"
    listing = list_operator_models()
    assert listing["count"] == 1
    assert listing["active_model_id"] == "glm-5.2"
    assert listing["models"][0]["model_id"] == "glm-5.2"


def test_api_add_model_double_run():
    clear_decision_tree_selection()
    app = FastAPI()
    register_settings_budget_routes(app)
    client = TestClient(app)

    empty = client.get("/settings/registered-models")
    assert empty.status_code == 200
    assert empty.json()["count"] == 0
    assert empty.json()["view_format"] == "html"

    r1 = client.post(
        "/settings/models/register",
        json={
            "model_id": "composer-2.5",
            "provider_id": "xai",
            "display_name": "Composer 2.5",
            "select": True,
        },
    )
    assert r1.status_code == 200, r1.text
    b1 = r1.json()
    assert b1["count"] == 1
    assert b1["model_id"] == "composer-2.5"
    assert b1["active_model_id"] == "composer-2.5"

    r2 = client.post(
        "/settings/models/register",
        json={
            "model_id": "composer-2.5",
            "provider_id": "xai",
            "select": True,
        },
    )
    assert r2.status_code == 200
    # Idempotent re-register keeps single entry
    assert r2.json()["count"] == 1
    assert r2.json()["active_model_id"] == "composer-2.5"

    bad = client.post(
        "/settings/models/register",
        json={"model_id": "orphan", "provider_id": ""},
    )
    # Pydantic min_length=1 → 422; empty provider rejected honestly
    assert bad.status_code in (400, 422)
