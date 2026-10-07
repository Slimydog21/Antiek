"""Private graph, money journal, HTTP, event and provider joins for owned wrestling."""

from __future__ import annotations

import asyncio
import json
import threading
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path
from types import SimpleNamespace

import httpx
import pytest
from fastapi.testclient import TestClient
from starlette.websockets import WebSocketDisconnect

from interfaces.research.api import (
    EventBroadcaster,
    compute_capacity_gate,
    create_app,
    note_taking,
    owned_wrestling,
    owner_byot_dispatch,
    settings_models_admin,
)
from runtime.byok.store import store_credential_with_metadata
from runtime.db_lock import connect_write
from substrate.auth.magic_link import mint_session_cookie
from substrate.books.owned_wrestling_sources import (
    OwnedSourceUnavailable,
    current_book_material,
    write_immutable_artifact,
)
from substrate.byot_usage.ledger import ByotUsageLedger
from substrate.dispatch import canonical_http, register_provider, reset_provider_registry
from substrate.event_log import trajectory
from substrate.graph import ensure_initialized, insert_chunk, insert_document
from substrate.schemas import Event

BODY = "A private sentence with one unique book passage."
_RECORD_ID = settings_models_admin._owner_id_prefix("owner-a") + "fixture"
CHOICE = {"authority": "user_model", "provider_id": _RECORD_ID,
          "model_id": "deepseek-flash-nothink"}


class _Provider(settings_models_admin._UserOpenAICompatProvider):
    def __init__(self, record):
        super().__init__(record)
        self.calls: list[str] = []
        self.after_call = None

    def respond(self, request: httpx.Request) -> httpx.Response:
        self.calls.append(json.loads(request.content)["messages"][0]["content"])
        if self.after_call is not None:
            self.after_call()
        return httpx.Response(200, json={
            "id": "owned-fixture", "object": "chat.completion", "model": "deepseek-flash",
            "choices": [{"index": 0, "message": {"role": "assistant",
                "content": '{"rendered_text":"Private answer","claims":[]}'},
                "finish_reason": "stop"}],
            "usage": {"prompt_tokens": 8, "completion_tokens": 9, "total_tokens": 17},
        })


def _work(action_id: str = "action-a") -> dict:
    return {
        "action_id": action_id, "user_prompt": "What does the private passage say?",
        "target_token_count": 128, "total_budget_cents": 10_000,
        "canonical_model": CHOICE, "prime_model": CHOICE,
        "approve_canonical_source_processing": True,
        "approve_prime_source_processing": True,
        "approve_canonical_fallback_if_prime_unavailable": True,
    }


def _request_event(joined, action_id: str = "action-a") -> Event:
    job = joined.ledger.owned_wrestling_job("owner-a", action_id)
    assert job is not None
    return Event.model_validate(next(
        row for row in trajectory(job.investigation_id)
        if row["event_id"] == job.request_event_id
    ))


def _delivery_rows(joined, action_id: str = "action-a") -> list[dict]:
    job = joined.ledger.owned_wrestling_job("owner-a", action_id)
    assert job is not None
    return [row for row in trajectory(job.investigation_id)
            if row["action_type"] == "distillation.delivered"]


def _delivery_outbox_ack(joined, action_id: str = "action-a") -> str | None:
    import sqlite3

    with sqlite3.connect(joined.ledger._db_path) as con:
        row = con.execute(
            "SELECT published_at FROM byot_owned_wrestling_outbox"
            " WHERE owner_user_id='owner-a' AND action_id=? AND event_kind='delivered'",
            (action_id,),
        ).fetchone()
    return row[0] if row is not None else None


