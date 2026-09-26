"""The project registry and tab-tree routes (THREAD-CONTRACT §1.5, §1.6).

FastAPI TestClient against a real DuckDB. The auth middleware's
enforcement-disabled default stamps the single-operator identity, so the
requesting owner is ``__operator__``; another owner is made by re-keying a
row at the store layer.

The tab tests hold the contract's number rules: a public number comes only
from allocate and belongs to one tab forever; a hier number is final once
accepted; a dropped tab frees nothing; a stale or conflicting PUT writes
nothing and answers the current snapshot so the client can rebase.
"""

from __future__ import annotations

import json
import os
import tempfile
from pathlib import Path
from typing import Any

import pytest
from fastapi.testclient import TestClient

from interfaces.research.api.app import create_app
from interfaces.research.api.broadcast import EventBroadcaster
from runtime.db_lock import connect_read, connect_write
from substrate.graph import ensure_initialized
from substrate.graph.ops import insert_document

FIXTURE = Path(__file__).resolve().parents[1] / "apps/reading/src/lib/api/__fixtures__/projectTabs.snapshot.json"
SHA = "a" * 64


class RecordingBroadcaster(EventBroadcaster):
    def __init__(self) -> None:
        super().__init__()
        self.events: list[Any] = []

    async def broadcast(self, event: Any) -> None:
        self.events.append(event)
        await super().broadcast(event)


@pytest.fixture
def env(monkeypatch):
    for variable in (
        "ANTIEK_AUTH_SECRET", "ANTIEK_DEV_LOGIN_TOKEN", "ANTIEK_OPERATOR_EMAIL", "ANTIEK_OPERATOR_TOKEN",
        "ANTIEK_OPERATOR_SERVICE_TOKEN_CLIENT_ID", "CF_ACCESS_CLIENT_SECRET", "ANTIEK_COOKIE_INSECURE",
    ):
        monkeypatch.delenv(variable, raising=False)
    tmpdir = tempfile.mkdtemp(prefix="project-routes-")
    db = os.path.join(tmpdir, "t.duckdb")
    events = os.path.join(tmpdir, "events")
    os.makedirs(events, exist_ok=True)
    monkeypatch.setenv("ANTIEK_DUCKDB_PATH", db)
    monkeypatch.setenv("ANTIEK_RESEARCH_EVENTS_DIR", events)
    monkeypatch.setenv("ANTIEK_RESEARCH_ARTIFACTS_DIR", os.path.join(tmpdir, "artifacts"))
    monkeypatch.setenv("ANTIEK_EMBEDDING_PROVIDER", "hash")
    ensure_initialized(db)
    bus = RecordingBroadcaster()
    client = TestClient(create_app(register_wrestling=False, broadcaster=bus))
    return {"db": db, "client": client, "bus": bus}


def _project(env, title: str = "Bridge failures") -> str:
    r = env["client"].post("/projects", json={"title": title})
    assert r.status_code == 201, r.text
    return r.json()["project_id"]


def _alloc(env, pid: str, tab_id: str, mothership: str = "research") -> int:
    r = env["client"].post(f"/projects/{pid}/tabs/{mothership}/allocate", json={"tab_id": tab_id})
    assert r.status_code == 200, r.text
    return r.json()["public_number"]


def _node(tab_id: str, hier: str, *, parent: str | None = None, side: str = "left", kind: str | None = None,
          public: int | None = None, mothership: str = "research", **extra: Any) -> dict[str, Any]:
    node = {
        "tab_id": tab_id, "parent_tab_id": parent, "side": side,
        "kind": kind or ("reader" if side == "left" else "research"),
        "ref": f"ref-{tab_id}", "title": tab_id, "mothership": mothership,
        "public_number": public, "hier_number": hier, "child_order": [],
    }
    node.update(extra)
    return node


def _tree(*nodes: dict[str, Any]) -> dict[str, Any]:
    """A tree from nodes in order: roots and child_order follow the order
    the nodes are given in."""
    by_id = {n["tab_id"]: json.loads(json.dumps(n)) for n in nodes}
    for n in by_id.values():
        n["child_order"] = []
    roots = []
    for n in nodes:
        if n["parent_tab_id"] is None:
            roots.append(n["tab_id"])
        else:
            by_id[n["parent_tab_id"]]["child_order"].append(n["tab_id"])
    return {"nodes": by_id, "root_order": roots}


