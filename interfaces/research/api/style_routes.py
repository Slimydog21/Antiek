"""Style-wheel HTTP API (spec §5.5 S2, bounded to the API + persistence).

``GET /styles``                 — the wheel: builtins + the caller's forks.
``POST /styles``                — create/fork a style (validated; forks
                                  only, builtin names are 409).
``DELETE /styles/{name}``       — remove a fork (builtins 409, unknown 404).
``GET /artifacts/{id}/render``  — re-project a stored artifact HTML in a
                                  chosen style (``restyle_artifact`` — NO
                                  model call, deterministic).

Per-user persistence: forks are stored keyed by ``user_id``
(``substrate/styles/store.py``). Every request assembles the caller's wheel
as ``default_registry()`` (the builtins) with that user's forks layered on
top — the builtins are always present and can never be overridden or
removed. Style resolution happens HERE, in the route handler (spec R5): a
style slug is resolved through the user's merged registry and passed to the
renderer BY VALUE, so ``render``/``restyle_artifact`` never read ambient
state (the determinism invariant, I3).

User identity: ``request.state.user_id`` is populated by the operator-auth
middleware in ``app.py``; the same static ``"__operator__"`` fallback the
rest of the API uses when auth is disabled.
"""

from __future__ import annotations

import logging
from pathlib import Path

from fastapi import APIRouter, HTTPException, Request
from fastapi.responses import HTMLResponse
from pydantic import BaseModel

from services.html_projection.context import RenderContext
from services.html_projection.gate import ScriptViolation, assert_script_free
from services.html_projection.island import IslandError
from services.html_projection.renderer import restyle_artifact
from services.html_projection.styles import (
    ProjectionStyle,
    StyleError,
    StyleRegistry,
    default_registry,
    validate_style,
)
from substrate.research_artifact.paths import artifact_path_for
from substrate.styles import UserStyleStore

_log = logging.getLogger(__name__)

style_router = APIRouter(tags=["styles"])

# A stored artifact HTML is a bounded, self-contained document (inlined
# CSS). Cap the read so a corrupted/oversized file cannot be read into
# memory wholesale.
_MAX_ARTIFACT_BYTES = 10 * 1024 * 1024


def _db_path() -> str:
    from substrate.graph import default_db_path, ensure_initialized

    path = default_db_path()
    ensure_initialized(path)
    return path


def _store() -> UserStyleStore:
    return UserStyleStore(_db_path())


def _user_id(request: Request) -> str:
    """The canonical identity attached by the auth middleware; the same
    static operator fallback as the rest of the API."""
    return str(getattr(request.state, "user_id", None) or "__operator__")


def _merged_registry(user_id: str) -> StyleRegistry:
    """The caller's wheel: builtins in fixed order, then their forks in
    creation order.

    Stored forks re-run validation on load (defense in depth — a fork is
    untrusted input even after it was once accepted). A stored fork that
    would now FAIL validation is skipped with a log line rather than
    bricking the whole wheel: every row was validated at write time, so
    this can only happen after a validator/gate tightening, and the honest
    v1 behavior is a degraded wheel, not a 500.
    """
    registry = default_registry()
    for fork in _store().list_for_user(user_id):
        try:
            registry.register(fork)
        except StyleError:
            _log.warning(
                "skipping stored style fork %r for user %r: no longer valid",
                fork.name,
                user_id,
            )
    return registry


class StyleOut(BaseModel):
    name: str
    label: str
    description: str
    builtin: bool
    source_fidelity: bool
    theme_css: str


class StyleIn(BaseModel):
    name: str
    label: str
    description: str = ""
    theme_css: str = ""
    source_fidelity: bool = False


class StyleListOut(BaseModel):
    styles: list[StyleOut]


def _to_out(style: ProjectionStyle) -> StyleOut:
    return StyleOut(
        name=style.name,
        label=style.label,
        description=style.description,
        builtin=style.builtin,
        source_fidelity=style.source_fidelity,
        theme_css=style.theme_css,
    )


@style_router.get("/styles", response_model=StyleListOut)
async def get_styles(request: Request) -> StyleListOut:
    """The wheel: builtins first (fixed order), then the caller's forks."""
    return StyleListOut(
        styles=[_to_out(s) for s in _merged_registry(_user_id(request)).list_styles()]
    )


