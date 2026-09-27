"""Write informs persistence (THREAD-CONTRACT §1.11a "Write informs (S5)"; LB-8).

``PUT /derived-assets/{asset_id}/blocks/{block_id}/informs`` replaces one
block's ordered document list by committing one §1.11 ``revise`` with
compare-and-set on the current revision. FastAPI TestClient against a real
DuckDB. The auth middleware's enforcement-disabled default stamps the
single-operator identity, so the requester is ``__operator__``; another
owner's asset is seeded under ``other``. A bare app with a stamping
middleware supplies a non-operator subject and the no-subject 401.

The IDs refer to the LB-8 executable spec §9 (T01-T28, T30); each names the
§10 mutants it must kill.
"""

from __future__ import annotations

import hashlib
import json
import os
import re
import subprocess
import sys
import threading
from collections.abc import Iterator
from dataclasses import dataclass
from pathlib import Path
from typing import Any

import pytest
from fastapi import FastAPI, Request
from fastapi.testclient import TestClient

from interfaces.research.api.app import create_app
from runtime.db_lock import connect_read, connect_write, flush_warm_writers
from substrate.graph import ensure_initialized
from substrate.graph.ops import insert_deliverable, insert_document, insert_section

ROOT = Path(__file__).resolve().parents[1]
BODY_HTML = "<article><p>One.</p><p>Two.</p></article>"
SHA = "a" * 64
MISSING_ASSET_404 = {"detail": "not_found"}


@dataclass
class Env:
    db: str
    events: str
    client: TestClient


