"""Owner-read path — the §9.0 privileged owner bypass (Activation SPR-owner-read).

The §9.0 retrieval gate is DENY-BY-DEFAULT: a non-privileged retrieval excludes
both ``restricted_pending_opt_in`` (gated-but-public, e.g. arXiv) and
``personal_reading`` (owner-only third-party content). Before this sprint the
owner's Read path (``ask_book`` / ``corpus_search``) retrieved with the DEFAULT
non-privileged tag, so the OWNER could not read his OWN gated/personal corpus.

This sprint wires those two endpoints to pass the PRIVILEGED ``operator_only``
tag ONLY for an AUTHENTICATED owner (resolved server-side from the auth
middleware's ``request.state.auth_method``). The bar these tests hold:

  1. Owner-authenticated ``ask_book`` / ``corpus_search`` over a
     ``personal_reading`` AND a ``restricted_pending_opt_in`` document RETURNS
     that content (answer grounded + citations / search hits present).
  2. Unauthenticated / non-owner callers do NOT — when enforcement is on the
     middleware 401s them before the gate even runs, so the bypass is
     impossible for a non-owner.
  3. The genuinely-public serve path (``/books/{id}/full-text``) still excludes
     the same gated document — the owner bypass is retrieval-only, the serve
     gate is untouched (regression guard).

These run with auth ENFORCEMENT ON (the prod posture: ANTIEK_OPERATOR_TOKEN /
ANTIEK_OPERATOR_EMAIL set) so the test exercises the REAL middleware path,
not the auth-disabled local-dev bypass. The owner credential is the operator
bearer token (deterministic, no inbox round-trip).
"""

from __future__ import annotations

import os
import sys
import tempfile
from concurrent.futures import ThreadPoolExecutor

import pytest

from runtime.db_lock import connect_write
from substrate.books import ingest as bingest
from substrate.graph.ops import insert_chunk, insert_document
from substrate.graph.schema import init_database

_OPERATOR_TOKEN = "op_secret_owner"
_OWNER_HEADERS = {"Authorization": f"Bearer {_OPERATOR_TOKEN}"}


# ---------------------------------------------------------------------------
# Fixtures + helpers (mirror tests/test_book_qa_meta_reading.py)
# ---------------------------------------------------------------------------


class StubEmbedding:
    """Deterministic 4-d embedding (matches test_book_qa_meta_reading.py)."""

    dimension = 4

    def encode(self, text: str) -> list[float]:
        h = sum(ord(c) * (i + 1) for i, c in enumerate(text)) or 1
        return [
            float(h % 7) / 7.0, float((h >> 3) % 11) / 11.0,
            float((h >> 5) % 13) / 13.0, float((h >> 7) % 17) / 17.0,
        ]


class _RecordingProvider:
    """A fake dispatch provider that records its prompts and returns a fixed
    reply, so the dispatch path is deterministic and key-free. Recording the
    prompt lets a test assert WHAT context the model saw."""

    def __init__(self, reply: str = "A synthesized answer.", name: str = "fake"):
        self.reply = reply
        self.name = name
        self.prompts: list[str] = []

    def call(self, *, model, prompt, max_tokens, temperature):
        from substrate.dispatch import RawProviderResponse

        self.prompts.append(prompt)
        return RawProviderResponse(
            text=self.reply, raw_usage={}, finish_reason="stop", latency_ms=1,
        )

    def normalize_usage(self, raw_usage):
        from substrate.dispatch import NormalizedUsage

        return NormalizedUsage(input_tokens=0, output_tokens=0)


def register_fake(reply: str = "A synthesized answer.") -> _RecordingProvider:
    """Register ONE fake provider under ALL research-tier override names so the
    provider_override lands on it whichever tier the caller chose. The shared
    instance records every prompt.

    The claude-less research-tier map (#309) resolves fast→zai / deep→
    zai_reasoning (GLM-5.2, thinking off / on); 'deepseek' is the config
    primary. All override aliases share the SAME prompt log."""
    from substrate.dispatch.router import register_provider

    deep = _RecordingProvider(reply, name="deepseek")
    register_provider(deep)
    for override_name in ("zai", "zai_reasoning", "xiaomi"):
        twin = _RecordingProvider(reply, name=override_name)
        twin.prompts = deep.prompts
        register_provider(twin)
    return deep


