"""Substack hydrate adapter — post body into HTML asset (residual bj)."""

from __future__ import annotations

import hashlib
import os
import sys
from dataclasses import dataclass
from datetime import UTC, datetime

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

_REPO = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
if _REPO not in sys.path:
    sys.path.insert(0, _REPO)

from interfaces.research.api import engagement_routes as eng_mod  # noqa: E402
from interfaces.research.api.engagement_routes import (  # noqa: E402
    get_engagement_store,
    register_engagement_routes,
    reset_engagement_stores,
)
from substrate.engagement_spine import (  # noqa: E402
    InMemoryEngagementStore,
    assemble_research_context,
    asset_id_for_ref,
    hydrate_with_publication_adapters,
    substack_post_fetch_publication,
)
from substrate.engagement_spine.source_refs import parse_source_reference  # noqa: E402
from substrate.engagement_spine.substack_hydration import (  # noqa: E402
    FetchedSubstackPost,
    hydrate_substack_body,
)
from substrate.marketplace_host import (  # noqa: E402
    InMemoryHostStore,
    project_hosted_book_html,
)


@dataclass
class _FakePost:
    title: str = "Deep research needs recursive twin notes"
    body_markdown: str = "Authors argue that LLMs are perfect note-takers for twin substrates."
    body_html: str = ""
    post_url: str = "https://research.substack.com/p/attention"
    author: str = "Researcher"
    truncated: bool = False


def test_legacy_substack_adapter_cannot_claim_canonical_body():
    store = InMemoryEngagementStore()

    def fetch_post(url: str):
        assert "substack" in url
        return _FakePost()

    asset = hydrate_with_publication_adapters(
        "https://research.substack.com/p/attention",
        store=store,
        substack_fetch_post=fetch_post,
        include_html=True,
    )
    assert asset.fetched is False
    assert asset.hydrated is False
    assert "recursive twin" in asset.title or "Deep research" in asset.title
    assert "note-takers" in asset.body_text
    assert "Researcher" in asset.body_text
    assert asset.view_format == "html"
    assert asset.html
    assert "application/pdf" not in asset.html.lower()


def test_substack_adapter_refuses_silent_network():
    fetch = substack_post_fetch_publication(fetch_post=None)
    ref = parse_source_reference("https://research.substack.com/p/attention")
    try:
        fetch(ref)
        raise AssertionError("expected RuntimeError")
    except RuntimeError as exc:
        assert "silent" in str(exc).lower() or "injected" in str(exc).lower()


def _full_html() -> str:
    prose = " ".join(
        f"research evidence insight question citation synthesis paragraph {i}" for i in range(18)
    )
    return f"<article><h1>Recursive research</h1><p>{prose}</p><script>alert(1)</script></article>"


def _fetched(
    url: str,
    *,
    final_url: str | None = None,
    truncated: bool = False,
    paywalled: bool = False,
    auth_challenge: bool = False,
    body_html: str | None = None,
) -> FetchedSubstackPost:
    body = _full_html() if body_html is None else body_html
    return FetchedSubstackPost(
        requested_url=url,
        final_url=final_url or url,
        redirect_chain=(url,),
        title="Deep research needs recursive twin notes",
        author="Researcher",
        published_at=datetime(2026, 7, 15, tzinfo=UTC),
        body_html=body,
        body_sha256=hashlib.sha256(body.encode()).hexdigest(),
        body_size_bytes=len(body.encode()),
        content_type="text/html; charset=utf-8",
        truncated=truncated,
        paywalled=paywalled,
        auth_challenge=auth_challenge,
        factory_id="operator-substack-fixture-v1",
        policy_id="tos-review-2026-07-15",
        policy_approved_by="operator",
        rollback_switch="ANTIEK_HYDRATE_LIVE_SUBSTACK",
    )