@pytest.fixture
def joined(tmp_path: Path, monkeypatch: pytest.MonkeyPatch, request):
    db = str(tmp_path / "graph.duckdb")
    journal = tmp_path / "money.sqlite3"
    monkeypatch.setenv("ANTIEK_DUCKDB_PATH", db)
    monkeypatch.setenv("ANTIEK_BYOT_USAGE_DB", str(journal))
    monkeypatch.setenv("ANTIEK_RESEARCH_EVENTS_DIR", str(tmp_path / "events"))
    monkeypatch.setenv("ANTIEK_EMBEDDING_PROVIDER", "hash")
    monkeypatch.setenv("ANTIEK_NOTE_TAKER_THRESHOLD", "1")
    for name in ("ANTIEK_OPERATOR_TOKEN", "ANTIEK_OPERATOR_EMAIL",
                 "ANTIEK_OPERATOR_SERVICE_TOKEN_CLIENT_ID"):
        monkeypatch.delenv(name, raising=False)
    ensure_initialized(db)
    with connect_write(db, purpose="test-owned-book") as con:
        insert_document(
            con, document_id="book-a", source_tier=4, document_type="book",
            raw_text=BODY, content_class="personal_reading", owner_user_id="owner-a",
            metadata={},
        )
        insert_chunk(con, document_id="book-a", chunk_index=0,
                     chunk_id="chunk-owned", text=BODY, token_count=9)
        con.execute("INSERT INTO book_assets(document_id) VALUES (?)", ["book-a"])

    monkeypatch.setenv("ANTIEK_USER_MODELS_PATH", str(tmp_path / "models.json"))
    monkeypatch.setenv("ANTIEK_BYOK_ARTIFACT", str(tmp_path / "credential.enc"))
    monkeypatch.setenv("ANTIEK_BYOK_KEY_FILE", str(tmp_path / "master.key"))
    metadata = store_credential_with_metadata(
        _RECORD_ID, "synthetic-owned-fixture-key", pipeline_kind="model_provider",
        owner_user_id="owner-a",
    )
    protocol = getattr(request, "param", "deepseek")
    model_id = ("deepseek-flash-nothink" if protocol == "deepseek"
                else "claude-haiku-4-5-20251001")
    record = settings_models_admin.UserModelRecord(
        id=_RECORD_ID, owner_user_id="owner-a",
        provider_kind="openai_compat" if protocol == "deepseek" else "anthropic",
        provider_catalog_id=protocol,
        model_id=model_id, display_name="Fixture model",
        base_url="https://api.deepseek.com" if protocol == "deepseek" else "https://api.anthropic.com",
        cred_ref=metadata.cred_id,
        cred_fingerprint=metadata.artifact_fingerprint,
    )
    with settings_models_admin._registry_guard(exclusive=True):
        settings_models_admin._write_registry_unlocked({record.id: record})
    fingerprint = settings_models_admin._record_fingerprint(record)
    real_auth = owner_byot_dispatch.authenticated_distinct_owner
    monkeypatch.setattr(owner_byot_dispatch, "authenticated_distinct_owner",
                        lambda request: request.headers["x-test-owner"])
    monkeypatch.setattr(owned_wrestling, "authenticated_distinct_owner",
                        lambda request: request.headers["x-test-owner"])
    reset_provider_registry()
    provider = (_Provider(record) if protocol == "deepseek"
                else settings_models_admin._make_provider(record))
    register_provider(provider)
    if protocol == "deepseek":
        monkeypatch.setattr(canonical_http, "_new_inner_transport",
                            lambda: httpx.MockTransport(provider.respond))
    note_calls: list[str] = []
    monkeypatch.setattr(note_taking, "dispatch", lambda prompt, role, **_kw: (
        note_calls.append(role) or SimpleNamespace(text='{"notes": []}')
    ))
    bus = EventBroadcaster()
    app = create_app(broadcaster=bus, cors_origins=[], wrestling_db_path=db,
                     register_providers=False)
    app.state.registered_providers = {record.id}
    app.state.user_model_registration_fingerprints = {record.id: fingerprint}
    yield SimpleNamespace(app=app, bus=bus, db=db, ledger=ByotUsageLedger(journal),
                          provider=provider, note_calls=note_calls, tmp_path=tmp_path,
                          real_auth=real_auth, protocol=protocol,
                          choice={**CHOICE, "model_id": model_id})
    reset_provider_registry()


@pytest.mark.asyncio
async def test_http_owner_replay_delivery_and_private_unfiltered_audience(joined):
    owner_a = SimpleNamespace()
    owner_b = SimpleNamespace()
    sub_a = await joined.bus.subscribe(owner_a, owner_user_id="owner-a")
    sub_b = await joined.bus.subscribe(owner_b, owner_user_id="owner-b")
    try:
        async with httpx.AsyncClient(transport=httpx.ASGITransport(app=joined.app),
                                     base_url="http://test") as client:
            first = await client.post("/books/book-a/wrestle", json=_work(),
                                      headers={"x-test-owner": "owner-a"})
            assert first.status_code == 202, first.text
            repeated = await client.post("/books/book-a/wrestle", json=_work(),
                                         headers={"x-test-owner": "owner-a"})
            assert repeated.status_code == 202, repeated.text
            assert repeated.json()["request_event_id"] == first.json()["request_event_id"]
            foreign = await client.get(
                f"/trajectory/{first.json()['investigation_id']}",
                headers={"x-test-owner": "owner-b"},
            )
            assert foreign.status_code == 404
            foreign_view = await client.get("/books/wrestle-actions/action-a",
                                            headers={"x-test-owner": "owner-b"})
            assert foreign_view.status_code == 404
            foreign_post = await client.post("/books/book-a/wrestle", json=_work("foreign"),
                                             headers={"x-test-owner": "owner-b"})
            assert foreign_post.status_code == 409
            changed_approval = await client.post(
                "/books/book-a/wrestle",
                json={**_work(), "approve_canonical_fallback_if_prime_unavailable": False},
                headers={"x-test-owner": "owner-a"},
            )
            assert changed_approval.status_code == 409
            own = await client.get(
                f"/trajectory/{first.json()['investigation_id']}",
                headers={"x-test-owner": "owner-a"},
            )
            assert own.status_code == 200
            assert len([row for row in own.json()["events"]
                        if row["action_type"] == "distillation.requested"]) == 1
            injected = await client.post("/events/typed", json={
                "investigation_id": first.json()["investigation_id"],
                "document_id": "book-a", "payload": {
                    "action_type": "distillation.requested", "user_prompt": "Unapproved",
                    "target_token_count": 5,
                },
            }, headers={"x-test-owner": "owner-b"})
            assert injected.status_code == 403

        await joined.bus.wait_for_handlers()
        job = joined.ledger.owned_wrestling_job("owner-a", "action-a")
        assert job is not None and job.state == "delivered"
        assert joined.ledger.action("owner-a", "action-a").state == "closed"
        rows = trajectory(job.investigation_id)
        assert len([row for row in rows if row["action_type"] == "distillation.delivered"]) == 1
        assert len(joined.provider.calls) == 1
        assert joined.note_calls == []
        assert note_taking._default_replay_service(db_path=joined.db).catch_up(
            job.investigation_id,
        ) == []
        assert joined.note_calls == []
        assert BODY in joined.provider.calls[0]
        assert sub_b.queue.empty()
        assert not sub_a.queue.empty()
        operation = joined.ledger.operation(
            "owner-a", owned_wrestling._stable_id("owcanon-", "owner-a", "action-a"),
        )
        assert operation is not None and operation.state == "settled"
        assert joined.ledger.owned_wrestling_job("owner-b", "foreign") is None
    finally:
        await joined.bus.unsubscribe(sub_a)
        await joined.bus.unsubscribe(sub_b)