def _put(env, pid: str, tree: dict[str, Any], version: int, *, mothership: str = "research",
         active: dict[str, Any] | None = None):
    return env["client"].put(
        f"/projects/{pid}/tabs/{mothership}",
        json={"tree": tree, "active": active or {"left": None, "right": None}, "expected_version": version},
    )


def _count(db: str, sql: str, params: list[Any]) -> int:
    con = connect_read(db)
    try:
        return int(con.execute(sql, params).fetchone()[0])
    finally:
        con.close()


def _rekey_project(db: str, pid: str, owner: str) -> None:
    with connect_write(db, purpose="test/rekey-project") as con:
        con.execute("UPDATE write_folders SET owner_user_id = ? WHERE folder_id = ?", [owner, pid])


# ── Registry (§1.5) ─────────────────────────────────────────────────


def test_a_project_round_trips_and_archives_out_of_the_list(env):
    c = env["client"]
    pid = _project(env)
    listed = c.get("/projects").json()["projects"]
    assert [(p["project_id"], p["title"], p["kind"], p["pinned"]) for p in listed] == [
        (pid, "Bridge failures", "project", False)
    ]
    r = c.patch(f"/projects/{pid}", json={"title": "Bridges", "pinned": True, "order": 2.5})
    assert r.status_code == 200, r.text
    assert (r.json()["title"], r.json()["pinned"], r.json()["order"]) == ("Bridges", True, 2.5)
    assert c.patch(f"/projects/{pid}", json={"archived": True}).json()["archived_at"]
    assert c.get("/projects").json()["projects"] == []
    assert [p["project_id"] for p in c.get("/projects?include_archived=true").json()["projects"]] == [pid]
    assert c.patch(f"/projects/{pid}", json={"archived": False}).json()["archived_at"] is None


def test_a_project_body_is_validated(env):
    c = env["client"]
    assert c.post("/projects", json={"title": "  "}).status_code == 422
    assert c.post("/projects", json={"title": "x" * 201}).status_code == 422
    assert c.post("/projects", json={"title": "ok", "kind": "books"}).status_code == 422
    assert c.post("/projects", json={"title": "ok", "owner_user_id": "someone"}).status_code == 422
    pid = _project(env)
    assert c.patch(f"/projects/{pid}", json={"pinned": "yes"}).status_code == 422
    assert c.patch(f"/projects/{pid}", json={"order": True}).status_code == 422
    assert c.patch(f"/projects/{pid}", json={"owner_user_id": "someone"}).status_code == 422


def test_another_owners_project_reads_exactly_like_a_missing_one(env):
    c = env["client"]
    mine, theirs = _project(env, "Mine"), _project(env, "Theirs")
    _rekey_project(env["db"], theirs, "user-bob")
    assert [p["project_id"] for p in c.get("/projects").json()["projects"]] == [mine]
    missing = c.get("/projects/fld-does-not-exist")
    for response in (
        c.get(f"/projects/{theirs}"),
        c.patch(f"/projects/{theirs}", json={"title": "mine now"}),
        c.post(f"/projects/{theirs}/members", json={"member_kind": "document", "member_id": "d"}),
        c.delete(f"/projects/{theirs}/members/d"),
        c.get(f"/projects/{theirs}/tabs/research"),
        c.post(f"/projects/{theirs}/tabs/research/allocate", json={"tab_id": "t1"}),
        _put(env, theirs, _tree(), 0),
    ):
        assert (response.status_code, response.json()) == (missing.status_code, missing.json())
    assert missing.status_code == 404


