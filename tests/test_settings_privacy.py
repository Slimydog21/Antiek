"""OYM P1 §2 — privacy toggles API (GET/PUT /settings/privacy).

Covers: canonical-surface GET with registry-derived defaults, PUT flip
+ GET reflection, forbidden-surface refusal, unknown-surface 404, and
store persistence across a factory round-trip. The autouse store
isolation fixture (tests/conftest.py) points ANTIEK_HOME at a tmp dir,
so nothing here can touch the operator's real ~/.antiek.
"""

from __future__ import annotations

from collections.abc import Iterator
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from interfaces.research.api.settings_privacy import create_preference_store
from substrate.telemetry_preferences import (
    InMemoryPreferenceStore,
    SqlitePreferenceStore,
    set_preference,
)


@pytest.fixture
def client(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> Iterator[TestClient]:
    # Hermetic state dir + explicit sqlite override; never the real home.
    monkeypatch.setenv("ANTIEK_HOME", str(tmp_path / "home"))
    monkeypatch.delenv("ANTIEK_TELEMETRY_DB", raising=False)
    from interfaces.research.api.app import create_app

    app = create_app()
    with TestClient(app) as c:
        yield c


def _surfaces(body: dict) -> dict[str, dict]:
    return {s["surface_name"]: s for s in body["surfaces"]}


def test_get_returns_all_canonical_surfaces_with_registry_defaults(
    client: TestClient,
) -> None:
    r = client.get("/settings/privacy")
    assert r.status_code == 200
    body = r.json()
    assert body["count"] == 3
    by_name = _surfaces(body)
    assert set(by_name) == {
        "skill_invocation_frequency",
        "source_tier_preference",
        "query_content_telemetry",
    }

    skill = by_name["skill_invocation_frequency"]
    assert skill["sensitivity"] == "low"
    assert skill["epsilon_per_day"] == 2.0
    assert skill["opt_in_required"] is False
    assert skill["enabled"] is True  # not opt-in → default ON
    assert skill["default_enabled"] is True

    tier = by_name["source_tier_preference"]
    assert tier["sensitivity"] == "medium"
    assert tier["epsilon_per_day"] == 1.0
    assert tier["opt_in_required"] is True
    assert tier["enabled"] is False  # opt-in → default OFF
    assert tier["default_enabled"] is False

    query = by_name["query_content_telemetry"]
    assert query["sensitivity"] == "forbidden"
    assert query["epsilon_per_day"] == 0.0
    assert query["enabled"] is False  # architecturally not collected
    assert query["default_enabled"] is False


def test_get_descriptions_surface_registry_names(client: TestClient) -> None:
    r = client.get("/settings/privacy")
    body = r.json()
    by_name = _surfaces(body)
    # The dashboard historically keyed the tier row
    # "source_tier_preference_signals"; the API surfaces the REGISTRY name
    # and keeps the dashboard's description copy under it.
    assert "source_tier_preference_signals" not in by_name
    assert "source tiers" in by_name["source_tier_preference"]["description"]
    assert "NOT COLLECTED" in by_name["query_content_telemetry"]["description"]


def test_put_flips_a_surface_and_get_reflects_it(client: TestClient) -> None:
    r = client.put(
        "/settings/privacy",
        json={"surface_name": "skill_invocation_frequency", "enabled": False},
    )
    assert r.status_code == 200
    row = r.json()
    assert row["surface_name"] == "skill_invocation_frequency"
    assert row["enabled"] is False

    r = client.get("/settings/privacy")
    assert r.status_code == 200
    row = _surfaces(r.json())["skill_invocation_frequency"]
    assert row["enabled"] is False

    # Flip back on; opt-in surface stays off until explicitly enabled.
    r = client.put(
        "/settings/privacy",
        json={"surface_name": "source_tier_preference", "enabled": True},
    )
    assert r.status_code == 200
    assert r.json()["enabled"] is True
    row = _surfaces(client.get("/settings/privacy").json())["source_tier_preference"]
    assert row["enabled"] is True


def test_put_forbidden_surface_enable_returns_400(client: TestClient) -> None:
    r = client.put(
        "/settings/privacy",
        json={"surface_name": "query_content_telemetry", "enabled": True},
    )
    assert r.status_code == 400
    detail = r.json()["detail"]
    assert "query_content_telemetry" in detail
    assert "not collected" in detail.lower()

    # Disabling a forbidden surface is an accepted idempotent no-op.
    r = client.put(
        "/settings/privacy",
        json={"surface_name": "query_content_telemetry", "enabled": False},
    )
    assert r.status_code == 200
    assert r.json()["enabled"] is False


def test_put_unknown_surface_returns_404(client: TestClient) -> None:
    r = client.put(
        "/settings/privacy",
        json={"surface_name": "not_a_real_surface", "enabled": True},
    )
    assert r.status_code == 404
    assert "not registered" in r.json()["detail"]


def test_put_rejects_extra_fields(client: TestClient) -> None:
    r = client.put(
        "/settings/privacy",
        json={"surface_name": "skill_invocation_frequency", "enabled": True, "extra": 1},
    )
    assert r.status_code == 422


def test_put_is_per_user_scoped(client: TestClient) -> None:
    # The API user (unauthenticated-local operator) flips a surface OFF;
    # another user's preference lives under their own user_id, so the API
    # user's GET row is untouched by it.
    r = client.put(
        "/settings/privacy",
        json={"surface_name": "skill_invocation_frequency", "enabled": False},
    )
    assert r.status_code == 200

    store = client.app.state.telemetry_preference_store
    set_preference(
        store,
        user_id="other-user",
        surface_name="skill_invocation_frequency",
        enabled=True,
    )

    r = client.get("/settings/privacy")
    assert r.status_code == 200
    row = _surfaces(r.json())["skill_invocation_frequency"]
    assert row["enabled"] is False


def test_store_factory_round_trip_persists_sqlite(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Persistence across a store round-trip via the factory's test path."""
    db_path = tmp_path / "telemetry" / "prefs.sqlite"
    monkeypatch.setenv("ANTIEK_TELEMETRY_DB", str(db_path))

    s1 = create_preference_store()
    assert isinstance(s1, SqlitePreferenceStore)
    set_preference(s1, user_id="__operator__", surface_name="skill_invocation_frequency", enabled=False)

    # Re-open through the factory at the same path → the write survived.
    s2 = create_preference_store()
    pref = s2.get(user_id="__operator__", surface_name="skill_invocation_frequency")
    assert pref is not None
    assert pref.enabled is False
    assert db_path.is_file()


def test_store_factory_uses_in_memory_without_state_dir(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """No ANTIEK_HOME / ANTIEK_TELEMETRY_DB → in-memory, never ~/.antiek."""
    monkeypatch.delenv("ANTIEK_HOME", raising=False)
    monkeypatch.delenv("ANTIEK_TELEMETRY_DB", raising=False)
    store = create_preference_store()
    assert isinstance(store, InMemoryPreferenceStore)


def test_store_factory_falls_back_to_in_memory_on_unwritable_path(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Unwritable sqlite path → in-memory fallback instead of a crash."""
    blocker = tmp_path / "blocker"
    blocker.mkdir()
    (blocker / "nested").mkdir()
    (blocker / "nested" / "file").write_text("occupied", encoding="utf-8")
    monkeypatch.setenv("ANTIEK_TELEMETRY_DB", str(blocker / "nested" / "file" / "db.sqlite"))
    store = create_preference_store()
    assert isinstance(store, InMemoryPreferenceStore)