@pytest.mark.asyncio
async def test_signed_cookie_http_owner_admission_and_foreign_refusal(joined, monkeypatch):
    monkeypatch.setattr(owner_byot_dispatch, "authenticated_distinct_owner", joined.real_auth)
    monkeypatch.setattr(owned_wrestling, "authenticated_distinct_owner", joined.real_auth)
    monkeypatch.setenv("ANTIEK_OPERATOR_EMAIL", "a@example.test,b@example.test")
    monkeypatch.setenv("ANTIEK_AUTH_SECRET", "fixture-secret-only")
    a_cookie = mint_session_cookie(user_id="owner-a", email="a@example.test")
    b_cookie = mint_session_cookie(user_id="owner-b", email="b@example.test")
    async with httpx.AsyncClient(transport=httpx.ASGITransport(app=joined.app),
                                 base_url="http://test") as client:
        client.cookies.set("ANTIEK_SESSION", a_cookie)
        accepted = await client.post("/books/book-a/wrestle", json=_work())
        assert accepted.status_code == 202, accepted.text
        await joined.bus.wait_for_handlers()
        investigation = accepted.json()["investigation_id"]
        assert len(_delivery_rows(joined)) == 1
        own = await client.get(f"/trajectory/{investigation}")
        assert own.status_code == 200
        client.cookies.set("ANTIEK_SESSION", b_cookie)
        assert (await client.get(f"/trajectory/{investigation}")).status_code == 404
        collection = await client.get("/trajectory")
        assert collection.status_code == 200
        assert all(row.get("investigation_id") != investigation
                   for row in collection.json()["events"])
        assert (await client.get("/books/wrestle-actions/action-a")).status_code == 404
        refused = await client.post("/books/book-a/wrestle", json=_work("foreign-cookie"))
        assert refused.status_code == 409
    assert joined.ledger.owned_wrestling_job("owner-b", "foreign-cookie") is None
    assert len(joined.provider.calls) == 1


@pytest.mark.asyncio
@pytest.mark.parametrize("mutation", ["taken_down", "body", "rights"])
async def test_real_rights_takedown_and_changed_source_refuse(joined, mutation):
    async with httpx.AsyncClient(transport=httpx.ASGITransport(app=joined.app),
                                 base_url="http://test") as client:
        with connect_write(joined.db, purpose="test-takedown") as con:
            con.execute("UPDATE book_assets SET taken_down=TRUE WHERE document_id='book-a'")
        denied = await client.post("/books/book-a/wrestle", json=_work("taken-down"),
                                   headers={"x-test-owner": "owner-a"})
        assert denied.status_code == 409
        assert joined.ledger.owned_wrestling_job("owner-a", "taken-down") is None
        with connect_write(joined.db, purpose="test-clear-takedown") as con:
            con.execute("UPDATE book_assets SET taken_down=FALSE WHERE document_id='book-a'")

        def mutate_after_provider():
            with connect_write(joined.db, purpose="test-mutate-during-provider") as con:
                if mutation == "taken_down":
                    con.execute("UPDATE book_assets SET taken_down=TRUE WHERE document_id='book-a'")
                elif mutation == "body":
                    con.execute("UPDATE documents SET raw_text=? WHERE document_id='book-a'",
                                ["A changed body without the admitted passage."])
                else:
                    con.execute("UPDATE documents SET metadata=? WHERE document_id='book-a'",
                                [json.dumps({
                                    "arxiv_id": "2401.00001",
                                    "license_uri": "https://arxiv.org/licenses/nonexclusive-distrib/1.0/",
                                })])

        joined.provider.after_call = mutate_after_provider
        accepted = await client.post("/books/book-a/wrestle", json=_work("source-change"),
                                     headers={"x-test-owner": "owner-a"})
        assert accepted.status_code == 202
        await joined.bus.wait_for_handlers()
        job = joined.ledger.owned_wrestling_job("owner-a", "source-change")
        assert job is not None and job.state == "unresolved"
        assert joined.ledger.operation(
            "owner-a", owned_wrestling._stable_id("owcanon-", "owner-a", "source-change"),
        ).state == "settled"
        assert all(row["action_type"] != "distillation.delivered"
                   for row in trajectory(job.investigation_id))


def test_guarded_rights_and_attribution_are_required_on_real_sql(joined):
    with pytest.raises(OwnedSourceUnavailable, match="owner"):
        current_book_material(joined.db, owner="owner-b", document_id="book-a")
    with connect_write(joined.db, purpose="test-rights-drift") as con:
        con.execute("UPDATE documents SET metadata=? WHERE document_id='book-a'", [json.dumps({
            "arxiv_id": "2401.00001",
            "license_uri": "https://arxiv.org/licenses/nonexclusive-distrib/1.0/",
        })])
    with pytest.raises(OwnedSourceUnavailable, match="rights"):
        current_book_material(joined.db, owner="owner-a", document_id="book-a")
    with connect_write(joined.db, purpose="test-missing-link") as con:
        con.execute("UPDATE documents SET metadata=? WHERE document_id='book-a'", [json.dumps({
            "license_uri": "https://creativecommons.org/licenses/by/4.0/",
        })])
    with pytest.raises(OwnedSourceUnavailable, match="rights"):
        current_book_material(joined.db, owner="owner-a", document_id="book-a")
    with connect_write(joined.db, purpose="test-valid-link") as con:
        con.execute("UPDATE documents SET metadata=? WHERE document_id='book-a'", [json.dumps({
            "arxiv_id": "2401.00001",
            "license_uri": "https://creativecommons.org/licenses/by/4.0/",
        })])
    material = current_book_material(joined.db, owner="owner-a", document_id="book-a")
    assert material["rights_tier"] == "T1"
    assert material["canonical_url"] == "https://arxiv.org/abs/2401.00001"


