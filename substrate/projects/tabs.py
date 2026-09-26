"""Tab trees: server-side, per account, per mode (THREAD-CONTRACT §1.6).

One tree per (owner, project, mothership) holds both panes of that mode.
The client applies operations locally and PUTs whole-tree snapshots with
the version it descends from; a stale version is a 409 carrying the current
snapshot, so the client rebases and every local spawn survives.

Numbers are addresses and never reused:

- A ``public_number`` is allocated per ``tab_id`` by ``allocate`` (idempotent,
  project-wide across motherships) and registered in ``tab_public_numbers``.
- A ``hier_number`` is computed by the client as ``<parent's>.<k>`` from the
  parent's server-maintained counter, and registered on the PUT that first
  carries it. Once accepted it is final, even if a later lift moves the tab
  under another parent.

Both registers are append-only, and every reuse check reads them, never a
diff against the previous snapshot, so a tab dropped from a snapshot never
frees its numbers. The diff only records history: a dropped node is written
to ``project_tab_retirements`` with its whole node, and a PUT that brings the
same ``tab_id`` back marks that row restored.

Everything a PUT writes happens in the caller's transaction, and every
refusal raises, so a refused PUT leaves nothing behind.
"""

from __future__ import annotations

import json
import re
from dataclasses import dataclass, field
from datetime import UTC, datetime, timedelta
from typing import Any

from runtime.db_lock import LockedConnection
from substrate.projects.registry import iso
from substrate.projects.schema import BRANCH_ORIGIN_KINDS, TAB_KINDS_BY_SIDE, table_exists

MAX_NODES = 1000
MAX_TREE_JSON_BYTES = 1_000_000
RETIRED_PAGE_MAX = 200
ROOT_KEY = "root"

TAB_ID_RE = re.compile(r"[A-Za-z0-9_-]{1,64}")
# Depth is unbounded (Part 2 §2.2); the 1,000-tab bound limits it.
HIER_RE = re.compile(r"[1-9][0-9]{0,8}(?:\.[1-9][0-9]{0,8})*")
SHA256_RE = re.compile(r"[0-9a-f]{64}")

_NODE_KEYS = frozenset({
    "tab_id", "parent_tab_id", "side", "kind", "ref", "title", "mothership", "pane", "public_number",
    "hier_number", "branch_origin", "opened_by", "child_order", "last_visited_child_id", "pruned_at",
})
_ORIGIN_KEYS = frozenset({"document_id", "anchor", "kind"})
_ANCHOR_KEYS = frozenset({
    "document_id", "source_locator", "region_id", "quote", "prefix", "suffix", "page_index", "anchor_id",
})
_LOCATOR_KEYS = frozenset({"start", "end", "text_sha256", "block_id"})
_OPENED_BY_KEYS = frozenset({"thread_id", "agent_kind"})
_PANE_KEYS = frozenset({"docked_kind", "docked_ref"})


class TabsError(Exception):
    """Base of the refusals a PUT or an allocate can raise."""


class VersionStale(TabsError):
    """The PUT descends from an older version: 409 ``version_stale``."""


class NumberConflict(TabsError):
    """A node carries a number the register gives another tab, or a new hier
    number below its parent's counter: 409 ``number_conflict``."""

    def __init__(self, tab_id: str, detail: str) -> None:
        super().__init__(f"{tab_id}: {detail}")
        self.tab_id = tab_id
        self.detail = detail


class TreeInvalid(TabsError):
    """A malformed snapshot: 422. ``reason`` is ``tab_origin_invalid`` for a
    bad branch origin (a bad kind, or an ``agent`` node without
    ``opened_by``) and ``tab_tree_invalid`` for anything else."""

    def __init__(self, detail: str, tab_id: str | None = None, reason: str = "tab_tree_invalid") -> None:
        super().__init__(f"{reason}: {detail}")
        self.reason = reason
        self.tab_id = tab_id
        self.detail = detail


