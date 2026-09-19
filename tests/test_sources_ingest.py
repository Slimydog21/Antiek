"""Tests for ``POST /sources/ingest`` (Sprint 12).

The acquisition adapters all do network IO, so for the endpoint
tests we monkeypatch each adapter's entry point to return a
synthetic result. The helpers ``_detect_source_kind`` and
``_extract_arxiv_id`` are exercised directly.
"""

from __future__ import annotations

import os
import sys
import tempfile

import pytest
from fastapi.testclient import TestClient

_REPO = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
if _REPO not in sys.path:
    sys.path.insert(0, _REPO)

from interfaces.research.api.app import (  # noqa: E402
    _detect_source_kind,
    _extract_arxiv_id,
    create_app,
)

# ─────────────────────────────────────────────────────────────────────
# 1. Helpers — kind detection
# ─────────────────────────────────────────────────────────────────────


def test_detect_source_kind_arxiv():
    assert _detect_source_kind("https://arxiv.org/abs/2402.03300") == "arxiv"
    assert _detect_source_kind("https://arxiv.org/pdf/2402.03300v2") == "arxiv"


def test_detect_source_kind_youtube():
    assert _detect_source_kind("https://www.youtube.com/watch?v=abc") == "youtube"
    assert _detect_source_kind("https://youtu.be/dQw4w9WgXcQ") == "youtube"


def test_detect_source_kind_podcast():
    assert _detect_source_kind("https://feeds.example.com/show.rss") == "podcast"
    assert _detect_source_kind("https://feeds.example.com/show.xml") == "podcast"
    assert _detect_source_kind("https://example.com/podcast/feed") == "podcast"


def test_detect_source_kind_url_default():
    assert _detect_source_kind("https://example.com/post.html") == "url"


def test_detect_source_kind_explicit_overrides_auto():
    """Explicit kind must take precedence over URL heuristic."""
    assert _detect_source_kind("https://arxiv.org/abs/x", "url") == "url"
    assert _detect_source_kind("https://example.com/x", "youtube") == "youtube"


# ─────────────────────────────────────────────────────────────────────
# 2. arXiv id extraction
# ─────────────────────────────────────────────────────────────────────


def test_extract_arxiv_id_from_abs_url():
    assert _extract_arxiv_id("https://arxiv.org/abs/2402.03300") == "2402.03300"


def test_extract_arxiv_id_from_pdf_url():
    assert _extract_arxiv_id("https://arxiv.org/pdf/2402.03300") == "2402.03300"


def test_extract_arxiv_id_strips_version_suffix():
    assert _extract_arxiv_id("https://arxiv.org/abs/2402.03300v2") == "2402.03300"


def test_extract_arxiv_id_bare_id():
    assert _extract_arxiv_id("2402.03300") == "2402.03300"
    assert _extract_arxiv_id("2402.03300v3") == "2402.03300"


def test_extract_arxiv_id_invalid_url():
    assert _extract_arxiv_id("https://example.com/post") is None
    assert _extract_arxiv_id("not-an-arxiv-id") is None


# ─────────────────────────────────────────────────────────────────────
# 3. POST /sources/ingest — endpoint integration
# ─────────────────────────────────────────────────────────────────────


@pytest.fixture
def temp_substrate(monkeypatch):
    tmp = tempfile.mkdtemp(prefix="antiek-sources-ingest-")
    db_path = os.path.join(tmp, "graph.duckdb")
    events_dir = os.path.join(tmp, "events")
    os.makedirs(events_dir, exist_ok=True)
    monkeypatch.setenv("ANTIEK_DUCKDB_PATH", db_path)
    monkeypatch.setenv("ANTIEK_RESEARCH_EVENTS_DIR", events_dir)
    yield {"db_path": db_path, "events_dir": events_dir, "tmpdir": tmp}


def _client(temp_substrate):
    app = create_app(
        register_wrestling=False,
        register_providers=False,
        cors_origins=[],
    )
    return TestClient(app)