def test_atomic_private_artifact_losers_compare_completed_bytes(tmp_path: Path):
    directory = tmp_path / "private"
    value = {"body": BODY}
    with ThreadPoolExecutor(max_workers=8) as pool:
        digests = list(pool.map(
            lambda _: write_immutable_artifact(directory, "source-identical", value),
            range(16),
        ))
    assert len(set(digests)) == 1
    assert (directory / "source-identical.json").read_bytes().endswith(b"}")
    (directory / ".source-interrupted-dead.tmp").write_bytes(b"partial")
    assert write_immutable_artifact(directory, "source-interrupted", value) == digests[0]
    with pytest.raises(OwnedSourceUnavailable, match="differs"):
        write_immutable_artifact(directory, "source-identical", {"body": "different"})


@pytest.mark.asyncio
async def test_concurrent_duplicate_observes_one_elected_provider_send(joined):
    entered = threading.Event()
    release = threading.Event()

    def hold_provider():
        entered.set()
        assert release.wait(10)

    joined.provider.after_call = hold_provider
    try:
        async with httpx.AsyncClient(transport=httpx.ASGITransport(app=joined.app),
                                     base_url="http://test") as client:
            accepted = await client.post("/books/book-a/wrestle", json=_work(),
                                         headers={"x-test-owner": "owner-a"})
        assert accepted.status_code == 202
        assert await asyncio.to_thread(entered.wait, 10)
        job = joined.ledger.owned_wrestling_job("owner-a", "action-a")
        request_row = next(row for row in trajectory(job.investigation_id)
                           if row["event_id"] == job.request_event_id)
        await owned_wrestling.consume(Event.model_validate(request_row),
                                     broadcaster=joined.bus, db_path=joined.db)
        assert joined.ledger.owned_wrestling_job("owner-a", "action-a").state == "running"
    finally:
        release.set()
    await joined.bus.wait_for_handlers()
    assert len(joined.provider.calls) == 1
    assert joined.ledger.owned_wrestling_job("owner-a", "action-a").state == "delivered"


@pytest.mark.asyncio
@pytest.mark.parametrize("failure", ["settlement", "dispatch_event"])
async def test_verified_result_recovery_after_journal_or_event_interruption(
    joined, monkeypatch, failure,
):
    if failure == "settlement":
        original = ByotUsageLedger.settle_action_attempt
        def interrupted(*args, **kwargs):
            raise RuntimeError("fixture interrupted settlement")
        monkeypatch.setattr(ByotUsageLedger, "settle_action_attempt", interrupted)
    else:
        original = owner_byot_dispatch.emit_typed
        def interrupted(*args, **kwargs):
            raise RuntimeError("fixture interrupted dispatch event publication")
        monkeypatch.setattr(owner_byot_dispatch, "emit_typed", interrupted)
    async with httpx.AsyncClient(transport=httpx.ASGITransport(app=joined.app),
                                 base_url="http://test") as client:
        accepted = await client.post("/books/book-a/wrestle", json=_work(),
                                     headers={"x-test-owner": "owner-a"})
    assert accepted.status_code == 202
    await joined.bus.wait_for_handlers()
    job = joined.ledger.owned_wrestling_job("owner-a", "action-a")
    assert job is not None and job.state == "running"
    operation_id = owned_wrestling._stable_id("owcanon-", "owner-a", "action-a")
    operation = joined.ledger.operation("owner-a", operation_id)
    assert operation is not None
    assert operation.state == ("settlement_pending" if failure == "settlement" else "settled")
    assert len(joined.provider.calls) == 1 and _delivery_rows(joined) == []
    if failure == "settlement":
        monkeypatch.setattr(ByotUsageLedger, "settle_action_attempt", original)
    else:
        monkeypatch.setattr(owner_byot_dispatch, "emit_typed", original)
    await owned_wrestling.consume(_request_event(joined),
                                 broadcaster=joined.bus, db_path=joined.db)
    assert joined.ledger.owned_wrestling_job("owner-a", "action-a").state == "delivered"
    settled = joined.ledger.operation("owner-a", operation_id)
    assert settled is not None and settled.state == "settled"
    assert len(joined.provider.calls) == 1 and len(_delivery_rows(joined)) == 1
    rows = trajectory(job.investigation_id)
    assert len([row for row in rows if row["action_type"] == "dispatch.call"]) == 1
    assert joined.ledger.action("owner-a", "action-a").state == "closed"


