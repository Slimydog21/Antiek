"""Project registry and tab-tree routes (THREAD-CONTRACT §1.5, §1.6).

``/projects`` is the registry over ``write_folders``; ``/write/folders``
stays Write's alias over the same rows. Every route resolves its owner from
middleware state (``_reader_owner_id``), never from the request, and another
owner's project answers exactly like a missing one.

The tab routes answer the contract's error bodies at the top level, so the
client narrows on ``reason`` without parsing strings:

- ``409 {reason: "version_stale", current}``
- ``409 {reason: "number_conflict", tab_id, detail, current}``
- ``422 {reason: "tab_origin_invalid" | "tab_tree_invalid", tab_id, detail}``

``current`` is the GET shape, read under the same write lock after the
refused PUT rolled back. An accepted PUT answers the new snapshot in the
GET shape, then broadcasts ``project.tabs.version_bumped``.
"""

from __future__ import annotations

import asyncio
import json
import sys
import uuid
from datetime import UTC, datetime
from typing import Any

from fastapi import Body, FastAPI, HTTPException, Query, Request
from fastapi.responses import JSONResponse

from interfaces.research.api.books import _reader_owner_id, _resolve_db_path
from substrate.projects import registry, tabs
from substrate.projects.schema import MOTHERSHIPS, init_projects_schema


def _project_out(p: registry.Project) -> dict[str, Any]:
    return {
        "project_id": p.project_id,
        "title": p.title,
        "kind": p.kind,
        "order": p.order,
        "pinned": p.pinned,
        "archived_at": p.archived_at,
        "primary_document_id": p.primary_document_id,
        "created_at": p.created_at,
        "updated_at": p.updated_at,
        "member_count": p.member_count,
    }


def _refuse(error: registry.ProjectError) -> HTTPException:
    return HTTPException(status_code=error.status, detail=error.code)


def _require_mothership(mothership: str) -> None:
    if mothership not in MOTHERSHIPS:
        raise HTTPException(status_code=404, detail="mothership_unknown")


def _invalid(error: tabs.TreeInvalid) -> JSONResponse:
    return JSONResponse(
        status_code=422, content={"reason": error.reason, "tab_id": error.tab_id, "detail": error.detail}
    )


def _body_fields(body: Any, allowed: set[str], required: set[str]) -> dict[str, Any]:
    """The body's fields, refusing an unknown or a missing one as
    ``tab_tree_invalid`` (the tab routes' one 422 shape)."""
    if not isinstance(body, dict):
        raise tabs.TreeInvalid("the body is a JSON object")
    unknown = sorted(set(body) - allowed)
    if unknown:
        raise tabs.TreeInvalid(f"unknown fields: {', '.join(unknown)}")
    missing = sorted(required - set(body))
    if missing:
        raise tabs.TreeInvalid(f"missing fields: {', '.join(missing)}")
    return body


async def _broadcast_version(request: Request, project_id: str, mothership: str, version: int) -> None:
    """Tell other devices the tree moved. Best effort: the PUT has committed,
    and a client that misses this refetches on its next load or 409."""
    from substrate.constants import ANTIEK_PARAM_VERSION
    from substrate.schemas.events import Event, ProjectTabsVersionBumpedPayload

    bus = getattr(request.app.state, "broadcaster", None)
    if bus is None:
        return
    payload = ProjectTabsVersionBumpedPayload(project_id=project_id, mothership=mothership, version=version)
    event = Event(
        event_id=f"evt-{uuid.uuid4().hex}",
        investigation_id=f"project-{project_id}",
        action_type=payload.action_type,
        payload=payload,
        param_version=ANTIEK_PARAM_VERSION,
        emitted_at=datetime.now(UTC),
    )
    try:
        await bus.broadcast(event)
    except Exception as exc:  # the write stands; only the live notice is lost
        print(f"project tabs broadcast failed for {project_id}/{mothership}: {exc!r}", file=sys.stderr)


