"""A known-id start replay is answered before the hard ACU capacity gate.

POST /investigations promises that a retry with a known ``investigation_id``
(house path) or ``operation_id`` (owner path) is an idempotent replay: the
same body returns the original ``start_event_id`` and runs nothing. The hard
capacity precheck used to run first, so when the original start used the
last ACU of the allowance the retry the caller sends after a lost response came
back 429 ``compute_capacity_exhausted`` instead. The id was also charged
before the replay check, so a known id whose start carries no ACU row (a
chase-spawned child, a pre-metering start) was billed 1 ACU on a replay or a
409 conflict that ran nothing.

A replay or a conflict is never refused at the cap nor charged anew; a
genuinely new start is still gated and charged exactly as before.
"""

from __future__ import annotations

import json
import os
from pathlib import Path

import pytest
from fastapi.testclient import TestClient
from test_acu_meter import isolated_db  # noqa: F401  (fixture)

from interfaces.research.api.app import create_app
from interfaces.research.api.auth import SESSION_COOKIE_NAME
from interfaces.research.api.broadcast import EventBroadcaster
from runtime.db_lock import connect_write
from substrate.auth import mint_session_cookie
from substrate.compute_capacity.acu_meter import (
    ensure_acu_ledger,
    record_investigation_start_acu,
)
from substrate.compute_capacity.store import get_capacity, set_capacity
from substrate.event_log import emit_typed
from substrate.schemas import InvestigationStartRequestedPayload

_OPERATOR = "__operator__"
_START = "investigation.start_requested"


class _SpyBus(EventBroadcaster):
    def __init__(self) -> None:
        super().__init__()
        self.seen: list[str] = []

    async def broadcast(self, event):  # type: ignore[override]
        self.seen.append(str(event.investigation_id))


def _seed(db: str, owner: str, *, limit: int, used: int) -> None:
    with connect_write(db, purpose="test:seed") as con:
        set_capacity(con, owner_user_id=owner, tier="custom", monthly_compute_units=limit)
        for i in range(used):
            record_investigation_start_acu(
                con, owner_user_id=owner, investigation_id=f"seed-{owner}-{i}",
            )


def _ledger(db: str, owner: str) -> tuple[list[str], int | None]:
    with connect_write(db, purpose="test:ledger") as con:
        ensure_acu_ledger(con)
        rows = con.execute(
            "SELECT investigation_id FROM owner_compute_acu_ledger ORDER BY 1"
        ).fetchall()
        return [r[0] for r in rows], get_capacity(con, owner).used_compute_units


def _start_rows() -> list[dict]:
    root = Path(os.environ["ANTIEK_RESEARCH_EVENTS_DIR"])
    rows: list[dict] = []
    for path in root.rglob("*.jsonl"):
        rows.extend(json.loads(line) for line in path.read_text().splitlines())
    return [r for r in rows if r["action_type"] == _START]


def _client(bus: _SpyBus) -> TestClient:
    app = create_app(
        broadcaster=bus, register_wrestling=False, register_providers=False,
        cors_origins=[],
    )
    bus.unregister_all_handlers()
    return TestClient(app)


_BODY = {
    "question": "Which evidence is strongest?",
    "investigation_id": "inv-cap-replay",
    "max_sub_questions": 4,
}


# ── house path (investigation_id) ────────────────────────────────────


def test_house_replay_after_start_used_last_acu_returns_original(isolated_db, monkeypatch):  # noqa: F811
    monkeypatch.setenv("ANTIEK_COMPUTE_CAPACITY_ENFORCEMENT", "hard")
    _seed(isolated_db, _OPERATOR, limit=1, used=0)
    bus = _SpyBus()
    client = _client(bus)

    first = client.post("/investigations", json=_BODY)
    assert first.status_code == 202, first.text
    assert _ledger(isolated_db, _OPERATOR) == (["inv-cap-replay"], 1)

    retry = client.post("/investigations", json=_BODY)
    assert retry.status_code == 202, retry.text
    assert retry.json()["start_event_id"] == first.json()["start_event_id"]
    assert retry.json()["investigation_id"] == "inv-cap-replay"
    assert len(_start_rows()) == 1
    assert bus.seen == ["inv-cap-replay"]
    assert _ledger(isolated_db, _OPERATOR) == (["inv-cap-replay"], 1)


def test_house_conflict_at_hard_cap_is_409_not_429(isolated_db, monkeypatch):  # noqa: F811
    monkeypatch.setenv("ANTIEK_COMPUTE_CAPACITY_ENFORCEMENT", "hard")
    _seed(isolated_db, _OPERATOR, limit=1, used=0)
    bus = _SpyBus()
    client = _client(bus)
    assert client.post("/investigations", json=_BODY).status_code == 202

    other = client.post(
        "/investigations", json={**_BODY, "question": "A different question here?"},
    )
    assert other.status_code == 409, other.text
    assert other.json()["detail"] == "investigation_id_conflict"
    assert len(_start_rows()) == 1
    assert bus.seen == ["inv-cap-replay"]


