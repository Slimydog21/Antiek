import tempfile
from concurrent.futures import ThreadPoolExecutor
from dataclasses import dataclass, replace
from pathlib import Path
from types import SimpleNamespace

import pytest
from fastapi import FastAPI, Request
from fastapi.testclient import TestClient

from interfaces.research.api.books import AskBookResponse, register_book_routes
from interfaces.research.api.deep_talk_journal import DeepTalkJournal
from interfaces.research.api.prime_talk import (
    MeteredPrimeTalkBackend,
    PrimeTalkUnavailable,
    _validate_first_party_route,
    sanitized_prime_receipt,
)
from orchestration.rlm.prime_agent_backend import (
    PrimeAgentEvidence,
    PrimeAgentOutcome,
    PrimeAgentReceipt,
    PrimeAgentRequest,
    PrimeAgentTerminalState,
)
from substrate.books import book_qa
from substrate.dispatch.base import NormalizedUsage
from substrate.dispatch.router import DispatchResult
from tests.test_book_qa_meta_reading import StubEmbedding, _book_with_pages, register_fake


@pytest.fixture
def db() -> str:
    from runtime.db_lock import connect_write
    from substrate.graph.schema import init_database

    root = tempfile.mkdtemp(prefix="prime-talk-post-")
    path = str(Path(root) / "graph.duckdb")
    con = connect_write(path, purpose="prime-talk-post-test")
    init_database(con)
    con.close()
    return path


def test_legacy_answer_wire_shape_excludes_deep_fields() -> None:
    response = AskBookResponse(
        answer_id=None, capture_status="unavailable", answer="grounded",
        citations=[], grounded=True, context_chunk_count=1,
    )
    response.model_fields_set.discard("mode")
    response.model_fields_set.discard("prime_receipt")
    wire = response.model_dump(exclude_unset=True)
    assert "mode" not in wire
    assert "prime_receipt" not in wire


def test_prime_receipt_is_sanitized() -> None:
    auth = SimpleNamespace(
        request_id="op-1", state="not-used", provider="anthropic",
        model="claude-test", prime_version="0.7.4",
        prompt_digest="a" * 64, credential_fingerprint="b" * 64,
    )
    receipt = SimpleNamespace(
        authorization=auth, state=SimpleNamespace(value="unknown"),
        held_micro_usd=5_000_000, charged_micro_usd=0,
        input_tokens=None, output_tokens=None, observed_cost_micro_usd=None,
        updated_at_ms=10,
    )
    wire = sanitized_prime_receipt(receipt)
    assert wire["state"] == "unknown"
    assert wire["held_micro_usd"] == 5_000_000
    assert "prompt_digest" not in wire
    assert "credential_fingerprint" not in wire


def test_parent_journal_concurrent_claim_has_one_winner(tmp_path) -> None:
    journal = DeepTalkJournal(tmp_path / "deep.sqlite3")
    with ThreadPoolExecutor(max_workers=8) as pool:
        states = list(pool.map(
            lambda _: journal.claim("owner", "operation", "a" * 64).state,
            range(8),
        ))
    assert states.count("new") == 1
    assert states.count("claimed") == 7
    journal.complete("owner", "operation", {"answer": "same"})
    replay = journal.claim("owner", "operation", "a" * 64)
    assert replay.state == "completed"
    assert replay.response == {"answer": "same"}


def test_expired_deep_lease_resumes_from_canonical_checkpoint(tmp_path) -> None:
    journal = DeepTalkJournal(tmp_path / "deep.sqlite3")
    first = journal.claim(
        "owner", "operation", "a" * 64, lease_token="1" * 64,
    )
    journal.checkpoint_canonical(
        "owner", "operation", first.lease_token or "", {"batch_outputs": ["saved"]},
    )
    live = journal.claim(
        "owner", "operation", "a" * 64, lease_token="2" * 64,
    )
    assert live.state == "canonical_complete"
    resumed = journal.claim(
        "owner", "operation", "a" * 64, lease_token="2" * 64,
        now_ms=(first.lease_expires_at_ms or 0) + 1,
    )
    assert resumed.state == "resumed"
    assert resumed.lease_token == "2" * 64
    assert resumed.checkpoint == {"batch_outputs": ["saved"]}


