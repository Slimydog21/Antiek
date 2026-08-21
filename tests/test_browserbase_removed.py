"""Regression contract for the retired Browserbase ingestion fallback."""

from __future__ import annotations

import inspect
import tomllib
from pathlib import Path

from acquisition.urls.adapter import ingest_url

ROOT = Path(__file__).resolve().parent.parent


def test_browserbase_is_absent_from_the_production_surface() -> None:
    """Reintroduction requires a deliberate dependency and governance change."""
    signature = inspect.signature(ingest_url)
    assert "fallback_to_browserbase" not in signature.parameters
    assert "browserbase_wait_for" not in signature.parameters

    assert not (ROOT / "acquisition/urls/client_browserbase.py").exists()
    assert not (ROOT / "acquisition/urls/budget_browserbase.py").exists()

    project = tomllib.loads((ROOT / "pyproject.toml").read_text(encoding="utf-8"))
    assert "browserbase" not in project["project"]["optional-dependencies"]

    integrations = tomllib.loads(
        (ROOT / "integrations.toml").read_text(encoding="utf-8")
    )
    assert "browserbase" not in integrations