@pytest.mark.asyncio
@pytest.mark.parametrize("joined", ["deepseek", "anthropic"], indirect=True)
@pytest.mark.parametrize("field", ["rendered_text", "claim_text"])
@pytest.mark.parametrize("fenced", [False, True])
async def test_escaped_credential_never_reaches_owned_artifact_or_delivery(
    joined, monkeypatch, field, fenced,
):
    secret = "synthetic-owned-fixture-key"
    escaped = "".join(f"\\u{ord(char):04x}" for char in secret)
    text = ('{"rendered_text":"' + escaped + '","claims":[]}' if field == "rendered_text"
            else '{"rendered_text":"Safe answer","claims":[{"text":"' + escaped
                 + '","confidence":"high"}]}')
    if fenced:
        text = "Answer follows. ```json\n" + text + "\n```"
    sends = []

    def reflect(request):
        sends.append(request)
        if joined.protocol == "deepseek":
            payload = {"id": "escaped-fixture", "object": "chat.completion",
                "model": "deepseek-flash", "choices": [{"index": 0,
                "message": {"role": "assistant", "content": text}, "finish_reason": "stop"}],
                "usage": {"prompt_tokens": 8, "completion_tokens": 9, "total_tokens": 17}}
        else:
            payload = {"id": "escaped-fixture", "type": "message", "role": "assistant",
                "model": joined.choice["model_id"], "content": [{"type": "text", "text": text}],
                "stop_reason": "end_turn", "usage": {"input_tokens": 8, "output_tokens": 9}}
        return httpx.Response(200, json=payload)

    monkeypatch.setattr(canonical_http, "_new_inner_transport",
                        lambda: httpx.MockTransport(reflect))
    work = {**_work(), "canonical_model": joined.choice, "prime_model": joined.choice}
    async with httpx.AsyncClient(transport=httpx.ASGITransport(app=joined.app),
                                 base_url="http://test") as client:
        accepted = await client.post("/books/book-a/wrestle", json=work,
                                     headers={"x-test-owner": "owner-a"})
    assert accepted.status_code == 202
    await joined.bus.wait_for_handlers()
    job = joined.ledger.owned_wrestling_job("owner-a", "action-a")
    assert job is not None and job.state == "unresolved"
    operation = joined.ledger.operation(
        "owner-a", owned_wrestling._stable_id("owcanon-", "owner-a", "action-a"),
    )
    assert operation is not None and operation.state == "unknown"
    assert operation.result_text is None and operation.actual_cents is None
    assert len(sends) == 1 and _delivery_rows(joined) == []
    assert secret not in json.dumps(trajectory(job.investigation_id))
    assert not list(joined.tmp_path.rglob("result-*"))
    await owned_wrestling.consume(_request_event(joined),
                                 broadcaster=joined.bus, db_path=joined.db)
    assert len(sends) == 1 and _delivery_rows(joined) == []


@pytest.mark.asyncio
@pytest.mark.parametrize("read_phase", ["initial", "after_append"])
async def test_dispatch_event_read_interruption_recovers_one_settled_answer(
    joined, monkeypatch, read_phase,
):
    original = owner_byot_dispatch.iter_physical_events
    reads = 0

    def interrupted(investigation_id):
        nonlocal reads
        reads += 1
        if reads == (1 if read_phase == "initial" else 2):
            raise TimeoutError("fixture event lock timeout")
        return original(investigation_id)

    monkeypatch.setattr(owner_byot_dispatch, "iter_physical_events", interrupted)
    async with httpx.AsyncClient(transport=httpx.ASGITransport(app=joined.app),
                                 base_url="http://test") as client:
        accepted = await client.post("/books/book-a/wrestle", json=_work(),
                                     headers={"x-test-owner": "owner-a"})
    assert accepted.status_code == 202
    await joined.bus.wait_for_handlers()
    job = joined.ledger.owned_wrestling_job("owner-a", "action-a")
    assert job is not None and job.state == "running"
    operation_id = owned_wrestling._stable_id("owcanon-", "owner-a", "action-a")
    settled = joined.ledger.operation("owner-a", operation_id)
    assert settled is not None and settled.state == "settled"
    assert len(joined.provider.calls) == 1 and _delivery_rows(joined) == []
    monkeypatch.setattr(owner_byot_dispatch, "iter_physical_events", original)
    await owned_wrestling.consume(_request_event(joined),
                                 broadcaster=joined.bus, db_path=joined.db)
    assert joined.ledger.owned_wrestling_job("owner-a", "action-a").state == "delivered"
    assert joined.ledger.operation("owner-a", operation_id) == settled
    assert len(joined.provider.calls) == 1 and len(_delivery_rows(joined)) == 1
    assert len([row for row in trajectory(job.investigation_id)
                if row["action_type"] == "dispatch.call"]) == 1


@pytest.mark.asyncio
async def test_conflicting_dispatch_event_is_not_treated_as_transient_read(joined, monkeypatch):
    original = owner_byot_dispatch.iter_physical_events

    def conflicting(investigation_id):
        rows = list(original(investigation_id))
        for row in rows:
            if row["action_type"] == "dispatch.call":
                row = json.loads(json.dumps(row))
                row["payload"]["model"] = "different-model"
            yield row

    monkeypatch.setattr(owner_byot_dispatch, "iter_physical_events", conflicting)
    async with httpx.AsyncClient(transport=httpx.ASGITransport(app=joined.app),
                                 base_url="http://test") as client:
        accepted = await client.post("/books/book-a/wrestle", json=_work(),
                                     headers={"x-test-owner": "owner-a"})
    assert accepted.status_code == 202
    await joined.bus.wait_for_handlers()
    job = joined.ledger.owned_wrestling_job("owner-a", "action-a")
    assert job is not None and job.state == "unresolved"
    operation = joined.ledger.operation(
        "owner-a", owned_wrestling._stable_id("owcanon-", "owner-a", "action-a"),
    )
    assert operation is not None and operation.state == "settled"
    assert len(joined.provider.calls) == 1 and _delivery_rows(joined) == []
    monkeypatch.setattr(owner_byot_dispatch, "iter_physical_events", original)
    await owned_wrestling.consume(_request_event(joined),
                                 broadcaster=joined.bus, db_path=joined.db)
    assert len(joined.provider.calls) == 1 and _delivery_rows(joined) == []


