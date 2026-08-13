"""Dispatch binding for the AI Role Lineup registry.

The lineup registry (``~/.antiek/settings/lineup.json``, written by
``PUT /settings/lineup``) stores the operator's model choices. This module
resolves them into the dispatch router's existing per-call override seam
(``provider_override``/``model_override`` in ``substrate.dispatch.router``),
so a lineup substitution ACTUALLY changes which model the platform routes
to — with the tier's fallback chain preserved.

Precedence (deliberate, tested):
  1. Caller-provided explicit override (highest — the code site wins).
  2. Lineup ACTION assignment (advanced[action_id] → its dispatch_role).
  3. Lineup ROLE assignment (general[role_id] → all dispatch roles the
     role owns, via the catalog).
  4. No assignment → platform default (config.yaml).

Owner scoping, honestly: ``dispatch()`` has no per-owner request context,
so the router binding applies the OPERATOR's lineup (``__operator__``
owner only). Per-owner BYOT bindings stay on the request-scoped seams
(``owner_byot_dispatch`` etc.), unchanged.

Cache: registry reads are mtime+size-keyed; a missing file is a fast
negative. A stale cache can lag a registry write by at most one dispatch
call — acceptable, and the PUT path re-reads on the next call anyway.
"""

from __future__ import annotations

import json
import os
from dataclasses import dataclass
from pathlib import Path

from .lineup_catalog import ACTION_BY_ID, ROLE_BY_ID

_OPERATOR_OWNER = "__operator__"
_registry_cache: dict[tuple[str, int, int], dict[str, object]] = {}


def _registry_path() -> Path:
    override = os.environ.get("ANTIEK_LINEUP_PATH", "").strip()
    if override:
        return Path(override)
    home = os.environ.get("ANTIEK_HOME", "").strip() or str(Path.home())
    return Path(home) / ".antiek" / "settings" / "lineup.json"


def _load_registry() -> dict[str, object]:
    path = _registry_path()
    try:
        st = path.stat()
    except OSError:
        return {}
    key = (str(path), st.st_mtime_ns, st.st_size)
    cached = _registry_cache.get(key)
    if cached is not None:
        return cached
    try:
        raw = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        raw = {}
    if not isinstance(raw, dict):
        raw = {}
    _registry_cache.clear()  # one-entry cache
    _registry_cache[key] = raw
    return raw


@dataclass(frozen=True, slots=True)
class DispatchOverride:
    provider_id: str
    model_id: str
    source: str  # "role_assignment" | "action_assignment"


def effective_override_for_dispatch_role(dispatch_role: str) -> DispatchOverride | None:
    """Operator lineup assignment for a backend dispatch role, or None.

    An ACTION assignment beats a ROLE assignment when both exist. Returns
    None when the operator has no assignment (platform default routing).
    """
    registry = _load_registry()
    owners = registry.get("owners", {})
    owner_map = owners.get(_OPERATOR_OWNER, {}) if isinstance(owners, dict) else {}
    general: dict[str, object] = owner_map.get("general", {}) if isinstance(owner_map, dict) else {}
    advanced: dict[str, object] = owner_map.get("advanced", {}) if isinstance(owner_map, dict) else {}

    # Action-level first: find the action whose dispatch_role matches.
    action_choice: dict[str, object] | None = None
    for action_id, choice in advanced.items():
        if not isinstance(choice, dict):
            continue
        action = ACTION_BY_ID.get(action_id)
        if action is not None and action.dispatch_role == dispatch_role:
            action_choice = choice
            break
    if action_choice is not None:
        provider_id = action_choice.get("provider_id")
        model_id = action_choice.get("model_id")
        if isinstance(provider_id, str) and isinstance(model_id, str):
            return DispatchOverride(
                provider_id=provider_id,
                model_id=model_id,
                source="action_assignment",
            )

    # Role-level: the role that owns any action with this dispatch_role.
    for role in ROLE_BY_ID.values():
        if any(a.dispatch_role == dispatch_role for a in role.actions):
            choice = general.get(role.role_id)
            if isinstance(choice, dict):
                provider_id = choice.get("provider_id")
                model_id = choice.get("model_id")
                if isinstance(provider_id, str) and isinstance(model_id, str):
                    return DispatchOverride(
                        provider_id=provider_id,
                        model_id=model_id,
                        source="role_assignment",
                    )
    return None



def effective_model_for_action(
    action_id: str,
    *,
    provider_family: str,
    default: str,
) -> str:
    """Operator lineup model for a NON-dispatch surface action.

    Voice/media/embedding surfaces each have exactly one provider family
    (openai / krea / local_embedding). An assignment is admitted only when
    it names that family AND a model in the action's allowed set; anything
    else is ignored so the surface keeps its default (the selector can
    never name a model the endpoint cannot serve). Precedence mirrors the
    dispatch binding: action assignment, then the owning role's general
    assignment, then ``default``.
    """
    action = ACTION_BY_ID.get(action_id)
    if action is None:
        return default
    allowed = set(action.allowed_models or ())
    candidate: tuple[str, str] | None = None

    registry = _load_registry()
    owners = registry.get("owners", {})
    owner_map = owners.get(_OPERATOR_OWNER, {}) if isinstance(owners, dict) else {}
    general: dict[str, object] = owner_map.get("general", {}) if isinstance(owner_map, dict) else {}
    advanced: dict[str, object] = owner_map.get("advanced", {}) if isinstance(owner_map, dict) else {}

    choice = advanced.get(action_id)
    if isinstance(choice, dict):
        pid = choice.get("provider_id")
        mid = choice.get("model_id")
        if isinstance(pid, str) and isinstance(mid, str):
            candidate = (pid, mid)

    if candidate is None:
        role = next(
            (r for r in ROLE_BY_ID.values() if any(a.action_id == action_id for a in r.actions)),
            None,
        )
        if role is not None:
            g = general.get(role.role_id)
            if isinstance(g, dict):
                pid = g.get("provider_id")
                mid = g.get("model_id")
                if isinstance(pid, str) and isinstance(mid, str):
                    candidate = (pid, mid)

    if candidate is None:
        return default
    pid, mid = candidate
    if pid != provider_family:
        return default
    if allowed and mid not in allowed:
        return default
    return mid