def test_a_reading_project_names_its_book_and_is_promoted_in_place(env):
    c = env["client"]
    with connect_write(env["db"], purpose="test/seed-book") as con:
        insert_document(con, document_id="doc-book", source_tier=2, document_type="book", title="A Book",
                        source_uri="test://book", investigation_id="inv-seed")
    assert c.post("/projects", json={"title": "Book", "kind": "reading"}).status_code == 422
    assert c.post("/projects", json={"title": "Book", "kind": "reading",
                                     "primary_document_id": "doc-missing"}).status_code == 422
    assert c.post("/projects", json={"title": "P", "primary_document_id": "doc-book"}).status_code == 422
    r = c.post("/projects", json={"title": "Book", "kind": "reading", "primary_document_id": "doc-book"})
    assert r.status_code == 201, r.text
    pid = r.json()["project_id"]
    promoted = c.patch(f"/projects/{pid}", json={"kind": "project"})
    assert (promoted.json()["project_id"], promoted.json()["kind"]) == (pid, "project")
    assert c.patch(f"/projects/{pid}", json={"kind": "reading"}).status_code == 422


def test_members_are_typed_soft_edges(env):
    c = env["client"]
    pid = _project(env)
    add = c.post(f"/projects/{pid}/members", json={"member_kind": "document", "member_id": "doc-1"})
    assert (add.status_code, add.json()) == (201, {"status": "added"})
    again = c.post(f"/projects/{pid}/members", json={"member_kind": "document", "member_id": "doc-1"})
    assert (again.status_code, again.json()) == (200, {"status": "already_member"})
    clash = c.post(f"/projects/{pid}/members", json={"member_kind": "investigation", "member_id": "doc-1"})
    assert (clash.status_code, clash.json()["detail"]) == (409, "member_kind_conflict")
    assert c.post(f"/projects/{pid}/members", json={"member_kind": "chunk", "member_id": "c"}).status_code == 422
    c.post(f"/projects/{pid}/members", json={"member_kind": "investigation", "member_id": "inv-9"})
    got = c.get(f"/projects/{pid}").json()
    assert [(m["member_kind"], m["member_id"]) for m in got["members"]] == [
        ("document", "doc-1"), ("investigation", "inv-9")
    ]
    assert got["member_count"] == 2
    assert c.delete(f"/projects/{pid}/members/doc-1").json() == {"status": "removed"}
    assert c.delete(f"/projects/{pid}/members/doc-1").json() == {"status": "not_member"}


def test_write_folders_and_projects_are_the_same_rows(env):
    c = env["client"]
    folder = c.post("/write/folders", json={"name": "Outline sources"})
    assert folder.status_code == 201, folder.text
    fid = folder.json()["folder_id"]
    projects = c.get("/projects").json()["projects"]
    assert [(p["project_id"], p["title"], p["kind"]) for p in projects] == [(fid, "Outline sources", "project")]
    c.patch(f"/projects/{fid}", json={"title": "Renamed"})
    names = {f["folder_id"]: f["name"] for f in c.get("/write/folders").json()["folders"]}
    assert names[fid] == "Renamed"


def test_a_non_node_member_is_never_a_write_block(env):
    from substrate.write import folders

    c = env["client"]
    fid = c.post("/write/folders", json={"name": "Sources"}).json()["folder_id"]
    assert c.post(f"/write/folders/{fid}/blocks", json={"node_id": "node-1"}).status_code == 202
    c.post(f"/projects/{fid}/members", json={"member_kind": "document", "member_id": "doc-1"})
    con = connect_read(env["db"])
    try:
        assert folders.list_folder_node_ids(con, fid) == ["node-1"]
        assert folders.folders_for_node(con, "doc-1") == []
        assert not folders.is_block_in_folder(con, folder_id=fid, node_id="doc-1")
        assert [(f.folder_id, f.member_count) for f in folders.list_folders(con)] == [(fid, 1)]
    finally:
        con.close()
    assert c.get(f"/projects/{fid}").json()["member_count"] == 2