@pytest.mark.asyncio
async def test_settled_result_survives_interruption_before_ready(joined, monkeypatch):
    original_write = owned_wrestling.write_immutable_artifact
    interrupted = False

    def fail_result_publication(directory, name, value):
        nonlocal interrupted
        if name.startswith("result-") and not interrupted:
            interrupted = True
            raise RuntimeError("lost worker after canonical settlement")
        return original_write(directory, name, value)

    monkeypatch.setattr(owned_wrestling, "write_immutable_artifact", fail_result_publication)
    async with httpx.AsyncClient(transport=httpx.ASGITransport(app=joined.app),
                                 base_url="http://test") as client:
        accepted = await client.post("/books/book-a/wrestle", json=_work(),
                                     headers={"x-test-owner": "owner-a"})
    assert accepted.status_code == 202
    await joined.bus.wait_for_handlers()
    job = joined.ledger.owned_wrestling_job("owner-a", "action-a")
    assert interrupted and job.state == "running"
    operation = joined.ledger.operation(
        "owner-a", owned_wrestling._stable_id("owcanon-", "owner-a", "action-a"),
    )
    assert operation is not None and operation.state == "settled"
    before = trajectory(job.investigation_id)
    original_pack = next(row for row in before if row["action_type"] == "context_pack.assembled")
    original_dispatch = next(row for row in before if row["action_type"] == "dispatch.call")
    assert original_dispatch["payload"]["context_pack_event_id"] == original_pack["event_id"]
    monkeypatch.setattr(owned_wrestling, "write_immutable_artifact", original_write)

    await owned_wrestling.consume(_request_event(joined),
                                 broadcaster=joined.bus, db_path=joined.db)
    await joined.bus.wait_for_handlers()
    finished = joined.ledger.owned_wrestling_job("owner-a", "action-a")
    assert finished.state == "delivered"
    assert joined.ledger.action("owner-a", "action-a").state == "closed"
    assert len(joined.provider.calls) == 1
    after = trajectory(job.investigation_id)
    assert [row["event_id"] for row in after
            if row["action_type"] == "context_pack.assembled"] == [original_pack["event_id"]]
    assert len(_delivery_rows(joined)) == 1


@pytest.mark.asyncio
async def test_settled_duplicate_does_not_displace_live_completion(joined, monkeypatch):
    entered = threading.Event()
    release = threading.Event()
    original_send = owned_wrestling.dispatch_talk_to_book_byot
    first_return = True
    lock = threading.Lock()

    def pause_first_settled_return(**kwargs):
        nonlocal first_return
        result = original_send(**kwargs)
        with lock:
            should_pause = first_return
            first_return = False
        if should_pause:
            entered.set()
            assert release.wait(10)
        return result

    monkeypatch.setattr(owned_wrestling, "dispatch_talk_to_book_byot", pause_first_settled_return)
    try:
        async with httpx.AsyncClient(transport=httpx.ASGITransport(app=joined.app),
                                     base_url="http://test") as client:
            accepted = await client.post("/books/book-a/wrestle", json=_work(),
                                         headers={"x-test-owner": "owner-a"})
        assert accepted.status_code == 202
        assert await asyncio.to_thread(entered.wait, 10)
        job = joined.ledger.owned_wrestling_job("owner-a", "action-a")
        original_token = job.execution_token
        original_pack = next(row for row in trajectory(job.investigation_id)
                             if row["action_type"] == "context_pack.assembled")
        duplicate = asyncio.create_task(owned_wrestling.consume(
            _request_event(joined), broadcaster=joined.bus, db_path=joined.db,
        ))
        await asyncio.wait_for(duplicate, 5)
        assert joined.ledger.owned_wrestling_job("owner-a", "action-a").execution_token == original_token
    finally:
        release.set()
    await joined.bus.wait_for_handlers()
    assert len(joined.provider.calls) == 1
    assert joined.ledger.owned_wrestling_job("owner-a", "action-a").state == "delivered"
    assert joined.ledger.action("owner-a", "action-a").state == "closed"
    rows = trajectory(job.investigation_id)
    assert [row["event_id"] for row in rows
            if row["action_type"] == "context_pack.assembled"] == [original_pack["event_id"]]
    assert len(_delivery_rows(joined)) == 1