@pytest.fixture(autouse=True)
def _clean_registry():
    from substrate.dispatch.router import reset_provider_registry

    reset_provider_registry()
    yield
    reset_provider_registry()


@pytest.fixture
def db(monkeypatch):
    tmp = tempfile.mkdtemp(prefix="antiek-owner-read-")
    db_path = os.path.join(tmp, "graph.duckdb")
    events_dir = os.path.join(tmp, "events")
    os.makedirs(events_dir, exist_ok=True)
    monkeypatch.setenv("ANTIEK_DUCKDB_PATH", db_path)
    monkeypatch.setenv("ANTIEK_RESEARCH_EVENTS_DIR", events_dir)
    con = connect_write(db_path, purpose="owner-read-test")
    init_database(con)
    con.close()
    return db_path


@pytest.fixture
def stub_embeddings(monkeypatch):
    """Force the (uninstalled) SentenceTransformer model to the deterministic
    stub on the search module the endpoints import from."""
    monkeypatch.setattr(
        sys.modules["substrate.graph.search"], "SentenceTransformerEmbedding",
        lambda: StubEmbedding(),
    )


@pytest.fixture
def owner_client(db, monkeypatch):
    """A TestClient with auth ENFORCEMENT ON (operator bearer). This is the
    prod posture: a request must carry the operator bearer to pass the
    middleware. Without the header the middleware 401s before any endpoint
    runs — that is the non-owner exclusion proof."""
    from fastapi.testclient import TestClient

    monkeypatch.setenv("ANTIEK_OPERATOR_TOKEN", _OPERATOR_TOKEN)
    from interfaces.research.api.app import create_app

    app = create_app(register_wrestling=False, register_providers=False, cors_origins=[])
    return TestClient(app)


def _gated_book(db_path, document_id, *, content_class, title, probe="GATEDPROBE"):
    """A book of ``content_class`` WITH chunks carrying a unique probe term, so a
    test can prove whether the §9.0 gate admitted (owner) or excluded (public)
    the body. The chunk anchors to 'Page 1' so an admitted citation resolves."""
    con = connect_write(db_path, purpose="insert")
    insert_document(
        con, document_id=document_id, source_tier=2, document_type="book",
        title=title, author="Author", raw_text=f"{probe} body " * 50,
    )
    insert_chunk(
        con, document_id=document_id, chunk_index=0,
        text=f"{probe} quantum passage about entanglement and superposition",
        section_path="Page 1", token_count=8,
        embedding=StubEmbedding().encode(f"{probe} quantum passage"),
    )
    con.close()
    con = connect_write(db_path, purpose="register")
    try:
        bingest.register_book(
            con, document_id=document_id, content_class=content_class,
            provenance="owner's own copy / aggregated, unknown rights",
        )
    finally:
        con.close()


# ---------------------------------------------------------------------------
# 1. Authenticated owner READS his own gated/personal corpus
# ---------------------------------------------------------------------------


