"""rev 8.11 Part D for Write informs (LB-8; pending co-sign).

D1: every committed revision writes one ``derived_asset.revised`` row to
``write_event_outbox`` in its own transaction, on ``write-<deliverable_id>``,
with no document ids; the log is never listed as a thread (T29).
D2: ``GET /derived-assets/{asset_id}/blocks/{block_id}/informs`` answers the
PUT's 200 shape at the current revision, 404 exactly as the PUT, and writes
nothing (T02, T03, T19, T22 read halves).

This file and the code it covers are one commit, so they can be dropped
together if the co-sign changes Part D.
"""

from __future__ import annotations

import hashlib
import json
import os
from collections.abc import Iterator
from pathlib import Path
from typing import Any

import pytest
from fastapi.testclient import TestClient

from interfaces.research.api.app import create_app
from runtime.db_lock import connect_read, connect_write, flush_warm_writers
from substrate.schemas.events import DerivedAssetRevisedPayload
from tests.test_derived_asset_informs_routes import (
    MISSING_ASSET_404,
    Env,
    _bare_client,
    _doc,
    _docs,
    _ids,
    _put,
    _seed,
    _state,
    make_env,
)


@pytest.fixture
def env(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> Iterator[Env]:
    yield from make_env(monkeypatch, tmp_path)


def _get(env: Env, asset_id: str, block_id: str) -> Any:
    return env.client.get(f"/derived-assets/{asset_id}/blocks/{block_id}/informs")


def _outbox(env: Env) -> list[tuple[Any, ...]]:
    con = connect_read(env.db)
    try:
        return con.execute(
            "SELECT operation_id, investigation_id, aggregate_kind, aggregate_id, event_json, state "
            "FROM write_event_outbox ORDER BY outbox_sequence"
        ).fetchall()
    finally:
        con.close()


def _operation_ids(env: Env) -> set[str]:
    con = connect_read(env.db)
    try:
        return {r[0] for r in con.execute("SELECT operation_id FROM derived_asset_operations").fetchall()}
    finally:
        con.close()


# ── D1 / T29: the event ─────────────────────────────────────────────────────


def test_t29_a_commit_writes_one_revised_event_without_document_ids(env: Env) -> None:
    asset, r1 = _seed(env)
    _docs(env, "docA", "docB")
    seeded = _outbox(env)
    assert len(seeded) == 1  # the seed's create event

    r = _put(env, asset, "b-1", _ids("docA", "docB"), r1, "k-1")
    assert r.status_code == 200, r.text
    rows = _outbox(env)
    assert len(rows) == 2
    operation_id, log_id, kind, aggregate_id, event_json, state = rows[-1]
    assert operation_id in _operation_ids(env) and operation_id.startswith("dop-")
    assert (log_id, kind, aggregate_id) == ("write-dlv-1", "derived_asset", asset)
    event = json.loads(event_json)
    assert event["action_type"] == "derived_asset.revised"
    assert event["investigation_id"] == "write-dlv-1"
    assert event["payload"] == {
        "action_type": "derived_asset.revised",
        "derived_asset_id": asset,
        "revision_id": r.json()["revision_id"],
        "parent_revision_id": r1,
        "operation": "informs",
        "block_ids": ["b-1"],
    }
    assert "docA" not in event_json and "docB" not in event_json
    # The route dispatches after commit: the row is delivered to the log.
    assert state == "delivered"
    lines = (Path(env.events) / "write-dlv-1.jsonl").read_text(encoding="utf-8").splitlines()
    assert json.loads(lines[-1])["event_id"] == event["event_id"]


def test_t29_the_create_event_has_no_parent(env: Env) -> None:
    asset, r1 = _seed(env)
    (operation_id, log_id, kind, aggregate_id, event_json, _state_) = _outbox(env)[0]
    payload = json.loads(event_json)["payload"]
    assert (log_id, kind, aggregate_id) == ("write-dlv-1", "derived_asset", asset)
    assert payload["operation"] == "create"
    assert payload["parent_revision_id"] is None
    assert payload["revision_id"] == r1
    assert payload["block_ids"] == ["b-1", "b-2"]
    assert operation_id in _operation_ids(env)


def test_t29_a_refusal_and_a_replay_write_no_event(env: Env) -> None:
    asset, r1 = _seed(env)
    _docs(env, "docA")
    assert _put(env, asset, "b-1", _ids("docA"), r1, "k-1").status_code == 200
    before = _state(env)
    assert _put(env, asset, "b-1", _ids("docA"), r1, "k-1").status_code == 200  # replay
    assert _put(env, asset, "b-1", _ids("docA"), r1, "k-2").status_code == 409  # stale
    assert _put(env, asset, "b-1", _ids("docA", "docA"), r1, "k-3").status_code == 409
    assert _state(env) == before


@pytest.mark.parametrize(  # type: ignore[untyped-decorator]
    ("operation", "parent", "ok"),
    [("create", None, True), ("create", "rev-0", False), ("informs", "rev-0", True), ("informs", None, False),
     ("edit", "rev-0", True), ("fork", "rev-0", False)],
)
def test_l6_the_parent_is_null_exactly_for_create(operation: str, parent: str | None, ok: bool) -> None:
    fields: dict[str, Any] = {
        "derived_asset_id": "write:d", "revision_id": "rev-1", "parent_revision_id": parent,
        "operation": operation, "block_ids": [],
    }
    if ok:
        DerivedAssetRevisedPayload(**fields)
    else:
        with pytest.raises(ValueError):
            DerivedAssetRevisedPayload(**fields)


def test_d1_the_write_log_is_never_listed_as_a_thread(env: Env) -> None:
    asset, r1 = _seed(env)
    _docs(env, "docA")
    assert _put(env, asset, "b-1", _ids("docA"), r1, "k-1").status_code == 200
    assert (Path(env.events) / "write-dlv-1.jsonl").exists()
    listed = env.client.get("/investigations", params={"limit": 500})
    assert listed.status_code == 200, listed.text
    assert all(not row["investigation_id"].startswith("write-") for row in listed.json()["investigations"])


# ── D2: the read ────────────────────────────────────────────────────────────


def test_d2_the_get_answers_the_puts_bytes_at_the_current_revision(env: Env) -> None:
    """T02's read half."""
    asset, r1 = _seed(env)
    _docs(env, "docA", "docB", "docC")
    put = _put(env, asset, "b-1", _ids("docC", "docA", "docB"), r1, "k-1")
    assert put.status_code == 200, put.text
    got = _get(env, asset, "b-1")
    assert got.status_code == 200
    assert got.content == put.content
    empty = _get(env, asset, "b-2")
    assert empty.json() == {"revision_id": put.json()["revision_id"], "block_id": "b-2", "informs": []}


def test_d2_a_second_app_reads_what_the_first_wrote(env: Env) -> None:
    """T03's read half: nothing is held in the app that wrote."""
    asset, r1 = _seed(env)
    _docs(env, "docA")
    put = _put(env, asset, "b-1", _ids("docA"), r1, "k-1")
    assert put.status_code == 200, put.text
    flush_warm_writers(env.db)
    second = TestClient(create_app(register_wrestling=False))
    assert second.get(f"/derived-assets/{asset}/blocks/b-1/informs").content == put.content


def test_d2_the_get_404s_exactly_as_the_put(env: Env) -> None:
    """T19 and T20's read halves."""
    foreign, _ = _seed(env, deliverable_id="dlv-foreign", owner="other")
    asset, _ = _seed(env)
    with connect_write(env.db, purpose="test/bare-asset") as con:
        con.execute(
            "INSERT INTO derived_assets (derived_asset_id, title, asset_kind, owner_user_id) "
            "VALUES ('write:dlv-bare', 'Bare', 'document', '__operator__')"
        )
    missing = _get(env, "write:dlv-nope", "b-1")
    assert missing.status_code == 404
    assert missing.json() == MISSING_ASSET_404
    for asset_id, block_id in ((foreign, "b-1"), (asset, "b-9"), ("write:dlv-bare", "b-1"), ("reformat:x", "b-1")):
        r = _get(env, asset_id, block_id)
        assert r.status_code == 404
        assert r.content == missing.content


def test_d2_the_get_follows_the_verified_subject(env: Env) -> None:
    alices, _ = _seed(env, deliverable_id="dlv-alice", owner="alice")
    bare = _bare_client()
    assert bare.get(f"/derived-assets/{alices}/blocks/b-1/informs", headers={"x-test-subject": "alice"}).status_code == 200
    assert bare.get(f"/derived-assets/{alices}/blocks/b-1/informs", headers={"x-test-subject": "bob"}).status_code == 404
    unauthenticated = bare.get(f"/derived-assets/{alices}/blocks/b-1/informs")
    assert unauthenticated.status_code == 401
    assert unauthenticated.json() == {"detail": "authenticated_owner_required"}


def test_d2_the_get_never_opens_the_writer(env: Env) -> None:
    """T22's route half. Kills M15 (GET opens connect_write)."""
    asset, r1 = _seed(env)
    _docs(env, "docA")
    assert _put(env, asset, "b-1", _ids("docA"), r1, "k-1").status_code == 200
    flush_warm_writers(env.db)
    before = _state(env)

    import interfaces.research.api.derived_asset_routes as routes
    import runtime.db_lock as db_lock
    from substrate.graph import schema as schema_mod

    def _forbidden(*_a: Any, **_k: Any) -> Any:
        raise AssertionError("a read must never open connect_write")

    with pytest.MonkeyPatch.context() as patch:
        for module in (routes, db_lock, schema_mod):
            patch.setattr(module, "connect_write", _forbidden)
        got = _get(env, asset, "b-1")
    assert got.status_code == 200, got.text
    assert [e["document_id"] for e in got.json()["informs"]] == ["docA"]
    assert _state(env) == before


def test_d2_the_get_is_documented_in_the_schema(env: Env) -> None:
    paths = env.client.app.openapi()["paths"]  # type: ignore[attr-defined]
    operations = paths["/derived-assets/{asset_id}/blocks/{block_id}/informs"]
    assert {"get", "put"} <= set(operations)
    assert not {"patch", "post", "delete"} & set(operations)


# ── T25: the enqueue step is inside the transaction ─────────────────────────


def test_t25_a_fault_after_the_enqueue_leaves_nothing_behind(env: Env) -> None:
    from substrate.derived_assets.informs import InformsRequest, put_block_informs

    asset, r1 = _seed(env)
    _doc(env, "docA")
    before = _state(env)

    def fault(name: str) -> None:
        if name == "after_enqueue":
            raise RuntimeError(name)

    body = {"informs": _ids("docA"), "expected_revision_id": r1, "idempotency_key": "k-1"}
    request = InformsRequest(
        body["informs"], r1, "k-1", hashlib.sha256(json.dumps(body).encode()).hexdigest()
    )
    with connect_write(env.db, purpose="test/enqueue-fault") as con, pytest.raises(RuntimeError), con.transaction():
        put_block_informs(con, owner_user_id="__operator__", asset_id=asset, block_id="b-1", request=request,
                          checkpoint=fault)
    assert _state(env) == before
    assert not os.path.exists(Path(env.events) / "write-dlv-1.jsonl")
