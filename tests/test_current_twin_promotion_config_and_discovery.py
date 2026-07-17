from __future__ import annotations

# ruff: noqa: F811 - pytest fixture is intentionally imported.
import json
import os
from pathlib import Path

import pytest
from fastapi.testclient import TestClient
from test_canonical_aggregate_projection import completed_parent  # noqa: F401
from test_current_twin_promotion_routes import _app, _runtime

from interfaces.research.api.current_twin_promotion_config import (
    CONFIG_ENV,
    CONFIG_SCHEMA,
    CurrentTwinPromotionConfigError,
    current_twin_promotion_runtime_from_environment,
)


def _manifest(runtime, path: Path) -> dict[str, object]:
    route = runtime.registry.resolve("acct")
    return {
        "schema": CONFIG_SCHEMA,
        "owners": [
            {
                "owner_id": "acct",
                "graph_db_path": route.graph_db_path,
                "promotion_ledger_path": route.promotion_path,
                "twin_ledger_path": route.twin_path,
                "review_verify_key_hex": route._promotion_verify_key.hex(),
            }
        ],
    }


def _write_manifest(path: Path, value: object) -> None:
    path.write_text(json.dumps(value), encoding="utf-8")
    path.chmod(0o600)


def test_unconfigured_factory_preserves_disabled_runtime() -> None:
    assert current_twin_promotion_runtime_from_environment({}) is None


def test_private_complete_manifest_builds_exact_owner_runtime(completed_parent, tmp_path) -> None:
    runtime, candidate, _, _ = _runtime(completed_parent)
    config = tmp_path / "promotion-read.json"
    _write_manifest(config, _manifest(runtime, config))
    configured = current_twin_promotion_runtime_from_environment(
        {CONFIG_ENV: str(config.resolve())}
    )
    assert configured is not None
    response = TestClient(_app(configured)).get(f"/reader/promotions/{candidate.candidate_id}")
    assert response.status_code == 200


def test_production_factory_wires_configured_runtime(
    completed_parent, tmp_path, monkeypatch
) -> None:
    import importlib

    runtime, _, _, _ = _runtime(completed_parent)
    config = tmp_path / "promotion-read.json"
    _write_manifest(config, _manifest(runtime, config))
    monkeypatch.setenv(CONFIG_ENV, str(config.resolve()))
    app_module = importlib.import_module("interfaces.research.api.app")
    app = app_module.create_app()
    from interfaces.research.api.current_twin_promotion_routes import (
        get_current_twin_promotion_runtime,
    )

    configured = app.dependency_overrides[get_current_twin_promotion_runtime]()
    assert configured.registry.resolve("acct").owner_id == "acct"


def test_configured_manifest_is_all_or_nothing_and_private(completed_parent, tmp_path) -> None:
    runtime, _, _, _ = _runtime(completed_parent)
    config = tmp_path / "promotion-read.json"
    value = _manifest(runtime, config)
    value["owners"][0].pop("twin_ledger_path")  # type: ignore[index,union-attr]
    _write_manifest(config, value)
    with pytest.raises(CurrentTwinPromotionConfigError, match="owner fields"):
        current_twin_promotion_runtime_from_environment({CONFIG_ENV: str(config.resolve())})


def test_manifest_path_replacement_during_read_fails_startup(
    completed_parent, tmp_path, monkeypatch
) -> None:
    import interfaces.research.api.current_twin_promotion_config as config_module

    runtime, _, _, _ = _runtime(completed_parent)
    config = tmp_path / "promotion-read.json"
    replacement = tmp_path / "replacement.json"
    _write_manifest(config, _manifest(runtime, config))
    _write_manifest(replacement, _manifest(runtime, replacement))
    original_read = config_module.os.read
    replaced = False

    def replacing_read(fd: int, size: int) -> bytes:
        nonlocal replaced
        value = original_read(fd, size)
        if not replaced:
            replaced = True
            os.replace(replacement, config)
        return value

    monkeypatch.setattr(config_module.os, "read", replacing_read)
    with pytest.raises(CurrentTwinPromotionConfigError, match="path changed"):
        current_twin_promotion_runtime_from_environment({CONFIG_ENV: str(config.resolve())})


def test_configured_manifest_rejects_public_permissions(completed_parent, tmp_path) -> None:
    runtime, _, _, _ = _runtime(completed_parent)
    config = tmp_path / "promotion-read.json"
    _write_manifest(config, _manifest(runtime, config))
    config.chmod(0o644)
    with pytest.raises(CurrentTwinPromotionConfigError, match="not private"):
        current_twin_promotion_runtime_from_environment({CONFIG_ENV: str(config.resolve())})


