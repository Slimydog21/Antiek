from __future__ import annotations

from datetime import UTC, datetime
from pathlib import Path

import pytest

from substrate.multimedia.execution_authorization_issuer import ExecutionAuthorizationIssuer
from substrate.multimedia.narration_authorization import (
    NarrationAuthorizationError,
    NarrationAuthorizationRequest,
    TrustedNarrationTerms,
    authorize_multimedia_chapter_narration,
)
from substrate.multimedia.narration_run import narration_child_revision
from substrate.multimedia.read_model import CreateMultimediaDraftRequest, MultimediaAssetStore

NOW = datetime(2026, 7, 12, tzinfo=UTC)
SIGNING_KEY = b"narration-authorization-signing" * 2


def _terms(_record, _chapter_id: str) -> TrustedNarrationTerms:
    return TrustedNarrationTerms(
        provider="trusted-tts",
        model="voice-1",
        endpoint_capability="text-to-speech",
        catalog_version="catalog-1",
        catalog_digest="a" * 64,
        quote_id="quote-1",
        quote_ttl_seconds=600,
        recovery_authority_id="recovery-1",
        recovery_verification_key_digest="b" * 64,
        maximum_ceiling_microdollars=500_000,
    )


def _ready(tmp_path: Path, *, route: str = "balanced"):
    store = MultimediaAssetStore(str(tmp_path / "assets"))
    draft = store.create_draft(
        CreateMultimediaDraftRequest(
            topic="Chapter narration authority",
            target_minutes=15,
            mode="video",
            route_policy=route,
        ),
        owner_id="owner-1",
    )
    return store, store.approve_dry_run(draft.asset.asset_id, owner_id="owner-1")


def _request(chapter_id: str, **changes) -> NarrationAuthorizationRequest:
    values = {
        "request_id": "request-1",
        "expected_revision_id": "rev-1",
        "chapter_id": chapter_id,
        "approved_ceiling_microdollars": 250_000,
        "operator_acknowledged_spend": True,
    }
    values.update(changes)
    return NarrationAuthorizationRequest(**values)


def test_server_derives_exact_child_body_and_durable_v2_replay(tmp_path: Path) -> None:
    store, ready = _ready(tmp_path)
    chapter_id = ready.plan.chapters[0].chapter_id
    issuer = ExecutionAuthorizationIssuer(
        db_path=str(tmp_path / "authority.duckdb"), signing_key=SIGNING_KEY
    )
    first = authorize_multimedia_chapter_narration(
        ready.asset.asset_id,
        _request(chapter_id),
        owner_id="owner-1",
        store=store,
        terms_resolver=_terms,
        issuer=issuer,
        clock=lambda: NOW,
    )
    assert first.prepared.revision_id == narration_child_revision("rev-1", chapter_id, 0)
    assert first.authorization.request_body_digest == first.prepared.body_digest
    assert first.authorization.provider == "trusted-tts"
    assert first.authorization.approved_ceiling_microdollars == 250_000

    replay = authorize_multimedia_chapter_narration(
        ready.asset.asset_id,
        _request(chapter_id),
        owner_id="owner-1",
        store=store,
        terms_resolver=_terms,
        issuer=issuer,
        clock=lambda: NOW,
    )
    assert replay == first


def test_changed_terms_conflict_and_never_reinterpret_request_id(tmp_path: Path) -> None:
    store, ready = _ready(tmp_path)
    chapter_id = ready.plan.chapters[0].chapter_id
    issuer = ExecutionAuthorizationIssuer(
        db_path=str(tmp_path / "authority.duckdb"), signing_key=SIGNING_KEY
    )
    authorize_multimedia_chapter_narration(
        ready.asset.asset_id,
        _request(chapter_id),
        owner_id="owner-1",
        store=store,
        terms_resolver=_terms,
        issuer=issuer,
        clock=lambda: NOW,
    )
    with pytest.raises(NarrationAuthorizationError, match="different terms"):
        authorize_multimedia_chapter_narration(
            ready.asset.asset_id,
            _request(chapter_id, speed=1.1),
            owner_id="owner-1",
            store=store,
            terms_resolver=_terms,
            issuer=issuer,
            clock=lambda: NOW,
        )


@pytest.mark.parametrize(
    ("owner", "changes", "message"),
    [
        ("owner-2", {}, "unavailable"),
        ("owner-1", {"expected_revision_id": "rev-old"}, "current"),
        ("owner-1", {"operator_acknowledged_spend": False}, "acknowledgement"),
        ("owner-1", {"approved_ceiling_microdollars": 500_001}, "exceeds"),
        ("owner-1", {"chapter_id": "missing"}, "unavailable"),
    ],
)
def test_owner_revision_ack_ceiling_and_chapter_fail_before_issuance(
    tmp_path: Path, owner: str, changes: dict[str, object], message: str
) -> None:
    store, ready = _ready(tmp_path)
    chapter_id = str(changes.pop("chapter_id", ready.plan.chapters[0].chapter_id))
    issuer = ExecutionAuthorizationIssuer(
        db_path=str(tmp_path / "authority.duckdb"), signing_key=SIGNING_KEY
    )
    with pytest.raises(NarrationAuthorizationError, match=message):
        authorize_multimedia_chapter_narration(
            ready.asset.asset_id,
            _request(chapter_id, **changes),
            owner_id=owner,
            store=store,
            terms_resolver=_terms,
            issuer=issuer,
            clock=lambda: NOW,
        )


def test_cheapest_and_unready_assets_cannot_issue(tmp_path: Path) -> None:
    store, ready = _ready(tmp_path, route="cheapest")
    chapter_id = ready.plan.chapters[0].chapter_id
    issuer = ExecutionAuthorizationIssuer(
        db_path=str(tmp_path / "authority.duckdb"), signing_key=SIGNING_KEY
    )
    with pytest.raises(NarrationAuthorizationError, match="cheapest"):
        authorize_multimedia_chapter_narration(
            ready.asset.asset_id,
            _request(chapter_id),
            owner_id="owner-1",
            store=store,
            terms_resolver=_terms,
            issuer=issuer,
            clock=lambda: NOW,
        )

    draft = store.create_draft(
        CreateMultimediaDraftRequest(
            topic="Unready narration",
            target_minutes=15,
            mode="audio",
            route_policy="balanced",
        ),
        owner_id="owner-1",
    )
    with pytest.raises(NarrationAuthorizationError, match="ready"):
        authorize_multimedia_chapter_narration(
            draft.asset.asset_id,
            _request(draft.plan.chapters[0].chapter_id),
            owner_id="owner-1",
            store=store,
            terms_resolver=lambda *_args: pytest.fail("terms must not resolve"),
            issuer=issuer,
            clock=lambda: NOW,
        )
