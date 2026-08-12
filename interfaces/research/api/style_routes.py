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

import hashlib
import logging

from fastapi import APIRouter, HTTPException, Request
from fastapi.responses import HTMLResponse
from pydantic import BaseModel, Field

from services.html_projection.context import RenderContext
from services.html_projection.gate import ScriptViolation, assert_script_free
from services.html_projection.island import IslandError, extract_island
from services.html_projection.renderer import restyle_artifact
from services.html_projection.styles import (
    ProjectionStyle,
    StyleError,
    StyleRegistry,
    default_registry,
    validate_style,
)
from substrate.research_artifact.paths import (
    artifact_path_for,
    artifact_source_path_for,
    read_bounded_nofollow,
    research_artifacts_dir,
    validate_artifact_id,
)
from substrate.research_artifact.store import ResearchArtifactStore
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
    name: str = Field(max_length=64)
    label: str = Field(max_length=128)
    description: str = Field(default="", max_length=2048)
    theme_css: str = Field(default="", max_length=100_000)
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
            detail=(f"cannot override builtin style {body.name!r}; fork it under a new name"),
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
    try:
        validate_artifact_id(artifact_id)
    except ValueError as err:
        raise HTTPException(status_code=404, detail="artifact not found") from err

    user_id = _user_id(request)
    artifact_store = ResearchArtifactStore(_db_path())
    record = artifact_store.get(artifact_id)
    stored_bytes: bytes | None = None
    if record is None:
        # Explicit compatibility policy: pre-ledger files belong only to the
        # local operator. Authenticated users must never inherit legacy data.
        if user_id != "__operator__":
            raise HTTPException(status_code=404, detail="artifact not found")
        path = artifact_path_for(artifact_id)
        if path.is_file():
            try:
                stored_bytes = read_bounded_nofollow(path, _MAX_ARTIFACT_BYTES)
            except OverflowError as err:
                raise HTTPException(status_code=413, detail=str(err)) from err
            except ValueError as err:
                raise HTTPException(status_code=404, detail="artifact not found") from err
            try:
                legacy_html = stored_bytes.decode("utf-8")
                extract_island(legacy_html)
            except UnicodeDecodeError as err:
                raise HTTPException(
                    status_code=422, detail="stored artifact is not valid UTF-8"
                ) from err
            except IslandError as err:
                raise HTTPException(
                    status_code=422, detail="legacy artifact has no usable data island"
                ) from err
            managed_path = artifact_source_path_for(
                artifact_id, hashlib.sha256(stored_bytes).hexdigest()
            )
            artifact_store.save_source(
                artifact_id, artifact_id, user_id, managed_path, stored_bytes
            )
            record = artifact_store.get(artifact_id)
            stored_bytes = None
    if record is None or record.owner_user_id != user_id:
        raise HTTPException(status_code=404, detail="artifact not found")
    path = record.source_path
    try:
        path.resolve(strict=False).relative_to(research_artifacts_dir().resolve())
    except (OSError, ValueError) as err:
        raise HTTPException(status_code=404, detail="artifact not found") from err
    if not path.is_file():
        raise HTTPException(
            status_code=404,
            detail=f"artifact {artifact_id!r} not found (no stored projection HTML)",
        )
    if stored_bytes is None:
        try:
            stored_bytes = read_bounded_nofollow(path, _MAX_ARTIFACT_BYTES)
        except OverflowError as err:
            raise HTTPException(status_code=413, detail=str(err)) from err
        except ValueError as err:
            raise HTTPException(status_code=404, detail="artifact not found") from err
    source_digest = hashlib.sha256(stored_bytes).hexdigest()
    if record.source_hash is None:
        try:
            artifact_store.bind_source_hash(
                artifact_id, user_id, record.source_path, source_digest
            )
        except (KeyError, ValueError) as err:
            raise HTTPException(status_code=422, detail="artifact source integrity changed") from err
    elif source_digest != record.source_hash:
        raise HTTPException(status_code=422, detail="artifact source hash mismatch")
    try:
        stored_html = stored_bytes.decode("utf-8")
    except UnicodeDecodeError as err:
        raise HTTPException(status_code=422, detail="stored artifact is not valid UTF-8") from err

    registry = _merged_registry(user_id)
    requested_style = style if style is not None else record.selected_style
    if requested_style is None:
        resolved = None
    else:
        try:
            resolved = registry.get(requested_style)
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
    selected_style = resolved.name if resolved is not None else "antiek"
    digest = hashlib.sha256(html.encode("utf-8")).hexdigest()
    return HTMLResponse(
        content=html,
        headers={
            "X-Artifact-ID": artifact_id,
            "X-Artifact-Style": selected_style,
            "X-Artifact-Version": "preview",
            "X-Content-SHA256": digest,
        },
    )


@style_router.post("/artifacts/{artifact_id}/render", response_class=HTMLResponse)
async def apply_artifact_style(
    artifact_id: str, request: Request, style: str | None = None
) -> HTMLResponse:
    """Durably apply a style; GET remains a side-effect-free preview."""
    preview = await render_artifact(artifact_id, request, style)
    user_id = _user_id(request)
    style_name = preview.headers["X-Artifact-Style"]
    digest = preview.headers["X-Content-SHA256"]
    html = bytes(preview.body).decode("utf-8")
    version, _ = ResearchArtifactStore(_db_path()).add_version(
        artifact_id, user_id, style_name, html, digest
    )
    preview.headers["X-Artifact-Version"] = str(version)
    return preview


async def _serve_version(artifact_id: str, request: Request, version: int | None) -> HTMLResponse:
    user_id = _user_id(request)
    stored = ResearchArtifactStore(_db_path()).get_version(artifact_id, user_id, version)
    if stored is None:
        raise HTTPException(status_code=404, detail="artifact version not found")
    try:
        raw = read_bounded_nofollow(stored.html_path, _MAX_ARTIFACT_BYTES)
        html = raw.decode("utf-8")
    except (ValueError, UnicodeDecodeError) as err:
        raise HTTPException(status_code=422, detail="stored version is corrupt") from err
    except OverflowError as err:
        raise HTTPException(status_code=413, detail=str(err)) from err
    if hashlib.sha256(raw).hexdigest() != stored.content_hash:
        raise HTTPException(status_code=422, detail="stored version hash mismatch")
    return HTMLResponse(
        content=html,
        headers={
            "X-Artifact-ID": stored.artifact_id,
            "X-Artifact-Style": stored.style_name,
            "X-Artifact-Version": str(stored.version),
            "X-Content-SHA256": stored.content_hash,
        },
    )


@style_router.get("/artifacts/{artifact_id}/versions/latest", response_class=HTMLResponse)
async def latest_artifact_version(artifact_id: str, request: Request) -> HTMLResponse:
    return await _serve_version(artifact_id, request, None)


@style_router.get("/artifacts/{artifact_id}/versions/{version}", response_class=HTMLResponse)
async def artifact_version(artifact_id: str, version: int, request: Request) -> HTMLResponse:
    if version < 1:
        raise HTTPException(status_code=404, detail="artifact version not found")
    return await _serve_version(artifact_id, request, version)


__all__ = ["style_router"]