@pytest.mark.asyncio
async def test_cancel_during_provider_retains_charge_without_delivery(joined):
    entered = threading.Event()
    release = threading.Event()
    owner = await joined.bus.subscribe(SimpleNamespace(), owner_user_id="owner-a")

    def hold_provider():
        entered.set()
        assert release.wait(10)

    joined.provider.after_call = hold_provider
    try:
        async with httpx.AsyncClient(transport=httpx.ASGITransport(app=joined.app),
                                     base_url="http://test") as client:
            accepted = await client.post("/books/book-a/wrestle", json=_work(),
                                         headers={"x-test-owner": "owner-a"})
            assert accepted.status_code == 202
            assert await asyncio.to_thread(entered.wait, 10)
            epoch = joined.ledger.action("owner-a", "action-a").epoch
            cancelled = await client.post(
                "/books/wrestle-actions/action-a/cancel",
                json={"expected_epoch": epoch}, headers={"x-test-owner": "owner-a"},
            )
            assert cancelled.status_code == 200, cancelled.text
    finally:
        release.set()
    await joined.bus.wait_for_handlers()
    operation = joined.ledger.operation(
        "owner-a", owned_wrestling._stable_id("owcanon-", "owner-a", "action-a"),
    )
    assert operation is not None and operation.state == "settled"
    assert len(joined.provider.calls) == 1
    assert _delivery_rows(joined) == []
    assert _delivery_outbox_ack(joined) is None
    assert all((event.action_type.value if hasattr(event.action_type, "value") else event.action_type)
               != "distillation.delivered" for event in tuple(owner.queue._queue))
    await owned_wrestling.consume(_request_event(joined),
                                 broadcaster=joined.bus, db_path=joined.db)
    assert _delivery_rows(joined) == []
    assert len(joined.provider.calls) == 1
    await joined.bus.unsubscribe(owner)


@pytest.mark.asyncio
async def test_cancel_after_ready_before_first_publication_has_no_delivery(joined, monkeypatch):
    entered = asyncio.Event()
    release = asyncio.Event()
    owner = await joined.bus.subscribe(SimpleNamespace(), owner_user_id="owner-a")
    original_publish = owned_wrestling._publish
    first_delivery = True

    async def pause_before_real_publication(job, payload, *, kind, **kwargs):
        nonlocal first_delivery
        if kind == "delivered" and first_delivery:
            first_delivery = False
            entered.set()
            await release.wait()
        return await original_publish(job, payload, kind=kind, **kwargs)

    monkeypatch.setattr(owned_wrestling, "_publish", pause_before_real_publication)
    try:
        async with httpx.AsyncClient(transport=httpx.ASGITransport(app=joined.app),
                                     base_url="http://test") as client:
            accepted = await client.post("/books/book-a/wrestle", json=_work(),
                                         headers={"x-test-owner": "owner-a"})
            assert accepted.status_code == 202
            await asyncio.wait_for(entered.wait(), 10)
            assert joined.ledger.owned_wrestling_job("owner-a", "action-a").state == "ready"
            assert _delivery_rows(joined) == []
            epoch = joined.ledger.action("owner-a", "action-a").epoch
            cancelled = await client.post(
                "/books/wrestle-actions/action-a/cancel",
                json={"expected_epoch": epoch}, headers={"x-test-owner": "owner-a"},
            )
            assert cancelled.status_code == 200, cancelled.text
    finally:
        release.set()
    await joined.bus.wait_for_handlers()
    operation = joined.ledger.operation(
        "owner-a", owned_wrestling._stable_id("owcanon-", "owner-a", "action-a"),
    )
    assert operation is not None and operation.state == "settled"
    assert len(joined.provider.calls) == 1
    assert _delivery_rows(joined) == []
    assert _delivery_outbox_ack(joined) is None
    assert all((event.action_type.value if hasattr(event.action_type, "value") else event.action_type)
               != "distillation.delivered" for event in tuple(owner.queue._queue))
    await owned_wrestling.consume(_request_event(joined),
                                 broadcaster=joined.bus, db_path=joined.db)
    assert _delivery_rows(joined) == []
    assert len(joined.provider.calls) == 1
    await joined.bus.unsubscribe(owner)


@pytest.mark.asyncio
async def test_ordinary_investigation_issuer_refuses_owned_and_unbound_reserved_ids(
    joined, monkeypatch,
):
    async with httpx.AsyncClient(transport=httpx.ASGITransport(app=joined.app),
                                 base_url="http://test") as client:
        accepted = await client.post("/books/book-a/wrestle", json=_work(),
                                     headers={"x-test-owner": "owner-a"})
        assert accepted.status_code == 202
        await joined.bus.wait_for_handlers()
        job = joined.ledger.owned_wrestling_job("owner-a", "action-a")
        before = trajectory(job.investigation_id)
        before_state = job.state
        joined.bus.unregister_all_handlers()
        observed: list[str] = []

        async def ordinary_start_observer(event):
            observed.append(event.investigation_id)

        joined.bus.register_handler("investigation.start_requested", ordinary_start_observer)
        original_meter = compute_capacity_gate.commit_start_acu
        metered: list[str] = []

        def record_real_meter(request, *, investigation_id, reason):
            metered.append(investigation_id)
            return original_meter(request, investigation_id=investigation_id, reason=reason)

        monkeypatch.setattr(compute_capacity_gate, "commit_start_acu", record_real_meter)
        for investigation_id in (job.investigation_id, "ownw-unbound-from-client"):
            response = await client.post("/investigations", json={
                "investigation_id": investigation_id,
                "question": "Can this ordinary issuer enter reserved work?",
                "context": "This text is outside the owned approval.",
            }, headers={"x-test-owner": "owner-a"})
            assert response.status_code in {403, 404, 409, 422}, response.text
            await joined.bus.wait_for_handlers()
            assert metered == []
            assert observed == []
            assert trajectory(job.investigation_id) == before
            assert trajectory("ownw-unbound-from-client") == []
            assert joined.ledger.owned_wrestling_job("owner-a", "action-a").state == before_state

        ordinary = await client.post("/investigations", json={
            "investigation_id": "inv-ordinary-control",
            "question": "Does the ordinary unbound issuer still work?",
        }, headers={"x-test-owner": "owner-a"})
        assert ordinary.status_code == 202, ordinary.text
        await joined.bus.wait_for_handlers()
        assert metered == ["inv-ordinary-control"]
        assert observed == ["inv-ordinary-control"]
        assert len([row for row in trajectory("inv-ordinary-control")
                    if row["action_type"] == "investigation.start_requested"]) == 1


