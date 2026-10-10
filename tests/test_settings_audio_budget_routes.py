"""Real private account/audio-vault/local-ledger controls; no provider sends."""

from __future__ import annotations

import asyncio
import sqlite3
import threading
from pathlib import Path

import httpx
import pytest
from fastapi import Request
from fastapi.testclient import TestClient

from interfaces.research.api.app import create_app
from runtime.byok import store
from substrate.auth import mint_session_cookie
from substrate.byot_usage.actions import MAX_MONEY
from substrate.byot_usage.ledger import ByotUsageLedger, KeyUsageRow
from tests.test_settings_audio_model_routes import (
    ALICE,
    BOB,
    OPERATOR,
    PREFIX,
    SECRET,
    PrivateAPI,
    binding,
    create,
    sign_in,
)
from tests.test_settings_audio_model_routes import (
    api as api,
)


@pytest.fixture
def budget_api(api: PrivateAPI, monkeypatch: pytest.MonkeyPatch) -> PrivateAPI:
    monkeypatch.setenv("ANTIEK_BYOT_USAGE_DB", str(api.root / "audio-usage.sqlite3"))
    return api


def url(record: str) -> str:
    return PREFIX + "/user/" + record + "/budget"


def usage_path(api: PrivateAPI) -> Path:
    return api.root / "audio-usage.sqlite3"


def subject(client: TestClient) -> str:
    owner = str(client.get("/auth/me").json()["user_id"])
    assert owner.startswith("acct_") and len(owner) == 37
    return owner


def checked(response: httpx.Response, status: int = 200) -> dict[str, object]:
    assert response.status_code == status
    assert response.headers["Cache-Control"] == "private, no-store"
    assert SECRET not in response.text
    data: dict[str, object] = response.json()
    return data


@pytest.mark.parametrize("cap", [0, 1, 250, MAX_MONEY])
def test_genuine_account_exact_cap_persists_and_other_account_cannot_read(
    budget_api: PrivateAPI, cap: int
) -> None:
    alice, bob = sign_in(budget_api), sign_in(budget_api, BOB)
    record = create(alice)
    assert checked(alice.get(url(record))) == {
        "id": record,
        "currency": "USD",
        "basis": "local_byot_usage_ledger",
        "approved": False,
        "limit_cents": None,
        "used_cents": 0,
        "held_cents": 0,
        "available_cents": None,
    }
    response = checked(alice.put(url(record), json={"limit_cents": cap}))
    assert response["approved"] is True and response["limit_cents"] == cap
    assert response["available_cents"] == cap
    assert checked(alice.get(url(record))) == response
    ledger = ByotUsageLedger(usage_path(budget_api))
    usage = ledger.key_usage(record, subject(alice))
    assert usage is not None and usage.limit_cents == cap
    assert ledger.key_usage(record, subject(bob)) is None
    foreign = checked(bob.get(url(record)), 404)
    missing = checked(bob.get(url("missing")), 404)
    assert foreign == missing


@pytest.mark.parametrize("method", ["GET", "PUT"])
@pytest.mark.parametrize("actor", ["anonymous", "operator", "bearer", "legacy", "forged-subject"])
def test_unauthorized_actor_refused_before_body_vault_and_ledger(
    budget_api: PrivateAPI, monkeypatch: pytest.MonkeyPatch, actor: str, method: str
) -> None:
    import interfaces.research.api.settings_audio_model_routes as routes

    client = sign_in(budget_api, OPERATOR) if actor == "operator" else TestClient(budget_api.app)
    if actor == "bearer":
        monkeypatch.setenv("ANTIEK_OPERATOR_TOKEN", "UNIT-audio-budget-machine-token")
        client = TestClient(create_app(register_wrestling=False, register_providers=False))
        client.headers["Authorization"] = "Bearer UNIT-audio-budget-machine-token"
    elif actor in {"legacy", "forged-subject"}:
        identity = "__operator__" if actor == "legacy" else "acct_" + "f" * 32
        client.cookies.set("ANTIEK_SESSION", mint_session_cookie(user_id=identity, email=ALICE))

    def forbidden(*_args: object, **_kwargs: object) -> None:
        raise AssertionError("refusal must precede private work")

    async def forbidden_body(_request: Request) -> dict[str, object]:
        raise AssertionError("refusal must precede decoding")

    monkeypatch.setattr(store, "prepare_current_master_key", forbidden)
    monkeypatch.setattr(ByotUsageLedger, "__init__", forbidden)
    monkeypatch.setattr(routes, "_body", forbidden_body)
    checked(client.request(method, url("missing"), content=SECRET), 401)
    assert not usage_path(budget_api).exists()
    assert budget_api.artifact.read_text() == "{}"
    assert binding(budget_api)._service is None


