"""Workstation routes (workstation-tabs SPR-01) — the container's
persistence + the corpus tabTree's server adapter.

GET /workstations · POST /workstations · PUT /workstations/{id}
(full-replace, optimistic revision — 409 on stale, never a silent clobber)
· DELETE /workstations/{id} · and the TabTreeAdapter's server side:
GET /workstations/{id}/tab-tree · PUT (expected_version — 409 on conflict,
the client rebases) · POST .../allocate (server-allocated, monotonic,
NEVER reused).

Owner-scoped per the books.py:140 convention (_reader_owner_id — ownership
from middleware state, never from request data). REFS-ONLY payloads: a
surface payload carrying a text field beyond a small id/locator is a 422
(the DB CHECK on byte size is the backstop). Snapshots are validated
server-side on save — a tree failing the corpus model's wire-shape +
number-contract invariants is a 422, never persisted.

The reconciliation note (PR #3431) governs: this module is the CONTAINER's
persistence, which stands as specced; the chrome (D2 keymap, D6 tabTree
client model, the cockpit chrome) is the corpus's — nothing here
reimplements it.
"""

from __future__ import annotations

from typing import Any, Literal

from fastapi import FastAPI, HTTPException, Request
from pydantic import BaseModel, Field

from interfaces.research.api.books import _reader_owner_id, _resolve_db_path
from substrate.workstations.schema import (
    SURFACE_KINDS,
    TAB_PAYLOAD_MAX_BYTES,
)
from substrate.workstations.store import (
    TabTreeStore,
    WorkstationStore,
    WorkstationTabRow,
    WorkstationWithTabs,
    mint_tab_id,
)


class WorkstationCreateIn(BaseModel):
    name: str = Field(min_length=1, max_length=80)
    color_token: Literal["sun", "aurora", "emperor", "success", "muted"] = "sun"


class TabIn(BaseModel):
    tab_id: str | None = None  # absent → the server mints one
    surface_kind: str
    """Refs-only: ids and small locators, never content (validated below;
    the DB CHECK on byte size is the backstop)."""
    surface_payload: dict[str, Any] = Field(default_factory=dict)


class WorkstationReplaceIn(BaseModel):
    name: str = Field(min_length=1, max_length=80)
    color_token: Literal["sun", "aurora", "emperor", "success", "muted"] = "sun"
    tabs: list[TabIn] = Field(default_factory=list)
    """Optimistic concurrency: the revision the client last saw."""
    revision: int = Field(ge=0)


class TabOut(BaseModel):
    tab_id: str
    surface_kind: str
    surface_payload: dict[str, Any]


class WorkstationOut(BaseModel):
    workstation_id: str
    name: str
    color_token: str
    position: int
    revision: int
    tabs: list[TabOut]


class WorkstationListOut(BaseModel):
    workstations: list[WorkstationOut]
    count: int


class TabTreeOut(BaseModel):
    workstation_id: str
    """The corpus wire shape: {tree, active_tab_id, retired_numbers} +
    the server's version (the client's next expected_version)."""
    snapshot: dict[str, Any]
    version: int


class TabTreeSaveIn(BaseModel):
    snapshot: dict[str, Any]
    expected_version: int = Field(ge=0)


class AllocateOut(BaseModel):
    public_number: int


def _ws_out(w: WorkstationWithTabs) -> WorkstationOut:
    return WorkstationOut(
        workstation_id=w.workstation.workstation_id,
        name=w.workstation.name,
        color_token=w.workstation.color_token,
        position=w.workstation.position,
        revision=w.workstation.revision,
        tabs=[
            TabOut(
                tab_id=t.tab_id,
                surface_kind=t.surface_kind,
                surface_payload=json_loads(t.surface_payload_json),
            )
            for t in w.tabs
        ],
    )


def json_loads(raw: str) -> Any:
    import json

    return json.loads(raw)


def _validate_payload_refs(payload: dict[str, Any]) -> None:
    """The refs-only rule at the API boundary: every string value is an id
    or a small locator — anything longer is content smuggling (422)."""
    import json as _json

    def walk(value: Any) -> None:
        if isinstance(value, str) and len(value) > 200:
            raise HTTPException(
                status_code=422,
                detail="surface_payload_not_refs: ids and small locators only",
            )
        if isinstance(value, dict):
            for v in value.values():
                walk(v)
        elif isinstance(value, list):
            for v in value:
                walk(v)

    walk(payload)
    if len(_json.dumps(payload)) > TAB_PAYLOAD_MAX_BYTES:
        raise HTTPException(
            status_code=422,
            detail="surface_payload_too_large: refs only, never content",
        )