@pytest.mark.parametrize(
    "content_class", ["personal_reading", "restricted_pending_opt_in"],
)
def test_owner_ask_book_reads_own_gated_content(
    db, owner_client, stub_embeddings, content_class,
):
    """The authenticated owner talking to HIS OWN gated/personal book gets the
    body: the answer is grounded, cites the chunk, and the gated body actually
    reached the model prompt (the privileged tag admitted it through §9.0)."""
    _gated_book(db, "doc-owner", content_class=content_class, title="Owned")
    provider = register_fake("Page one covers entanglement.")

    res = owner_client.post(
        "/books/doc-owner/ask",
        json={"question": "what is the quantum passage about?"},
        headers=_OWNER_HEADERS,
    )
    assert res.status_code == 200, res.text
    body = res.json()
    assert body["grounded"] is True, "owner read must ground on the gated body"
    assert body["citations"], "a grounded owner answer must cite the gated chunk"
    assert body["citations"][0]["document_id"] == "doc-owner"
    # PROOF the gate admitted the body: the unique probe term reached the prompt.
    assert provider.prompts, "the owner read must dispatch a model on the gated body"
    assert any("GATEDPROBE" in p for p in provider.prompts), (
        "the owner's own gated/personal body must reach the model context"
    )
    assert body["answer_id"].startswith("evt-")


def test_answer_capture_judgment_and_eval_export(
    db, owner_client, stub_embeddings,
):
    from substrate.event_log import trajectory

    _gated_book(db, "doc-eval", content_class="personal_reading", title="Eval")
    register_fake("A grounded answer for evaluation.")
    answered = owner_client.post(
        "/books/doc-eval/ask",
        json={"question": "what does the passage establish?"},
        headers=_OWNER_HEADERS,
    )
    assert answered.status_code == 200, answered.text
    answer_id = answered.json()["answer_id"]
    answer_row = next(row for row in trajectory("read-doc-eval") if row["event_id"] == answer_id)
    payload = answer_row["payload"]
    assert payload["provider"] == "zai_reasoning"
    assert payload["model"]
    assert payload["input_tokens"] == 0
    assert payload["output_tokens"] == 0
    assert payload["latency_ms"] == 1
    assert payload["citations"][0]["document_id"] == "doc-eval"

    judged = owner_client.post(
        f"/books/doc-eval/answers/{answer_id}/judgment",
        json={"verdict": "good"},
        headers=_OWNER_HEADERS,
    )
    assert judged.status_code == 200, judged.text
    replay = owner_client.post(
        f"/books/doc-eval/answers/{answer_id}/judgment",
        json={"verdict": "good"},
        headers=_OWNER_HEADERS,
    )
    assert replay.status_code == 200
    assert replay.json()["judgment_id"] == judged.json()["judgment_id"]
    conflict = owner_client.post(
        f"/books/doc-eval/answers/{answer_id}/judgment",
        json={"verdict": "bad"},
        headers=_OWNER_HEADERS,
    )
    assert conflict.status_code == 409

    exported = owner_client.get(
        "/books/doc-eval/answer-evaluations",
        headers=_OWNER_HEADERS,
    )
    assert exported.status_code == 200, exported.text
    assert exported.json()["count"] == 1
    record = exported.json()["answers"][0]
    assert record["answer_id"] == answer_id
    assert record["verdict"] == "good"
    assert record["question"] == "what does the passage establish?"


def test_disabled_event_log_returns_answer_without_inviting_paid_retry(
    db, owner_client, stub_embeddings, monkeypatch,
):
    _gated_book(db, "doc-disabled", content_class="personal_reading", title="Disabled")
    provider = register_fake()
    monkeypatch.setenv("ANTIEK_EVENTS_DISABLED", "1")
    response = owner_client.post(
        "/books/doc-disabled/ask",
        json={"question": "what is here?"},
        headers=_OWNER_HEADERS,
    )
    assert response.status_code == 200
    assert response.json()["answer_id"] is None
    assert response.json()["capture_status"] == "unavailable"
    assert response.json()["answer"]
    assert len(provider.prompts) == 1


def test_capture_exception_returns_paid_answer_once(
    db, owner_client, stub_embeddings, monkeypatch,
):
    import substrate.event_log

    _gated_book(db, "doc-capture-error", content_class="personal_reading", title="Capture")
    provider = register_fake()

    def fail_capture(*_args, **_kwargs):
        raise OSError("simulated event-store failure")

    monkeypatch.setattr(substrate.event_log, "emit_typed", fail_capture)
    response = owner_client.post(
        "/books/doc-capture-error/ask",
        json={"question": "what is here?"},
        headers=_OWNER_HEADERS,
    )
    assert response.status_code == 200
    assert response.json()["answer_id"] is None
    assert response.json()["capture_status"] == "unavailable"
    assert len(provider.prompts) == 1