@dataclass(frozen=True)
class Snapshot:
    """The GET shape (contract §1.6), also the ``current`` of every 409."""

    tree: dict[str, Any]
    active: dict[str, str | None]
    version: int
    next_child_index: dict[str, int]
    retired: list[dict[str, Any]] = field(default_factory=list)

    def to_wire(self) -> dict[str, Any]:
        return {
            "tree": self.tree,
            "active": dict(self.active),
            "version": self.version,
            "next_child_index": dict(self.next_child_index),
            "retired": list(self.retired),
        }


def empty_tree() -> dict[str, Any]:
    return {"nodes": {}, "root_order": []}


# ---------------------------------------------------------------------------
# Validation: pure, before any database read
# ---------------------------------------------------------------------------


def _is_str(value: Any, max_len: int, *, min_len: int = 1) -> bool:
    return isinstance(value, str) and min_len <= len(value) <= max_len


def _is_count(value: Any, *, minimum: int = 0) -> bool:
    return isinstance(value, int) and not isinstance(value, bool) and value >= minimum


def _check_keys(value: Any, allowed: frozenset[str], what: str, tab_id: str) -> dict[str, Any]:
    if not isinstance(value, dict):
        raise TreeInvalid(f"{what} is not an object", tab_id)
    unknown = sorted(set(value) - allowed)
    if unknown:
        raise TreeInvalid(f"{what} has unknown fields: {', '.join(unknown)}", tab_id)
    return value


def _check_anchor(anchor: Any, tab_id: str) -> None:
    a = _check_keys(anchor, _ANCHOR_KEYS, "branch_origin.anchor", tab_id)
    if not _is_str(a.get("document_id"), 256):
        raise TreeInvalid("branch_origin.anchor.document_id is required", tab_id)
    locator = a.get("source_locator")
    if locator is not None:
        loc = _check_keys(locator, _LOCATOR_KEYS, "branch_origin.anchor.source_locator", tab_id)
        start, end = loc.get("start"), loc.get("end")
        if not (isinstance(start, int) and isinstance(end, int) and _is_count(start) and _is_count(end)
                and end >= start):
            raise TreeInvalid("source_locator needs 0 <= start <= end", tab_id)
        if not (isinstance(loc.get("text_sha256"), str) and SHA256_RE.fullmatch(loc["text_sha256"])):
            raise TreeInvalid("source_locator.text_sha256 is a sha256 hex digest", tab_id)
        if "block_id" in loc and loc["block_id"] is not None and not _is_str(loc["block_id"], 256):
            raise TreeInvalid("source_locator.block_id is a string", tab_id)
    for key, limit in (("region_id", 256), ("anchor_id", 64), ("quote", 2000), ("prefix", 2000), ("suffix", 2000)):
        if a.get(key) is not None and not _is_str(a[key], limit, min_len=0):
            raise TreeInvalid(f"branch_origin.anchor.{key} is a string of at most {limit} characters", tab_id)
    if a.get("page_index") is not None and not _is_count(a["page_index"]):
        raise TreeInvalid("branch_origin.anchor.page_index is a non-negative integer", tab_id)