@pytest.mark.parametrize("method", ["GET", "PUT"])
def test_foreign_and_missing_records_refuse_before_ledger_creation(
    budget_api: PrivateAPI, method: str
) -> None:
    alice, bob = sign_in(budget_api), sign_in(budget_api, BOB)
    record = create(alice)
    vault = budget_api.artifact.read_bytes()
    foreign = checked(bob.request(method, url(record), json={"limit_cents": 5}), 404)
    missing = checked(bob.request(method, url("missing"), json={"limit_cents": 5}), 404)
    assert foreign == missing
    assert not usage_path(budget_api).exists()
    assert budget_api.artifact.read_bytes() == vault
    assert alice.get(PREFIX + "/user").json()["models"][0]["registered"] is True


@pytest.mark.parametrize(
    "body",
    [
        b"{",
        b"[]",
        b"null",
        b"{}",
        b'{"limit_cents":true}',
        b'{"limit_cents":false}',
        b'{"limit_cents":1.0}',
        b'{"limit_cents":"5"}',
        b'{"limit_cents":null}',
        b'{"limit_cents":-1}',
        b'{"limit_cents":NaN}',
        b'{"limit_cents":Infinity}',
        b'{"limit_cents":1,"limit_cents":2}',
        b'{"limit_cents":1,"owner_user_id":"foreign"}',
        b'{"limit_cents":1,"path":"/private-canary"}',
        b'{"limit_cents":1,"credential_id":"UNIT-audio-http-secret-not-a-provider-key"}',
        b'{"limit_cents":1,"unlimited":true}',
        ('{"limit_cents":' + str(MAX_MONEY + 1) + "}").encode(),
    ],
)
def test_exact_integer_body_refusal_is_value_free_and_precedes_binding(
    budget_api: PrivateAPI, body: bytes
) -> None:
    alice = sign_in(budget_api)
    checked(alice.put(url("missing"), content=body), 422)
    assert binding(budget_api)._service is None
    assert not usage_path(budget_api).exists()
    assert budget_api.artifact.read_text() == "{}"


@pytest.mark.parametrize("size,status", [(8192, 200), (8193, 413)])
def test_body_exact_inclusive_bound(budget_api: PrivateAPI, size: int, status: int) -> None:
    alice = sign_in(budget_api)
    record = create(alice)
    body = b'{"limit_cents":0}'
    body += b" " * (size - len(body))
    checked(alice.put(url(record), content=body), status)
    assert usage_path(budget_api).exists() is (status == 200)


@pytest.mark.parametrize("cap,available", [(0, 0), (50, 0), (100, 10)])
def test_used_prepared_and_unknown_liabilities_survive_lower_cap_and_disable_delete(
    budget_api: PrivateAPI, cap: int, available: int
) -> None:
    alice = sign_in(budget_api)
    owner, record = subject(alice), create(alice)
    checked(alice.put(url(record), json={"limit_cents": 200}))
    ledger = ByotUsageLedger(usage_path(budget_api))
    ledger.record_settlement(record, owner, 40, "a" * 64)
    ledger.prepare_operation(record, owner, "UNIT-unknown", 30, "b" * 64)
    ledger.mark_operation_sent(owner, "UNIT-unknown")
    ledger.mark_operation_unknown(owner, "UNIT-unknown")
    ledger.prepare_operation(record, owner, "UNIT-prepared", 20, "c" * 64)
    unknown = ledger.operation(owner, "UNIT-unknown")
    prepared = ledger.operation(owner, "UNIT-prepared")
    projected = checked(alice.put(url(record), json={"limit_cents": cap}))
    assert projected["used_cents"] == 40 and projected["held_cents"] == 50
    assert projected["available_cents"] == available and projected["limit_cents"] == cap
    assert alice.patch(PREFIX + "/user/" + record, json={"enabled": False}).status_code == 204
    assert checked(alice.get(url(record))) == projected
    assert alice.get(PREFIX + "/user").json()["models"][0]["registered"] is False
    assert ledger.operation(owner, "UNIT-unknown") == unknown
    assert ledger.operation(owner, "UNIT-prepared") == prepared
    assert alice.delete(PREFIX + "/user/" + record).status_code == 200
    checked(alice.get(url(record)), 404)
    usage = ledger.key_usage(record, owner)
    assert usage is not None and (usage.used_cents, usage.held_cents, usage.limit_cents) == (
        40,
        50,
        cap,
    )
    assert ledger.operation(owner, "UNIT-unknown") == unknown
    assert ledger.operation(owner, "UNIT-prepared") == prepared


def test_restart_budget_does_not_manufacture_registration(budget_api: PrivateAPI) -> None:
    alice = sign_in(budget_api)
    record = create(alice)
    other = TestClient(create_app(register_wrestling=False, register_providers=False))
    other.cookies.update(alice.cookies)
    checked(other.put(url(record), json={"limit_cents": 10}))
    row = other.get(PREFIX + "/user").json()["models"][0]
    assert row["registered"] is False and row["dispatch_authority"] == "unbound"
    assert binding(budget_api)._service is not None
    assert alice.get(PREFIX + "/user").json()["models"][0]["registered"] is True


