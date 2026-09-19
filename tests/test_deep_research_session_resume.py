from __future__ import annotations

import pytest

from substrate.engagement_spine.authority import EngagementAuthority
from substrate.engagement_spine.store import InMemoryEngagementStore, authorized_store
from substrate.floating_session.resume_projection import (
    DeepResearchSessionNotFound,
    DeepResearchSessionUnavailable,
    resolve_deep_research_session,
)
from substrate.floating_session.store import (
    FileSessionStore,
    InMemorySessionStore,
    authorized_session_store,
)


def _rows(account: str):
    sessions = authorized_session_store(InMemorySessionStore(), EngagementAuthority(account))
    engagement = authorized_store(InMemoryEngagementStore(), EngagementAuthority(account))
    sessions.put_session({"session_id": "same", "spawn_id": "spawn", "parent_asset_id": "asset", "investigation_id": "inv"})
    engagement.put_spawn({"spawn_id": "spawn", "parent_asset_id": "asset", "investigation_id": "inv", "status": "running", "research_tier": "deep"})
    return sessions, engagement


def test_projection_is_exact_current_and_read_only() -> None:
    sessions, engagement = _rows("alice")
    before_session = dict(sessions.get_session("same") or {})
    before_spawn = dict(engagement.get_spawn("spawn") or {})
    projection = resolve_deep_research_session("same", session_store=sessions, engagement_store=engagement)
    assert projection.__dict__ == {"session_id": "same", "spawn_id": "spawn", "investigation_id": "inv", "parent_asset_id": "asset", "status": "running", "research_tier": "deep", "view_format": "html"}
    assert sessions.get_session("same") == before_session
    assert engagement.get_spawn("spawn") == before_spawn


def test_same_display_id_is_owner_qualified() -> None:
    base_sessions = InMemorySessionStore()
    base_engagement = InMemoryEngagementStore()
    alice_s = authorized_session_store(base_sessions, EngagementAuthority("alice"))
    alice_e = authorized_store(base_engagement, EngagementAuthority("alice"))
    bob_s = authorized_session_store(base_sessions, EngagementAuthority("bob"))
    bob_e = authorized_store(base_engagement, EngagementAuthority("bob"))
    for sessions, engagement, asset in ((alice_s, alice_e, "alice-asset"), (bob_s, bob_e, "bob-asset")):
        sessions.put_session({"session_id": "same", "spawn_id": "spawn", "parent_asset_id": asset, "investigation_id": "inv"})
        engagement.put_spawn({"spawn_id": "spawn", "parent_asset_id": asset, "investigation_id": "inv", "status": "reserved", "research_tier": "fast"})
    assert resolve_deep_research_session("same", session_store=alice_s, engagement_store=alice_e).parent_asset_id == "alice-asset"
    assert resolve_deep_research_session("same", session_store=bob_s, engagement_store=bob_e).parent_asset_id == "bob-asset"


def test_missing_and_corrupt_file_are_distinct(tmp_path) -> None:
    base = FileSessionStore(tmp_path)
    sessions = authorized_session_store(base, EngagementAuthority("alice"))
    engagement = authorized_store(InMemoryEngagementStore(), EngagementAuthority("alice"))
    with pytest.raises(DeepResearchSessionNotFound):
        resolve_deep_research_session("missing", session_store=sessions, engagement_store=engagement)
    storage_id = EngagementAuthority("alice").storage_id("session", "broken")
    base._session_path(storage_id).write_text("{", encoding="utf-8")
    with pytest.raises(DeepResearchSessionUnavailable):
        resolve_deep_research_session("broken", session_store=sessions, engagement_store=engagement)


def test_contradictory_spawn_relationship_is_unavailable() -> None:
    sessions, engagement = _rows("alice")
    row = engagement.get_spawn("spawn")
    assert row is not None
    row["investigation_id"] = "other"
    engagement.put_spawn(row)
    with pytest.raises(DeepResearchSessionUnavailable):
        resolve_deep_research_session("same", session_store=sessions, engagement_store=engagement)