def test_policy_hydration_sanitizes_and_reopens_owner_html():
    url = "https://research.substack.com/p/attention"
    store = InMemoryHostStore()
    outcome = hydrate_substack_body(
        requested_url=url,
        owner_id="alice",
        investigation_id="inv-substack",
        store=store,
        fetch_post=lambda requested: _fetched(requested),
        emit_document_loaded=lambda *args: "evt-substack",
    )
    assert outcome.hydrated is True
    assert outcome.document is not None
    assert outcome.receipt["factory"]["policy_approved_by"] == "operator"
    assert outcome.receipt["rights"]["redistributable"] is False
    stored = store.get_document(outcome.document.document_id)
    assert stored is not None
    assert stored["owner_id"] == "alice"
    assert "alert(1)" not in stored["body_text"]
    html = project_hosted_book_html(outcome.document.document_id, store=store)
    assert "research evidence" in html
    assert "alert(1)" not in html
    assert "<script" not in html.lower()


def test_paywall_refusal_is_typed_and_writes_nothing():
    url = "https://research.substack.com/p/attention"
    store = InMemoryHostStore()
    outcome = hydrate_substack_body(
        requested_url=url,
        owner_id="alice",
        investigation_id="inv-substack",
        store=store,
        fetch_post=lambda requested: _fetched(requested, paywalled=True),
        emit_document_loaded=lambda *args: "forbidden",
    )
    assert outcome.hydrated is False
    assert outcome.receipt["reason"] == "paywall_detected"
    assert outcome.receipt["factory"]["policy_id"] == "tos-review-2026-07-15"
    assert store.list_membership("alice") == []


@pytest.mark.parametrize(
    ("flags", "reason"),
    [
        ({"auth_challenge": True}, "auth_challenge_detected"),
        ({"truncated": True}, "truncated_teaser"),
    ],
)
def test_auth_and_truncation_refuse_without_writes(flags, reason):
    url = "https://research.substack.com/p/attention"
    store = InMemoryHostStore()
    outcome = hydrate_substack_body(
        requested_url=url,
        owner_id="alice",
        investigation_id="inv",
        store=store,
        fetch_post=lambda requested: _fetched(requested, **flags),
        emit_document_loaded=lambda *args: "forbidden",
    )
    assert outcome.receipt["reason"] == reason
    assert store.list_membership("alice") == []


def test_factory_failure_is_typed_once_and_oversize_is_rejected():
    url = "https://research.substack.com/p/attention"
    store = InMemoryHostStore()
    calls = 0

    def fail(_url):
        nonlocal calls
        calls += 1
        raise RuntimeError("factory unavailable")

    unavailable = hydrate_substack_body(
        requested_url=url,
        owner_id="alice",
        investigation_id="inv",
        store=store,
        fetch_post=fail,
        emit_document_loaded=lambda *args: "forbidden",
    )
    assert calls == 1
    assert unavailable.receipt["reason"] == "RuntimeError"
    with pytest.raises(ValueError, match="exceeds"):
        hydrate_substack_body(
            requested_url=url,
            owner_id="alice",
            investigation_id="inv",
            store=store,
            fetch_post=lambda requested: _fetched(requested, body_html="x" * 500_001),
            emit_document_loaded=lambda *args: "forbidden",
        )
    assert store.list_membership("alice") == []


def test_malformed_receipt_and_policy_authority_are_rejected():
    url = "https://research.substack.com/p/attention"
    store = InMemoryHostStore()
    forged = _fetched(url)
    forged = FetchedSubstackPost(**{**forged.__dict__, "body_sha256": "0" * 64})
    with pytest.raises(ValueError, match="does not match"):
        hydrate_substack_body(
            requested_url=url,
            owner_id="alice",
            investigation_id="inv",
            store=store,
            fetch_post=lambda _url: forged,
            emit_document_loaded=lambda *args: "forbidden",
        )
    no_policy = FetchedSubstackPost(**{**_fetched(url).__dict__, "policy_approved_by": ""})
    with pytest.raises(ValueError, match="policy authority"):
        hydrate_substack_body(
            requested_url=url,
            owner_id="alice",
            investigation_id="inv",
            store=store,
            fetch_post=lambda _url: no_policy,
            emit_document_loaded=lambda *args: "forbidden",
        )
    assert store.list_membership("alice") == []


