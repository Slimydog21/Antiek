"""PostHog shim — disabled by default; no network."""

from __future__ import annotations

import os

import pytest

from substrate.observability import posthog as ph


@pytest.fixture(autouse=True)
def _clear_posthog_env(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.delenv("ANTIEK_POSTHOG_ENABLED", raising=False)
    monkeypatch.delenv("POSTHOG_PROJECT_API_KEY", raising=False)
    ph._client = None  # noqa: SLF001
    ph._init_attempted = False  # noqa: SLF001


def test_disabled_without_env() -> None:
    assert ph.is_enabled() is False
    assert ph.capture("test_event") is None


def test_enabled_flag_without_key() -> None:
    os.environ["ANTIEK_POSTHOG_ENABLED"] = "1"
    assert ph.is_enabled() is False