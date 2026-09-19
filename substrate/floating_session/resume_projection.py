"""Pure, owner-authorized projection for an existing floating research session."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Literal

from substrate.dispatch.research_tier import normalize_research_tier
from substrate.engagement_spine.store import EngagementStore

from .store import SessionStore, SessionStoreUnavailable

SessionStatus = Literal["reserved", "running", "complete", "failed"]
_STATUSES = frozenset({"reserved", "running", "complete", "failed"})


class DeepResearchSessionNotFound(LookupError):
    pass


class DeepResearchSessionUnavailable(RuntimeError):
    pass


@dataclass(frozen=True)
class DeepResearchSessionProjection:
    session_id: str
    spawn_id: str
    investigation_id: str
    parent_asset_id: str
    status: SessionStatus
    research_tier: str
    view_format: Literal["html"] = "html"


def resolve_deep_research_session(
    session_id: str, *, session_store: SessionStore, engagement_store: EngagementStore
) -> DeepResearchSessionProjection:
    """Read only strict rows; never use the status-refreshing session lifecycle API."""
    try:
        strict_session = getattr(session_store, "get_session_strict", None)
        session = strict_session(session_id) if callable(strict_session) else session_store.get_session(session_id)
        if session is None:
            raise DeepResearchSessionNotFound
        spawn_id = session.get("spawn_id")
        parent_id = session.get("parent_asset_id")
        investigation_id = session.get("investigation_id")
        if not all(isinstance(value, str) and value for value in (spawn_id, parent_id, investigation_id)):
            raise DeepResearchSessionUnavailable
        strict_spawn = getattr(engagement_store, "get_spawn_strict", None)
        spawn = strict_spawn(spawn_id) if callable(strict_spawn) else engagement_store.get_spawn(spawn_id)
        if spawn is None:
            raise DeepResearchSessionUnavailable
        status = spawn.get("status")
        if (
            spawn.get("spawn_id") != spawn_id
            or spawn.get("parent_asset_id") != parent_id
            or spawn.get("investigation_id") != investigation_id
            or status not in _STATUSES
        ):
            raise DeepResearchSessionUnavailable
        return DeepResearchSessionProjection(
            session_id=session_id,
            spawn_id=spawn_id,
            investigation_id=investigation_id,
            parent_asset_id=parent_id,
            status=status,
            research_tier=normalize_research_tier(spawn.get("research_tier")),
        )
    except DeepResearchSessionNotFound:
        raise
    except (SessionStoreUnavailable, OSError, RuntimeError, TypeError, ValueError) as exc:
        raise DeepResearchSessionUnavailable from exc