def _validate_tree_snapshot(snapshot: dict[str, Any]) -> None:
    """The corpus model's invariants at the server boundary (tabTree.ts's
    fromSnapshot wire shape + the public_number contract): a failing tree is
    a 422, never persisted."""
    problems: list[str] = []
    tree = snapshot.get("tree")
    if (
        not isinstance(tree, dict)
        or not isinstance(tree.get("nodes"), dict)
        or not isinstance(tree.get("history"), dict)
        or not isinstance(tree.get("root_order"), list)
    ):
        raise HTTPException(
            status_code=422, detail="invalid_snapshot: snapshot.tree is malformed"
        )
    nodes = tree["nodes"]
    history = tree["history"]
    all_nodes = [nodes[k] for k in nodes] + [
        history[k].get("node") for k in history if isinstance(history[k], dict)
    ]
    numbers: dict[int, str] = {}
    for n in all_nodes:
        if (
            not isinstance(n, dict)
            or not isinstance(n.get("tab_id"), str)
            or not isinstance(n.get("hier_number"), str)
            or not isinstance(n.get("child_order"), list)
        ):
            problems.append("a node is malformed")
            continue
        pn = n.get("public_number")
        if pn is not None:
            if not isinstance(pn, int) or pn < 1:
                problems.append(f"{n.get('tab_id')}: public_number must be a positive integer")
            elif pn in numbers:
                problems.append(f"public number {pn} is held by two tabs")
            else:
                numbers[pn] = n["tab_id"]
    # The retired-numbers consistency (the model's fromSnapshot rule):
    # every closed tab's public number is retired — never reusable.
    retired = snapshot.get("retired_numbers") or []
    retired_numbers = {
        r.get("public_number") for r in retired if isinstance(r, dict)
    }
    for k in history:
        node = history[k].get("node") if isinstance(history[k], dict) else None
        if isinstance(node, dict):
            pn = node.get("public_number")
            if pn is not None and pn not in retired_numbers:
                problems.append(f"{node.get('tab_id')}: a closed tab's number is not retired")
    if problems:
        raise HTTPException(
            status_code=422, detail="invalid_snapshot: " + "; ".join(problems)
        )