@pytest.mark.parametrize("damage", ["removed", "replaced", "foreign"])
def test_current_credential_binding_required_before_ledger(
    budget_api: PrivateAPI, damage: str
) -> None:
    alice, bob = sign_in(budget_api), sign_in(budget_api, BOB)
    record = create(alice)
    meta = store.list_credentials(artifact_path=str(budget_api.artifact))[0]
    assert store.delete_credential(meta.cred_id, artifact_path=str(budget_api.artifact))
    if damage != "removed":
        store.store_credential_with_metadata(
            record,
            SECRET + "-replacement",
            owner_user_id=subject(bob) if damage == "foreign" else subject(alice),
            pipeline_kind="audio_model_provider",
            artifact_path=str(budget_api.artifact),
            key_bytes=bytes(range(32)),
        )
    receiving = TestClient(create_app(register_wrestling=False, register_providers=False))
    receiving.cookies.update(alice.cookies)
    checked(receiving.get(url(record)), 503)
    checked(receiving.put(url(record), json={"limit_cents": 10}), 503)
    assert not usage_path(budget_api).exists()
    checked(alice.get(url(record)), 503)
    assert binding(budget_api)._service is None


@pytest.mark.parametrize("failure", ["before-commit", "after-commit", "readback"])
def test_mutation_unknown_is_explicit_and_get_recovers_without_second_write(
    budget_api: PrivateAPI, monkeypatch: pytest.MonkeyPatch, failure: str
) -> None:
    alice = sign_in(budget_api)
    record = create(alice)
    writes: list[int] = []
    original = ByotUsageLedger.set_limit

    def failed_set(
        self: ByotUsageLedger, api_key_id: str, owner_user_id: str, limit_cents: int | None
    ) -> None:
        writes.append(1)
        if failure != "before-commit":
            original(self, api_key_id, owner_user_id, limit_cents)
        if failure != "readback":
            raise sqlite3.OperationalError(SECRET)

    def failed_read(
        self: ByotUsageLedger, api_key_id: str, owner_user_id: str
    ) -> KeyUsageRow | None:
        raise sqlite3.OperationalError(SECRET)

    with monkeypatch.context() as patch:
        patch.setattr(ByotUsageLedger, "set_limit", failed_set)
        if failure == "readback":
            patch.setattr(ByotUsageLedger, "key_usage", failed_read)
        response = checked(alice.put(url(record), json={"limit_cents": 12}), 503)
        assert response == {
            "detail": "audio budget mutation unconfirmed",
            "mutation_confirmed": False,
        }
        assert writes == [1]
    recovered = checked(alice.get(url(record)))
    assert recovered["limit_cents"] == (None if failure == "before-commit" else 12)
    assert writes == [1]


def test_blocked_ledger_is_off_loop_and_catalogue_remains_available(
    budget_api: PrivateAPI, monkeypatch: pytest.MonkeyPatch
) -> None:
    alice = sign_in(budget_api)
    record = create(alice)
    checked(alice.put(url(record), json={"limit_cents": 2}))
    entered, release = threading.Event(), threading.Event()
    original = ByotUsageLedger.key_usage
    worker_ids: list[int] = []

    def blocked(self: ByotUsageLedger, api_key_id: str, owner_user_id: str) -> KeyUsageRow | None:
        worker_ids.append(threading.get_ident())
        entered.set()
        assert release.wait(3)
        return original(self, api_key_id, owner_user_id)

    monkeypatch.setattr(ByotUsageLedger, "key_usage", blocked)

    async def exercise() -> None:
        loop_thread = threading.get_ident()
        async with httpx.AsyncClient(
            transport=httpx.ASGITransport(app=budget_api.app),
            base_url=str(alice.base_url),
            cookies=alice.cookies,
        ) as client:
            pending = asyncio.create_task(client.get(url(record)))
            try:
                assert await asyncio.to_thread(entered.wait, 2)
                catalog = await asyncio.wait_for(client.get(PREFIX + "/catalog"), 1)
                assert catalog.status_code == 200
                assert worker_ids and all(value != loop_thread for value in worker_ids)
            finally:
                release.set()
            checked(await asyncio.wait_for(pending, 3))

    asyncio.run(exercise())


@pytest.mark.parametrize("method", ["POST", "PATCH", "DELETE"])
def test_no_other_budget_method_or_dispatch_admitted(budget_api: PrivateAPI, method: str) -> None:
    alice = sign_in(budget_api)
    checked(alice.request(method, url("missing"), json={"limit_cents": 5}), 403)
    assert not usage_path(budget_api).exists()