def test_write_folders_are_owner_scoped(env):
    c = env["client"]
    mine = c.post("/write/folders", json={"name": "Mine"}).json()["folder_id"]
    theirs = c.post("/write/folders", json={"name": "Theirs"}).json()["folder_id"]
    _rekey_project(env["db"], theirs, "user-bob")
    assert [f["folder_id"] for f in c.get("/write/folders").json()["folders"]] == [mine]
    assert c.post(f"/write/folders/{theirs}/blocks", json={"node_id": "n"}).status_code == 404
    assert c.delete(f"/write/folders/{theirs}/blocks/n").status_code == 404
    assert c.post(f"/write/folders/{mine}/blocks", json={"node_id": "n"}).status_code == 202


# ── Tab trees (§1.6) ────────────────────────────────────────────────


def test_the_shared_wire_fixture_round_trips(env):
    fixture = json.loads(FIXTURE.read_text())
    pid = _project(env)
    m = fixture["mothership"]
    assert [_alloc(env, pid, t, m) for t in fixture["allocate"]] == [1, 2, 3, 4]
    put1 = fixture["put1"]
    r1 = _put(env, pid, put1["tree"], put1["expected_version"], mothership=m, active=put1["active"])
    assert r1.status_code == 200, r1.text
    tree2 = json.loads(json.dumps(put1["tree"]))
    for dropped in fixture["put2"]["drop"]:
        del tree2["nodes"][dropped]
        tree2["root_order"].remove(dropped)
    put2 = fixture["put2"]
    r2 = _put(env, pid, tree2, put2["expected_version"], mothership=m, active=put2["active"])
    assert r2.status_code == 200, r2.text
    got = env["client"].get(f"/projects/{pid}/tabs/{m}").json()
    assert got == r2.json()
    expected = fixture["expected"]
    for entry in got["retired"]:
        assert entry.pop("closed_at").endswith("Z")
    for entry in expected["retired"]:
        entry.pop("closed_at")
    assert got == expected


def test_allocate_is_idempotent_per_tab_and_project_wide(env):
    pid = _project(env)
    assert _alloc(env, pid, "a") == 1
    assert _alloc(env, pid, "a") == 1
    assert _alloc(env, pid, "b", "writing") == 2
    assert _alloc(env, pid, "b", "writing") == 2
    assert _alloc(env, pid, "c", "reading") == 3
    bad = env["client"].post(f"/projects/{pid}/tabs/research/allocate", json={"tab_id": "no spaces"})
    assert (bad.status_code, bad.json()["reason"]) == (422, "tab_tree_invalid")


def test_a_public_number_another_tab_holds_is_a_number_conflict(env):
    pid = _project(env)
    _alloc(env, pid, "a")
    _alloc(env, pid, "b")
    r = _put(env, pid, _tree(_node("a", "1", public=1), _node("b", "2", public=1)), 0)
    assert r.status_code == 422  # the same number twice in one snapshot
    r = _put(env, pid, _tree(_node("b", "1", public=1)), 0)
    assert r.status_code == 409, r.text
    body = r.json()
    assert (body["reason"], body["tab_id"]) == ("number_conflict", "b")
    assert body["current"]["version"] == 0


def test_an_invented_public_number_is_refused(env):
    pid = _project(env)
    r = _put(env, pid, _tree(_node("a", "1", public=7)), 0)
    assert r.status_code == 422, r.text
    assert (r.json()["reason"], r.json()["tab_id"]) == ("tab_tree_invalid", "a")


def test_a_numbering_tab_is_accepted_and_given_its_registered_number(env):
    pid = _project(env)
    r = _put(env, pid, _tree(_node("a", "1")), 0)
    assert r.status_code == 200 and r.json()["tree"]["nodes"]["a"]["public_number"] is None
    _alloc(env, pid, "a")
    r = _put(env, pid, _tree(_node("a", "1")), 1)
    assert r.json()["tree"]["nodes"]["a"]["public_number"] == 1


def test_a_closed_tabs_numbers_are_never_reused_by_another_tab(env):
    pid = _project(env)
    _alloc(env, pid, "a")
    assert _put(env, pid, _tree(_node("a", "1", public=1)), 0).status_code == 200
    assert _put(env, pid, _tree(), 1).status_code == 200
    _alloc(env, pid, "c")
    reuse_public = _put(env, pid, _tree(_node("c", "2", public=1)), 2)
    assert (reuse_public.status_code, reuse_public.json()["reason"]) == (409, "number_conflict")
    reuse_hier = _put(env, pid, _tree(_node("c", "1", public=2)), 2)
    assert (reuse_hier.status_code, reuse_hier.json()["reason"]) == (409, "number_conflict")
    assert _put(env, pid, _tree(_node("c", "2", public=2)), 2).status_code == 200