def test_concurrent_judgment_requests_append_once(
    db, owner_client, stub_embeddings,
):
    from substrate.event_log import trajectory

    _gated_book(db, "doc-race", content_class="personal_reading", title="Race")
    register_fake()
    answered = owner_client.post(
        "/books/doc-race/ask",
        json={"question": "what is here?"},
        headers=_OWNER_HEADERS,
    )
    answer_id = answered.json()["answer_id"]

    def judge_once(_index):
        return owner_client.post(
            f"/books/doc-race/answers/{answer_id}/judgment",
            json={"verdict": "good"},
            headers=_OWNER_HEADERS,
        )

    with ThreadPoolExecutor(max_workers=8) as pool:
        responses = list(pool.map(judge_once, range(8)))
    assert {response.status_code for response in responses} == {200}
    assert len({response.json()["judgment_id"] for response in responses}) == 1
    judgments = [
        row for row in trajectory("read-doc-race")
        if row["action_type"] == "read.book_answer_judged"
    ]
    assert len(judgments) == 1


def test_ungrounded_answer_records_explicit_no_model_receipt(
    db, owner_client, stub_embeddings,
):
    from substrate.event_log import trajectory

    con = connect_write(db, purpose="empty-book")
    insert_document(
        con, document_id="doc-empty", source_tier=2, document_type="book",
        title="Scanned", author="Author", raw_text="",
    )
    bingest.register_book(
        con, document_id="doc-empty", content_class="personal_reading",
        provenance="owner scan",
    )
    con.close()
    response = owner_client.post(
        "/books/doc-empty/ask",
        json={"question": "what is here?"},
        headers=_OWNER_HEADERS,
    )
    assert response.status_code == 200, response.text
    row = next(
        row for row in trajectory("read-doc-empty")
        if row["event_id"] == response.json()["answer_id"]
    )
    assert row["payload"]["grounded"] is False
    for field in ("provider", "model", "input_tokens", "output_tokens", "cost_usd", "latency_ms"):
        assert row["payload"][field] is None


def test_judgment_rejects_forged_or_other_owner_answer(
    db, owner_client,
):
    from substrate.event_log import emit_typed
    from substrate.schemas import ReadBookAnsweredPayload

    answer_id = emit_typed(
        "read-doc-owned-by-other",
        ReadBookAnsweredPayload(
            owner_id="other-owner",
            question="private question",
            answer="private answer",
            grounded=False,
            context_chunk_count=0,
            research_tier="deep",
        ),
        document_id="doc-owned-by-other",
    )
    response = owner_client.post(
        f"/books/doc-owned-by-other/answers/{answer_id}/judgment",
        json={"verdict": "good"},
        headers=_OWNER_HEADERS,
    )
    assert response.status_code == 404
    forged = owner_client.post(
        "/books/doc-owned-by-other/answers/evt-forged/judgment",
        json={"verdict": "good"},
        headers=_OWNER_HEADERS,
    )
    assert forged.status_code == 404


@pytest.mark.parametrize(
    "content_class", ["personal_reading", "restricted_pending_opt_in"],
)
def test_owner_corpus_search_finds_own_gated_content(
    db, owner_client, stub_embeddings, content_class,
):
    """The authenticated owner's corpus search surfaces HIS OWN gated/personal
    book (the privileged tag admits it through the §9.0 chunk gate)."""
    _gated_book(db, "doc-owner-cs", content_class=content_class, title="Owned CS")

    res = owner_client.get(
        "/corpus/search",
        params={"q": "quantum passage entanglement"},
        headers=_OWNER_HEADERS,
    )
    assert res.status_code == 200, res.text
    body = res.json()
    ids = {h["document_id"] for h in body["hits"]}
    assert "doc-owner-cs" in ids, "owner search must include his own gated book"
    assert any("GATEDPROBE" in h["snippet"] for h in body["hits"]), (
        "owner search must surface the gated chunk body"
    )