def register_workstation_routes(app: FastAPI) -> None:
    """Mount the workstation routes. One call from create_app."""

    @app.get(
        "/workstations",
        response_model=WorkstationListOut,
        tags=["workstations"],
    )
    def list_workstations(request: Request) -> WorkstationListOut:
        from runtime.db_lock import connect_read

        owner = _reader_owner_id(request)
        db = _resolve_db_path()
        con = connect_read(db)
        try:
            rows = WorkstationStore().list_for_owner(con, owner_user_id=owner)
        finally:
            con.close()
        return WorkstationListOut(
            workstations=[_ws_out(w) for w in rows], count=len(rows)
        )

    @app.post(
        "/workstations",
        response_model=WorkstationOut,
        status_code=201,
        tags=["workstations"],
    )
    def create_workstation(body: WorkstationCreateIn, request: Request) -> WorkstationOut:
        from runtime.db_lock import connect_write

        owner = _reader_owner_id(request)
        db = _resolve_db_path()
        with connect_write(db, purpose="workstations/create") as con:
            position = len(WorkstationStore().list_for_owner(con, owner_user_id=owner))
            row = WorkstationStore().create_workstation(
                con, owner_user_id=owner, name=body.name, color_token=body.color_token,
                position=position,
            )
        return WorkstationOut(
            workstation_id=row.workstation_id,
            name=row.name,
            color_token=row.color_token,
            position=row.position,
            revision=row.revision,
            tabs=[],
        )

    @app.put(
        "/workstations/{workstation_id}",
        response_model=WorkstationOut,
        tags=["workstations"],
    )
    def replace_workstation(
        workstation_id: str, body: WorkstationReplaceIn, request: Request
    ) -> WorkstationOut:
        from runtime.db_lock import connect_write

        owner = _reader_owner_id(request)
        db = _resolve_db_path()
        with connect_write(db, purpose="workstations/replace") as con, con.transaction():
            # The 404/409 distinction: the read is owner-scoped, then the
            # revision check — never a silent clobber.
            existing = WorkstationStore().get_for_owner(
                con, owner_user_id=owner, workstation_id=workstation_id
            )
            if existing is None:
                raise HTTPException(status_code=404, detail="workstation_not_found")
            if body.revision != existing.revision:
                raise HTTPException(
                    status_code=409,
                    detail="workstation_stale_revision: the set moved — re-read and retry",
                )
            tab_rows: list[tuple[str, int, str, str]] = []
            for i, tab in enumerate(body.tabs):
                if tab.surface_kind not in SURFACE_KINDS:
                    raise HTTPException(
                        status_code=422,
                        detail=f"surface_kind_unknown: {tab.surface_kind}",
                    )
                _validate_payload_refs(tab.surface_payload)
                import json as _json

                tab_rows.append(
                    (
                        tab.tab_id or mint_tab_id(),
                        i,
                        tab.surface_kind,
                        _json.dumps(tab.surface_payload, sort_keys=True),
                    )
                )
            row = WorkstationStore().replace_workstation(
                con,
                owner_user_id=owner,
                workstation_id=workstation_id,
                name=body.name,
                color_token=body.color_token,
                tabs=tab_rows,
                expected_revision=body.revision,
            )
            assert row is not None  # the checks above landed it
            tabs = con.execute(
                "SELECT tab_id, workstation_id, position, surface_kind, "
                "surface_payload_json, created_at, updated_at FROM workstation_tabs "
                "WHERE workstation_id = ? ORDER BY position ASC, tab_id ASC",
                [workstation_id],
            ).fetchall()
        return _ws_out(
            WorkstationWithTabs(
                workstation=row,
                tabs=tuple(WorkstationTabRow(
                    tab_id=str(t[0]), workstation_id=str(t[1]), position=int(t[2]),
                    surface_kind=str(t[3]), surface_payload_json=str(t[4]),
                    created_at=str(t[5]), updated_at=str(t[6]),
                ) for t in tabs),
            )
        )

    @app.delete(
        "/workstations/{workstation_id}",
        status_code=204,
        tags=["workstations"],
    )
    def delete_workstation(workstation_id: str, request: Request) -> None:
        from runtime.db_lock import connect_write

        owner = _reader_owner_id(request)
        db = _resolve_db_path()
        with connect_write(db, purpose="workstations/delete") as con:
            gone = WorkstationStore().delete_workstation(
                con, owner_user_id=owner, workstation_id=workstation_id
            )
        if not gone:
            raise HTTPException(status_code=404, detail="workstation_not_found")
        return

    # ── The corpus tabTree adapter's server side ────────────────────────

    @app.get(
        "/workstations/{workstation_id}/tab-tree",
        response_model=TabTreeOut,
        tags=["workstations", "tab-tree"],
    )
    def load_tab_tree(workstation_id: str, request: Request) -> TabTreeOut:
        from runtime.db_lock import connect_read

        owner = _reader_owner_id(request)
        db = _resolve_db_path()
        con = connect_read(db)
        try:
            existing = WorkstationStore().get_for_owner(
                con, owner_user_id=owner, workstation_id=workstation_id
            )
            if existing is None:
                raise HTTPException(status_code=404, detail="workstation_not_found")
            row = TabTreeStore().load_tree(
                con, owner_user_id=owner, workstation_id=workstation_id
            )
        finally:
            con.close()
        if row is None:
            # No tree yet — the empty snapshot at version 0 (the client's
            # emptyTabTree shape, honestly absent rather than fabricated).
            return TabTreeOut(workstation_id=workstation_id, snapshot={}, version=0)
        return TabTreeOut(
            workstation_id=workstation_id,
            snapshot=json_loads(row.tree_json),
            version=row.version,
        )

    @app.put(
        "/workstations/{workstation_id}/tab-tree",
        response_model=TabTreeOut,
        tags=["workstations", "tab-tree"],
    )
    def save_tab_tree(
        workstation_id: str, body: TabTreeSaveIn, request: Request
    ) -> TabTreeOut:
        from runtime.db_lock import connect_write

        owner = _reader_owner_id(request)
        db = _resolve_db_path()
        with connect_write(db, purpose="workstations/tab-tree/save") as con, con.transaction():
                existing = WorkstationStore().get_for_owner(
                    con, owner_user_id=owner, workstation_id=workstation_id
                )
                if existing is None:
                    raise HTTPException(status_code=404, detail="workstation_not_found")
                _validate_tree_snapshot(body.snapshot)
                import json as _json

                row = TabTreeStore().save_tree(
                    con,
                    owner_user_id=owner,
                    workstation_id=workstation_id,
                    tree_json=_json.dumps(body.snapshot, sort_keys=True),
                    expected_version=body.expected_version,
                )
                if row is None:
                    raise HTTPException(
                        status_code=409,
                        detail="tab_tree_version_conflict: the tree moved — rebase and retry",
                    )
        return TabTreeOut(
            workstation_id=workstation_id,
            snapshot=json_loads(row.tree_json),
            version=row.version,
        )

    @app.post(
        "/workstations/{workstation_id}/tab-tree/allocate",
        response_model=AllocateOut,
        tags=["workstations", "tab-tree"],
    )
    def allocate_number(workstation_id: str, request: Request) -> AllocateOut:
        """The corpus's number contract, server-enforced: workstation-wide,
        monotonic, NEVER reused."""
        from runtime.db_lock import connect_write

        owner = _reader_owner_id(request)
        db = _resolve_db_path()
        with connect_write(db, purpose="workstations/tab-tree/allocate") as con:
            existing = WorkstationStore().get_for_owner(
                con, owner_user_id=owner, workstation_id=workstation_id
            )
            if existing is None:
                raise HTTPException(status_code=404, detail="workstation_not_found")
            n = TabTreeStore().allocate_number(
                con, owner_user_id=owner, workstation_id=workstation_id
            )
        return AllocateOut(public_number=n)