def test_restoring_a_tab_reclaims_its_own_numbers(env):
    pid = _project(env)
    _alloc(env, pid, "a")
    node = _node("a", "1", public=1, side="right", kind="dialogue")
    _put(env, pid, _tree(node), 0)
    closed = _put(env, pid, _tree(), 1).json()
    assert [(e["node"]["tab_id"], e["close_mode"]) for e in closed["retired"]] == [("a", "close")]
    restored = _put(env, pid, _tree(closed["retired"][0]["node"]), 2)
    assert restored.status_code == 200, restored.text
    assert restored.json()["retired"] == []
    assert restored.json()["tree"]["nodes"]["a"] == node
    closed_again = _put(env, pid, _tree(), 3).json()
    assert len(closed_again["retired"]) == 1
    assert _count(env["db"], "SELECT COUNT(*) FROM project_tab_retirements WHERE tab_id = 'a'", []) == 2


def test_a_stale_put_is_version_stale_with_the_current_snapshot(env):
    pid = _project(env)
    assert _put(env, pid, _tree(_node("a", "1")), 0).status_code == 200
    r = _put(env, pid, _tree(_node("b", "1")), 0)
    assert r.status_code == 409
    body = r.json()
    assert body["reason"] == "version_stale"
    assert body["current"]["version"] == 1
    assert list(body["current"]["tree"]["nodes"]) == ["a"]
    assert env["client"].get(f"/projects/{pid}/tabs/research").json()["version"] == 1


def test_a_spawn_made_during_an_inflight_save_survives_the_409(env):
    """D6-F11: two devices at version 1 each spawn a child under tab p. The
    first save lands; the second is refused with the current snapshot,
    renumbers its pending child from the new counter, and both survive."""
    pid = _project(env)
    base = [_node("p", "1")]
    assert _put(env, pid, _tree(*base), 0).status_code == 200
    first = _put(env, pid, _tree(*base, _node("x", "1.1", parent="p")), 1)
    assert first.status_code == 200
    second = _put(env, pid, _tree(*base, _node("y", "1.1", parent="p")), 1)
    assert (second.status_code, second.json()["reason"]) == (409, "version_stale")
    current = second.json()["current"]
    k = current["next_child_index"]["p"]
    assert k == 2
    rebased = _tree(*base, _node("x", "1.1", parent="p"), _node("y", f"1.{k}", parent="p"))
    ok = _put(env, pid, rebased, current["version"])
    assert ok.status_code == 200, ok.text
    assert ok.json()["tree"]["nodes"]["p"]["child_order"] == ["x", "y"]
    assert ok.json()["next_child_index"]["p"] == 3


def test_a_new_hier_number_below_its_parents_counter_is_a_number_conflict(env):
    pid = _project(env)
    assert _put(env, pid, _tree(_node("p", "1"), _node("x", "1.3", parent="p")), 0).status_code == 200
    r = _put(env, pid, _tree(_node("p", "1"), _node("x", "1.3", parent="p"), _node("y", "1.2", parent="p")), 1)
    assert (r.status_code, r.json()["reason"], r.json()["tab_id"]) == (409, "number_conflict", "y")
    wrong_parent = _put(env, pid, _tree(_node("p", "1"), _node("x", "1.3", parent="p"),
                                        _node("y", "2.4", parent="p")), 1)
    assert (wrong_parent.status_code, wrong_parent.json()["tab_id"]) == (422, "y")


def test_new_siblings_are_measured_against_the_accepted_counter(env):
    pid = _project(env)
    r = _put(env, pid, _tree(_node("p", "1"), _node("b", "1.3", parent="p"), _node("a", "1.1", parent="p")), 0)
    assert r.status_code == 200, r.text
    assert r.json()["next_child_index"] == {"root": 2, "p": 4}


