"""Operator privacy toggles — P1 §2 (own-your-mind program).

Wires the unwired telemetry store (``substrate/telemetry_preferences/``,
zero API/UI references before this module) to the PrivacyDashboard via
``GET /settings/privacy`` + ``PUT /settings/privacy``.

Honesty rules (load-bearing):

  * The surface list is the LIVE production registry
    (``substrate.dp_shuffler.production``), never a local copy. A surface
    the substrate registers appears here automatically; one it drops
    disappears. The registry is the only source of
    surface_name/sensitivity/epsilon_per_day/opt_in_required.
  * ``query_content_telemetry`` is registered ``sensitivity="forbidden"``
    (ε = 0, master-spec §13.3 — "E2E encryption with no learning, or no
    collection"). It is surfaced READ-ONLY: enabling it returns 400 and
    the GET row always reports ``enabled=false`` — the substrate is
    architecturally incapable of collecting it, so a toggle that claims
    otherwise would be theater.
  * ``default_enabled`` is derived from the registry: opt-in surfaces
    default OFF, everything else defaults ON (forbidden surfaces are
    pinned OFF). ``enabled`` is the store's answer with that default
    applied — a user's explicit preference always wins.
  * Store resolution never writes to the operator's real ``~/.antiek``
    implicitly: ``ANTIEK_TELEMETRY_DB`` wins, then ``ANTIEK_HOME``, then
    an in-memory store (no state-dir contract). If the sqlite path turns
    out unwritable, the factory falls back to in-memory rather than
    crashing the settings surface.
"""

from __future__ import annotations

import os
import sqlite3
from pathlib import Path

from fastapi import APIRouter, FastAPI, HTTPException, Request
from pydantic import BaseModel, ConfigDict

from substrate.dp_shuffler.epsilon_registry import SurfaceConfig
from substrate.dp_shuffler.production import get_production_registry
from substrate.telemetry_preferences import (
    InMemoryPreferenceStore,
    PreferenceStore,
    SqlitePreferenceStore,
    is_enabled,
    set_preference,
)

settings_privacy_router = APIRouter(prefix="/settings", tags=["settings"])

# Canonical (registry-name-keyed) descriptions, mirroring the
# PrivacyDashboard's per-category copy. The dashboard historically keyed
# the source-tier row as ``source_tier_preference_signals`` while the
# registry names the surface ``source_tier_preference``; the API surfaces
# the REGISTRY name and carries the dashboard's copy under that key.
CATEGORY_DESCRIPTIONS: dict[str, str] = {
    "skill_invocation_frequency": (
        "Which substrate skills fire and at what rate. Low sensitivity; "
        "the DP randomizer ensures no single invocation is identifying."
    ),
    "source_tier_preference": (
        "Which source tiers (Tier 1 = peer-reviewed primary, "
        "Tier 5 = anonymous) you accept versus reject. The shuffled "
        "aggregate informs the dispatch router's tier hints."
    ),
    "query_content_telemetry": (
        "The text of your research queries and the content of your "
        "private notes. Per master-spec §13.3: NOT COLLECTED at any ε "
        "that preserves utility — Antiek chooses no collection."
    ),
}

_ENV_DB_PATH = "ANTIEK_TELEMETRY_DB"
_ENV_HOME = "ANTIEK_HOME"
_DB_RELATIVE_PATH = Path("telemetry") / "preferences.sqlite"
_LEGACY_OWNER_USER_ID = "__operator__"


def default_telemetry_preferences_db_path() -> Path | None:
    """Resolve the sqlite store path from the environment.

    ``ANTIEK_TELEMETRY_DB`` wins when set (explicit contract — tests
    point it at a tmp path). Otherwise ``ANTIEK_HOME`` is the state dir
    (the repo's canonical override for ``~/.antiek``). When neither is
    set there is NO writable state-dir contract, and this returns
    ``None`` — the factory then uses an in-memory store instead of
    silently creating files under the operator's real home directory.
    """
    explicit = os.environ.get(_ENV_DB_PATH, "").strip()
    if explicit:
        return Path(os.path.expanduser(explicit))
    home = os.environ.get(_ENV_HOME, "").strip()
    if home:
        return Path(os.path.expanduser(home)) / _DB_RELATIVE_PATH
    return None


def create_preference_store(
    *,
    db_path: str | None = None,
) -> PreferenceStore:
    """Store factory: sqlite when a state-dir contract exists, else in-memory.

    ``db_path`` is a test seam (callers that already resolved a path).
    Fallback to ``InMemoryPreferenceStore`` is deliberate: the settings
    surface must keep working (with per-process persistence) even when
    the state dir is unwritable or unconfigured — never crash, never
    touch an implicit path.
    """
    path = Path(os.path.expanduser(db_path)) if db_path else default_telemetry_preferences_db_path()
    if path is None:
        return InMemoryPreferenceStore()
    try:
        return SqlitePreferenceStore(db_path=str(path))
    except (OSError, sqlite3.Error):
        return InMemoryPreferenceStore()