def _check_node(key: str, node: Any, mothership: str) -> None:
    n = _check_keys(node, _NODE_KEYS, "node", key)
    tab_id = n.get("tab_id")
    if not isinstance(tab_id, str) or not TAB_ID_RE.fullmatch(tab_id):
        raise TreeInvalid("tab_id is 1 to 64 letters, digits, '-' or '_'", key)
    if tab_id != key:
        raise TreeInvalid(f"node is keyed {key!r} but names tab_id {tab_id!r}", key)
    if n.get("parent_tab_id") is not None and not isinstance(n["parent_tab_id"], str):
        raise TreeInvalid("parent_tab_id is a string or null", tab_id)
    side = n.get("side")
    if side not in TAB_KINDS_BY_SIDE:
        raise TreeInvalid("side is left or right", tab_id)
    if n.get("kind") not in TAB_KINDS_BY_SIDE[side]:
        raise TreeInvalid(f"a {side} tab's kind is one of {', '.join(TAB_KINDS_BY_SIDE[side])}", tab_id)
    if not _is_str(n.get("ref"), 256):
        raise TreeInvalid("ref is a non-empty string", tab_id)
    if not _is_str(n.get("title"), 300, min_len=0):
        raise TreeInvalid("title is a string of at most 300 characters", tab_id)
    if n.get("mothership") != mothership:
        raise TreeInvalid(f"a node in the {mothership} tree has mothership {n.get('mothership')!r}", tab_id)
    if n.get("pane") is not None:
        pane = _check_keys(n["pane"], _PANE_KEYS, "pane", tab_id)
        for k, v in pane.items():
            if v is not None and not _is_str(v, 256):
                raise TreeInvalid(f"pane.{k} is a string", tab_id)
    if n.get("public_number") is not None and not _is_count(n["public_number"], minimum=1):
        raise TreeInvalid("public_number is a positive integer or null", tab_id)
    if not (isinstance(n.get("hier_number"), str) and HIER_RE.fullmatch(n["hier_number"])):
        raise TreeInvalid("hier_number is dotted positive integers, like 3.2.1", tab_id)
    opened_by = n.get("opened_by")
    if opened_by is not None:
        ob = _check_keys(opened_by, _OPENED_BY_KEYS, "opened_by", tab_id)
        if not (_is_str(ob.get("thread_id"), 256) and _is_str(ob.get("agent_kind"), 64)):
            raise TreeInvalid("opened_by is {thread_id, agent_kind}", tab_id, "tab_origin_invalid")
    origin = n.get("branch_origin")
    if origin is not None:
        o = _check_keys(origin, _ORIGIN_KEYS, "branch_origin", tab_id)
        if o.get("kind") not in BRANCH_ORIGIN_KINDS:
            raise TreeInvalid(f"branch_origin.kind {o.get('kind')!r} is not a branch origin", tab_id, "tab_origin_invalid")
        if o["kind"] == "agent" and opened_by is None:
            raise TreeInvalid("an agent-opened tab needs opened_by", tab_id, "tab_origin_invalid")
        if not _is_str(o.get("document_id"), 256):
            raise TreeInvalid("branch_origin.document_id is required", tab_id)
        if o.get("anchor") is not None:
            _check_anchor(o["anchor"], tab_id)
    child_order = n.get("child_order")
    if not isinstance(child_order, list) or not all(isinstance(c, str) for c in child_order):
        raise TreeInvalid("child_order is a list of tab ids", tab_id)
    if n.get("last_visited_child_id") is not None and n["last_visited_child_id"] not in child_order:
        raise TreeInvalid("last_visited_child_id is one of the tab's children", tab_id)
    if n.get("pruned_at") is not None and not _is_str(n["pruned_at"], 40):
        raise TreeInvalid("pruned_at is a timestamp string or null", tab_id)


