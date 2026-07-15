import os
from types import SimpleNamespace

import pytest
from fastapi.testclient import TestClient

from interfaces.research.api.app import create_app
from interfaces.research.api.artifact_routes import (
    _read_store_file,
    _trajectory_belongs_to_owner,
    _verified_index,
)
from substrate.research_artifact.compose import composition_id_for, render_composition_index


def test_compose_routes_validate_lifecycle_and_hide_paths(monkeypatch, tmp_path):
    monkeypatch.setenv("ANTIEK_OPERATOR_TOKEN", "secret")
    monkeypatch.setattr(
        "interfaces.research.api.artifact_routes.trajectory",
        lambda iid: [{"action_type": "investigation.completed"}],
    )
    result = SimpleNamespace(
        composition_id="cmp-" + "a" * 64,
        ordered_set_digest="a" * 64,
        members=[
            SimpleNamespace(investigation_id="inv-a", content_hash="1" * 64),
            SimpleNamespace(investigation_id="inv-b", content_hash="2" * 64),
        ],
        hash_conflicts=[],
    )
    monkeypatch.setattr(
        "interfaces.research.api.artifact_routes.compose_artifacts", lambda *args, **kwargs: result
    )
    client = TestClient(create_app(register_wrestling=False, register_providers=False))
    assert (
        client.post(
            "/research/artifacts/compose", json={"investigation_ids": ["inv-a", "inv-b"]}
        ).status_code
        == 401
    )
    response = client.post(
        "/research/artifacts/compose",
        headers={"Authorization": "Bearer secret"},
        json={"investigation_ids": ["inv-a", "inv-b"]},
    )
    assert response.status_code == 200
    assert "path" not in response.text and "file://" not in response.text
    assert response.json()["members"][0]["investigation_id"] == "inv-a"


def test_compose_route_rejects_unknown_and_nonterminal(monkeypatch):
    monkeypatch.delenv("ANTIEK_OPERATOR_TOKEN", raising=False)
    client = TestClient(create_app(register_wrestling=False, register_providers=False))
    monkeypatch.setattr("interfaces.research.api.artifact_routes.trajectory", lambda iid: [])
    assert (
        client.post(
            "/research/artifacts/compose", json={"investigation_ids": ["inv-a", "inv-b"]}
        ).status_code
        == 404
    )
    monkeypatch.setattr(
        "interfaces.research.api.artifact_routes.trajectory",
        lambda iid: [{"action_type": "investigation.failed"}],
    )
    assert (
        client.post(
            "/research/artifacts/compose", json={"investigation_ids": ["inv-a", "inv-b"]}
        ).status_code
        == 409
    )


def test_compose_route_rejects_completion_superseded_by_failure(monkeypatch):
    monkeypatch.delenv("ANTIEK_OPERATOR_TOKEN", raising=False)
    client = TestClient(create_app(register_wrestling=False, register_providers=False))
    monkeypatch.setattr(
        "interfaces.research.api.artifact_routes.trajectory",
        lambda iid: [
            {"action_type": "investigation.completed"},
            {"action_type": "investigation.failed"},
        ],
    )
    response = client.post(
        "/research/artifacts/compose",
        json={"investigation_ids": ["inv-a", "inv-b"]},
    )
    assert response.status_code == 409


def test_compose_route_rejects_stopped_completion(monkeypatch):
    monkeypatch.delenv("ANTIEK_OPERATOR_TOKEN", raising=False)
    client = TestClient(create_app(register_wrestling=False, register_providers=False))
    monkeypatch.setattr(
        "interfaces.research.api.artifact_routes.trajectory",
        lambda iid: [
            {
                "action_type": "investigation.completed",
                "payload": {"outcome": "stopped"},
            }
        ],
    )
    response = client.post(
        "/research/artifacts/compose",
        json={"investigation_ids": ["inv-a", "inv-b"]},
    )
    assert response.status_code == 409


def test_composition_owner_is_exact_and_legacy_is_operator_only():
    owned = [{"action_type": "investigation.start_requested",
              "payload": {"owner_user_id": "owner-a"}}]
    legacy = [{"action_type": "investigation.start_requested", "payload": {}}]
    assert _trajectory_belongs_to_owner(owned, "owner-a") is True
    assert _trajectory_belongs_to_owner(owned, "owner-b") is False
    assert _trajectory_belongs_to_owner(legacy, "__operator__") is True
    assert _trajectory_belongs_to_owner(legacy, "owner-a") is False


def test_store_reader_refuses_symlinked_files(monkeypatch, tmp_path):
    store = tmp_path / "artifacts"
    compositions = store / "compositions"
    compositions.mkdir(parents=True)
    outside = tmp_path / "outside.html"
    outside.write_text("secret", encoding="utf-8")
    os.symlink(outside, compositions / ("cmp-" + "a" * 64 + ".html"))
    monkeypatch.setenv("ANTIEK_RESEARCH_ARTIFACTS_DIR", str(store))
    with pytest.raises(OSError):
        _read_store_file("cmp-" + "a" * 64 + ".html")


def test_index_verifier_rejects_regular_file_replacement():
    identity = [("inv-a", "1" * 64, "2" * 64), ("inv-b", "3" * 64, "4" * 64)]
    composition_id = composition_id_for(identity)
    metadata = {
        "composition_id": composition_id,
        "hash_conflicts": [],
        "members": [
            {"investigation_id": iid, "content_hash": content, "rendered_sha256": rendered}
            for iid, content, rendered in identity
        ],
        "ordered_set_digest": composition_id.removeprefix("cmp-"),
        "schema_version": 1,
    }
    original = render_composition_index(metadata).encode()
    assert _verified_index(original, composition_id)["composition_id"] == composition_id
    with pytest.raises(ValueError):
        _verified_index(
            original.replace(b"Composed research", b"Altered research", 1), composition_id
        )
    altered = dict(metadata)
    altered["schema_version"] = 2
    with pytest.raises(ValueError):
        _verified_index(render_composition_index(altered).encode(), composition_id)
    altered = dict(metadata)
    altered["schema_version"] = True
    with pytest.raises(ValueError):
        _verified_index(render_composition_index(altered).encode(), composition_id)
    altered = dict(metadata)
    altered["extra"] = "unbound"
    with pytest.raises(ValueError):
        _verified_index(render_composition_index(altered).encode(), composition_id)


def test_composition_launch_requires_auth_headers_and_closed_body(monkeypatch):
    monkeypatch.setenv("ANTIEK_OPERATOR_TOKEN", "secret")
    client = TestClient(create_app(register_wrestling=False, register_providers=False))
    url = "/research/artifacts/compositions/cmp-" + "a" * 64 + "/launch"
    valid = {"question": "What follows?", "research_tier": "fast"}
    assert client.post(url, json=valid).status_code == 401
    assert client.post(
        url, headers={"Authorization": "Bearer secret"}, json=valid
    ).status_code == 428
    assert client.post(
        url,
        headers={"Authorization": "Bearer secret", "If-Match": '"etag"',
                 "Idempotency-Key": "launch-key-1"},
        json={**valid, "context": "browser supplied"},
    ).status_code == 422