# ---------------------------------------------------------------------------
# 2. Non-owner / unauthenticated callers are EXCLUDED (the bypass binds to auth)
# ---------------------------------------------------------------------------


@pytest.mark.parametrize(
    "content_class", ["personal_reading", "restricted_pending_opt_in"],
)
def test_unauthenticated_ask_book_is_blocked(
    db, owner_client, stub_embeddings, content_class,
):
    """Auth is ON; a caller with NO credential is 401'd by the middleware BEFORE
    the endpoint runs — so the §9.0 bypass is unreachable to a non-owner. The
    gated body is never retrieved, never prompted, never returned."""
    _gated_book(db, "doc-noauth", content_class=content_class, title="Owned")
    provider = register_fake("should never be called")

    res = owner_client.post(
        "/books/doc-noauth/ask",
        json={"question": "what is the quantum passage about?"},
        # No Authorization header.
    )
    assert res.status_code == 401, res.text
    assert res.json()["error"]["code"] == "operator_auth_required"
    assert provider.prompts == [], "a blocked caller must never dispatch a model"


@pytest.mark.parametrize(
    "content_class", ["personal_reading", "restricted_pending_opt_in"],
)
def test_wrong_credential_ask_book_is_blocked(
    db, owner_client, stub_embeddings, content_class,
):
    """A WRONG bearer (a non-owner who guessed) is 401'd — the bypass binds to
    the OWNER credential, not to 'any caller'."""
    _gated_book(db, "doc-wrong", content_class=content_class, title="Owned")
    register_fake("should never be called")

    res = owner_client.post(
        "/books/doc-wrong/ask",
        json={"question": "what is the quantum passage about?"},
        headers={"Authorization": "Bearer not_the_owner"},
    )
    assert res.status_code == 401, res.text
    assert res.json()["error"]["code"] == "operator_auth_required"


@pytest.mark.parametrize(
    "content_class", ["personal_reading", "restricted_pending_opt_in"],
)
def test_unauthenticated_corpus_search_is_blocked(
    db, owner_client, stub_embeddings, content_class,
):
    """Auth on; no credential ⇒ 401 before the corpus-search gate runs. The
    gated book never appears because the request never reaches retrieval."""
    _gated_book(db, "doc-noauth-cs", content_class=content_class, title="Owned")

    res = owner_client.get(
        "/corpus/search", params={"q": "quantum passage entanglement"},
        # No Authorization header.
    )
    assert res.status_code == 401, res.text
    assert res.json()["error"]["code"] == "operator_auth_required"


def test_local_dev_corpus_search_stays_gated(db, monkeypatch):
    """ENFORCEMENT OFF (no auth env) ⇒ auth_method='unauthenticated_local'. The
    §9.0 owner bypass is NOT granted on this path: a local client still EXCLUDES
    restricted/personal content. This is the mechanical proof of the fail-closed
    rule canonically stated at ``_owner_read_policy_tag`` / ``_OWNER_AUTH_METHODS``
    in interfaces/research/api/books.py (the bypass binds to a real credential,
    never to 'auth happened to be off' — so a box accidentally deployed without
    auth cannot leak the gated corpus)."""
    from fastapi.testclient import TestClient

    monkeypatch.delenv("ANTIEK_OPERATOR_TOKEN", raising=False)
    monkeypatch.delenv("ANTIEK_OPERATOR_EMAIL", raising=False)
    monkeypatch.setattr(
        sys.modules["substrate.graph.search"], "SentenceTransformerEmbedding",
        lambda: StubEmbedding(),
    )
    from interfaces.research.api.app import create_app

    app = create_app(register_wrestling=False, register_providers=False, cors_origins=[])
    client = TestClient(app)

    _gated_book(db, "doc-local-personal", content_class="personal_reading", title="P")
    _gated_book(
        db, "doc-local-restricted",
        content_class="restricted_pending_opt_in", title="R",
    )
    res = client.get("/corpus/search", params={"q": "quantum passage entanglement"})
    assert res.status_code == 200, res.text
    ids = {h["document_id"] for h in res.json()["hits"]}
    assert "doc-local-personal" not in ids
    assert "doc-local-restricted" not in ids