def validate_snapshot(tree: Any, active: Any, mothership: str) -> list[str]:
    """Check a snapshot's shape and structure. Returns its tab ids in tree
    order (parents before children), or raises ``TreeInvalid``."""
    if not isinstance(tree, dict) or set(tree) != {"nodes", "root_order"}:
        raise TreeInvalid("tree is {nodes, root_order}")
    nodes, root_order = tree["nodes"], tree["root_order"]
    if not isinstance(nodes, dict) or not isinstance(root_order, list):
        raise TreeInvalid("tree.nodes is an object and tree.root_order a list")
    if len(nodes) > MAX_NODES:
        raise TreeInvalid(f"a tree holds at most {MAX_NODES} tabs")
    for key, node in nodes.items():
        _check_node(key, node, mothership)

    children: dict[str, list[str]] = {key: [] for key in nodes}
    roots: list[str] = []
    for key, node in nodes.items():
        parent = node.get("parent_tab_id")
        if parent is None:
            roots.append(key)
        elif parent == key or parent not in nodes:
            raise TreeInvalid(f"parent_tab_id {parent!r} is not an open tab", key)
        else:
            children[parent].append(key)
    if len(root_order) != len(set(root_order)) or set(root_order) != set(roots):
        raise TreeInvalid("root_order lists every root tab exactly once")
    for key, node in nodes.items():
        order = node["child_order"]
        if len(order) != len(set(order)) or set(order) != set(children[key]):
            raise TreeInvalid("child_order lists every child exactly once", key)

    ordered: list[str] = []
    frontier = list(root_order)
    while frontier:
        tab_id = frontier.pop(0)
        ordered.append(tab_id)
        frontier.extend(nodes[tab_id]["child_order"])
    if len(ordered) != len(nodes):
        raise TreeInvalid("the parent links form a cycle")

    seen_public: dict[int, str] = {}
    seen_hier: dict[str, str] = {}
    for tab_id in ordered:
        node = nodes[tab_id]
        number = node.get("public_number")
        if number is not None:
            if number in seen_public:
                raise TreeInvalid(f"public_number {number} is on two tabs", tab_id)
            seen_public[number] = tab_id
        if node["hier_number"] in seen_hier:
            raise TreeInvalid(f"hier_number {node['hier_number']} is on two tabs", tab_id)
        seen_hier[node["hier_number"]] = tab_id

    if not isinstance(active, dict) or set(active) != {"left", "right"}:
        raise TreeInvalid("active is {left, right}")
    for side in ("left", "right"):
        target = active[side]
        if target is None:
            continue
        if not isinstance(target, str) or target not in nodes or nodes[target]["side"] != side:
            raise TreeInvalid(f"active.{side} is null or an open {side} tab", target if isinstance(target, str) else None)
    return ordered


# ---------------------------------------------------------------------------
# Reads
# ---------------------------------------------------------------------------


def _retired(
    con: Any, owner_user_id: str, project_id: str, mothership: str, before: datetime | None, limit: int
) -> list[dict[str, Any]]:
    if not table_exists(con, "project_tab_retirements"):
        return []
    sql = (
        "SELECT closed_at, close_mode, node_json FROM project_tab_retirements "
        "WHERE owner_user_id = ? AND project_id = ? AND mothership = ? AND restored_at IS NULL"
    )
    params: list[Any] = [owner_user_id, project_id, mothership]
    if before is not None:
        sql += " AND closed_at < ?"
        params.append(before)
    sql += " ORDER BY closed_at DESC LIMIT ?"
    params.append(limit)
    return [
        {"closed_at": iso(r[0]), "close_mode": str(r[1]), "node": json.loads(r[2])}
        for r in con.execute(sql, params).fetchall()
    ]


def read_snapshot(con: Any, *, owner_user_id: str, project_id: str, mothership: str) -> Snapshot:
    """The current snapshot, with the 200 most recent unrestored retirements
    read on the same connection. A tree never written is version 0."""
    row = None
    if table_exists(con, "project_tabs"):
        row = con.execute(
            "SELECT tree_json, active_left, active_right, next_child_index_json, version FROM project_tabs "
            "WHERE owner_user_id = ? AND project_id = ? AND mothership = ?",
            [owner_user_id, project_id, mothership],
        ).fetchone()
    retired = _retired(con, owner_user_id, project_id, mothership, None, RETIRED_PAGE_MAX)
    if row is None:
        return Snapshot(empty_tree(), {"left": None, "right": None}, 0, {}, retired)
    return Snapshot(
        tree=json.loads(row[0]),
        active={"left": row[1], "right": row[2]},
        version=int(row[4]),
        next_child_index={str(k): int(v) for k, v in json.loads(row[3]).items()},
        retired=retired,
    )