def test_new_start_at_hard_cap_is_still_refused_and_uncharged(isolated_db, monkeypatch):  # noqa: F811
    """Positive control: the replay carve-out is not a capacity bypass."""
    monkeypatch.setenv("ANTIEK_COMPUTE_CAPACITY_ENFORCEMENT", "hard")
    _seed(isolated_db, _OPERATOR, limit=1, used=0)
    bus = _SpyBus()
    client = _client(bus)
    assert client.post("/investigations", json=_BODY).status_code == 202

    for body in (
        {"question": "A brand new question?"},
        {**_BODY, "investigation_id": "inv-cap-fresh"},
    ):
        refused = client.post("/investigations", json=body)
        assert refused.status_code == 429, refused.text
        assert refused.json()["detail"]["code"] == "compute_capacity_exhausted"
    assert len(_start_rows()) == 1
    assert bus.seen == ["inv-cap-replay"]
    assert _ledger(isolated_db, _OPERATOR) == (["inv-cap-replay"], 1)


def test_retry_of_charged_but_unappended_start_is_not_refused(isolated_db, monkeypatch):  # noqa: F811
    """The charge landed and used the last ACU, then the append failed. The
    retry is the same paid start, not a new one: the charge is idempotent on
    the id, so the precheck must not 429 it either."""
    import interfaces.research.api.app as app_module

    monkeypatch.setenv("ANTIEK_COMPUTE_CAPACITY_ENFORCEMENT", "hard")
    _seed(isolated_db, _OPERATOR, limit=1, used=0)
    bus = _SpyBus()
    client = TestClient(_client(bus).app, raise_server_exceptions=False)
    real_emit = app_module.emit_typed

    def append_fails(*args, **kwargs):
        raise OSError("simulated event-log append failure")

    monkeypatch.setattr(app_module, "emit_typed", append_fails)
    lost = client.post("/investigations", json=_BODY)
    assert lost.status_code == 500
    assert _start_rows() == []
    assert _ledger(isolated_db, _OPERATOR) == (["inv-cap-replay"], 1)

    monkeypatch.setattr(app_module, "emit_typed", real_emit)
    retry = client.post("/investigations", json=_BODY)
    assert retry.status_code == 202, retry.text
    assert len(_start_rows()) == 1
    assert bus.seen == ["inv-cap-replay"]
    assert _ledger(isolated_db, _OPERATOR) == (["inv-cap-replay"], 1)


@pytest.mark.parametrize("used", [0, 1])
def test_id_charged_to_another_owner_is_a_conflict_not_a_free_run(isolated_db, monkeypatch, used):  # noqa: F811
    """The ledger holds one charge per id. A start another owner paid for
    (charged, then its append failed) is neither this owner's retry nor a new
    start this owner could be charged for: it must not run on the other
    owner's charge (under the cap) nor skip this owner's cap (at it)."""
    monkeypatch.setenv("ANTIEK_COMPUTE_CAPACITY_ENFORCEMENT", "hard")
    _seed(isolated_db, _OPERATOR, limit=1, used=used)
    with connect_write(isolated_db, purpose="test:other-owner") as con:
        set_capacity(con, owner_user_id="someone-else", tier="custom", monthly_compute_units=5)
        record_investigation_start_acu(
            con, owner_user_id="someone-else", investigation_id="inv-cap-replay",
        )
    before = _ledger(isolated_db, _OPERATOR)
    bus = _SpyBus()
    other = _client(bus).post("/investigations", json=_BODY)
    assert other.status_code == 409, other.text
    assert other.json()["detail"] == "investigation_id_conflict"
    assert _start_rows() == []
    assert bus.seen == []
    assert _ledger(isolated_db, _OPERATOR) == before


def _emit_uncharged_start(investigation_id: str, **payload: object) -> str:
    """A start already on the trajectory with no ACU row: what a chase child
    (emitted by the orchestrator) or a pre-metering start looks like."""
    event_id = emit_typed(
        investigation_id,
        InvestigationStartRequestedPayload(**payload),  # type: ignore[arg-type]
        role="orchestrator",
        policy_id="orchestrator-chase",
    )
    assert event_id is not None
    return event_id


def test_replay_of_uncharged_start_is_neither_gated_nor_charged(isolated_db, monkeypatch):  # noqa: F811
    monkeypatch.setenv("ANTIEK_COMPUTE_CAPACITY_ENFORCEMENT", "hard")
    _seed(isolated_db, _OPERATOR, limit=1, used=1)
    original = _emit_uncharged_start(
        "inv-cap-replay", question=_BODY["question"], context="", max_sub_questions=4,
    )
    bus = _SpyBus()
    retry = _client(bus).post("/investigations", json=_BODY)
    assert retry.status_code == 202, retry.text
    assert retry.json()["start_event_id"] == original
    assert len(_start_rows()) == 1
    assert bus.seen == []
    assert _ledger(isolated_db, _OPERATOR) == ([f"seed-{_OPERATOR}-0"], 1)