def _allow_operator_domain(temp_substrate, domain: str) -> None:
    from datetime import UTC, datetime

    from runtime.db_lock import connect_write
    from substrate.graph import ensure_initialized
    from substrate.investigation_streams import initialize_composite_stream
    from substrate.investigation_tenancy import InvestigationAuthority
    from substrate.legal_gate.policy_store import account_policy_authority, append_policy_event

    authority = InvestigationAuthority("__operator__", "__operator__")
    initialize_composite_stream(authority)
    ensure_initialized(temp_substrate["db_path"])
    with connect_write(temp_substrate["db_path"], purpose="test_allow_url_domain") as con:
        append_policy_event(
            con,
            account_policy_authority(authority),
            scope_kind="account",
            matcher_kind="domain",
            matcher_value=domain,
            decision="allow",
            citation_ref="test-license",
            issuer_id="test-operator",
            reason_code="licensed_source",
            effective_at=datetime.now(UTC),
        )


def test_ingest_youtube_endpoint_fails_closed_before_legacy_adapter(monkeypatch, temp_substrate):
    import acquisition.youtube as _yt

    monkeypatch.setattr(
        _yt,
        "ingest_youtube",
        lambda *a, **kw: (_ for _ in ()).throw(AssertionError("legacy writer invoked")),
    )

    client = _client(temp_substrate)
    resp = client.post(
        "/sources/ingest",
        json={"url": "https://youtu.be/dQw4w9WgXcQ"},
    )
    assert resp.status_code == 202
    body = resp.json()
    assert body["status"] == "error"
    assert body["detected_kind"] == "youtube"
    assert "legal_admission_required" in body["error_message"]


def test_ingest_podcast_endpoint_fails_closed_before_legacy_adapter(monkeypatch, temp_substrate):
    import acquisition.podcasts as _pod

    monkeypatch.setattr(
        _pod,
        "ingest_feed",
        lambda *a, **kw: (_ for _ in ()).throw(AssertionError("legacy writer invoked")),
    )

    client = _client(temp_substrate)
    resp = client.post(
        "/sources/ingest",
        json={"url": "https://feeds.example.com/show.rss", "max_episodes": 5},
    )
    assert resp.status_code == 202
    body = resp.json()
    assert body["status"] == "error"
    assert body["detected_kind"] == "podcast"
    assert "legal_admission_required" in body["error_message"]


def test_ingest_url_endpoint_default(monkeypatch, temp_substrate):
    """URLs that don't match a known kind fall through to acquisition.urls."""
    from dataclasses import dataclass

    @dataclass
    class _R:
        document_id: str = "doc-url-abc"
        document_loaded_event_id: str = "evt-url"
        chunks_written: int = 3
        skipped_reason: str | None = None
        title: str = "Generic Article"
        chunk_ids: list = None
        node_ids: list = None

    import acquisition.urls as _urls

    captured = {}

    def fake_ingest(*args, **kwargs):
        captured.update(kwargs)
        return _R()

    monkeypatch.setattr(_urls, "ingest_url", fake_ingest)

    _allow_operator_domain(temp_substrate, "example.com")
    client = _client(temp_substrate)
    resp = client.post(
        "/sources/ingest",
        json={"url": "https://example.com/article"},
    )
    assert resp.status_code == 202
    body = resp.json()
    assert body["status"] == "ingested"
    assert body["detected_kind"] == "url"
    assert body["document_id"] == "doc-url-abc"
    assert captured["authority"].account_id == "__operator__"
    assert captured["authority"].investigation_id == "__operator__"