@style_router.post("/styles", response_model=StyleOut, status_code=201)
async def post_style(body: StyleIn, request: Request) -> StyleOut:
    """Create (or replace) a fork on the caller's wheel.

    The body is treated as untrusted input: it is validated through the
    SAME zero-script + external-asset gate the renderer's output must pass
    (``validate_style``) before anything is persisted. Builtin names are
    refused with 409 — the house defaults are stable anchors on the wheel;
    fork one under a new name instead. Re-posting an existing fork's name
    replaces that fork (wheel position is preserved).
    """
    user_id = _user_id(request)
    registry = _merged_registry(user_id)
    existing = registry.get(body.name) if registry.has(body.name) else None
    if existing is not None and existing.builtin:
        raise HTTPException(
            status_code=409,
            detail=(
                f"cannot override builtin style {body.name!r}; "
                "fork it under a new name"
            ),
        )
    style = ProjectionStyle(
        name=body.name,
        label=body.label,
        description=body.description,
        theme_css=body.theme_css,
        source_fidelity=body.source_fidelity,
        builtin=False,
    )
    try:
        validate_style(style)
    except StyleError as err:
        raise HTTPException(status_code=422, detail=str(err)) from err
    _store().save(user_id, style)
    return _to_out(style)


@style_router.delete("/styles/{name}", status_code=204)
async def delete_style(name: str, request: Request) -> None:
    """Remove a fork from the caller's wheel. Builtins cannot be removed
    (409); unknown names are 404."""
    user_id = _user_id(request)
    registry = _merged_registry(user_id)
    if not registry.has(name):
        raise HTTPException(
            status_code=404, detail=f"unknown style {name!r}; known: {registry.names()}"
        )
    if registry.get(name).builtin:
        raise HTTPException(
            status_code=409,
            detail=f"cannot remove builtin style {name!r}",
        )
    _store().delete(user_id, name)


@style_router.get("/artifacts/{artifact_id}/render", response_class=HTMLResponse)
async def render_artifact(
    artifact_id: str, request: Request, style: str | None = None
) -> HTMLResponse:
    """Re-project a stored artifact in the chosen style — NO model call.

    Loads the artifact's stored projection HTML, recovers the canonical
    doc-model from its data island, and re-renders under ``style`` via
    ``restyle_artifact`` (the wheel's "regenerate in this style" action).
    ``style`` is resolved through the caller's merged registry here, in the
    route (spec R5), and passed by value; absent/``None`` → the Antiek
    default. A stored file without a projection data island cannot be
    restyled and is refused with a typed 422 (honest: the HTML was never a
    projection-engine artifact).
    """
    path: Path = artifact_path_for(artifact_id)
    if not path.is_file():
        raise HTTPException(
            status_code=404,
            detail=f"artifact {artifact_id!r} not found (no stored projection HTML)",
        )
    stored_bytes = path.read_bytes()
    if len(stored_bytes) > _MAX_ARTIFACT_BYTES:
        raise HTTPException(
            status_code=413,
            detail=f"stored artifact {artifact_id!r} exceeds {_MAX_ARTIFACT_BYTES} bytes",
        )
    stored_html = stored_bytes.decode("utf-8", errors="replace")

    user_id = _user_id(request)
    registry = _merged_registry(user_id)
    if style is None:
        resolved = None  # renderer default == the Antiek builtin
    else:
        try:
            resolved = registry.get(style)
        except StyleError as err:
            raise HTTPException(status_code=404, detail=str(err)) from err

    try:
        html = restyle_artifact(stored_html, RenderContext(), style=resolved)
    except IslandError as err:
        raise HTTPException(
            status_code=422,
            detail=(
                f"stored artifact {artifact_id!r} carries no usable projection "
                f"data island; cannot restyle: {err}"
            ),
        ) from err
    try:
        assert_script_free(html)
    except ScriptViolation as err:
        raise HTTPException(
            status_code=500,
            detail="restyled artifact failed the zero-script gate; refused",
        ) from err
    return HTMLResponse(content=html)


__all__ = ["style_router"]
