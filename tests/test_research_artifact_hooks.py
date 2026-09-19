"""ANT-AHT-02 — env-gated export hook."""

from __future__ import annotations

from unittest.mock import patch

from substrate.research_artifact.authority import ArtifactAuthority
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
        assert m.call_count == 1
        assert m.call_args.kwargs["emit_event"] is True
        assert m.call_args.kwargs["authority"].account_id == "__operator__"


def test_hook_preserves_explicit_account_authority(monkeypatch):
    monkeypatch.setenv("ANTIEK_EXPORT_RESEARCH_ARTIFACT", "1")
    authority = ArtifactAuthority("alice", "inv-y")
    with patch("substrate.research_artifact.export.export_research_artifact") as m:
        maybe_export_after_investigation_complete("inv-y", authority=authority)
        assert m.call_args.kwargs["authority"] is authority