def test_redirect_escape_and_non_substack_input_fail_before_write():
    store = InMemoryHostStore()
    with pytest.raises(ValueError, match="Substack acquisition requires"):
        hydrate_substack_body(
            requested_url="https://evil.example/p/attention",
            owner_id="alice",
            investigation_id="inv",
            store=store,
            fetch_post=lambda requested: _fetched(requested),
            emit_document_loaded=lambda *args: "forbidden",
        )
    with pytest.raises(ValueError, match="redirect escaped"):
        hydrate_substack_body(
            requested_url="https://research.substack.com/p/attention",
            owner_id="alice",
            investigation_id="inv",
            store=store,
            fetch_post=lambda requested: _fetched(
                requested, final_url="https://other.substack.com/p/attention"
            ),
            emit_document_loaded=lambda *args: "forbidden",
        )
    assert store.list_membership("alice") == []


def test_intermediate_redirect_escape_wrong_mime_and_empty_body_fail_closed():
    url = "https://research.substack.com/p/attention"
    store = InMemoryHostStore()
    escaped = FetchedSubstackPost(
        **{
            **_fetched(url).__dict__,
            "redirect_chain": (
                url,
                "https://evil.example/p/intercepted",
                url,
            ),
        }
    )
    with pytest.raises(ValueError, match="redirect chain escaped"):
        hydrate_substack_body(
            requested_url=url,
            owner_id="alice",
            investigation_id="inv",
            store=store,
            fetch_post=lambda _url: escaped,
            emit_document_loaded=lambda *args: "forbidden",
        )
    wrong_mime = FetchedSubstackPost(
        **{**_fetched(url).__dict__, "content_type": "application/json"}
    )
    with pytest.raises(ValueError, match="non-HTML"):
        hydrate_substack_body(
            requested_url=url,
            owner_id="alice",
            investigation_id="inv",
            store=store,
            fetch_post=lambda _url: wrong_mime,
            emit_document_loaded=lambda *args: "forbidden",
        )
    with pytest.raises(ValueError, match="empty body"):
        hydrate_substack_body(
            requested_url=url,
            owner_id="alice",
            investigation_id="inv",
            store=store,
            fetch_post=lambda requested: _fetched(requested, body_html="   "),
            emit_document_loaded=lambda *args: "forbidden",
        )
    assert store.list_membership("alice") == []


def test_persistence_failure_propagates_instead_of_becoming_unavailable():
    url = "https://research.substack.com/p/attention"
    store = InMemoryHostStore()

    def fail_event(*_args):
        raise RuntimeError("durable event log unavailable")

    with pytest.raises(RuntimeError, match="durable event log unavailable"):
        hydrate_substack_body(
            requested_url=url,
            owner_id="alice",
            investigation_id="inv",
            store=store,
            fetch_post=lambda requested: _fetched(requested),
            emit_document_loaded=fail_event,
        )


def test_api_hydrate_with_policy_injected_substack_fetch(monkeypatch):
    monkeypatch.setenv("ANTIEK_HYDRATE_LIVE_SUBSTACK", "1")
    reset_engagement_stores()
    eng_mod.hydrate_fetch_publication = None
    eng_mod.hydrate_arxiv_fetch_by_id = None
    eng_mod.hydrate_substack_fetch_post = lambda url: _fetched(url)
    host_store = InMemoryHostStore()
    monkeypatch.setattr(
        "services.hosted_documents.events.emit_document_loaded",
        lambda *args: "evt-substack-api",
    )

    app = FastAPI()
    app.state.marketplace_host_store = host_store
    register_engagement_routes(app)
    client = TestClient(app)
    try:
        r1 = client.post(
            "/engagement/hydrate-ref",
            json={
                "reference": "https://research.substack.com/p/attention",
                "include_html": True,
            },
        )
        assert r1.status_code == 200, r1.text
        b1 = r1.json()
        assert b1["fetched"] is True
        assert b1["hydrated"] is True
        assert b1["hydration_status"] == "body_complete"
        assert "research evidence" in b1["body_text"]
        assert b1["twins"]["source_provenance"]["source_sha256"]
        context = assemble_research_context(
            b1["asset_id"],
            store=get_engagement_store(),
            include_twin_promote=False,
        )
        assert context.asset_provenance is not None
        assert context.asset_provenance["canonical_hosted_document_id"]
        assert "source_provenance" in context.prompt_block()
        assert b1["view_format"] == "html"
        r2 = client.post(
            "/engagement/hydrate-ref",
            json={
                "reference": "https://research.substack.com/p/attention",
                "include_html": True,
            },
        )
        assert r2.status_code == 200
        assert r2.json()["asset_id"] == b1["asset_id"]
    finally:
        eng_mod.hydrate_substack_fetch_post = None