def test_an_accepted_hier_number_is_final_but_survives_a_lift(env):
    pid = _project(env)
    tree = _tree(_node("p", "1"), _node("q", "1.1", parent="p"), _node("r", "1.1.1", parent="q"))
    assert _put(env, pid, tree, 0).status_code == 200
    renumbered = _put(env, pid, _tree(_node("p", "1"), _node("q", "1.2", parent="p"),
                                      _node("r", "1.1.1", parent="q")), 1)
    assert (renumbered.status_code, renumbered.json()["tab_id"]) == (422, "q")
    lifted = _put(env, pid, _tree(_node("p", "1"), _node("r", "1.1.1", parent="p")), 1)
    assert lifted.status_code == 200, lifted.text
    assert [(e["node"]["tab_id"], e["close_mode"]) for e in lifted.json()["retired"]] == [("q", "lift_children")]


def test_close_modes_are_read_off_the_diff(env):
    pid = _project(env)
    tree = _tree(_node("a", "1"), _node("a1", "1.1", parent="a"), _node("a11", "1.1.1", parent="a1"),
                 _node("b", "2"), _node("c", "3"), _node("c1", "3.1", parent="c"))
    assert _put(env, pid, tree, 0).status_code == 200
    after = _put(env, pid, _tree(_node("c1", "3.1")), 1)
    assert after.status_code == 200, after.text
    modes = {e["node"]["tab_id"]: e["close_mode"] for e in after.json()["retired"]}
    assert modes == {"a": "prune", "a1": "prune", "a11": "prune", "b": "close", "c": "lift_children"}
    pruned = {e["node"]["tab_id"]: e["node"].get("pruned_at") for e in after.json()["retired"]}
    assert all(pruned[t] for t in ("a", "a1", "a11")) and pruned["b"] is None


def test_retirements_page_exactly_by_closed_at(env):
    pid = _project(env)
    assert _put(env, pid, _tree(_node("a", "1"), _node("b", "2"), _node("c", "3")), 0).status_code == 200
    after = _put(env, pid, _tree(), 1).json()
    stamps = [e["closed_at"] for e in after["retired"]]
    assert len(set(stamps)) == 3 and stamps == sorted(stamps, reverse=True)
    c = env["client"]
    first = c.get(f"/projects/{pid}/tabs/research/retired?limit=2").json()
    assert [e["node"]["tab_id"] for e in first["retired"]] == ["c", "b"]
    second = c.get(f"/projects/{pid}/tabs/research/retired",
                   params={"limit": 2, "before": first["next_before"]}).json()
    assert [e["node"]["tab_id"] for e in second["retired"]] == ["a"]
    assert second["next_before"] is None


def test_each_mothership_keeps_its_own_tree(env):
    pid = _project(env)
    _alloc(env, pid, "r1", "research")
    assert _put(env, pid, _tree(_node("r1", "1", public=1)), 0).status_code == 200
    writing = env["client"].get(f"/projects/{pid}/tabs/writing").json()
    assert (writing["version"], writing["tree"]) == (0, {"nodes": {}, "root_order": []})
    stolen = _put(env, pid, _tree(_node("r1", "1", public=1, mothership="writing")), 0, mothership="writing")
    assert (stolen.status_code, stolen.json()["tab_id"]) == (422, "r1")
    mixed = _put(env, pid, _tree(_node("w1", "1", mothership="research")), 0, mothership="writing")
    assert mixed.status_code == 422
    assert env["client"].get(f"/projects/{pid}/tabs/books").status_code == 404


def test_branch_origins_are_checked(env):
    pid = _project(env)
    origin = {"document_id": "doc-1", "kind": "agent"}
    no_opener = _put(env, pid, _tree(_node("a", "1", branch_origin=origin)), 0)
    assert (no_opener.status_code, no_opener.json()["reason"]) == (422, "tab_origin_invalid")
    island = _put(env, pid, _tree(_node("a", "1", branch_origin={"document_id": "doc-1", "kind": "island"})), 0)
    assert (island.status_code, island.json()["reason"]) == (422, "tab_origin_invalid")
    ok = _put(env, pid, _tree(_node("a", "1", branch_origin=origin,
                                    opened_by={"thread_id": "inv-1", "agent_kind": "research"})), 0)
    assert ok.status_code == 200, ok.text


