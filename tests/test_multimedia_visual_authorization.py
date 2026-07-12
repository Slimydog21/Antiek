from __future__ import annotations

from datetime import UTC, datetime, timedelta
from pathlib import Path

import duckdb
import pytest

from integrations.krea.catalog import Imagen3Request, prepare_request, verify_quote
from substrate.multimedia.execution_authorization import verify_async_execution_authorization
from substrate.multimedia.read_model import CreateMultimediaDraftRequest, MultimediaAssetStore
from substrate.multimedia.visual_authorization import (
    VisualAuthorizationError,
    VisualAuthorizationRegistry,
    VisualAuthorizationRequest,
    VisualAuthorizationTerms,
)

NOW = datetime(2026, 7, 12, 12, tzinfo=UTC)
KEY = b"visual-authorization-key-material" * 2


def _ready(tmp_path: Path, *, route: str = "balanced", mode: str = "video"):
    store = MultimediaAssetStore(str(tmp_path / "assets"))
    draft = store.create_draft(
        CreateMultimediaDraftRequest(
            topic="Aircraft manufacturing history", target_minutes=15,
            mode=mode, route_policy=route,
            sources=("Grounded aircraft factory evidence.",),
        ),
        owner_id="owner-1",
    )
    return store, store.approve_dry_run(draft.asset.asset_id, owner_id="owner-1")


def _terms() -> VisualAuthorizationTerms:
    return VisualAuthorizationTerms(
        recovery_authority_id="recovery-1",
        recovery_verification_key_digest="b" * 64,
        maximum_ceiling_microdollars=500_000,
        quote_ttl_seconds=600,
    )


def _request(record, **changes) -> VisualAuthorizationRequest:
    values = {
        "request_id": "visual-request-1",
        "expected_revision_id": record.asset.revision_id,
        "chapter_id": record.plan.chapters[0].chapter_id,
        "approved_ceiling_microdollars": 250_000,
        "operator_acknowledged_spend": True,
        "ttl_seconds": 900,
    }
    values.update(changes)
    return VisualAuthorizationRequest(**values)


def test_derives_exact_quote_and_v2_authority_then_replays_across_clock_change(tmp_path: Path) -> None:
    store, ready = _ready(tmp_path)
    registry = VisualAuthorizationRegistry(db_path=str(tmp_path / "auth.duckdb"), signing_key=KEY)
    first = registry.authorize(
        ready.asset.asset_id, _request(ready), owner_id="owner-1", store=store,
        terms=_terms(), now=NOW,
    )
    replay = registry.authorize(
        ready.asset.asset_id, _request(ready), owner_id="owner-1", store=store,
        terms=_terms(), now=NOW + timedelta(minutes=2),
    )
    assert replay == first
    assert (first.width, first.height) == (1280, 720)
    assert first.authorization.quote_id == first.quote.quote_id
    assert first.authorization.request_body_digest == first.request_body_digest
    chapter = ready.plan.chapters[0]
    scene = next(row for row in ready.plan.scenes if row.chapter_id == chapter.chapter_id)
    prompt = (
        f"Generated educational documentary visual. Clearly generated, not archival. "
        f"Chapter: {chapter.title}. Visual intent: {scene.visual_intent}. "
        f"Information purpose: {scene.information_purpose}. Avoid decorative filler."
    )
    prepared = prepare_request(
        Imagen3Request(prompt=prompt, width=1280, height=720, seed=first.seed)
    )
    verify_quote(
        first.quote, signing_key=KEY, prepared=prepared,
        expected_quote_id=first.authorization.quote_id,
        expected_expires_at=first.authorization.quote_expires_at,
        expected_ceiling_microdollars=250_000, now=NOW,
    )
    verify_async_execution_authorization(
        first.authorization, signing_key=KEY, operator_id="owner-1",
        asset_id=ready.asset.asset_id, revision_id=ready.asset.revision_id,
        provider="krea", route_policy="balanced", model="imagen-3",
        endpoint_capability="text-to-image", catalog_version=prepared.catalog_version,
        catalog_digest=prepared.catalog_digest, quote_id=first.quote.quote_id,
        recovery_authority_id="recovery-1", recovery_verification_key_digest="b" * 64,
        approved_ceiling_microdollars=250_000,
        request_body_digest=prepared.body_digest, now=NOW,
    )


