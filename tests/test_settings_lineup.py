"""AI Role Lineup vertical — operator model-selection registry.

All offline + deterministic: registry + user-model files redirected to tmp
via env; the bench union (user models + presets + dispatch tiers) is
exercised through the REAL settings mount seam without any network.
"""

from __future__ import annotations

import json
from collections.abc import Iterator
from pathlib import Path

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

from interfaces.research.api.settings_budget import register_settings_budget_routes
from interfaces.research.api.settings_lineup import (
    ACTION_BY_ID,
    _registry_path,
    register_settings_lineup_routes,
)
from substrate.dispatch.router import reset_provider_registry


def _fresh_app() -> FastAPI:
    app = FastAPI()
    register_settings_budget_routes(app)
    register_settings_lineup_routes(app)
    return app


@pytest.fixture
def env(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> Path:
    monkeypatch.setenv("ANTIEK_HOME", str(tmp_path))
    monkeypatch.setenv(
        "ANTIEK_USER_MODELS_PATH", str(tmp_path / "settings" / "user_models.json")
    )
    monkeypatch.setenv("ANTIEK_BYOK_ARTIFACT", str(tmp_path / "byok" / "credentials.enc"))
    monkeypatch.setenv("ANTIEK_BYOK_KEY_FILE", str(tmp_path / "byok" / "master.key"))
    monkeypatch.setenv("ANTIEK_LINEUP_PATH", str(tmp_path / "settings" / "lineup.json"))
    reset_provider_registry()
    return tmp_path


@pytest.fixture
def client(env: Path) -> Iterator[TestClient]:
    with TestClient(_fresh_app()) as c:
        yield c
    reset_provider_registry()


def test_catalog_is_complete_and_consistent(client: TestClient) -> None:
    """Every advanced action lives under exactly one general role; the
    four operator-defined roles are present and the discovered roles are
    flagged honestly."""
    resp = client.get("/settings/lineup")
    assert resp.status_code == 200
    data = resp.json()
    role_ids = {r["role_id"] for r in data["general"]}
    assert {"writer", "data_miner", "data_refinement", "data_verification"} <= role_ids
    assert "orchestrator" in role_ids  # discovered-missing role
    assert "critic" in role_ids
    assert "media_creator" in role_ids
    assert "voice" in role_ids
    assert "indexer" in role_ids
    action_ids = {a["action_id"] for a in data["advanced"]}
    assert action_ids == set(ACTION_BY_ID)
    # no orphan action: every action is listed under its role's actions
    for role in data["general"]:
        for action in role["actions"]:
            assert action["action_id"] in action_ids


def test_bench_contains_dispatch_tiers_and_presets(client: TestClient) -> None:
    resp = client.get("/settings/lineup")
    assert resp.status_code == 200
    bench = {(b["provider_id"], b["model_id"]) for b in resp.json()["bench"]}
    # dispatch config tiers must be substitutable (server defaults)
    assert ("zai", "glm-5.2") in bench
    assert ("deepseek", "deepseek-v4-pro") in bench
    assert ("xiaomi", "mimo-v2.5-pro") in bench
    # BYOT presets must be on the bench
    assert ("openai", "gpt-5.6-luna") in bench
    assert ("anthropic", "claude-haiku-4-5-20251001") in bench


def test_put_and_get_roundtrip(client: TestClient) -> None:
    put = client.put(
        "/settings/lineup",
        json={
            "general": {
                "writer": {"provider_id": "zai", "model_id": "glm-5.2"},
                "data_miner": None,
            },
            "advanced": {
                "verification": {"provider_id": "deepseek", "model_id": "deepseek-v4-pro"}
            },
        },
    )
    assert put.status_code == 200, put.text
    data = put.json()
    assert data["assignments"]["general"]["writer"] == {
        "provider_id": "zai",
        "model_id": "glm-5.2",
    }
    assert data["assignments"]["general"]["data_miner"] is None
    assert data["assignments"]["advanced"]["verification"] == {
        "provider_id": "deepseek",
        "model_id": "deepseek-v4-pro",
    }
    # persisted to the sidecar
    registry = json.loads(_registry_path().read_text(encoding="utf-8"))
    assert "__operator__" in registry["owners"]

    # GET returns the same view
    get = client.get("/settings/lineup")
    assert get.status_code == 200
    assert get.json()["assignments"] == data["assignments"]


def test_unknown_slot_and_off_bench_model_rejected(client: TestClient) -> None:
    bad_slot = client.put(
        "/settings/lineup", json={"general": {"not_a_role": {"provider_id": "zai", "model_id": "glm-5.2"}}}
    )
    assert bad_slot.status_code == 422
    assert "unknown role slot" in bad_slot.json()["detail"]

    off_bench = client.put(
        "/settings/lineup",
        json={"general": {"writer": {"provider_id": "openai", "model_id": "gpt-9999-nonexistent"}}},
    )
    assert off_bench.status_code == 422
    assert "not on the bench" in off_bench.json()["detail"]

    bad_action = client.put(
        "/settings/lineup", json={"advanced": {"no_such_action": {"provider_id": "zai", "model_id": "glm-5.2"}}}
    )
    assert bad_action.status_code == 422
    assert "unknown action slot" in bad_action.json()["detail"]


def test_auto_null_is_always_valid(client: TestClient) -> None:
    put = client.put(
        "/settings/lineup",
        json={"general": {"writer": None, "data_verification": None}, "advanced": {"verification": None}},
    )
    assert put.status_code == 200, put.text
    assert put.json()["assignments"]["general"]["writer"] is None
    assert put.json()["assignments"]["advanced"]["verification"] is None


def test_catalog_dispatch_roles_resolve_in_config(client: TestClient) -> None:
    """The catalog must never name a dispatch role the router cannot route:
    every llm action's dispatch_role must exist in config.role_tiers (this
    is what the dispatch binding depends on), and the true dispatch-role
    set is the config's — event-log labels are not dispatch roles."""
    import pathlib as _pl

    from substrate.dispatch.lineup_catalog import ACTION_BY_ID
    from substrate.dispatch.router import DispatchConfig

    cfg = DispatchConfig.from_yaml(
        _pl.Path(__file__).resolve().parents[1] / "substrate" / "dispatch" / "config.yaml"
    )
    configured = set(cfg.role_tiers)
    for action in ACTION_BY_ID.values():
        if action.kind == "llm" and action.dispatch_role is not None:
            assert action.dispatch_role in configured, (
                f"action {action.action_id!r} names dispatch_role "
                f"{action.dispatch_role!r} which is not in config.role_tiers"
            )
    # the previously-fabricated event-label roles must NOT appear as dispatch
    # roles anywhere in the catalog
    for action in ACTION_BY_ID.values():
        assert action.dispatch_role not in {
            "write_repository", "write_composition", "write_editor",
            "attribution", "extractor",
        }
    # the one true config gap is now closed
    assert "interviewer" in configured


def test_default_tiers_are_present_in_catalog(client: TestClient) -> None:
    resp = client.get("/settings/lineup")
    assert resp.status_code == 200
    by_id = {a["action_id"]: a for a in resp.json()["advanced"]}
    assert by_id["research_synthesis"]["default_tier"] == "synthesis"
    assert by_id["verification"]["default_tier"] == "verify"
    assert by_id["evidence_retrieval"]["default_tier"] == "flash"
    assert by_id["text_to_speech"]["default_tier"] == "tts"
    assert by_id["image_generation"]["default_tier"] is None  # non-dispatch media