def test_api_factory_installed_env_off_makes_zero_factory_requests(monkeypatch):
    monkeypatch.delenv("ANTIEK_HYDRATE_LIVE_SUBSTACK", raising=False)
    reset_engagement_stores()
    calls = 0

    def fetch(url):
        nonlocal calls
        calls += 1
        return _fetched(url)

    eng_mod.hydrate_substack_fetch_post = fetch
    app = FastAPI()
    register_engagement_routes(app)
    try:
        response = TestClient(app).post(
            "/engagement/hydrate-ref",
            json={"reference": "https://research.substack.com/p/attention"},
        )
        assert response.status_code == 200
        assert calls == 0
        assert response.json()["hydrated"] is False
        assert response.json()["fetched"] is False
    finally:
        eng_mod.hydrate_substack_fetch_post = None


def test_api_paywall_writes_no_engagement_or_host_asset(monkeypatch):
    monkeypatch.setenv("ANTIEK_HYDRATE_LIVE_SUBSTACK", "1")
    reset_engagement_stores()
    host_store = InMemoryHostStore()
    eng_mod.hydrate_substack_fetch_post = lambda url: _fetched(url, truncated=True)
    app = FastAPI()
    app.state.marketplace_host_store = host_store
    register_engagement_routes(app)
    try:
        response = TestClient(app).post(
            "/engagement/hydrate-ref",
            json={"reference": "https://research.substack.com/p/attention"},
        )
        assert response.status_code == 200
        assert response.json()["asset_written"] is False
        assert response.json()["hydration_receipt"]["reason"] == "truncated_teaser"
        assert host_store.list_membership("__operator__") == []
        ref = parse_source_reference("https://research.substack.com/p/attention")
        assert get_engagement_store().get_document(asset_id_for_ref(ref)) is None
    finally:
        eng_mod.hydrate_substack_fetch_post = None


@pytest.mark.parametrize(
    "mutate",
    [
        lambda fetched: FetchedSubstackPost(
            **{**fetched.__dict__, "content_type": "application/json"}
        ),
        lambda fetched: FetchedSubstackPost(
            **{
                **fetched.__dict__,
                "final_url": "https://other.substack.com/p/attention",
            }
        ),
        lambda fetched: FetchedSubstackPost(**{**fetched.__dict__, "body_sha256": "0" * 64}),
    ],
)
def test_api_malformed_factory_responses_are_typed_400_and_write_nothing(monkeypatch, mutate):
    monkeypatch.setenv("ANTIEK_HYDRATE_LIVE_SUBSTACK", "1")
    reset_engagement_stores()
    host_store = InMemoryHostStore()
    eng_mod.hydrate_substack_fetch_post = lambda url: mutate(_fetched(url))
    app = FastAPI()
    app.state.marketplace_host_store = host_store
    register_engagement_routes(app)
    try:
        response = TestClient(app).post(
            "/engagement/hydrate-ref",
            json={"reference": "https://research.substack.com/p/attention"},
        )
        assert response.status_code == 400
        assert host_store.list_membership("__operator__") == []
        ref = parse_source_reference("https://research.substack.com/p/attention")
        assert get_engagement_store().get_document(asset_id_for_ref(ref)) is None
    finally:
        eng_mod.hydrate_substack_fetch_post = None
