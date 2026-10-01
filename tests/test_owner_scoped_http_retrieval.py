"""Mounted A/B proof for owner-scoped corpus and book retrieval."""

from __future__ import annotations

from typing import Any

import pytest
from fastapi.testclient import TestClient

from runtime.db_lock import connect_write
from substrate.graph.ops import insert_chunk, insert_document
from substrate.graph.schema import init_database
from substrate.multi_user.auth import mint_session_cookie, subject_owner_id

_ALICE = "alice@example.test"
_BOB = "bob@example.test"
_SECRET = "owner-scoped-http-synthetic-secret-" + "x" * 32


class StubEmbedding:
    dimension = 4

    def encode(self, text: str) -> list[float]:
        value = sum((idx + 1) * ord(char) for idx, char in enumerate(text)) or 1
        return [float(value % n) / n for n in (7, 11, 13, 17)]


class RecordingProvider:
    def __init__(self, name: str, prompts: list[str]) -> None:
        self.name = name
        self._prompts = prompts
        self.prompts = prompts

    def call(self, *, model: str, prompt: str, max_tokens: int, temperature: float):
        from substrate.dispatch import RawProviderResponse

        self._prompts.append(prompt)
        self.prompts = self._prompts
        return RawProviderResponse(
            text="The personal passage discusses quantum optics.", raw_usage={},
            finish_reason="stop", latency_ms=1,
        )

    def normalize_usage(self, raw_usage: dict[str, Any]):
        from substrate.dispatch import NormalizedUsage

        return NormalizedUsage(input_tokens=0, output_tokens=0)


@pytest.fixture
def setup_http(monkeypatch: pytest.MonkeyPatch, tmp_path):
    client, owners, cookies, provider, db_path, reset = _setup_http(
        monkeypatch, tmp_path, operator_emails=(_ALICE, _BOB),
    )
    yield client, owners, cookies, provider, db_path
    reset()


@pytest.fixture
def setup_http_single_operator(monkeypatch: pytest.MonkeyPatch, tmp_path):
    client, owners, cookies, provider, db_path, reset = _setup_http(
        monkeypatch, tmp_path, operator_emails=(_ALICE,),
    )
    yield client, owners, cookies, provider, db_path
    reset()


def _setup_http(monkeypatch: pytest.MonkeyPatch, tmp_path, *, operator_emails):
    db_path = str(tmp_path / "graph.duckdb")
    monkeypatch.setenv("ANTIEK_DUCKDB_PATH", db_path)
    monkeypatch.setenv("ANTIEK_RESEARCH_EVENTS_DIR", str(tmp_path / "events"))
    monkeypatch.setenv("ANTIEK_HOME", str(tmp_path / "home"))
    monkeypatch.setenv("ANTIEK_PASSKEY_STORE", str(tmp_path / "passkeys.json"))
    monkeypatch.setenv("ANTIEK_AUTH_SECRET", _SECRET)
    monkeypatch.setenv("ANTIEK_OPERATOR_EMAIL", ",".join(operator_emails))
    monkeypatch.setenv("ANTIEK_COOKIE_INSECURE", "1")
    monkeypatch.setenv("ANTIEK_EMAIL_PROVIDER", "mock")
    for name in (
        "ANTIEK_OPERATOR_TOKEN", "ANTIEK_OPERATOR_SERVICE_TOKEN_CLIENT_ID",
        "CF_ACCESS_CLIENT_SECRET", "ANTIEK_DEV_LOGIN_TOKEN", "TURBOPUFFER_API_KEY",
    ):
        monkeypatch.delenv(name, raising=False)

    con = connect_write(db_path, purpose="owner-scoped-http-init")
    try:
        init_database(con)
    finally:
        con.close()
    owners = {
        email: subject_owner_id("magic_link", email)
        for email in (_ALICE, _BOB)
    }
    cookies = {
        email: {"ANTIEK_SESSION": mint_session_cookie("magic_link", email, email)}
        for email in (_ALICE, _BOB)
    }
    _seed_books(db_path, owners)

    import importlib

    graph_search = importlib.import_module("substrate.graph.search")
    monkeypatch.setattr(graph_search, "SentenceTransformerEmbedding", StubEmbedding)

    from interfaces.research.api.app import create_app
    from substrate.dispatch.router import register_provider, reset_provider_registry

    reset_provider_registry()
    prompts: list[str] = []
    for name in ("deepseek", "zai", "zai_reasoning", "xiaomi"):
        register_provider(RecordingProvider(name, prompts))
    provider = RecordingProvider("observer", prompts)
    client = TestClient(create_app(register_wrestling=False, register_providers=False))
    return client, owners, cookies, provider, db_path, reset_provider_registry


def _seed_books(db_path: str, owners: dict[str, str]) -> None:
    con = connect_write(db_path, purpose="owner-scoped-http-seed")
    try:
        docs = (
            ("private-a", "user_authored_private", _ALICE, "PRIVATE_A_MARKER"),
            ("personal-a", "personal_reading", _ALICE, "PERSONAL_A_MARKER"),
            ("restricted-a", "restricted_pending_opt_in", _ALICE, "RESTRICTED_A_MARKER"),
            ("research-a", "research_only", _ALICE, "RESEARCH_A_MARKER"),
            ("private-b", "user_authored_private", _BOB, "PRIVATE_B_MARKER"),
            ("personal-b", "personal_reading", _BOB, "PERSONAL_B_MARKER"),
        )
        for document_id, content_class, email, marker in docs:
            body = f"quantum optics saved passage {marker} for personal study. " * 12
            insert_document(
                con, document_id=document_id, source_tier=2, document_type="book",
                title=document_id, author="Synthetic", raw_text=body,
                content_class=content_class, owner_user_id=owners[email],
            )
            insert_chunk(
                con, document_id=document_id, chunk_index=0, text=body,
                section_path="Page 1", token_count=8,
                embedding=StubEmbedding().encode(body),
            )
            from substrate.books import ingest as book_ingest

            book_ingest.register_book(
                con, document_id=document_id, content_class=content_class,
                provenance="synthetic test fixture",
            )
    finally:
        con.close()