def register_project_routes(app: FastAPI) -> None:
    """Mount /projects. One call from create_app."""

    from runtime.db_lock import connect_read, connect_write

    # ── Registry (§1.5) ──────────────────────────────────────────────

    @app.get("/projects", tags=["projects"])
    def list_projects(request: Request, include_archived: bool = Query(default=False)) -> dict[str, Any]:
        owner = _reader_owner_id(request)
        con = connect_read(_resolve_db_path())
        try:
            items = registry.list_projects(con, owner_user_id=owner, include_archived=include_archived)
        finally:
            con.close()
        return {"projects": [_project_out(p) for p in items]}

    @app.post("/projects", status_code=201, tags=["projects"])
    def create_project(request: Request, body: dict[str, Any] = Body(...)) -> dict[str, Any]:
        owner = _reader_owner_id(request)
        unknown = sorted(set(body) - {"title", "kind", "primary_document_id"})
        if unknown:
            raise HTTPException(status_code=422, detail="project_body_invalid")
        with connect_write(_resolve_db_path(), purpose="projects/create") as con:
            init_projects_schema(con)
            try:
                project = registry.create_project(
                    con,
                    owner_user_id=owner,
                    title=body.get("title"),
                    kind=body.get("kind", "project"),
                    primary_document_id=body.get("primary_document_id"),
                )
            except registry.ProjectError as e:
                raise _refuse(e) from None
        return _project_out(project)

    @app.get("/projects/{project_id}", tags=["projects"])
    def get_project(project_id: str, request: Request) -> dict[str, Any]:
        owner = _reader_owner_id(request)
        con = connect_read(_resolve_db_path())
        try:
            project = registry.require_project(con, owner_user_id=owner, project_id=project_id)
            members = registry.list_members(con, owner_user_id=owner, project_id=project_id)
        except registry.ProjectError as e:
            raise _refuse(e) from None
        finally:
            con.close()
        out = _project_out(project)
        out["members"] = [
            {"member_kind": m.member_kind, "member_id": m.member_id, "added_at": m.added_at} for m in members
        ]
        return out

    @app.patch("/projects/{project_id}", tags=["projects"])
    def patch_project(project_id: str, request: Request, body: dict[str, Any] = Body(...)) -> dict[str, Any]:
        owner = _reader_owner_id(request)
        with connect_write(_resolve_db_path(), purpose="projects/patch") as con:
            init_projects_schema(con)
            try:
                project = registry.update_project(con, owner_user_id=owner, project_id=project_id, changes=body)
            except registry.ProjectError as e:
                raise _refuse(e) from None
        return _project_out(project)

    @app.post("/projects/{project_id}/members", tags=["projects"])
    def add_member(project_id: str, request: Request, body: dict[str, Any] = Body(...)) -> JSONResponse:
        owner = _reader_owner_id(request)
        if sorted(body) != ["member_id", "member_kind"]:
            raise HTTPException(status_code=422, detail="member_body_invalid")
        with connect_write(_resolve_db_path(), purpose="projects/members/add") as con:
            init_projects_schema(con)
            try:
                status = registry.add_member(
                    con,
                    owner_user_id=owner,
                    project_id=project_id,
                    member_kind=body["member_kind"],
                    member_id=body["member_id"],
                )
            except registry.ProjectError as e:
                raise _refuse(e) from None
        return JSONResponse(status_code=201 if status == "added" else 200, content={"status": status})

    @app.delete("/projects/{project_id}/members/{member_id}", tags=["projects"])
    def remove_member(project_id: str, member_id: str, request: Request) -> dict[str, Any]:
        owner = _reader_owner_id(request)
        with connect_write(_resolve_db_path(), purpose="projects/members/remove") as con:
            init_projects_schema(con)
            try:
                status = registry.remove_member(con, owner_user_id=owner, project_id=project_id, member_id=member_id)
            except registry.ProjectError as e:
                raise _refuse(e) from None
        return {"status": status}

    # ── Tab trees (§1.6) ─────────────────────────────────────────────

    @app.get("/projects/{project_id}/tabs/{mothership}", tags=["projects", "tabs"])
    def get_tabs(project_id: str, mothership: str, request: Request) -> dict[str, Any]:
        owner = _reader_owner_id(request)
        _require_mothership(mothership)
        con = connect_read(_resolve_db_path())
        try:
            registry.require_project(con, owner_user_id=owner, project_id=project_id)
            snapshot = tabs.read_snapshot(con, owner_user_id=owner, project_id=project_id, mothership=mothership)
        except registry.ProjectError as e:
            raise _refuse(e) from None
        finally:
            con.close()
        return snapshot.to_wire()

    @app.get("/projects/{project_id}/tabs/{mothership}/retired", tags=["projects", "tabs"])
    def get_retired(
        project_id: str,
        mothership: str,
        request: Request,
        before: str | None = Query(default=None),
        limit: int = Query(default=tabs.RETIRED_PAGE_MAX, ge=1, le=tabs.RETIRED_PAGE_MAX),
    ) -> dict[str, Any]:
        owner = _reader_owner_id(request)
        _require_mothership(mothership)
        cursor = None
        if before is not None:
            try:
                cursor = datetime.fromisoformat(before)
            except ValueError:
                raise HTTPException(status_code=422, detail="before_invalid") from None
            if cursor.tzinfo is None:
                raise HTTPException(status_code=422, detail="before_invalid")
        con = connect_read(_resolve_db_path())
        try:
            registry.require_project(con, owner_user_id=owner, project_id=project_id)
            page = tabs.retired_page(
                con, owner_user_id=owner, project_id=project_id, mothership=mothership, before=cursor, limit=limit
            )
        except registry.ProjectError as e:
            raise _refuse(e) from None
        finally:
            con.close()
        return {"retired": page, "next_before": page[-1]["closed_at"] if len(page) == limit else None}

    def _put(owner: str, project_id: str, mothership: str, body: Any) -> tuple[int, dict[str, Any]]:
        try:
            fields = _body_fields(body, {"tree", "active", "expected_version"}, {"tree", "active", "expected_version"})
            if len(json.dumps(fields["tree"])) > tabs.MAX_TREE_JSON_BYTES:
                raise tabs.TreeInvalid(f"a tree is at most {tabs.MAX_TREE_JSON_BYTES} bytes of JSON")
        except tabs.TreeInvalid as e:
            return 422, {"reason": e.reason, "tab_id": e.tab_id, "detail": e.detail}
        with connect_write(_resolve_db_path(), purpose="projects/tabs/put") as con:
            init_projects_schema(con)
            try:
                registry.require_project(con, owner_user_id=owner, project_id=project_id)
            except registry.ProjectError as e:
                raise _refuse(e) from None
            try:
                with con.transaction():
                    snapshot = tabs.put_snapshot(
                        con,
                        owner_user_id=owner,
                        project_id=project_id,
                        mothership=mothership,
                        tree=fields["tree"],
                        active=fields["active"],
                        expected_version=fields["expected_version"],
                    )
            except tabs.TreeInvalid as e:
                return 422, {"reason": e.reason, "tab_id": e.tab_id, "detail": e.detail}
            except tabs.VersionStale:
                current = tabs.read_snapshot(con, owner_user_id=owner, project_id=project_id, mothership=mothership)
                return 409, {"reason": "version_stale", "current": current.to_wire()}
            except tabs.NumberConflict as e:
                current = tabs.read_snapshot(con, owner_user_id=owner, project_id=project_id, mothership=mothership)
                return 409, {"reason": "number_conflict", "tab_id": e.tab_id, "detail": e.detail,
                             "current": current.to_wire()}
        return 200, snapshot.to_wire()

    @app.put("/projects/{project_id}/tabs/{mothership}", tags=["projects", "tabs"])
    async def put_tabs(
        project_id: str, mothership: str, request: Request, body: Any = Body(...)
    ) -> JSONResponse:
        owner = _reader_owner_id(request)
        _require_mothership(mothership)
        status, content = await asyncio.to_thread(_put, owner, project_id, mothership, body)
        if status == 200:
            await _broadcast_version(request, project_id, mothership, int(content["version"]))
        return JSONResponse(status_code=status, content=content)

    @app.post("/projects/{project_id}/tabs/{mothership}/allocate", tags=["projects", "tabs"])
    def allocate_tab(project_id: str, mothership: str, request: Request, body: Any = Body(...)) -> JSONResponse:
        owner = _reader_owner_id(request)
        _require_mothership(mothership)
        try:
            fields = _body_fields(body, {"tab_id"}, {"tab_id"})
        except tabs.TreeInvalid as e:
            return _invalid(e)
        with connect_write(_resolve_db_path(), purpose="projects/tabs/allocate") as con:
            init_projects_schema(con)
            try:
                registry.require_project(con, owner_user_id=owner, project_id=project_id)
            except registry.ProjectError as e:
                raise _refuse(e) from None
            try:
                with con.transaction():
                    number = tabs.allocate(
                        con, owner_user_id=owner, project_id=project_id, mothership=mothership,
                        tab_id=fields["tab_id"],
                    )
            except tabs.TreeInvalid as e:
                return _invalid(e)
        return JSONResponse(status_code=200, content={"public_number": number})