@pytest.fixture
def env(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> Iterator[Env]:
    yield from make_env(monkeypatch, tmp_path)


def make_env(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> Iterator[Env]:
    """The fixture's body, shared with tests/test_derived_asset_informs_read.py."""
    for variable in (
        "ANTIEK_AUTH_SECRET", "ANTIEK_DEV_LOGIN_TOKEN", "ANTIEK_OPERATOR_EMAIL", "ANTIEK_OPERATOR_TOKEN",
        "ANTIEK_OPERATOR_SERVICE_TOKEN_CLIENT_ID", "CF_ACCESS_CLIENT_SECRET", "ANTIEK_COOKIE_INSECURE",
    ):
        monkeypatch.delenv(variable, raising=False)
    db = str(tmp_path / "graph.duckdb")
    events = str(tmp_path / "events")
    os.makedirs(events, exist_ok=True)
    monkeypatch.setenv("ANTIEK_DUCKDB_PATH", db)
    monkeypatch.setenv("ANTIEK_RESEARCH_EVENTS_DIR", events)
    monkeypatch.setenv("ANTIEK_RESEARCH_ARTIFACTS_DIR", str(tmp_path / "artifacts"))
    monkeypatch.setenv("ANTIEK_EMBEDDING_PROVIDER", "hash")
    ensure_initialized(db)
    client = TestClient(create_app(register_wrestling=False))
    yield Env(db=db, events=events, client=client)
    flush_warm_writers(db)


# ── fixtures over the store ────────────────────────────────────────────────


def _seed(
    env: Env,
    *,
    deliverable_id: str = "dlv-1",
    blocks: tuple[str, ...] = ("b-1", "b-2"),
    owner: str = "__operator__",
) -> tuple[str, str]:
    """Revision 1 of ``write:<deliverable_id>`` through the §1.11 create
    primitive (LB-8 gives it no production caller)."""
    asset_id = f"write:{deliverable_id}"
    return asset_id, _create(env, asset_id, blocks=blocks, owner=owner).revision_id


def _create(env: Env, asset_id: str, *, blocks: tuple[str, ...], owner: str) -> Any:
    from substrate.derived_assets.repository import RevisionBody, create_revision

    body = RevisionBody(
        canonical_html=BODY_HTML, manifest_json='{"members":[]}', sanitizer_policy="antiek-write",
        sanitizer_version="1",
    )
    with connect_write(env.db, purpose="test/seed-asset") as con, con.transaction():
        return create_revision(
            con, asset_id=asset_id, owner_user_id=owner, asset_kind="document", title="Bridge failures",
            body=body, blocks=list(blocks), members=[], idempotency_key=f"create:{asset_id}",
            request_sha256=hashlib.sha256(asset_id.encode()).hexdigest(),
            event_log_id=asset_id.replace(":", "-"),
        )


def _doc(env: Env, document_id: str, content_class: str | None = "public_domain", owner: str = "__operator__") -> None:
    with connect_write(env.db, purpose="test/seed-doc") as con:
        insert_document(
            con,
            document_id=document_id,
            source_tier=2,
            document_type="paper",
            title=document_id,
            content_class=content_class,
            owner_user_id=owner,
        )


def _docs(env: Env, *ids: str) -> None:
    for document_id in ids:
        _doc(env, document_id)


def _put(env: Env, asset_id: str, block_id: str, informs: list[Any], expected: str, key: str) -> Any:
    return env.client.put(
        f"/derived-assets/{asset_id}/blocks/{block_id}/informs",
        json={"informs": informs, "expected_revision_id": expected, "idempotency_key": key},
    )


def _ids(*document_ids: str) -> list[dict[str, Any]]:
    return [{"document_id": d} for d in document_ids]


def _read(env: Env, asset_id: str, block_id: str, owner: str = "__operator__") -> dict[str, Any]:
    """A read through the module's read-only function on a read handle."""
    from substrate.derived_assets.informs import read_block_informs

    con = connect_read(env.db)
    try:
        return read_block_informs(con, asset_id, block_id, owner)
    finally:
        con.close()


def _listed(answer: dict[str, Any]) -> list[str]:
    return [entry["document_id"] for entry in answer["informs"]]


def _rows_at(env: Env, asset_id: str, revision_id: str, block_id: str) -> list[tuple[Any, ...]]:
    con = connect_read(env.db)
    try:
        return con.execute(
            "SELECT ordinal, document_id, anchor FROM derived_asset_block_informs "
            "WHERE derived_asset_id = ? AND revision_id = ? AND block_id = ? ORDER BY ordinal",
            [asset_id, revision_id, block_id],
        ).fetchall()
    finally:
        con.close()


_STATE_TABLES = (
    "derived_assets",
    "derived_asset_revisions",
    "derived_asset_revision_members",
    "derived_asset_current_revisions",
    "derived_asset_revision_blocks",
    "derived_asset_block_informs",
    "derived_asset_operations",
    "write_event_outbox",
)


def _state(env: Env) -> dict[str, Any]:
    """Every row count this feature can touch, plus the pointer and the
    asset timestamps, so "nothing written" is one comparison."""
    con = connect_read(env.db)
    try:
        counts = {t: con.execute(f"SELECT count(*) FROM {t}").fetchone()[0] for t in _STATE_TABLES}
        counts["pointers"] = con.execute(
            "SELECT derived_asset_id, current_revision_id, generation, updated_at "
            "FROM derived_asset_current_revisions ORDER BY derived_asset_id"
        ).fetchall()
        counts["assets"] = con.execute(
            "SELECT derived_asset_id, updated_at FROM derived_assets ORDER BY derived_asset_id"
        ).fetchall()
        return counts
    finally:
        con.close()


def _bare_client() -> TestClient:
    """The router alone, with a middleware that stamps a verified subject
    from ``x-test-subject`` (absent: no subject at all)."""
    from interfaces.research.api.derived_asset_routes import derived_asset_router

    bare = FastAPI()
    bare.include_router(derived_asset_router)

    @bare.middleware("http")
    async def stamp(request: Request, call_next: Any) -> Any:
        subject = request.headers.get("x-test-subject")
        if subject:
            request.state.user_id = subject
            request.state.auth_method = "session_cookie"
        return await call_next(request)

    return TestClient(bare)


# ── T01: the P13 lost update, server side ──────────────────────────────────


def test_t01_p13_lost_update_is_impossible_server_side(env: Env) -> None:
    """Kills M1 (no CAS), M2 (no carry-forward), M7 (key burned on refusal)."""
    asset, r1 = _seed(env)
    _docs(env, "docA", "docB", "docC", "docE")

    one = _put(env, asset, "b-1", _ids("docA"), r1, "x-1")
    assert one.status_code == 200, one.text
    r2 = one.json()["revision_id"]

    # X, holding R2, writes b-2. The whole-record save would have erased b-1.
    two = _put(env, asset, "b-2", _ids("docB"), r2, "x-2")
    assert two.status_code == 200, two.text
    r3 = two.json()["revision_id"]
    assert _listed(_read(env, asset, "b-1")) == ["docA"]
    assert [row[1] for row in _rows_at(env, asset, r3, "b-1")] == ["docA"]

    three = _put(env, asset, "b-1", _ids("docA", "docE"), r3, "x-3")
    assert three.status_code == 200, three.text
    r4 = three.json()["revision_id"]

    # Y still holds R2: a stale writer never overwrites the newer list.
    before = _state(env)
    stale = _put(env, asset, "b-1", _ids("docA", "docC"), r2, "y-1")
    assert stale.status_code == 409, stale.text
    assert stale.json() == {"reason": "revision_moved", "current_revision_id": r4}
    assert _state(env) == before

    # Y rebases on R4 and re-applies its order under the same key.
    rebased = _put(env, asset, "b-1", _ids("docA", "docE", "docC"), r4, "y-1")
    assert rebased.status_code == 200, rebased.text
    r5 = rebased.json()["revision_id"]

    b1 = _read(env, asset, "b-1")
    b2 = _read(env, asset, "b-2")
    assert b1["revision_id"] == b2["revision_id"] == r5
    assert _listed(b1) == ["docA", "docE", "docC"]
    assert _listed(b2) == ["docB"]


# ── T02-T04: order, reload, replace-all ────────────────────────────────────


def test_t02_the_list_order_is_the_ordinal_and_a_reorder_leaves_the_parent(env: Env) -> None:
    """Kills M3 (append), M4 (order by document_id)."""
    asset, r1 = _seed(env)
    _docs(env, "docA", "docB", "docC")

    first = _put(env, asset, "b-1", _ids("docC", "docA", "docB"), r1, "k-1")
    assert first.status_code == 200, first.text
    body = first.json()
    r2 = body["revision_id"]
    assert body == {
        "revision_id": r2,
        "block_id": "b-1",
        "informs": [
            {"ordinal": 0, "document_id": "docC"},
            {"ordinal": 1, "document_id": "docA"},
            {"ordinal": 2, "document_id": "docB"},
        ],
    }
    assert _read(env, asset, "b-1") == body

    reorder = _put(env, asset, "b-1", _ids("docB", "docC", "docA"), r2, "k-2")
    assert reorder.status_code == 200, reorder.text
    assert _listed(reorder.json()) == ["docB", "docC", "docA"]
    assert [e["ordinal"] for e in reorder.json()["informs"]] == [0, 1, 2]
    # The parent revision is immutable: its rows keep the old order.
    assert [row[:2] for row in _rows_at(env, asset, r2, "b-1")] == [(0, "docC"), (1, "docA"), (2, "docB")]


_SUBPROCESS_READ = """
import json, sys
from runtime.db_lock import connect_read
from substrate.graph import schema
from substrate.derived_assets.informs import read_block_informs
assert not schema._INITIALIZED_PATHS
con = connect_read(sys.argv[1])
try:
    print(json.dumps(read_block_informs(con, sys.argv[2], sys.argv[3], "__operator__"), sort_keys=True))
finally:
    con.close()
"""


def test_t03_a_fresh_process_reads_what_was_written(env: Env) -> None:
    """Kills M21 (informs kept in a process cache)."""
    asset, r1 = _seed(env)
    _docs(env, "docA", "docB")
    put = _put(env, asset, "b-1", _ids("docB", "docA"), r1, "k-1")
    assert put.status_code == 200, put.text
    flush_warm_writers(env.db)

    proc = subprocess.run(
        [sys.executable, "-c", _SUBPROCESS_READ, env.db, asset, "b-1"],
        capture_output=True,
        text=True,
        cwd=str(ROOT),
        env={**os.environ, "PYTHONPATH": str(ROOT)},
        timeout=120,
    )
    assert proc.returncode == 0, proc.stderr
    assert json.loads(proc.stdout.strip().splitlines()[-1]) == put.json()


def test_t04_a_put_replaces_the_whole_list_and_leaves_other_blocks(env: Env) -> None:
    """Kills M3 (append instead of replace)."""
    asset, r1 = _seed(env)
    _docs(env, "docA", "docB", "docC")
    other = _put(env, asset, "b-2", _ids("docC"), r1, "k-0")
    assert other.status_code == 200, other.text

    first = _put(env, asset, "b-1", _ids("docA", "docB"), other.json()["revision_id"], "k-1")
    assert first.status_code == 200, first.text
    second = _put(env, asset, "b-1", _ids("docB"), first.json()["revision_id"], "k-2")
    assert second.status_code == 200, second.text
    assert _listed(second.json()) == ["docB"]
    assert _listed(_read(env, asset, "b-1")) == ["docB"]

    empty = _put(env, asset, "b-1", [], second.json()["revision_id"], "k-3")
    assert empty.status_code == 200, empty.text
    assert empty.json()["informs"] == []
    assert _read(env, asset, "b-1")["informs"] == []
    assert _listed(_read(env, asset, "b-2")) == ["docC"]


# ── T05-T14: the 422 informs_invalid contract ──────────────────────────────


def _invalid(index: int, detail: str) -> dict[str, Any]:
    return {"reason": "informs_invalid", "index": index, "detail": detail}


def test_t05_the_cap_is_fifty_and_the_list_is_never_trimmed(env: Env) -> None:
    """Kills M11 (cap of > 51, or silent trimming)."""
    asset, r1 = _seed(env)
    ids = [f"doc-{i:02d}" for i in range(51)]
    _docs(env, *ids)

    before = _state(env)
    over = _put(env, asset, "b-1", _ids(*ids), r1, "k-1")
    assert over.status_code == 422, over.text
    assert over.json() == _invalid(50, "too_many_entries")
    assert _state(env) == before

    exact = _put(env, asset, "b-1", _ids(*ids[:50]), r1, "k-1")
    assert exact.status_code == 200, exact.text
    assert _listed(exact.json()) == ids[:50]
    assert [e["ordinal"] for e in exact.json()["informs"]] == list(range(50))


def test_t06_a_duplicate_is_reported_at_its_second_occurrence(env: Env) -> None:
    """Kills M12 (duplicate reported at its first occurrence)."""
    asset, r1 = _seed(env)
    _docs(env, "docA", "docB")
    before = _state(env)
    r = _put(env, asset, "b-1", _ids("docA", "docB", "docA"), r1, "k-1")
    assert r.status_code == 422, r.text
    assert r.json() == _invalid(2, "duplicate_document")
    assert _state(env) == before


def test_t07_an_unknown_document_is_not_readable(env: Env) -> None:
    """Kills M8 together with T08."""
    asset, r1 = _seed(env)
    _docs(env, "docA")
    r = _put(env, asset, "b-1", _ids("docA", "nope"), r1, "k-1")
    assert r.status_code == 422, r.text
    assert r.json() == _invalid(1, "document_not_readable")


def test_t08_another_owners_private_document_reads_exactly_like_a_missing_one(env: Env) -> None:
    """Kills M8 (a different detail for missing and foreign-private)."""
    asset, r1 = _seed(env)
    _docs(env, "docA")
    _doc(env, "docP", content_class="personal_reading", owner="other")
    missing = _put(env, asset, "b-1", _ids("docA", "nope"), r1, "k-1")
    foreign = _put(env, asset, "b-1", _ids("docA", "docP"), r1, "k-2")
    assert missing.status_code == foreign.status_code == 422
    assert foreign.content == missing.content


def test_t09_an_unknown_content_class_fails_closed_even_for_its_owner(env: Env) -> None:
    """Kills M9 (a denylist predicate that admits unknown classes)."""
    asset, r1 = _seed(env)
    _docs(env, "docA")
    with connect_write(env.db, purpose="test/unknown-class") as con:
        con.execute(
            "INSERT INTO documents (document_id, source_tier, document_type, content_class, owner_user_id) "
            "VALUES ('docU', 2, 'paper', 'user_authored_private', '__operator__')"
        )
    r = _put(env, asset, "b-1", _ids("docA", "docU"), r1, "k-1")
    assert r.status_code == 422, r.text
    assert r.json() == _invalid(1, "document_not_readable")


def test_t10_the_readable_matrix(env: Env) -> None:
    """NULL is grandfathered, a gated class is citable, the owner reads their
    own personal_reading, and legacy user_owned keeps its behaviour."""
    asset, r1 = _seed(env)
    _doc(env, "docNull", content_class=None)
    _doc(env, "docPd", content_class="public_domain")
    _doc(env, "docGated", content_class="restricted_pending_opt_in")
    _doc(env, "docMine", content_class="personal_reading", owner="__operator__")
    _doc(env, "docLegacy", content_class="user_owned")
    listed = ["docNull", "docPd", "docGated", "docMine", "docLegacy"]
    r = _put(env, asset, "b-1", _ids(*listed), r1, "k-1")
    assert r.status_code == 200, r.text
    assert _listed(r.json()) == listed


def test_t11_an_anchor_must_name_its_entrys_document(env: Env) -> None:
    """Kills M13 (anchor-document equality dropped)."""
    asset, r1 = _seed(env)
    _docs(env, "docA", "docB")
    before = _state(env)
    r = _put(
        env, asset, "b-1",
        [{"document_id": "docA"}, {"document_id": "docB", "anchor": {"document_id": "docA"}}],
        r1, "k-1",
    )
    assert r.status_code == 422, r.text
    assert r.json() == _invalid(1, "anchor_other_document")
    assert _state(env) == before


@pytest.mark.parametrize(  # type: ignore[untyped-decorator]
    "anchor",
    [
        {"document_id": "docB", "anchor_id": "ahl-1"},
        {"document_id": "docB", "source_locator": {"start": 5, "end": 5, "text_sha256": SHA}},
        {"document_id": "docB", "source_locator": {"start": 0, "end": 4, "text_sha256": "z" * 64}},
        {"document_id": "docB", "page_index": -1},
        {"quote": "no document"},
        "docB",
    ],
    ids=["anchor_id", "end_le_start", "sha_not_hex", "page_index_negative", "no_document_id", "not_object"],
)
def test_t12_a_malformed_anchor_is_anchor_invalid_at_its_index(env: Env, anchor: Any) -> None:
    asset, r1 = _seed(env)
    _docs(env, "docA", "docB")
    before = _state(env)
    r = _put(env, asset, "b-1", [{"document_id": "docA"}, {"document_id": "docB", "anchor": anchor}], r1, "k-1")
    assert r.status_code == 422, r.text
    assert r.json() == _invalid(1, "anchor_invalid")
    assert _state(env) == before


def test_t13_cite_only_drops_quotes_on_a_non_servable_document(env: Env) -> None:
    """Kills M14 (quotes kept on a non-servable document)."""
    asset, r1 = _seed(env)
    _doc(env, "docGated", content_class="restricted_pending_opt_in")
    _doc(env, "docPd", content_class="public_domain")
    decomposed = "Café\r\nbridge"
    anchor_gated = {
        "document_id": "docGated",
        "source_locator": {"start": 0, "end": 4, "text_sha256": SHA},
        "quote": "withheld words",
        "prefix": "before",
        "suffix": "after",
        "page_index": 3,
    }
    anchor_pd = {"document_id": "docPd", "quote": decomposed, "prefix": "pre\r", "suffix": "post", "region_id": "rg-1"}
    r = _put(
        env, asset, "b-1",
        [{"document_id": "docGated", "anchor": anchor_gated}, {"document_id": "docPd", "anchor": anchor_pd}],
        r1, "k-1",
    )
    assert r.status_code == 200, r.text
    gated, pd = r.json()["informs"]
    assert gated["anchor"] == {
        "document_id": "docGated",
        "source_locator": {"start": 0, "end": 4, "text_sha256": SHA},
        "page_index": 3,
    }
    assert pd["anchor"] == {
        "document_id": "docPd",
        "quote": "Café\nbridge",
        "prefix": "pre\n",
        "suffix": "post",
        "region_id": "rg-1",
    }
    rows = _rows_at(env, asset, r.json()["revision_id"], "b-1")
    stored_gated = json.loads(rows[0][2])
    assert not {"quote", "prefix", "suffix"} & set(stored_gated)
    assert json.loads(rows[1][2])["quote"] == "Café\nbridge"
    # An entry without an anchor stores NULL and answers without the key.
    plain = _put(env, asset, "b-2", _ids("docPd"), r.json()["revision_id"], "k-2")
    assert plain.json()["informs"] == [{"ordinal": 0, "document_id": "docPd"}]
    assert _rows_at(env, asset, plain.json()["revision_id"], "b-2") == [(0, "docPd", None)]


@pytest.mark.parametrize(  # type: ignore[untyped-decorator]
    "entry",
    [
        {"document_id": "docB", "document_title": "B"},
        {"document_id": "docB", "assigned_at": "t0"},
        {"document_id": ""},
        {"document_id": 7},
        {},
        "docB",
    ],
    ids=["document_title", "assigned_at", "empty_id", "non_string_id", "no_id", "not_object"],
)
def test_t14_a_malformed_entry_is_entry_invalid(env: Env, entry: Any) -> None:
    asset, r1 = _seed(env)
    _docs(env, "docA", "docB")
    r = _put(env, asset, "b-1", [{"document_id": "docA"}, entry], r1, "k-1")
    assert r.status_code == 422, r.text
    assert r.json() == _invalid(1, "entry_invalid")


@pytest.mark.parametrize(  # type: ignore[untyped-decorator]
    "body",
    [
        {"informs": [], "idempotency_key": "k-1"},
        {"informs": [], "expected_revision_id": "rev-x"},
        {"expected_revision_id": "rev-x", "idempotency_key": "k-1"},
        {"informs": {}, "expected_revision_id": "rev-x", "idempotency_key": "k-1"},
        {"informs": [], "expected_revision_id": "", "idempotency_key": "k-1"},
        {"informs": [], "expected_revision_id": "rev-x", "idempotency_key": ""},
        {"informs": [], "expected_revision_id": "rev-x", "idempotency_key": "k" * 257},
        {"informs": [], "expected_revision_id": "rev-x", "idempotency_key": "k-1", "extra": 1},
        ["informs"],
    ],
    ids=["no_expected", "no_key", "no_informs", "informs_not_list", "empty_expected", "empty_key",
         "key_too_long", "unknown_field", "not_object"],
)
def test_t14_a_malformed_body_is_informs_body_invalid(env: Env, body: Any) -> None:
    asset, _ = _seed(env)
    before = _state(env)
    r = env.client.put(f"/derived-assets/{asset}/blocks/b-1/informs", json=body)
    assert r.status_code == 422, r.text
    assert r.json() == {"detail": "informs_body_invalid"}
    assert _state(env) == before


def test_t14_a_body_that_is_not_json_is_informs_body_invalid(env: Env) -> None:
    asset, _ = _seed(env)
    for raw in (b"{", b"", b'{"informs": NaN}'):
        r = env.client.put(
            f"/derived-assets/{asset}/blocks/b-1/informs",
            content=raw,
            headers={"content-type": "application/json"},
        )
        assert r.status_code == 422, (raw, r.text)
        assert r.json() == {"detail": "informs_body_invalid"}


# ── T15-T18: compare-and-set and idempotency ───────────────────────────────


def test_t15_a_stale_expected_revision_is_409_and_writes_nothing(env: Env) -> None:
    """Kills M1."""
    asset, r1 = _seed(env)
    _docs(env, "docA", "docB")
    moved = _put(env, asset, "b-1", _ids("docA"), r1, "k-1")
    assert moved.status_code == 200, moved.text
    r2 = moved.json()["revision_id"]

    before = _state(env)
    for expected in (r1, "rev-never-existed"):
        r = _put(env, asset, "b-1", _ids("docB"), expected, f"k-stale-{expected}")
        assert r.status_code == 409, r.text
        assert r.json() == {"reason": "revision_moved", "current_revision_id": r2}
    assert _state(env) == before
    assert _listed(_read(env, asset, "b-1")) == ["docA"]


def test_t16_a_replay_is_byte_identical_and_writes_nothing(env: Env) -> None:
    """Kills M5 (replay checked after the CAS)."""
    asset, r1 = _seed(env)
    _docs(env, "docA", "docB")
    first = _put(env, asset, "b-1", _ids("docA"), r1, "k-1")
    assert first.status_code == 200, first.text

    before = _state(env)
    again = _put(env, asset, "b-1", _ids("docA"), r1, "k-1")
    assert again.status_code == 200, again.text
    assert again.content == first.content
    assert _state(env) == before

    moved = _put(env, asset, "b-2", _ids("docB"), first.json()["revision_id"], "k-2")
    assert moved.status_code == 200, moved.text
    late = _put(env, asset, "b-1", _ids("docA"), r1, "k-1")
    assert late.status_code == 200, late.text
    assert late.content == first.content


def test_t17_the_same_key_with_another_body_is_idempotency_conflict(env: Env) -> None:
    """Kills M6 (request identity without block_id or informs)."""
    asset, r1 = _seed(env)
    other_asset, other_r1 = _seed(env, deliverable_id="dlv-2")
    _docs(env, "docA", "docB")
    first = _put(env, asset, "b-1", _ids("docA"), r1, "k-1")
    assert first.status_code == 200, first.text

    before = _state(env)
    conflicts = [
        _put(env, asset, "b-1", _ids("docB"), r1, "k-1"),
        _put(env, asset, "b-2", _ids("docA"), r1, "k-1"),
        _put(env, other_asset, "b-1", _ids("docA"), other_r1, "k-1"),
        _put(env, asset, "b-1", [{"document_id": "docA", "anchor": {"document_id": "docA"}}], r1, "k-1"),
    ]
    for r in conflicts:
        assert r.status_code == 409, r.text
        assert r.json() == {"reason": "idempotency_conflict"}
    assert _state(env) == before


def test_t18_a_refusal_does_not_burn_the_key(env: Env) -> None:
    """Kills M7 (the idempotency record written before validation or on a refusal)."""
    asset, r1 = _seed(env)
    _docs(env, "docA", "docB")
    refused = _put(env, asset, "b-1", _ids("docA", "docA"), r1, "k-2")
    assert refused.status_code == 422, refused.text
    accepted = _put(env, asset, "b-1", _ids("docA", "docB"), r1, "k-2")
    assert accepted.status_code == 200, accepted.text
    assert _listed(accepted.json()) == ["docA", "docB"]


# ── T19-T21: ownership, block membership, check order ──────────────────────


def test_t19_another_owners_asset_is_exactly_a_missing_one(env: Env) -> None:
    """Kills M10 (owner check skipped)."""
    foreign, foreign_r1 = _seed(env, deliverable_id="dlv-foreign", owner="other")
    _docs(env, "docA")
    before = _state(env)
    missing = _put(env, "write:dlv-nope", "b-1", _ids("docA"), foreign_r1, "k-1")
    theirs = _put(env, foreign, "b-1", _ids("docA"), foreign_r1, "k-2")
    assert missing.status_code == theirs.status_code == 404
    assert missing.json() == MISSING_ASSET_404
    assert theirs.content == missing.content
    assert _state(env) == before


def test_t19_the_owner_is_the_verified_subject_not_the_operator_default(env: Env) -> None:
    """Kills M10 (owner compared against the ``__operator__`` default)."""
    alices, alice_r1 = _seed(env, deliverable_id="dlv-alice", owner="alice")
    operators, operator_r1 = _seed(env, deliverable_id="dlv-operator", owner="__operator__")
    _docs(env, "docA")
    bare = _bare_client()
    mine = bare.put(
        f"/derived-assets/{alices}/blocks/b-1/informs",
        json={"informs": _ids("docA"), "expected_revision_id": alice_r1, "idempotency_key": "k-1"},
        headers={"x-test-subject": "alice"},
    )
    assert mine.status_code == 200, mine.text
    not_mine = bare.put(
        f"/derived-assets/{operators}/blocks/b-1/informs",
        json={"informs": _ids("docA"), "expected_revision_id": operator_r1, "idempotency_key": "k-2"},
        headers={"x-test-subject": "alice"},
    )
    assert not_mine.status_code == 404
    assert not_mine.json() == MISSING_ASSET_404


def test_t19_without_a_subject_the_answer_is_401_and_nothing_is_written(env: Env) -> None:
    asset, r1 = _seed(env)
    _docs(env, "docA")
    before = _state(env)
    r = _bare_client().put(
        f"/derived-assets/{asset}/blocks/b-1/informs",
        json={"informs": _ids("docA"), "expected_revision_id": r1, "idempotency_key": "k-1"},
    )
    assert r.status_code == 401
    assert r.json() == {"detail": "authenticated_owner_required"}
    assert _state(env) == before


def test_t20_a_block_outside_the_current_revision_is_404(env: Env) -> None:
    asset, r1 = _seed(env)
    _docs(env, "docA")
    missing = _put(env, "write:dlv-nope", "b-1", _ids("docA"), r1, "k-0")
    r = _put(env, asset, "b-9", _ids("docA"), r1, "k-1")
    assert r.status_code == 404
    assert r.content == missing.content


def test_t20_a_block_placed_through_legacy_write_routes_is_404_the_w3_gap(env: Env) -> None:
    with connect_write(env.db, purpose="test/legacy-deliverable") as con:
        deliverable_id = insert_deliverable(con, title="Memo", deliverable_kind="research_memo")
        section_id = insert_section(con, deliverable_id=deliverable_id, section_index=0, title="One")
    asset, r1 = _seed(env, deliverable_id=deliverable_id)
    _docs(env, "docA")
    placed = env.client.post(
        "/write/blocks",
        json={
            "section_id": section_id, "block_kind": "operator_note", "provenance_kind": "user_authored",
            "block_index": 0, "content": "A note", "deliverable_id": deliverable_id,
        },
    )
    assert placed.status_code == 201, placed.text
    r = _put(env, asset, placed.json()["outline_block_id"], _ids("docA"), r1, "k-1")
    assert r.status_code == 404
    assert r.json() == MISSING_ASSET_404


def test_t20_a_deliverable_with_no_revision_is_404(env: Env) -> None:
    """R-LB8-5: LB-8 writes no revision 1."""
    with connect_write(env.db, purpose="test/asset-without-revision") as con:
        con.execute(
            "INSERT INTO derived_assets (derived_asset_id, title, asset_kind, owner_user_id) "
            "VALUES ('write:dlv-bare', 'Bare', 'document', '__operator__')"
        )
    _docs(env, "docA")
    before = _state(env)
    r = _put(env, "write:dlv-bare", "b-1", _ids("docA"), "rev-x", "k-1")
    assert r.status_code == 404
    assert r.json() == MISSING_ASSET_404
    assert _state(env) == before


def test_t20_informs_are_only_for_write_assets(env: Env) -> None:
    """A derived asset outside the ``write:`` namespace has no Write blocks."""
    head = _create(env, "reformat:gen-1", blocks=("b-1",), owner="__operator__")
    _docs(env, "docA")
    r = _put(env, "reformat:gen-1", "b-1", _ids("docA"), head.revision_id, "k-1")
    assert r.status_code == 404
    assert r.json() == MISSING_ASSET_404


def test_t21_the_checks_run_in_the_signed_order(env: Env) -> None:
    """Kills M19 (a 422 before the 404 or the 409)."""
    foreign, foreign_r1 = _seed(env, deliverable_id="dlv-foreign", owner="other")
    asset, r1 = _seed(env)
    ids = [f"doc-{i:02d}" for i in range(51)]
    _docs(env, *ids)

    assert _put(env, foreign, "b-1", _ids(*ids), foreign_r1, "k-1").status_code == 404
    assert _put(env, asset, "b-9", _ids(*ids), r1, "k-2").status_code == 404

    moved = _put(env, asset, "b-1", _ids("doc-00"), r1, "k-3")
    assert moved.status_code == 200, moved.text
    stale_dup = _put(env, asset, "b-1", _ids("doc-00", "doc-00"), r1, "k-4")
    assert stale_dup.status_code == 409
    assert stale_dup.json()["reason"] == "revision_moved"
    # The replay check precedes the block check: a used key on another block
    # is a conflict, not a 404.
    reused = _put(env, asset, "b-9", _ids("doc-00"), r1, "k-3")
    assert reused.status_code == 409
    assert reused.json() == {"reason": "idempotency_conflict"}


# ── T22-T24: reads, the metadata guard, races ──────────────────────────────


def test_t22_the_read_function_writes_nothing(env: Env) -> None:
    asset, r1 = _seed(env)
    _docs(env, "docA")
    assert _put(env, asset, "b-1", _ids("docA"), r1, "k-1").status_code == 200
    flush_warm_writers(env.db)
    before = _state(env)

    import runtime.db_lock as db_lock
    import substrate.derived_assets.informs as informs_mod

    def _forbidden(*_a: Any, **_k: Any) -> Any:
        raise AssertionError("a read must never open connect_write")

    with pytest.MonkeyPatch.context() as patch:
        patch.setattr(db_lock, "connect_write", _forbidden)
        if hasattr(informs_mod, "connect_write"):
            patch.setattr(informs_mod, "connect_write", _forbidden)
        assert _listed(_read(env, asset, "b-1")) == ["docA"]
    assert _state(env) == before


def test_t23_no_route_patches_deliverable_metadata(env: Env) -> None:
    """Informs are never a ``deliverables.metadata`` PATCH (signed §1.11a)."""
    spec = env.client.app.openapi()  # type: ignore[attr-defined]
    for path, operations in spec["paths"].items():
        if path.startswith(("/deliverables", "/write/deliverables")):
            assert not {"patch", "put"} & set(operations), path
    pattern = re.compile(r"UPDATE\s+deliverables\s+SET\b[^;\"']*\bmetadata\b", re.IGNORECASE)
    offenders = []
    for top in ("interfaces", "substrate", "orchestration", "runtime", "middleware", "processing"):
        base = ROOT / top
        if not base.is_dir():
            continue
        for path in base.rglob("*.py"):
            if pattern.search(path.read_text(encoding="utf-8", errors="replace")):
                offenders.append(str(path.relative_to(ROOT)))
    assert offenders == []


def test_t24_two_writers_on_one_revision_one_wins(env: Env) -> None:
    """Kills M1 (no CAS) under a real race."""
    asset, r1 = _seed(env)
    _docs(env, "docA", "docB")
    barrier = threading.Barrier(2)
    results: dict[str, Any] = {}

    def writer(name: str, doc: str) -> None:
        barrier.wait()
        results[name] = _put(env, asset, "b-1", _ids(doc), r1, f"k-{name}")

    threads = [threading.Thread(target=writer, args=(n, d)) for n, d in (("x", "docA"), ("y", "docB"))]
    for t in threads:
        t.start()
    for t in threads:
        t.join(timeout=60)
    statuses = sorted(r.status_code for r in results.values())
    assert statuses == [200, 409], {k: v.text for k, v in results.items()}
    winner = next(r for r in results.values() if r.status_code == 200)
    loser = next(r for r in results.values() if r.status_code == 409)
    assert loser.json() == {"reason": "revision_moved", "current_revision_id": winner.json()["revision_id"]}
    assert _state(env)["derived_asset_revisions"] == 2


def test_t24_one_key_in_two_threads_commits_once(env: Env) -> None:
    """Kills M5 (replay after the CAS) under a real race."""
    asset, r1 = _seed(env)
    _docs(env, "docA")
    barrier = threading.Barrier(2)
    results: list[Any] = []
    lock = threading.Lock()

    def writer() -> None:
        barrier.wait()
        r = _put(env, asset, "b-1", _ids("docA"), r1, "k-same")
        with lock:
            results.append(r)

    threads = [threading.Thread(target=writer) for _ in range(2)]
    for t in threads:
        t.start()
    for t in threads:
        t.join(timeout=60)
    assert [r.status_code for r in results] == [200, 200], [r.text for r in results]
    assert results[0].content == results[1].content
    state = _state(env)
    assert state["derived_asset_revisions"] == 2
    assert state["derived_asset_operations"] == 2  # the seed's create receipt and one commit


# ── T30: the edge reaches the route ────────────────────────────────────────


def test_t30_the_edge_allowlist_names_derived_assets() -> None:
    caddy = (ROOT / "infrastructure/ansible/templates/Caddyfile.j2").read_text(encoding="utf-8")
    line = next(line for line in caddy.splitlines() if line.strip().startswith("@api_routes path "))
    assert "/derived-assets*" in line.split()


def test_request_identity_is_the_canonical_json_of_path_and_body() -> None:
    """A4: sha256 of canonical ``{asset_id, block_id, body}``; no text
    normalization, so a different Unicode form is a different request."""
    from substrate.derived_assets.informs import request_sha256

    body = {"informs": [{"document_id": "dé"}], "expected_revision_id": "r", "idempotency_key": "k"}
    expected = hashlib.sha256(
        json.dumps(
            {"asset_id": "write:x", "block_id": "b", "body": body},
            sort_keys=True, separators=(",", ":"), ensure_ascii=False,
        ).encode("utf-8")
    ).hexdigest()
    assert request_sha256("write:x", "b", body) == expected
    decomposed = {**body, "informs": [{"document_id": "dé"}]}
    assert request_sha256("write:x", "b", decomposed) != expected