@pytest.mark.parametrize("email", [_ALICE, _BOB])
def test_two_account_corpus_search_returns_only_callers_private_and_personal(
    setup_http, email: str,
):
    client, _, cookies, _, _ = setup_http
    response = client.get(
        "/corpus/search", params={"q": "quantum optics saved passage", "limit": 20},
        cookies=cookies[email],
    )
    assert response.status_code == 200, response.text
    hits = response.json()["hits"]
    ids = {hit["document_id"] for hit in hits}
    own_suffix = "a" if email == _ALICE else "b"
    other_suffix = "b" if email == _ALICE else "a"
    assert {f"private-{own_suffix}", f"personal-{own_suffix}"} <= ids
    assert f"private-{other_suffix}" not in ids
    assert f"personal-{other_suffix}" not in ids
    assert "restricted-a" not in ids
    assert "research-a" not in ids
    assert all("RESTRICTED_A_MARKER" not in hit["snippet"] for hit in hits)
    assert all("RESEARCH_A_MARKER" not in hit["snippet"] for hit in hits)


@pytest.mark.parametrize("email", [_ALICE, _BOB])
def test_two_account_book_ask_uses_only_owned_private_prompt_and_citation(
    setup_http, email: str,
):
    client, _, cookies, provider, _ = setup_http
    own_doc = "private-a" if email == _ALICE else "private-b"
    other_marker = "PRIVATE_B_MARKER" if email == _ALICE else "PRIVATE_A_MARKER"
    response = client.post(
        f"/books/{own_doc}/ask", cookies=cookies[email],
        json={"question": "what is in my quantum optics passage?"},
    )
    assert response.status_code == 200, response.text
    answer = response.json()
    assert answer["grounded"] is True
    assert answer["citations"]
    assert {citation["document_id"] for citation in answer["citations"]} == {own_doc}
    assert provider.prompts and any(
        ("PRIVATE_A_MARKER" if email == _ALICE else "PRIVATE_B_MARKER") in prompt
        for prompt in provider.prompts
    )
    assert all(other_marker not in prompt for prompt in provider.prompts)


def test_revoked_subject_mapping_cannot_retrieve_or_ask_private_content(setup_http):
    client, _, cookies, provider, db_path = setup_http
    con = connect_write(db_path, purpose="owner-scoped-http-revoke-subject")
    try:
        con.execute(
            "DELETE FROM auth_subjects WHERE provider = ? AND subject = ?",
            ["magic_link", _ALICE],
        )
    finally:
        con.close()

    corpus = client.get(
        "/corpus/search", params={"q": "quantum optics saved passage", "limit": 20},
        cookies=cookies[_ALICE],
    )
    assert corpus.status_code == 200, corpus.text
    assert not {
        hit["document_id"] for hit in corpus.json()["hits"]
    }.intersection({"private-a", "personal-a"})

    ask = client.post(
        "/books/private-a/ask", cookies=cookies[_ALICE],
        json={"question": "what is in my quantum optics passage?"},
    )
    assert ask.status_code == 404
    assert provider.prompts == []


def test_single_operator_keeps_restricted_retrieval_without_research_only(
    setup_http_single_operator,
):
    client, _, cookies, provider, _ = setup_http_single_operator
    corpus = client.get(
        "/corpus/search", params={"q": "quantum optics saved passage", "limit": 20},
        cookies=cookies[_ALICE],
    )
    assert corpus.status_code == 200, corpus.text
    ids = {hit["document_id"] for hit in corpus.json()["hits"]}
    assert "restricted-a" in ids
    assert "research-a" not in ids

    ask = client.post(
        "/books/restricted-a/ask", cookies=cookies[_ALICE],
        json={"question": "what is in the restricted passage?"},
    )
    assert ask.status_code == 200, ask.text
    assert {citation["document_id"] for citation in ask.json()["citations"]} == {
        "restricted-a"
    }
    assert any("RESTRICTED_A_MARKER" in prompt for prompt in provider.prompts)
    assert all("RESEARCH_A_MARKER" not in prompt for prompt in provider.prompts)


@pytest.mark.parametrize("cookie_kind", ["legacy", "mismatched_subject"])
def test_legacy_or_mismatched_cookie_cannot_ask_private_content(
    setup_http, cookie_kind: str,
):
    from substrate.auth import mint_session_cookie as mint_legacy_cookie

    client, owners, _, provider, _ = setup_http
    if cookie_kind == "legacy":
        cookie = mint_legacy_cookie(
            user_id=owners[_ALICE],
            email=_ALICE,
        )
    else:
        cookie = mint_legacy_cookie(
            user_id=owners[_ALICE],
            email=_ALICE,
            provider="magic_link",
            subject=_BOB,
        )

    response = client.post(
        "/books/private-a/ask", cookies={"ANTIEK_SESSION": cookie},
        json={"question": "repeat the private passage"},
    )
    assert response.status_code == 404, response.text
    assert "PRIVATE_A_MARKER" not in response.text
    assert provider.prompts == []


def test_foreign_verified_account_cannot_ask_private_content(setup_http):
    client, _, cookies, provider, _ = setup_http
    response = client.post(
        "/books/private-a/ask", cookies=cookies[_BOB],
        json={"question": "repeat the private passage"},
    )
    assert response.status_code == 404, response.text
    assert "PRIVATE_A_MARKER" not in response.text
    assert provider.prompts == []