def test_conflict_on_uncharged_start_charges_nothing(isolated_db, monkeypatch):  # noqa: F811
    monkeypatch.setenv("ANTIEK_COMPUTE_CAPACITY_ENFORCEMENT", "hard")
    _seed(isolated_db, _OPERATOR, limit=10, used=0)
    _emit_uncharged_start(
        "inv-cap-replay", question="A chase child question?",
        parent_investigation_id="inv-parent", spawn_context="A chase child question?",
    )
    bus = _SpyBus()
    other = _client(bus).post("/investigations", json=_BODY)
    assert other.status_code == 409, other.text
    assert other.json()["detail"] == "investigation_id_conflict"
    assert bus.seen == []
    assert _ledger(isolated_db, _OPERATOR) == ([], None)  # never charged


# ── owner path (operation_id) ────────────────────────────────────────

_SECRET = "owner-cap-test-" + "x" * 48
_EMAIL = "owner@example.test"
_OWNER = "owner-cap"
_OWNER_BODY = {
    "question": "Which evidence is strongest?",
    "operation_id": "op-cap-1",
    "model_choice": {
        "authority": "user_model",
        "provider_id": "owner-provider",
        "model_id": "owner-model",
    },
}


@pytest.fixture
def owner_client(isolated_db, monkeypatch, tmp_path):  # noqa: F811
    monkeypatch.setenv("ANTIEK_COMPUTE_CAPACITY_ENFORCEMENT", "hard")
    monkeypatch.setenv("ANTIEK_OWNER_LAUNCH_DB", str(tmp_path / "launches.sqlite3"))
    monkeypatch.setenv("ANTIEK_AUTH_SECRET", _SECRET)
    monkeypatch.setenv("ANTIEK_OPERATOR_EMAIL", _EMAIL)
    monkeypatch.delenv("ANTIEK_OPERATOR_TOKEN", raising=False)
    Path(os.environ["ANTIEK_RESEARCH_EVENTS_DIR"]).mkdir(mode=0o700, exist_ok=True)
    bus = _SpyBus()
    client = _client(bus)
    client.cookies.set(SESSION_COOKIE_NAME, mint_session_cookie(user_id=_OWNER, email=_EMAIL))
    return client, bus, isolated_db


def test_owner_replay_after_start_used_last_acu_returns_original(owner_client):
    client, bus, db = owner_client
    _seed(db, _OWNER, limit=1, used=0)

    first = client.post("/investigations", json=_OWNER_BODY)
    assert first.status_code == 202, first.text
    investigation_id = first.json()["investigation_id"]
    assert _ledger(db, _OWNER) == ([investigation_id], 1)

    retry = client.post("/investigations", json=_OWNER_BODY)
    assert retry.status_code == 202, retry.text
    assert retry.json()["start_event_id"] == first.json()["start_event_id"]
    assert retry.json()["owner_model_status"] == "replayed"
    assert len(_start_rows()) == 1
    assert bus.seen == [investigation_id]
    assert _ledger(db, _OWNER) == ([investigation_id], 1)

    # A different operation at the cap is a genuinely new start: refused.
    fresh = client.post("/investigations", json={**_OWNER_BODY, "operation_id": "op-cap-2"})
    assert fresh.status_code == 429, fresh.text
    assert _ledger(db, _OWNER) == ([investigation_id], 1)


def test_owner_conflict_at_hard_cap_is_409_not_429(owner_client):
    client, _, db = owner_client
    _seed(db, _OWNER, limit=1, used=0)
    assert client.post("/investigations", json=_OWNER_BODY).status_code == 202

    mutated = {**_OWNER_BODY, "question": "A different question here?"}
    conflict = client.post("/investigations", json=mutated)
    assert conflict.status_code == 409, conflict.text
    assert conflict.json() == {"detail": "owner_model_operation_conflict"}
    assert len(_start_rows()) == 1


def test_other_owner_reusing_an_operation_at_its_cap_gets_the_constant_409(owner_client, monkeypatch):
    """Another owner's charged operation is a conflict for this owner, never
    a 429 that differs from the answer below the cap, and never a free run."""
    client, bus, db = owner_client
    _seed(db, _OWNER, limit=5, used=0)
    assert client.post("/investigations", json=_OWNER_BODY).status_code == 202
    _seed(db, "owner-2", limit=1, used=1)
    monkeypatch.setenv("ANTIEK_OPERATOR_EMAIL", f"{_EMAIL},other@example.test")
    other = TestClient(client.app)
    other.cookies.set(
        SESSION_COOKIE_NAME,
        mint_session_cookie(user_id="owner-2", email="other@example.test"),
    )
    reused = other.post("/investigations", json=_OWNER_BODY)
    assert reused.status_code == 409, reused.text
    assert reused.json() == {"detail": "owner_model_operation_conflict"}
    assert len(_start_rows()) == 1
    assert len(bus.seen) == 1
    with connect_write(db, purpose="test:ledger") as con:
        assert get_capacity(con, "owner-2").used_compute_units == 1