class PrivacySurfaceResponse(BaseModel):
    """One telemetry surface as the dashboard renders it."""

    surface_name: str
    sensitivity: str
    epsilon_per_day: float
    opt_in_required: bool
    description: str
    enabled: bool
    default_enabled: bool


class PrivacySettingsResponse(BaseModel):
    surfaces: list[PrivacySurfaceResponse]
    count: int


class PrivacyUpdateRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    surface_name: str
    enabled: bool


def _surface_description(surface: SurfaceConfig) -> str:
    return CATEGORY_DESCRIPTIONS.get(surface.surface_name) or surface.description


def _surface_row(
    store: PreferenceStore,
    *,
    user_id: str,
    surface: SurfaceConfig,
) -> PrivacySurfaceResponse:
    """One GET/PUT row for a registry surface.

    Forbidden surfaces are pinned OFF (``enabled`` and
    ``default_enabled`` both False): query-content telemetry is not
    collected at any ε, so no store row may flip it to "enabled".
    """
    forbidden = surface.sensitivity == "forbidden"
    default_enabled = not surface.opt_in_required and not forbidden
    enabled = (
        False
        if forbidden
        else is_enabled(
            store,
            user_id=user_id,
            surface_name=surface.surface_name,
            default_when_missing=default_enabled,
        )
    )
    return PrivacySurfaceResponse(
        surface_name=surface.surface_name,
        sensitivity=surface.sensitivity,
        epsilon_per_day=surface.epsilon_per_day,
        opt_in_required=surface.opt_in_required,
        description=_surface_description(surface),
        enabled=enabled,
        default_enabled=default_enabled,
    )


def _request_owner_user_id(request: Request) -> str:
    value = getattr(request.state, "user_id", _LEGACY_OWNER_USER_ID)
    if not isinstance(value, str) or not value or len(value) > 256:
        raise HTTPException(status_code=401, detail="authenticated user identity required")
    return value


def _store_for_app(app: FastAPI) -> PreferenceStore:
    """The app-owned store instance, created once per app lifetime.

    Created lazily on first use so tests that re-point the env before
    creating the TestClient get the store they asked for; held on
    ``app.state`` so one process serves one consistent store.
    """
    store = getattr(app.state, "telemetry_preference_store", None)
    if store is None:
        store = create_preference_store()
        app.state.telemetry_preference_store = store
    return store


@settings_privacy_router.get("/privacy", response_model=PrivacySettingsResponse)
def get_settings_privacy(request: Request) -> PrivacySettingsResponse:
    """Every canonical surface with its live toggle state + ε budget."""
    user_id = _request_owner_user_id(request)
    store = _store_for_app(request.app)
    surfaces = [
        _surface_row(store, user_id=user_id, surface=surface)
        for surface in get_production_registry().list_surfaces()
    ]
    return PrivacySettingsResponse(surfaces=surfaces, count=len(surfaces))


@settings_privacy_router.put("/privacy", response_model=PrivacySurfaceResponse)
def put_settings_privacy(
    request: Request,
    body: PrivacyUpdateRequest,
) -> PrivacySurfaceResponse:
    """Flip one surface's telemetry preference.

    Refuses surfaces the registry does not know (404 — the registry is
    the closed set of collectable signals) and refuses ENABLING a
    forbidden surface (400 — query-content telemetry is architecturally
    not collected per §13.3; storing "enabled" would be a lie).
    Disabling a forbidden surface is accepted (idempotent no-op).
    """
    user_id = _request_owner_user_id(request)
    store = _store_for_app(request.app)
    surface = get_production_registry().surfaces.get(body.surface_name)
    if surface is None:
        raise HTTPException(
            status_code=404,
            detail=(
                f"surface {body.surface_name!r} is not registered in the "
                "production registry; the registry is the closed set of "
                "telemetry surfaces"
            ),
        )
    if surface.sensitivity == "forbidden" and body.enabled:
        raise HTTPException(
            status_code=400,
            detail=(
                f"surface {body.surface_name!r} is marked forbidden per "
                "master-spec §13.3 — query-content telemetry is "
                "architecturally not collected at any ε. There is nothing "
                "to enable."
            ),
        )
    set_preference(
        store,
        user_id=user_id,
        surface_name=body.surface_name,
        enabled=body.enabled,
    )
    return _surface_row(store, user_id=user_id, surface=surface)


def register_settings_privacy_routes(app: FastAPI) -> None:
    """Mount the privacy router. Additive; safe to call once per app."""
    app.include_router(settings_privacy_router)
    if not hasattr(app.state, "telemetry_preference_store"):
        app.state.telemetry_preference_store = create_preference_store()


__all__ = [
    "CATEGORY_DESCRIPTIONS",
    "PrivacySettingsResponse",
    "PrivacySurfaceResponse",
    "PrivacyUpdateRequest",
    "create_preference_store",
    "default_telemetry_preferences_db_path",
    "register_settings_privacy_routes",
    "settings_privacy_router",
]
