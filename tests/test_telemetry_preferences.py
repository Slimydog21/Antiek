"""Tests for substrate.telemetry_preferences."""

from __future__ import annotations

import os
import tempfile

import pytest

from substrate.dp_shuffler import EpsilonRegistry, SurfaceConfig
from substrate.telemetry_preferences import (
    InMemoryPreferenceStore,
    SqlitePreferenceStore,
    UserTelemetryPreferences,
    apply_defaults_from_registry,
    is_enabled,
    list_preferences,
    set_preference,
)


# ── InMemory store ─────────────────────────────────────────────


def test_set_and_get_preference():
    store = InMemoryPreferenceStore()
    set_preference(store, user_id="u-1", surface_name="skill_invocation_frequency", enabled=False)
    pref = store.get(user_id="u-1", surface_name="skill_invocation_frequency")
    assert pref is not None
    assert pref.enabled is False


def test_is_enabled_default_when_missing_true():
    store = InMemoryPreferenceStore()
    assert is_enabled(
        store, user_id="u-1", surface_name="never_set",
        default_when_missing=True,
    ) is True


def test_is_enabled_default_when_missing_false():
    store = InMemoryPreferenceStore()
    assert is_enabled(
        store, user_id="u-1", surface_name="opt_in_required",
        default_when_missing=False,
    ) is False


def test_explicit_preference_overrides_default():
    store = InMemoryPreferenceStore()
    set_preference(store, user_id="u-1", surface_name="surf", enabled=False)
    assert is_enabled(store, user_id="u-1", surface_name="surf",
                      default_when_missing=True) is False


def test_list_for_user_isolates_per_user():
    store = InMemoryPreferenceStore()
    set_preference(store, user_id="u-1", surface_name="a", enabled=True)
    set_preference(store, user_id="u-1", surface_name="b", enabled=False)
    set_preference(store, user_id="u-2", surface_name="a", enabled=False)
    assert len(store.list_for_user("u-1")) == 2
    assert len(store.list_for_user("u-2")) == 1


def test_delete_for_user_removes_only_that_user():
    store = InMemoryPreferenceStore()
    set_preference(store, user_id="u-1", surface_name="a", enabled=True)
    set_preference(store, user_id="u-2", surface_name="a", enabled=True)
    n = store.delete_for_user("u-1")
    assert n == 1
    assert len(store.list_for_user("u-1")) == 0
    assert len(store.list_for_user("u-2")) == 1


# ── SQLite store persistence ───────────────────────────────────


def test_sqlite_store_persists_across_reopen(tmp_path):
    db_path = str(tmp_path / "prefs.sqlite")
    s1 = SqlitePreferenceStore(db_path=db_path)
    set_preference(s1, user_id="u-1", surface_name="surf", enabled=False)
    # Reopen.
    s2 = SqlitePreferenceStore(db_path=db_path)
    pref = s2.get(user_id="u-1", surface_name="surf")
    assert pref is not None
    assert pref.enabled is False


def test_sqlite_upsert_replaces_existing(tmp_path):
    db_path = str(tmp_path / "prefs.sqlite")
    store = SqlitePreferenceStore(db_path=db_path)
    set_preference(store, user_id="u-1", surface_name="surf", enabled=True)
    set_preference(store, user_id="u-1", surface_name="surf", enabled=False)
    rows = store.list_for_user("u-1")
    assert len(rows) == 1
    assert rows[0].enabled is False


# ── EpsilonRegistry-driven defaults ────────────────────────────


def _registry_with_three() -> EpsilonRegistry:
    reg = EpsilonRegistry()
    reg.register(SurfaceConfig(
        surface_name="opt_in_required_surf",
        epsilon_per_day=1.0, sensitivity="high",
        description="high sensitivity opt-in",
        opt_in_required=True,
    ))
    reg.register(SurfaceConfig(
        surface_name="non_opt_in_surf",
        epsilon_per_day=2.0, sensitivity="low",
        description="low sensitivity automatic",
        opt_in_required=False,
    ))
    reg.register(SurfaceConfig(
        surface_name="forbidden_surf",
        epsilon_per_day=0.0, sensitivity="forbidden",
        description="not collected",
        opt_in_required=False,
    ))
    return reg


def test_apply_defaults_seeds_three_surfaces():
    store = InMemoryPreferenceStore()
    reg = _registry_with_three()
    n = apply_defaults_from_registry(store, user_id="u-1", registry=reg)
    assert n == 3


def test_apply_defaults_opt_in_required_seeds_false():
    store = InMemoryPreferenceStore()
    reg = _registry_with_three()
    apply_defaults_from_registry(store, user_id="u-1", registry=reg)
    pref = store.get(user_id="u-1", surface_name="opt_in_required_surf")
    assert pref is not None
    assert pref.enabled is False


def test_apply_defaults_non_opt_in_seeds_true():
    store = InMemoryPreferenceStore()
    reg = _registry_with_three()
    apply_defaults_from_registry(store, user_id="u-1", registry=reg)
    pref = store.get(user_id="u-1", surface_name="non_opt_in_surf")
    assert pref is not None
    assert pref.enabled is True


def test_apply_defaults_forbidden_seeds_false():
    store = InMemoryPreferenceStore()
    reg = _registry_with_three()
    apply_defaults_from_registry(store, user_id="u-1", registry=reg)
    pref = store.get(user_id="u-1", surface_name="forbidden_surf")
    assert pref is not None
    assert pref.enabled is False


def test_apply_defaults_does_not_override_explicit_preference():
    store = InMemoryPreferenceStore()
    reg = _registry_with_three()
    # User has already opted into the opt-in-required surface.
    set_preference(store, user_id="u-1", surface_name="opt_in_required_surf", enabled=True)
    n = apply_defaults_from_registry(store, user_id="u-1", registry=reg)
    # Only the other two get seeded.
    assert n == 2
    pref = store.get(user_id="u-1", surface_name="opt_in_required_surf")
    assert pref is not None
    assert pref.enabled is True  # preserved