def retired_page(
    con: Any, *, owner_user_id: str, project_id: str, mothership: str, before: datetime | None, limit: int
) -> tuple[list[dict[str, Any]], str | None]:
    """Older unrestored retirements, newest first, and the cursor for the
    next page, or None when this page is the last. ``closed_at`` is unique
    per (owner, project, mothership), so ``before`` pages exactly. One row
    past the page is read, so an exactly full last page still answers None."""
    size = max(1, min(limit, RETIRED_PAGE_MAX))
    rows = _retired(con, owner_user_id, project_id, mothership, before, size + 1)
    page = rows[:size]
    return page, (page[-1]["closed_at"] if len(rows) > size else None)


# ---------------------------------------------------------------------------
# Writes (the caller holds the write lock and a transaction)
# ---------------------------------------------------------------------------


def allocate(
    con: LockedConnection,
    *,
    owner_user_id: str,
    project_id: str,
    mothership: str,
    tab_id: Any,
    now: datetime | None = None,
) -> int:
    """The tab's public number: its registered one if it has one (so a retry
    from any device burns nothing), else the project's next number."""
    if not isinstance(tab_id, str) or not TAB_ID_RE.fullmatch(tab_id):
        raise TreeInvalid("tab_id is 1 to 64 letters, digits, '-' or '_'")
    held = con.execute(
        "SELECT public_number FROM tab_public_numbers WHERE owner_user_id = ? AND project_id = ? AND tab_id = ?",
        [owner_user_id, project_id, tab_id],
    ).fetchone()
    if held is not None:
        return int(held[0])
    counter = con.execute(
        "SELECT next_public_number FROM project_tab_counters WHERE owner_user_id = ? AND project_id = ?",
        [owner_user_id, project_id],
    ).fetchone()
    number = 1 if counter is None else int(counter[0])
    con.execute(
        "INSERT INTO tab_public_numbers (owner_user_id, project_id, public_number, tab_id, mothership, issued_at) "
        "VALUES (?, ?, ?, ?, ?, ?)",
        [owner_user_id, project_id, number, tab_id, mothership, now or datetime.now(UTC)],
    )
    con.execute(
        "INSERT INTO project_tab_counters (owner_user_id, project_id, next_public_number) VALUES (?, ?, ?) "
        "ON CONFLICT (owner_user_id, project_id) DO UPDATE SET next_public_number = excluded.next_public_number",
        [owner_user_id, project_id, number + 1],
    )
    return number


def _close_mode(tab_id: str, previous: dict[str, Any], kept: dict[str, Any], dropped: set[str],
                memo: dict[str, str]) -> str:
    """How a dropped tab left, read off the diff: its children were lifted
    if any of them stayed; it was pruned if it took children with it or went
    with a pruned parent; otherwise it was closed.

    Called in the previous tree's order, parents first, so a dropped
    parent's mode is already in ``memo``: no recursion, whatever the depth."""
    node = previous[tab_id]
    children = node.get("child_order") or []
    parent = node.get("parent_tab_id")
    if any(child in kept for child in children):
        mode = "lift_children"
    elif children or (parent in dropped and memo.get(parent) == "prune"):
        mode = "prune"
    else:
        mode = "close"
    memo[tab_id] = mode
    return mode


def _tree_order(tree: dict[str, Any]) -> list[str]:
    ordered: list[str] = []
    frontier = list(tree.get("root_order") or [])
    nodes = tree.get("nodes") or {}
    while frontier:
        tab_id = frontier.pop(0)
        if tab_id in nodes:
            ordered.append(tab_id)
            frontier.extend(nodes[tab_id].get("child_order") or [])
    return ordered