def test_ingest_url_without_explicit_allow_is_zero_fetch(monkeypatch, temp_substrate):
    import acquisition.urls as _urls

    monkeypatch.setattr(
        _urls,
        "ingest_url",
        lambda *_args, **_kwargs: pytest.fail("URL fetch ran without explicit policy allow"),
    )
    response = _client(temp_substrate).post(
        "/sources/ingest", json={"url": "https://example.com/article"}
    )
    assert response.status_code == 202
    assert response.json()["status"] == "skipped"
    assert response.json()["skipped_reason"] == "legal_policy:no_explicit_external_allow"


def test_ingest_url_scalar_id_cannot_cross_authenticated_account(monkeypatch, temp_substrate):
    from interfaces.research.api.investigation_access import (
        RequestInvestigationAuthority,
    )
    from substrate.investigation_streams import initialize_composite_stream
    from substrate.investigation_tenancy import InvestigationAuthority

    bob = InvestigationAuthority("bob", "shared-investigation")
    initialize_composite_stream(bob)
    alice = InvestigationAuthority("alice", "shared-investigation")
    app_module = sys.modules["interfaces.research.api.app"]
    monkeypatch.setattr(
        app_module,
        "authority_from_request",
        lambda _request, _investigation_id: RequestInvestigationAuthority(
            alice, frozenset({"research:write"}), "session"
        ),
    )
    import acquisition.urls as _urls

    monkeypatch.setattr(
        _urls,
        "ingest_url",
        lambda *_args, **_kwargs: pytest.fail("cross-account adapter call"),
    )
    response = _client(temp_substrate).post(
        "/sources/ingest",
        json={
            "url": "https://example.com/article",
            "investigation_id": "shared-investigation",
        },
    )
    assert response.status_code == 202
    body = response.json()
    assert body["status"] == "error"
    assert "InvestigationAccessDenied" in body["error_message"]


def test_ingest_arxiv_invalid_id_returns_error(monkeypatch, temp_substrate):
    """An arxiv-looking URL we cannot parse must round-trip as an
    error response, not a 500."""
    # Force a URL that pattern-matches arxiv but yields no id.
    # NOTE: ``interfaces.research.api.__init__`` re-exports ``app`` (the
    # FastAPI instance), so the dotted import resolves to that, not the
    # submodule. Reach into ``sys.modules`` to get the submodule itself.
    _app_mod = sys.modules["interfaces.research.api.app"]
    monkeypatch.setattr(_app_mod, "_extract_arxiv_id", lambda u: None)

    client = _client(temp_substrate)
    resp = client.post(
        "/sources/ingest",
        json={"url": "https://arxiv.org/abs/garbage"},
    )
    assert resp.status_code == 202
    body = resp.json()
    assert body["status"] == "error"
    assert body["detected_kind"] == "arxiv"
    assert "arXiv id" in (body["error_message"] or "")


def test_ingest_with_explicit_kind_overrides_detection(monkeypatch, temp_substrate):
    """Operator can force the adapter choice via ``kind``."""
    from dataclasses import dataclass

    @dataclass
    class _R:
        document_id: str = "doc-url-forced"
        document_loaded_event_id: str = "evt"
        chunks_written: int = 1
        skipped_reason: str | None = None
        title: str = "Forced URL"
        chunk_ids: list = None
        node_ids: list = None

    import acquisition.urls as _urls

    monkeypatch.setattr(_urls, "ingest_url", lambda *a, **kw: _R())

    _allow_operator_domain(temp_substrate, "arxiv.org")
    client = _client(temp_substrate)
    # An arxiv URL forced to be ingested as a plain URL
    resp = client.post(
        "/sources/ingest",
        json={"url": "https://arxiv.org/abs/2402.03300", "kind": "url"},
    )
    assert resp.status_code == 202
    body = resp.json()
    assert body["detected_kind"] == "url"
    assert body["document_id"] == "doc-url-forced"


def test_ingest_short_url_validation_error(temp_substrate):
    """Pydantic min_length should reject obviously bogus URLs."""
    client = _client(temp_substrate)
    resp = client.post("/sources/ingest", json={"url": "x"})
    assert resp.status_code == 422