def test_configured_manifest_rejects_foreign_owner(completed_parent, tmp_path, monkeypatch) -> None:
    import interfaces.research.api.current_twin_promotion_config as config_module

    runtime, _, _, _ = _runtime(completed_parent)
    config = tmp_path / "promotion-read.json"
    _write_manifest(config, _manifest(runtime, config))
    monkeypatch.setattr(config_module.os, "geteuid", lambda: os.stat(config).st_uid + 1)
    with pytest.raises(CurrentTwinPromotionConfigError, match="not private"):
        current_twin_promotion_runtime_from_environment({CONFIG_ENV: str(config.resolve())})


def test_source_discovery_returns_only_current_exact_revision(
    completed_parent, monkeypatch
) -> None:
    import substrate.twin_recursion.evidence_promotion as promotion_module

    runtime, candidate, result, _ = _runtime(completed_parent)
    original_verify = promotion_module.TwinEvidencePromotionLedger.verify_integrity
    integrity_scans = 0

    def counted_verify(self) -> None:
        nonlocal integrity_scans
        integrity_scans += 1
        original_verify(self)

    monkeypatch.setattr(
        promotion_module.TwinEvidencePromotionLedger, "verify_integrity", counted_verify
    )
    client = TestClient(_app(runtime))
    response = client.get(
        f"/reader/sources/{candidate.source_asset_id}/reviewed-promotions",
        params={"source_hash": candidate.source_hash},
    )
    assert response.status_code == 200
    assert response.json() == {
        "source_asset_id": candidate.source_asset_id,
        "source_hash": candidate.source_hash,
        "items": [
            {
                "candidate_id": candidate.candidate_id,
                "node_id": result.node_id,
                "review_id": result.review_id,
                "kind": candidate.kind,
                "text": candidate.text,
                "evidence_count": 1,
                "href": f"/reader/promotions/{candidate.candidate_id}",
            }
        ],
        "complete": True,
        "authority": "current_owner_reviewed_source_promotions_v1",
    }
    assert response.headers["cache-control"] == "private, no-store"
    assert integrity_scans == 1
    empty = client.get(
        f"/reader/sources/{candidate.source_asset_id}/reviewed-promotions",
        params={"source_hash": "another-revision"},
    )
    assert empty.status_code == 200
    assert empty.json()["items"] == []
    assert integrity_scans == 2


def test_source_discovery_foreign_owner_is_uniform_private_not_found(completed_parent) -> None:
    runtime, candidate, _, _ = _runtime(completed_parent)
    response = TestClient(_app(runtime, owner="foreign")).get(
        f"/reader/sources/{candidate.source_asset_id}/reviewed-promotions",
        params={"source_hash": candidate.source_hash},
    )
    assert response.status_code == 404
    assert response.headers["cache-control"] == "private, no-store"
    namespace = TestClient(_app(runtime)).get(
        f"/reader/sources/{candidate.source_asset_id}/reviewed-promotions/missing"
    )
    assert namespace.status_code == 404
    assert namespace.headers["cache-control"] == "private, no-store"


def test_source_discovery_refuses_stale_or_overflowed_authority(
    completed_parent, monkeypatch
) -> None:
    import substrate.twin_recursion.evidence_promotion as promotion_module
    from runtime.db_lock import connect_write

    runtime, candidate, _, db_path = _runtime(completed_parent)
    client = TestClient(_app(runtime))
    monkeypatch.setattr(promotion_module, "MAX_SOURCE_PROMOTIONS", 0)
    overflow = client.get(
        f"/reader/sources/{candidate.source_asset_id}/reviewed-promotions",
        params={"source_hash": candidate.source_hash},
    )
    assert overflow.status_code == 503
    assert overflow.headers["cache-control"] == "private, no-store"
    monkeypatch.setattr(promotion_module, "MAX_SOURCE_PROMOTIONS", 32)
    with connect_write(db_path, purpose="cycle119-stale-evidence") as graph:
        graph.execute("UPDATE chunks SET text='changed' WHERE chunk_id='evidence-chunk'")
    stale = client.get(
        f"/reader/sources/{candidate.source_asset_id}/reviewed-promotions",
        params={"source_hash": candidate.source_hash},
    )
    assert stale.status_code == 503
    assert stale.headers["cache-control"] == "private, no-store"
