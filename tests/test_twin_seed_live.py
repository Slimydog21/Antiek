"""Env-gated live note_taker inject for twin seed (residual bz)."""

from __future__ import annotations

import os
import sys

_REPO = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
if _REPO not in sys.path:
    sys.path.insert(0, _REPO)

from substrate.engagement_spine import (  # noqa: E402
    ANTIEK_TWIN_SEED_LIVE_ENV,
    InMemoryEngagementStore,
    clear_twin_seed_live,
    configure_twin_seed_live,
    list_twin_notes,
    seed_twins_for_asset,
    twin_seed_live_enabled,
)


def test_live_default_off():
    os.environ.pop(ANTIEK_TWIN_SEED_LIVE_ENV, None)
    clear_twin_seed_live()
    assert twin_seed_live_enabled() is False


def test_live_requires_env_and_fn():
    store = InMemoryEngagementStore()

    def live(title: str, body: str):
        return [
            ("insight", f"LIVE insight on {title}"),
            ("question", f"LIVE question on {title}?"),
        ]

    os.environ[ANTIEK_TWIN_SEED_LIVE_ENV] = "1"
    configure_twin_seed_live(live)
    try:
        out = seed_twins_for_asset(
            "asset_live",
            store=store,
            title="Paper X",
            body_text="body",
        )
        assert out["seeded"] is True
        assert out["live_seed"] is True
        notes = list_twin_notes("asset_live", store=store)
        texts = " ".join(n.text for n in notes)
        assert "LIVE insight" in texts
        assert "LIVE question" in texts
    finally:
        clear_twin_seed_live()
        os.environ.pop(ANTIEK_TWIN_SEED_LIVE_ENV, None)


def test_force_offline_ignores_live():
    store = InMemoryEngagementStore()

    def live(title: str, body: str):
        raise AssertionError("must not call live")

    os.environ[ANTIEK_TWIN_SEED_LIVE_ENV] = "1"
    configure_twin_seed_live(live)
    try:
        out = seed_twins_for_asset(
            "asset_off",
            store=store,
            title="Paper Y",
            force_offline=True,
        )
        assert out["live_seed"] is False
        notes = list_twin_notes("asset_off", store=store)
        assert any("Asset identity" in n.text for n in notes)
    finally:
        clear_twin_seed_live()
        os.environ.pop(ANTIEK_TWIN_SEED_LIVE_ENV, None)


def test_injector_without_env_stays_offline():
    store = InMemoryEngagementStore()
    called = []

    def live(title: str, body: str):
        called.append(1)
        return [("insight", "x"), ("question", "y")]

    os.environ.pop(ANTIEK_TWIN_SEED_LIVE_ENV, None)
    configure_twin_seed_live(live)
    try:
        out = seed_twins_for_asset(
            "asset_stub", store=store, title="Z"
        )
        assert out["live_seed"] is False
        assert called == []
    finally:
        clear_twin_seed_live()