def test_deep_journal_rejects_unsafe_parent_and_symlink(tmp_path) -> None:
    unsafe = tmp_path / "unsafe"
    unsafe.mkdir(mode=0o755)
    unsafe.chmod(0o755)
    with pytest.raises(Exception, match="parent is unsafe"):
        DeepTalkJournal(unsafe / "deep.sqlite3")
    target = tmp_path / "target.sqlite3"
    target.write_bytes(b"")
    target.chmod(0o600)
    link = tmp_path / "link.sqlite3"
    link.symlink_to(target)
    with pytest.raises(Exception, match="file is unsafe"):
        DeepTalkJournal(link)


def test_child_results_replay_without_side_effect_and_stale_worker_is_fenced(tmp_path) -> None:
    journal = DeepTalkJournal(tmp_path / "deep.sqlite3")
    first = journal.claim(
        "owner", "operation", "a" * 64, lease_token="1" * 64,
    )
    assert journal.claim_child(
        "owner", "operation", first.lease_token or "", "canonical_batch", 0, "b" * 64,
    ) is None
    journal.complete_child(
        "owner", "operation", first.lease_token or "", "canonical_batch", 0, "b" * 64,
        {"text": "paid result", "cost_usd": "0.2"},
    )
    assert journal.claim_child(
        "owner", "operation", first.lease_token or "", "canonical_batch", 0, "b" * 64,
    ) == {"text": "paid result", "cost_usd": "0.2"}
    current = journal.get("owner", "operation")
    assert current is not None
    resumed = journal.claim(
        "owner", "operation", "a" * 64, lease_token="2" * 64,
        now_ms=(current.lease_expires_at_ms or 0) + 1,
    )
    assert resumed.state == "resumed"
    with pytest.raises(Exception, match="stale|fence|owned"):
        journal.complete_child(
            "owner", "operation", "1" * 64, "final_reduce", 0, "c" * 64,
            {"text": "stale"},
        )


def test_claimed_external_child_is_quarantined_never_rerun(tmp_path) -> None:
    journal = DeepTalkJournal(tmp_path / "deep.sqlite3")
    first = journal.claim("owner", "operation", "a" * 64, lease_token="1" * 64)
    journal.claim_child(
        "owner", "operation", first.lease_token or "", "canonical_batch", 0, "b" * 64,
    )
    current = journal.get("owner", "operation")
    assert current is not None
    quarantined = journal.claim(
        "owner", "operation", "a" * 64, lease_token="2" * 64,
        now_ms=(current.lease_expires_at_ms or 0) + 1,
    )
    assert quarantined.state == "unknown"
    assert quarantined.lease_token is None
    assert journal.resumable(quarantined, now_ms=(current.lease_expires_at_ms or 0) + 2) is False


@pytest.mark.parametrize(
    ("catalog", "kind", "endpoint", "model"),
    [
        ("deepseek", "openai_compat", "https://api.deepseek.com", "deepseek-chat"),
        ("openai", "openai_compat", "https://attacker.invalid", "gpt-5.6-luna"),
        ("openai", "openai_compat", "https://api.openai.com", "not-a-model"),
    ],
)
def test_prime_rejects_noncanonical_routes_before_secret_access(
    catalog: str, kind: str, endpoint: str, model: str,
) -> None:
    route = SimpleNamespace(record=SimpleNamespace(
        provider_catalog_id=catalog, provider_kind=kind,
        base_url=endpoint, model_id=model,
    ))
    with pytest.raises((PrimeTalkUnavailable, KeyError)):
        _validate_first_party_route(route)