@pytest.mark.asyncio
async def test_publication_interruption_recovers_ready_and_closes_action(joined, monkeypatch):
    broadcast = joined.bus.broadcast
    interrupted = False

    async def interrupt_delivered(event):
        nonlocal interrupted
        action = event.action_type.value if hasattr(event.action_type, "value") else event.action_type
        if action == "distillation.delivered" and not interrupted:
            interrupted = True
            raise RuntimeError("lost process after durable delivery append")
        await broadcast(event)

    monkeypatch.setattr(joined.bus, "broadcast", interrupt_delivered)
    async with httpx.AsyncClient(transport=httpx.ASGITransport(app=joined.app),
                                 base_url="http://test") as client:
        accepted = await client.post("/books/book-a/wrestle", json=_work(),
                                     headers={"x-test-owner": "owner-a"})
    assert accepted.status_code == 202
    await joined.bus.wait_for_handlers()
    job = joined.ledger.owned_wrestling_job("owner-a", "action-a")
    assert interrupted and job.state == "ready"
    assert joined.ledger.action("owner-a", "action-a").state == "open"
    request_row = next(row for row in trajectory(job.investigation_id)
                       if row["event_id"] == job.request_event_id)
    await owned_wrestling.consume(Event.model_validate(request_row),
                                 broadcaster=joined.bus, db_path=joined.db)
    finished = joined.ledger.owned_wrestling_job("owner-a", "action-a")
    assert finished.state == "delivered"
    assert joined.ledger.action("owner-a", "action-a").state == "closed"
    assert len(joined.provider.calls) == 1
    assert len([row for row in trajectory(job.investigation_id)
                if row["action_type"] == "distillation.delivered"]) == 1
    await owned_wrestling.consume(_request_event(joined),
                                 broadcaster=joined.bus, db_path=joined.db)
    assert len(_delivery_rows(joined)) == 1
    assert len(joined.provider.calls) == 1


@pytest.mark.asyncio
async def test_request_emit_then_broadcast_crash_replays_one_action(joined, monkeypatch):
    broadcast = joined.bus.broadcast
    failed = False

    async def interrupt_request(event):
        nonlocal failed
        action = event.action_type.value if hasattr(event.action_type, "value") else event.action_type
        if action == "distillation.requested" and not failed:
            failed = True
            raise RuntimeError("lost response after durable request append")
        await broadcast(event)

    monkeypatch.setattr(joined.bus, "broadcast", interrupt_request)
    async with httpx.AsyncClient(transport=httpx.ASGITransport(app=joined.app),
                                 base_url="http://test") as client:
        with pytest.raises(RuntimeError, match="lost response"):
            await client.post("/books/book-a/wrestle", json=_work(),
                              headers={"x-test-owner": "owner-a"})
        replay = await client.post("/books/book-a/wrestle", json=_work(),
                                   headers={"x-test-owner": "owner-a"})
    assert replay.status_code == 202
    await joined.bus.wait_for_handlers()
    job = joined.ledger.owned_wrestling_job("owner-a", "action-a")
    assert job.state == "delivered"
    assert len(joined.provider.calls) == 1
    assert len([row for row in trajectory(job.investigation_id)
                if row["event_id"] == job.request_event_id]) == 1


@pytest.mark.asyncio
async def test_verified_cookie_owner_gates_filtered_and_unfiltered_websockets(joined, monkeypatch):
    async with httpx.AsyncClient(transport=httpx.ASGITransport(app=joined.app),
                                 base_url="http://test") as client:
        accepted = await client.post("/books/book-a/wrestle", json=_work(),
                                     headers={"x-test-owner": "owner-a"})
    assert accepted.status_code == 202
    await joined.bus.wait_for_handlers()
    job = joined.ledger.owned_wrestling_job("owner-a", "action-a")
    delivered = Event.model_validate(next(
        row for row in trajectory(job.investigation_id)
        if row["event_id"] == job.delivered_event_id
    ))
    monkeypatch.setattr(owner_byot_dispatch, "authenticated_distinct_owner", joined.real_auth)
    monkeypatch.setenv("ANTIEK_OPERATOR_EMAIL", "a@example.test,b@example.test")
    monkeypatch.setenv("ANTIEK_AUTH_SECRET", "fixture-secret-only")
    a_cookie = mint_session_cookie(user_id="owner-a", email="a@example.test")
    b_cookie = mint_session_cookie(user_id="owner-b", email="b@example.test")
    with TestClient(joined.app) as client:
        client.cookies.set("ANTIEK_SESSION", b_cookie)
        with (
            pytest.raises(WebSocketDisconnect) as refused,
            client.websocket_connect(f"/ws/events?investigation_id={job.investigation_id}"),
        ):
            pass
        assert refused.value.code == 1008
        client.cookies.set("ANTIEK_SESSION", a_cookie)
        with client.websocket_connect("/ws/events") as owner_socket:
            client.cookies.set("ANTIEK_SESSION", b_cookie)
            with client.websocket_connect("/ws/events"):
                client.portal.call(joined.bus.broadcast, delivered)
                assert owner_socket.receive_json()["event_id"] == job.delivered_event_id
                foreign = next(sub for sub in joined.bus._subscribers
                               if sub.owner_user_id == "owner-b")
                assert foreign.queue.empty()