def put_snapshot(
    con: LockedConnection,
    *,
    owner_user_id: str,
    project_id: str,
    mothership: str,
    tree: Any,
    active: Any,
    expected_version: Any,
    now: datetime | None = None,
) -> Snapshot:
    """Accept a snapshot, or raise ``TreeInvalid``, ``VersionStale`` or
    ``NumberConflict``. Run it inside ``con.transaction()``: a refusal
    raised after a register write must roll that write back."""
    ordered = validate_snapshot(tree, active, mothership)
    if not _is_count(expected_version):
        raise TreeInvalid("expected_version is a non-negative integer")
    stamp = now or datetime.now(UTC)
    scope = [owner_user_id, project_id, mothership]

    row = con.execute(
        "SELECT tree_json, next_child_index_json, version FROM project_tabs "
        "WHERE owner_user_id = ? AND project_id = ? AND mothership = ?",
        scope,
    ).fetchone()
    current_version = 0 if row is None else int(row[2])
    if expected_version != current_version:
        raise VersionStale(f"expected version {expected_version}, current {current_version}")
    previous = empty_tree() if row is None else json.loads(row[0])
    # Every new k is measured against the counters of the accepted snapshot,
    # never against counters this PUT has already moved: new siblings arrive
    # in child_order, which the operator may have reordered.
    floors: dict[str, int] = {} if row is None else {str(k): int(v) for k, v in json.loads(row[1]).items()}
    counters = dict(floors)

    public_by_tab: dict[str, tuple[int, str]] = {}
    tab_by_public: dict[int, str] = {}
    for tab_id, number, owner_mothership in con.execute(
        "SELECT tab_id, public_number, mothership FROM tab_public_numbers WHERE owner_user_id = ? AND project_id = ?",
        [owner_user_id, project_id],
    ).fetchall():
        public_by_tab[str(tab_id)] = (int(number), str(owner_mothership))
        tab_by_public[int(number)] = str(tab_id)
    hier_by_tab: dict[str, str] = {}
    tab_by_hier: dict[str, str] = {}
    for tab_id, hier in con.execute(
        "SELECT tab_id, hier_number FROM tab_hier_numbers WHERE owner_user_id = ? AND project_id = ? AND mothership = ?",
        scope,
    ).fetchall():
        hier_by_tab[str(tab_id)] = str(hier)
        tab_by_hier[str(hier)] = str(tab_id)

    nodes: dict[str, Any] = tree["nodes"]
    previous_nodes: dict[str, Any] = previous.get("nodes") or {}
    restorable = {
        str(r[0])
        for r in con.execute(
            "SELECT DISTINCT tab_id FROM project_tab_retirements WHERE owner_user_id = ? AND project_id = ? "
            "AND mothership = ? AND restored_at IS NULL",
            scope,
        ).fetchall()
    }
    stored: dict[str, dict[str, Any]] = {}
    for tab_id in ordered:
        node = dict(nodes[tab_id])
        # A retired pruned node carries pruned_at, and a restore PUTs that
        # node back unchanged. It is taken only as a restore, and the open
        # tree never stores it: the tab is open again.
        if node.pop("pruned_at", None) is not None and (tab_id in previous_nodes or tab_id not in restorable):
            raise TreeInvalid("pruned_at belongs to a retired tab; only a restore may carry it", tab_id)
        registered = public_by_tab.get(tab_id)
        if registered is not None and registered[1] != mothership:
            raise TreeInvalid(f"this tab's number was allocated in the {registered[1]} tree", tab_id)
        number = node.get("public_number")
        if number is None:
            if registered is not None:
                node["public_number"] = registered[0]
        else:
            holder = tab_by_public.get(number)
            if holder is None:
                raise TreeInvalid(f"public_number {number} was never allocated; numbers come from allocate", tab_id)
            if holder != tab_id:
                raise NumberConflict(tab_id, f"public_number {number} belongs to another tab")

        hier = node["hier_number"]
        accepted = hier_by_tab.get(tab_id)
        if accepted is not None:
            if hier != accepted:
                if tab_by_hier.get(hier) is not None:
                    raise NumberConflict(tab_id, f"hier_number {hier} belongs to another tab")
                raise TreeInvalid(f"hier_number {hier} differs from its accepted {accepted}; numbers are final", tab_id)
        else:
            parent = node.get("parent_tab_id")
            key = ROOT_KEY if parent is None else parent
            prefix = "" if parent is None else stored[parent]["hier_number"] + "."
            tail = hier[len(prefix):] if hier.startswith(prefix) else ""
            if not tail or "." in tail:
                expected = f"{prefix}<k>" if prefix else "<k>"
                raise TreeInvalid(f"a new tab's hier_number is {expected}, not {hier}", tab_id)
            if tab_by_hier.get(hier) is not None:
                raise NumberConflict(tab_id, f"hier_number {hier} belongs to another tab")
            k = int(tail)
            floor = floors.get(key, 1)
            if k < floor:
                raise NumberConflict(tab_id, f"hier_number {hier} is below its parent's next index {floor}")
            con.execute(
                "INSERT INTO tab_hier_numbers (owner_user_id, project_id, mothership, hier_number, tab_id, issued_at) "
                "VALUES (?, ?, ?, ?, ?, ?)",
                [*scope, hier, tab_id, stamp],
            )
            hier_by_tab[tab_id] = hier
            tab_by_hier[hier] = tab_id
            counters[key] = max(counters.get(key, 1), k + 1)
        stored[tab_id] = node

    dropped = [tab_id for tab_id in _tree_order(previous) if tab_id not in nodes]
    if dropped:
        latest = con.execute(
            "SELECT max(closed_at) FROM project_tab_retirements "
            "WHERE owner_user_id = ? AND project_id = ? AND mothership = ?",
            scope,
        ).fetchone()[0]
        start = stamp if latest is None or stamp > latest else latest + timedelta(microseconds=1)
        dropped_set = set(dropped)
        memo: dict[str, str] = {}
        for i, tab_id in enumerate(dropped):
            closed_at = start + timedelta(microseconds=i)
            mode = _close_mode(tab_id, previous_nodes, nodes, dropped_set, memo)
            node_json = dict(previous_nodes[tab_id])
            if mode == "prune":
                node_json["pruned_at"] = iso(closed_at)
            con.execute(
                "INSERT INTO project_tab_retirements (owner_user_id, project_id, mothership, tab_id, closed_at, "
                "close_mode, node_json) VALUES (?, ?, ?, ?, ?, ?, ?)",
                [*scope, tab_id, closed_at, mode, json.dumps(node_json, sort_keys=True)],
            )
    for tab_id in ordered:
        if tab_id not in previous_nodes:
            con.execute(
                "UPDATE project_tab_retirements SET restored_at = ? WHERE owner_user_id = ? AND project_id = ? "
                "AND mothership = ? AND tab_id = ? AND restored_at IS NULL",
                [stamp, *scope, tab_id],
            )

    stored_tree = {"nodes": stored, "root_order": list(tree["root_order"])}
    con.execute(
        "INSERT INTO project_tabs (owner_user_id, project_id, mothership, tree_json, active_left, active_right, "
        "next_child_index_json, version, updated_at) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?) "
        "ON CONFLICT (owner_user_id, project_id, mothership) DO UPDATE SET tree_json = excluded.tree_json, "
        "active_left = excluded.active_left, active_right = excluded.active_right, "
        "next_child_index_json = excluded.next_child_index_json, version = excluded.version, "
        "updated_at = excluded.updated_at",
        [*scope, json.dumps(stored_tree, sort_keys=True), active["left"], active["right"],
         json.dumps(counters, sort_keys=True), current_version + 1, stamp],
    )
    return read_snapshot(con, owner_user_id=owner_user_id, project_id=project_id, mothership=mothership)