# ---------------------------------------------------------------------------
# 3. The genuinely-public serve path is UNCHANGED (regression guard)
# ---------------------------------------------------------------------------


@pytest.mark.parametrize(
    "content_class", ["personal_reading", "restricted_pending_opt_in"],
)
def test_public_serve_path_still_excludes_gated_body_for_owner(
    db, owner_client, content_class,
):
    """The owner bypass is RETRIEVAL-ONLY. The public full-text SERVE path
    (``serve_full_text_guarded``, an allowlist that never consults policy_tag)
    must still WITHHOLD the gated/personal body — even for the authenticated
    owner. personal_reading + restricted_pending_opt_in are NOT in the servable
    allowlist; the serve gate is untouched by this sprint."""
    _gated_book(db, "doc-serve", content_class=content_class, title="Owned")

    res = owner_client.get("/books/doc-serve/full-text", headers=_OWNER_HEADERS)
    assert res.status_code == 200, res.text
    body = res.json()
    assert body["servable"] is False, (
        f"{content_class} must never be publicly servable via /full-text"
    )
    assert body["full_text"] is None, "the gated body must not be served inline"


# ---------------------------------------------------------------------------
# SINGLE-OPERATOR ENFORCEMENT — the verifier-critic + Strix "cross-tenant in
# multi-operator" High, closed STRUCTURALLY (not just documented).
# ---------------------------------------------------------------------------


def test_multi_operator_config_fails_closed_to_non_privileged(monkeypatch):
    """With 2+ operator emails the owner-read privilege FAILS CLOSED to the
    non-privileged tag, so an authenticated owner's session cannot
    cross-tenant-read another operator's ``personal_reading`` corpus.
    ``_owner_read_policy_tag`` gates the privilege on
    ``operator_allowlist_from_env()`` resolving <= 1 operator."""
    from types import SimpleNamespace

    from interfaces.research.api.books import (
        _OWNER_READ_POLICY_TAG,
        _PUBLIC_READ_POLICY_TAG,
        _owner_read_policy_tag,
    )

    def _req(auth_method: str) -> object:
        return SimpleNamespace(state=SimpleNamespace(auth_method=auth_method))

    # Single operator (<= 1 email): an authenticated owner gets the privilege.
    monkeypatch.setenv("ANTIEK_OPERATOR_EMAIL", "solo@example.com")
    assert _owner_read_policy_tag(_req("antiek_session_cookie")) == _OWNER_READ_POLICY_TAG  # type: ignore[arg-type]
    assert _owner_read_policy_tag(_req("bearer_token")) == _OWNER_READ_POLICY_TAG  # type: ignore[arg-type]

    # Multi-operator (2 emails): the SAME authenticated methods now FAIL CLOSED.
    monkeypatch.setenv("ANTIEK_OPERATOR_EMAIL", "alice@example.com,bob@example.com")
    assert _owner_read_policy_tag(_req("antiek_session_cookie")) == _PUBLIC_READ_POLICY_TAG  # type: ignore[arg-type]
    assert _owner_read_policy_tag(_req("cloudflare_access_email")) == _PUBLIC_READ_POLICY_TAG  # type: ignore[arg-type]
    assert _owner_read_policy_tag(_req("bearer_token")) == _PUBLIC_READ_POLICY_TAG  # type: ignore[arg-type]

    # A non-owner is non-privileged regardless of operator count.
    assert _owner_read_policy_tag(_req("unauthenticated_local")) == _PUBLIC_READ_POLICY_TAG  # type: ignore[arg-type]