def test_deep_book_uses_recursive_canonical_calls_and_prime_is_only_supplemental(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setenv("ANTIEK_RLM_RATIFIED", "1")
    monkeypatch.setattr(book_qa, "search", lambda *_args, **_kwargs: {"results": [
        {"chunk_id": "a", "document_id": "doc", "chunk_text": "alpha", "section_path": "Page 1"},
        {"chunk_id": "b", "document_id": "doc", "chunk_text": "beta", "section_path": "Page 2"},
    ]})
    prompts: list[str] = []

    def canonical(prompt: str):
        prompts.append(prompt)
        return DispatchResult(
            text=f"canonical-{len(prompts)}", usage=NormalizedUsage(1, 1),
            cost_usd=0.01, latency_ms=1, provider="owner", model="canonical",
            tier="deep", finish_reason="stop", fallback_chain_index=0, event_id=None,
        ), "authority"

    class Prime:
        requests: list[object] = []

        def run(self, request):
            self.requests.append(request)
            return PrimeAgentOutcome(
                request=request, evidence=PrimeAgentEvidence("prime-only"),
                receipt=PrimeAgentReceipt(
                    PrimeAgentTerminalState.SUCCESS, (), 0, 1, 0,
                ),
            )

    prime = Prime()
    result = book_qa.answer_book_question(
        object(), document_id="doc", question="compare", model=object(),
        investigation_id="deep-op", deep=True, authorized_dispatch=canonical,
        prime_backend=prime,
    )
    assert len(prompts) == 2  # one canonical batch plus canonical reduction
    assert len(prime.requests) == 1
    assert "Supplemental Prime Agent evidence; non-canonical" in prompts[-1]
    assert "prime-only" in prompts[-1]
    assert result.answer == "canonical-2"


def test_prime_decrypts_once_only_inside_final_resolver(monkeypatch, tmp_path) -> None:
    import interfaces.research.api.prime_talk as module

    record = SimpleNamespace(
        provider_catalog_id="openai", provider_kind="openai_compat",
        base_url="https://api.openai.com", model_id="gpt-5.6-luna",
        cred_ref="cred",
    )
    route = SimpleNamespace(
        record=record, credential_id="cred", credential_fingerprint="a" * 64,
    )
    monkeypatch.setattr(module, "resolve_owner_model_authority", lambda *_a, **_k: route)
    monkeypatch.setattr(module, "resolve_prime_agent_binary", lambda: tmp_path / "prime")
    monkeypatch.setattr(
        module, "verify_prime_agent_installation",
        lambda _path: SimpleNamespace(version=(0, 7, 4)),
    )
    decrypts: list[str] = []
    monkeypatch.setattr(
        module, "load_credential",
        lambda ref: (decrypts.append(ref) or SimpleNamespace(reveal=lambda: "secret-key")),
    )

    def invoke(**kwargs):
        assert decrypts == []
        resolved = kwargs["credential_resolver"].resolve(kwargs["authorization"])
        assert resolved.secret.reveal() == "secret-key"
        return SimpleNamespace(receipt=SimpleNamespace(state=SimpleNamespace(value="succeeded")))

    monkeypatch.setattr(module, "invoke_prime_rpc_evidence", invoke)

    class Ledger:
        def receipt(self, _request_id):
            raise KeyError

    backend = MeteredPrimeTalkBackend(
        app=SimpleNamespace(), choice=SimpleNamespace(), owner_id="owner",
        operation_id="op", document_digest="b" * 64,
        resource_revalidator=lambda: True, ledger=Ledger(), cwd=tmp_path,
    )
    backend.run(PrimeAgentRequest("prompt", "deep", "request"))
    assert decrypts == ["cred"]


def test_deep_status_endpoint_is_owner_scoped_and_recovers_exact_response(
    monkeypatch, tmp_path,
) -> None:
    monkeypatch.setenv("ANTIEK_PRIME_LEDGER_DIR", str(tmp_path))
    journal = DeepTalkJournal(tmp_path / "deep-talk.sqlite3")
    journal.claim("owner-a", "deep-op", "a" * 64)
    stored = {
        "answer_id": None, "capture_status": "unavailable", "answer": "stored",
        "citations": [], "grounded": True, "context_chunk_count": 1, "mode": "deep",
    }
    journal.complete("owner-a", "deep-op", stored)
    app = FastAPI()

    @app.middleware("http")
    async def signed_owner(request: Request, call_next):
        request.state.auth_method = "antiek_session_cookie"
        request.state.user_id = request.headers.get("x-owner", "owner-a")
        return await call_next(request)

    register_book_routes(app)
    client = TestClient(app)
    recovered = client.get(
        "/books/deep-operations/deep-op", headers={"x-owner": "owner-a"},
    )
    assert recovered.status_code == 200
    assert recovered.json()["state"] == "completed"
    assert recovered.json()["response"]["answer"] == "stored"
    hidden = client.get(
        "/books/deep-operations/deep-op", headers={"x-owner": "owner-b"},
    )
    assert hidden.status_code == 404


@dataclass
class _PrimeSpy:
    calls: int = 0
    canonical_calls: int = 0
    transfer_db: str | None = None
    document_id: str | None = None
    decrypts: int = 0


def _signed_ask_app(monkeypatch, tmp_path: Path, db: str, spy: _PrimeSpy):
    import importlib

    import interfaces.research.api.books as books_module
    import interfaces.research.api.owner_byot_dispatch as owner_dispatch
    import interfaces.research.api.prime_talk as prime_module
    search_module = importlib.import_module("substrate.graph.search")

    monkeypatch.setenv("ANTIEK_PRIME_LEDGER_DIR", str(tmp_path / "private"))
    (tmp_path / "private").mkdir(mode=0o700)
    monkeypatch.setenv("ANTIEK_RLM_RATIFIED", "1")
    monkeypatch.setenv("ANTIEK_AUTH_SECRET", "signed-deep-test-" + "x" * 48)
    monkeypatch.setenv("ANTIEK_OPERATOR_EMAIL", "owner@example.test")
    monkeypatch.setenv("ANTIEK_COOKIE_INSECURE", "1")
    monkeypatch.delenv("ANTIEK_OPERATOR_TOKEN", raising=False)
    monkeypatch.setattr(books_module, "_resolve_db_path", lambda: db)
    monkeypatch.setattr(search_module, "SentenceTransformerEmbedding", lambda: StubEmbedding())

    def init(self, **kwargs):
        self.operation_id = kwargs["operation_id"]
        self.child_journal = None
        self.child_owner = self.child_parent_id = self.child_lease_token = None
        self.resource_authority_guard = kwargs.get("resource_authority_guard")

    def run(self, request):
        import hashlib

        from orchestration.rlm.prime_authority import PrimeAuthorizationRequest, PrimeCallState
        from orchestration.rlm.prime_rpc_evidence import PrimeRPCEvidence, PrimeRPCOutcome

        prompt_digest = hashlib.sha256(request.prompt.encode()).hexdigest()
        cached = None
        if self.child_journal is not None:
            cached = self.child_journal.claim_child(
                self.child_owner, self.child_parent_id, self.child_lease_token,
                "prime", 0, prompt_digest,
            )

        if spy.transfer_db is not None and spy.document_id is not None:
            from runtime.db_lock import connect_write
            con = connect_write(spy.transfer_db, purpose="transfer-race-test")
            con.execute(
                "UPDATE documents SET owner_user_id='owner-b' WHERE document_id=?",
                [spy.document_id],
            )
            con.close()
        if cached is None and self.resource_authority_guard is not None:
            with self.resource_authority_guard() as current:
                if not current:
                    raise RuntimeError("resource authority changed")
                spy.decrypts += 1
        if cached is None:
            spy.calls += 1
        now = 100
        auth = PrimeAuthorizationRequest(
            owner_id="owner-a", payer_id="owner-a", session_id=self.operation_id,
            request_id=self.operation_id, idempotency_key=self.operation_id,
            workflow="deep-talk-to-book", prompt_digest="a" * 64,
            provider="openai", credential_id="cred", credential_fingerprint="b" * 64,
            credential_env_name="OPENAI_API_KEY", model="gpt-5.6-luna",
            prime_version="0.7.4", max_cost_micro_usd=5_000_000,
            issued_at_ms=1, expires_at_ms=1000, nonce=self.operation_id,
        )
        receipt = SimpleNamespace(
            authorization=auth, state=PrimeCallState.SUCCEEDED,
            held_micro_usd=0, charged_micro_usd=10, input_tokens=1, output_tokens=1,
            cache_read_tokens=0, cache_write_tokens=0, observed_cost_micro_usd=10,
            stop_reason="stop", evidence_digest="c" * 64, output_digest="d" * 64,
            provider_request_id="provider-request", provider_event_id="provider-event",
            created_at_ms=now, updated_at_ms=now, started_at_ms=now,
            usage_observed_at_ms=now, terminal_at_ms=now,
        )
        outcome = PrimeRPCOutcome(
            PrimeRPCEvidence("paid supplemental", "openai", "gpt-5.6-luna", "0.7.4"),
            receipt, (),
        )
        if cached is None and self.child_journal is not None:
            self.child_journal.complete_child(
                self.child_owner, self.child_parent_id, self.child_lease_token,
                "prime", 0, prompt_digest,
                {"evidence": "paid supplemental", "state": "succeeded"},
            )
        return outcome

    monkeypatch.setattr(prime_module.MeteredPrimeTalkBackend, "__init__", init)
    monkeypatch.setattr(prime_module.MeteredPrimeTalkBackend, "run", run)

    def canonical_byot(**kwargs):
        spy.canonical_calls += 1
        result = DispatchResult(
            text="canonical", usage=NormalizedUsage(1, 1), cost_usd=0.01,
            latency_ms=1, provider="canonical", model="m", tier="deep",
            finish_reason="stop", fallback_chain_index=0, event_id=None,
        )
        return result, SimpleNamespace(digest=lambda: "canonical-authority")

    monkeypatch.setattr(owner_dispatch, "dispatch_talk_to_book_byot", canonical_byot)
    from interfaces.research.api.app import create_app
    from substrate.auth import mint_session_cookie

    app = create_app(register_wrestling=False, register_providers=False, cors_origins=[])
    client = TestClient(app)
    client.cookies.set(
        "ANTIEK_SESSION",
        mint_session_cookie(user_id="owner-a", email="owner@example.test"),
    )
    return client


def test_signed_deep_prime_post_concurrency_and_exact_replay(
    monkeypatch, tmp_path, db,
) -> None:
    _book_with_pages(db, "doc-post")
    from runtime.db_lock import connect_write
    con = connect_write(db, purpose="owner-test")
    con.execute("UPDATE documents SET owner_user_id='owner-a' WHERE document_id='doc-post'")
    con.close()
    register_fake("canonical")
    spy = _PrimeSpy()
    client = _signed_ask_app(monkeypatch, tmp_path, db, spy)
    payload = {
        "question": "compare", "mode": "deep", "operation_id": "canonical-op-post",
        "model_choice": {"authority": "user_model", "provider_id": "canonical", "model_id": "m"},
        "prime": {
            "enabled": True, "operation_id": "prime-op-post",
            "model_choice": {"authority": "user_model", "provider_id": "chosen", "model_id": "m"},
            "max_cost_micro_usd": 5_000_000,
        },
    }
    unsigned = TestClient(client.app)
    assert unsigned.post("/books/doc-post/ask", json=payload).status_code == 401
    unsigned.cookies.set("ANTIEK_SESSION", "forged-cookie")
    assert unsigned.post("/books/doc-post/ask", json=payload).status_code == 401
    with ThreadPoolExecutor(max_workers=2) as pool:
        responses = list(pool.map(
            lambda _: client.post("/books/doc-post/ask", json=payload), range(2),
        ))
    assert sorted(response.status_code for response in responses) in ([200, 200], [200, 409])
    winner = next(response for response in responses if response.status_code == 200)
    calls = (spy.canonical_calls, spy.calls)
    replay = client.post("/books/doc-post/ask", json=payload)
    assert replay.status_code == 200
    assert replay.content == winner.content
    assert (spy.canonical_calls, spy.calls) == calls
    assert calls == (2, 1)


def test_signed_deep_prime_distinct_operations_have_independent_sessions(
    monkeypatch, tmp_path, db,
) -> None:
    _book_with_pages(db, "doc-sequential")
    from runtime.db_lock import connect_write
    con = connect_write(db, purpose="owner-test")
    con.execute("UPDATE documents SET owner_user_id='owner-a' WHERE document_id='doc-sequential'")
    con.close()
    register_fake("canonical")
    spy = _PrimeSpy()
    client = _signed_ask_app(monkeypatch, tmp_path, db, spy)
    for operation in ("prime-seq-1", "prime-seq-2"):
        response = client.post("/books/doc-sequential/ask", json={
            "question": "compare", "mode": "deep", "operation_id": f"canonical-{operation}",
            "model_choice": {
                "authority": "user_model", "provider_id": "canonical", "model_id": "m",
            }, "prime": {
                "enabled": True, "operation_id": operation,
                "model_choice": {
                    "authority": "user_model", "provider_id": "chosen", "model_id": "m",
                }, "max_cost_micro_usd": 5_000_000,
            },
        })
        assert response.status_code == 200, response.text
        assert response.json()["prime_receipt"]["operation_id"] == operation
    assert spy.calls == 2


def test_signed_post_owner_transfer_at_handoff_refuses_before_decrypt_spawn(
    monkeypatch, tmp_path, db,
) -> None:
    _book_with_pages(db, "doc-transfer")
    from runtime.db_lock import connect_write
    con = connect_write(db, purpose="owner-test")
    con.execute("UPDATE documents SET owner_user_id='owner-a' WHERE document_id='doc-transfer'")
    con.close()
    register_fake("canonical")
    spy = _PrimeSpy(transfer_db=db, document_id="doc-transfer")
    client = _signed_ask_app(monkeypatch, tmp_path, db, spy)
    response = client.post("/books/doc-transfer/ask", json={
        "question": "compare", "mode": "deep", "operation_id": "canonical-transfer",
        "model_choice": {"authority": "user_model", "provider_id": "canonical", "model_id": "m"},
        "prime": {
            "enabled": True, "operation_id": "prime-transfer",
            "model_choice": {
                "authority": "user_model", "provider_id": "chosen", "model_id": "m",
            }, "max_cost_micro_usd": 5_000_000,
        },
    })
    assert response.status_code == 503
    assert spy.decrypts == 0
    assert spy.calls == 0


def test_signed_expired_resume_reuses_all_persisted_children_zero_calls(
    monkeypatch, tmp_path, db,
) -> None:
    import sqlite3

    from interfaces.research.api.deep_talk_journal import DeepTalkJournal
    from runtime.db_lock import connect_write

    _book_with_pages(db, "doc-resume")
    con = connect_write(db, purpose="owner-test")
    con.execute("UPDATE documents SET owner_user_id='owner-a' WHERE document_id='doc-resume'")
    con.close()
    register_fake("canonical")
    spy = _PrimeSpy()
    original_complete = DeepTalkJournal.complete
    crash_once = True

    def crash_after_children(self, *args, **kwargs):
        nonlocal crash_once
        if crash_once:
            crash_once = False
            raise RuntimeError("crash after paid children")
        return original_complete(self, *args, **kwargs)

    monkeypatch.setattr(DeepTalkJournal, "complete", crash_after_children)
    client = _signed_ask_app(monkeypatch, tmp_path, db, spy)
    payload = {
        "question": "compare", "mode": "deep", "operation_id": "canonical-resume",
        "model_choice": {"authority": "user_model", "provider_id": "canonical", "model_id": "m"},
        "prime": {
            "enabled": True, "operation_id": "prime-resume",
            "model_choice": {
                "authority": "user_model", "provider_id": "chosen", "model_id": "m",
            }, "max_cost_micro_usd": 5_000_000,
        },
    }
    with pytest.raises(RuntimeError, match="crash after paid children"):
        client.post("/books/doc-resume/ask", json=payload)
    before = (spy.canonical_calls, spy.calls)
    assert before == (2, 1)
    path = tmp_path / "private" / "deep-talk.sqlite3"
    with sqlite3.connect(path) as journal_db:
        journal_db.execute(
            "UPDATE deep_operations SET lease_expires_at_ms=0"
            " WHERE operation_id='canonical-resume'"
        )
    resumed = client.post("/books/doc-resume/ask", json=payload)
    assert resumed.status_code == 200, resumed.text
    assert (spy.canonical_calls, spy.calls) == before


def test_prime_reconcile_endpoint_requires_operator_and_settles_exact_usage(
    monkeypatch, tmp_path,
) -> None:
    from interfaces.research.api.prime_talk import prime_talk_ledger
    from orchestration.rlm.prime_authority import PrimeAuthorizationRequest

    private = tmp_path / "private"
    private.mkdir(mode=0o700)
    monkeypatch.setenv("ANTIEK_PRIME_LEDGER_DIR", str(private))
    monkeypatch.setenv("ANTIEK_AUTH_SECRET", "reconcile-test-" + "x" * 48)
    monkeypatch.setenv("ANTIEK_OPERATOR_EMAIL", "owner@example.test")
    monkeypatch.setenv("ANTIEK_OPERATOR_TOKEN", "operator-reconcile-token")
    monkeypatch.setenv("ANTIEK_OPERATOR_SERVICE_TOKEN_CLIENT_ID", "service-id")
    monkeypatch.setenv("ANTIEK_COOKIE_INSECURE", "1")
    ledger = prime_talk_ledger()
    authorization = PrimeAuthorizationRequest(
        owner_id="owner-a", payer_id="owner-a", session_id="reconcile-session",
        request_id="reconcile-op", idempotency_key="reconcile-op",
        workflow="deep-talk-to-book", prompt_digest="a" * 64,
        provider="openai", credential_id="cred", credential_fingerprint="b" * 64,
        credential_env_name="OPENAI_API_KEY", model="gpt-5.6-luna",
        prime_version="0.7.4", max_cost_micro_usd=5_000_000,
        issued_at_ms=1, expires_at_ms=1000, nonce="reconcile-nonce",
    )
    ledger.authorize(authorization, now_ms=100)
    ledger.mark_started("reconcile-op", now_ms=101)
    ledger.mark_unknown("reconcile-op", now_ms=102)
    from interfaces.research.api.app import create_app
    from substrate.auth import mint_session_cookie
    app = create_app(register_wrestling=False, register_providers=False, cors_origins=[])
    client = TestClient(app)
    client.cookies.set(
        "ANTIEK_SESSION", mint_session_cookie(user_id="owner-a", email="owner@example.test"),
    )
    body = {
        "owner_id": "owner-a", "resolution": "exact_usage", "evidence_digest": "e" * 64,
        "input_tokens": 10, "output_tokens": 2, "cost_micro_usd": 50,
        "observed_at_ms": 103, "provider_request_id": "provider-r",
        "provider_event_id": "provider-e",
    }
    denied = client.post("/books/prime-operations/reconcile-op/reconcile", json=body)
    assert denied.status_code == 403
    client.cookies.clear()
    forged = client.post(
        "/books/prime-operations/reconcile-op/reconcile",
        json={**body, "owner_id": "owner-b"},
        headers={"authorization": "Bearer operator-reconcile-token"},
    )
    assert forged.status_code == 404
    malformed = client.post(
        "/books/prime-operations/reconcile-op/reconcile",
        json={**body, "evidence_digest": "not-a-digest"},
        headers={"authorization": "Bearer operator-reconcile-token"},
    )
    assert malformed.status_code == 422
    accepted = client.post(
        "/books/prime-operations/reconcile-op/reconcile", json=body,
        headers={"authorization": "Bearer operator-reconcile-token"},
    )
    assert accepted.status_code == 200, accepted.text
    assert accepted.json()["state"] == "succeeded"
    assert accepted.json()["charged_micro_usd"] == 50

    second = replace(
        authorization, request_id="reconcile-no-charge",
        idempotency_key="reconcile-no-charge", nonce="reconcile-no-charge",
        session_id="reconcile-no-charge",
    )
    ledger.authorize(second, now_ms=100)
    ledger.mark_started(second.request_id, now_ms=101)
    ledger.mark_unknown(second.request_id, now_ms=102)
    service = client.post(
        "/books/prime-operations/reconcile-no-charge/reconcile",
        json={
            "owner_id": "owner-a", "resolution": "confirmed_no_charge",
            "evidence_digest": "f" * 64,
        },
        headers={"Cf-Access-Client-Id": "service-id"},
    )
    assert service.status_code == 200, service.text
    assert service.json()["state"] == "cancelled"
