"""ANT-AHT-02 — env-gated export hook."""

from __future__ import annotations

from unittest.mock import patch

from substrate.research_artifact.hooks import maybe_export_after_investigation_complete


def test_hook_noop_when_env_unset(monkeypatch):
    monkeypatch.delenv("ANTIEK_EXPORT_RESEARCH_ARTIFACT", raising=False)
    with patch("substrate.research_artifact.export.export_research_artifact") as m:
        maybe_export_after_investigation_complete("inv-x")
        m.assert_not_called()


def test_hook_exports_when_env_set(monkeypatch):
    monkeypatch.setenv("ANTIEK_EXPORT_RESEARCH_ARTIFACT", "1")
    with patch("substrate.research_artifact.export.export_research_artifact") as m:
        maybe_export_after_investigation_complete("inv-y")
        m.assert_called_once_with("inv-y", emit_event=True)