@pytest.mark.parametrize(
    "tree, active",
    [
        ({"nodes": {}}, None),
        ({"nodes": {}, "root_order": [], "history": {}}, None),
        (_tree(_node("a", "1", pruned_at="2026-09-26T00:00:00Z")), None),
        (_tree(_node("a", "1", side="left", kind="research")), None),
        (_tree(_node("a", "1", side="right", kind="reader")), None),
        (_tree(_node("a", "1", color="red")), None),
        (_tree(_node("a", "1.0")), None),
        ({"nodes": {"a": _node("a", "1", parent="b"), "b": _node("b", "2", parent="a")}, "root_order": []}, None),
        ({"nodes": {"a": _node("a", "1")}, "root_order": ["a", "a"]}, None),
        ({"nodes": {"x": _node("a", "1")}, "root_order": ["x"]}, None),
        (_tree(_node("a", "1")), {"left": None, "right": "a"}),
        (_tree(_node("a", "1")), {"left": "zzz", "right": None}),
        (_tree(_node("a", "1")), {"left": None}),
    ],
)
def test_malformed_snapshots_are_tab_tree_invalid(env, tree, active):
    pid = _project(env)
    r = _put(env, pid, tree, 0, active=active)
    assert (r.status_code, r.json()["reason"]) == (422, "tab_tree_invalid"), r.text


def test_a_put_body_is_exactly_tree_active_and_expected_version(env):
    pid = _project(env)
    c = env["client"]
    url = f"/projects/{pid}/tabs/research"
    empty = {"nodes": {}, "root_order": []}
    active = {"left": None, "right": None}
    assert c.put(url, json={"tree": empty, "active": active}).status_code == 422
    assert c.put(url, json={"tree": empty, "active": active, "expected_version": 0, "x": 1}).status_code == 422
    assert c.put(url, json={"tree": empty, "active": active, "expected_version": -1}).status_code == 422
    assert c.put(url, json={"tree": empty, "active": active, "expected_version": True}).status_code == 422


def test_a_refused_put_writes_nothing(env):
    pid = _project(env)
    _alloc(env, pid, "held")
    _put(env, pid, _tree(_node("held", "1", public=1)), 0)
    registers = "SELECT COUNT(*) FROM tab_hier_numbers"
    retirements = "SELECT COUNT(*) FROM project_tab_retirements"
    before = (_count(env["db"], registers, []), _count(env["db"], retirements, []))
    # "fresh" registers hier 2 before "thief" is refused for the public
    # number "held" owns, and dropping "held" would retire it. The snapshot
    # is well formed, so the refusal comes from the registers, mid-write:
    # the rollback must take the register row with it.
    r = _put(env, pid, _tree(_node("fresh", "2"), _node("thief", "3", public=1)), 1)
    assert (r.status_code, r.json()["reason"], r.json()["tab_id"]) == (409, "number_conflict", "thief")
    assert (_count(env["db"], registers, []), _count(env["db"], retirements, [])) == before
    current = env["client"].get(f"/projects/{pid}/tabs/research").json()
    assert (current["version"], list(current["tree"]["nodes"]), current["retired"]) == (1, ["held"], [])
    assert _put(env, pid, _tree(_node("held", "1", public=1), _node("fresh", "2")), 1).status_code == 200


def test_an_accepted_put_broadcasts_the_version_and_nothing_else(env):
    pid = _project(env)
    assert _put(env, pid, _tree(_node("a", "1")), 0).status_code == 200
    assert _put(env, pid, _tree(_node("b", "1")), 0).status_code == 409
    bumps = [e for e in env["bus"].events if e.action_type == "project.tabs.version_bumped"]
    assert len(bumps) == 1
    payload = bumps[0].payload
    assert (payload.project_id, payload.mothership, payload.version) == (pid, "research", 1)
    assert bumps[0].investigation_id == f"project-{pid}"