def test_highest_quality_uses_larger_server_dimensions(tmp_path: Path) -> None:
    store, ready = _ready(tmp_path, route="highest_quality")
    result = VisualAuthorizationRegistry(
        db_path=str(tmp_path / "auth.duckdb"), signing_key=KEY
    ).authorize(
        ready.asset.asset_id, _request(ready), owner_id="owner-1", store=store,
        terms=_terms(), now=NOW,
    )
    assert (result.width, result.height) == (1920, 1080)


def test_changed_request_terms_and_database_tampering_fail_closed(tmp_path: Path) -> None:
    store, ready = _ready(tmp_path)
    path = str(tmp_path / "auth.duckdb")
    registry = VisualAuthorizationRegistry(db_path=path, signing_key=KEY)
    registry.authorize(
        ready.asset.asset_id, _request(ready), owner_id="owner-1", store=store,
        terms=_terms(), now=NOW,
    )
    with pytest.raises(VisualAuthorizationError, match="different terms"):
        registry.authorize(
            ready.asset.asset_id,
            _request(ready, approved_ceiling_microdollars=200_000),
            owner_id="owner-1", store=store, terms=_terms(), now=NOW,
        )
    with duckdb.connect(path) as connection:
        connection.execute("UPDATE multimedia_visual_authorizations SET scene_id='tampered'")
    with pytest.raises(VisualAuthorizationError, match="integrity"):
        registry.authorize(
            ready.asset.asset_id, _request(ready), owner_id="owner-1", store=store,
            terms=_terms(), now=NOW,
        )


def test_trusted_recovery_configuration_drift_conflicts(tmp_path: Path) -> None:
    store, ready = _ready(tmp_path)
    registry = VisualAuthorizationRegistry(db_path=str(tmp_path / "auth.duckdb"), signing_key=KEY)
    registry.authorize(
        ready.asset.asset_id, _request(ready), owner_id="owner-1", store=store,
        terms=_terms(), now=NOW,
    )
    changed = VisualAuthorizationTerms("recovery-2", "c" * 64, 500_000, 300)
    with pytest.raises(VisualAuthorizationError, match="different terms"):
        registry.authorize(
            ready.asset.asset_id, _request(ready), owner_id="owner-1", store=store,
            terms=changed, now=NOW,
        )


@pytest.mark.parametrize(
    ("owner", "route", "mode", "changes", "message"),
    [
        ("owner-2", "balanced", "video", {}, "unavailable"),
        ("owner-1", "cheapest", "video", {}, "cheapest"),
        ("owner-1", "balanced", "audio", {}, "audio"),
        ("owner-1", "balanced", "video", {"expected_revision_id": "stale"}, "current"),
        ("owner-1", "balanced", "video", {"operator_acknowledged_spend": False}, "acknowledgement"),
        ("owner-1", "balanced", "video", {"approved_ceiling_microdollars": 500_001}, "ceiling"),
        ("owner-1", "balanced", "video", {"chapter_id": "missing"}, "unavailable"),
    ],
)
def test_invalid_authority_never_issues(tmp_path, owner, route, mode, changes, message) -> None:
    store, ready = _ready(tmp_path, route=route, mode=mode)
    with pytest.raises(VisualAuthorizationError, match=message):
        VisualAuthorizationRegistry(
            db_path=str(tmp_path / "auth.duckdb"), signing_key=KEY
        ).authorize(
            ready.asset.asset_id, _request(ready, **changes), owner_id=owner,
            store=store, terms=_terms(), now=NOW,
        )
