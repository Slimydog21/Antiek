"""SPR-01 — zero-spend compose interrogation preview packets."""

from __future__ import annotations

import os
import tempfile
from contextlib import contextmanager

import pytest

import substrate.research_artifact.compose_interrogate as interrogation_module
from substrate.graph import ensure_initialized
from substrate.graph.insight_question import promote_insight
from substrate.research_artifact import (
    MAX_INTERROGATION_CONTEXT_CHARS,
    MAX_INTERROGATION_PROMPT_CHARS,
    ComposeInterrogationIntegrityError,
    InvalidInterrogationPrompt,
    build_interrogation_preview,
    create_compose_draft,
    preview_artifacts,
)


@pytest.fixture
def artifact_env(monkeypatch):
    tmpdir = tempfile.mkdtemp(prefix="compose-interrogate-")
    db = os.path.join(tmpdir, "t.duckdb")
    events = os.path.join(tmpdir, "events")
    arts = os.path.join(tmpdir, "artifacts")
    os.makedirs(events, exist_ok=True)
    monkeypatch.setenv("ANTIEK_DUCKDB_PATH", db)
    monkeypatch.setenv("ANTIEK_RESEARCH_EVENTS_DIR", events)
    monkeypatch.setenv("ANTIEK_RESEARCH_ARTIFACTS_DIR", arts)
    monkeypatch.setenv("ANTIEK_EMBEDDING_PROVIDER", "hash")
    ensure_initialized(db)
    return {"db": db, "events": events, "arts": arts}


def _draft(investigation_ids: list[str]):
    preview = preview_artifacts(investigation_ids)
    return create_compose_draft(
        investigation_ids,
        expected_fingerprint=preview.selection_fingerprint or "",
    )


def test_interrogation_preview_is_ordered_and_receipted(artifact_env):
    promote_insight(text="Alpha evidence.", investigation_id="inv-alpha", source_document_id="doc-a")
    promote_insight(text="Beta evidence.", investigation_id="inv-beta", source_document_id="doc-b")
    draft = _draft(["inv-alpha", "inv-beta"])

    packet = build_interrogation_preview(
        draft.compose_id or "",
        "Where do the sources agree?",
        expected_fingerprint=draft.selection_fingerprint,
    )

    assert packet.provider_called is False
    assert packet.compose_id == draft.compose_id
    assert packet.selection_fingerprint == draft.selection_fingerprint
    assert len(packet.prompt_hash) == 64
    assert packet.context_chars == len(packet.context)
    assert packet.context.index("investigation_id: inv-alpha") < packet.context.index(
        "investigation_id: inv-beta"
    )
    assert [r.investigation_id for r in packet.member_receipts] == ["inv-alpha", "inv-beta"]
    assert [r.content_hash for r in packet.member_receipts] == [
        m.content_hash for m in draft.members
    ]


def test_interrogation_preview_rejects_prompt_bounds(artifact_env):
    promote_insight(text="Alpha.", investigation_id="inv-alpha", source_document_id="doc")
    promote_insight(text="Beta.", investigation_id="inv-beta", source_document_id="doc")
    draft = _draft(["inv-alpha", "inv-beta"])

    with pytest.raises(InvalidInterrogationPrompt):
        build_interrogation_preview(draft.compose_id or "", " ")
    with pytest.raises(InvalidInterrogationPrompt):
        build_interrogation_preview(
            draft.compose_id or "",
            "x" * (MAX_INTERROGATION_PROMPT_CHARS + 1),
        )


def test_interrogation_preview_bounds_context_with_fair_member_receipts(artifact_env):
    promote_insight(text="A" * 70000, investigation_id="inv-long", source_document_id="doc")
    promote_insight(text="Short but present.", investigation_id="inv-short", source_document_id="doc")
    draft = _draft(["inv-long", "inv-short"])

    packet = build_interrogation_preview(
        draft.compose_id or "",
        "Summarize tension.",
        expected_fingerprint=draft.selection_fingerprint,
    )

    assert packet.context_chars <= MAX_INTERROGATION_CONTEXT_CHARS
    assert "investigation_id: inv-long" in packet.context
    assert "investigation_id: inv-short" in packet.context
    assert packet.truncated_fields > 0
    assert packet.omitted_chars > 0
    assert all(receipt.included_chars > 0 for receipt in packet.member_receipts)


def test_interrogation_preview_validates_fingerprint_and_member_hash(artifact_env):
    promote_insight(text="Alpha evidence.", investigation_id="inv-alpha", source_document_id="doc")
    promote_insight(text="Beta evidence.", investigation_id="inv-beta", source_document_id="doc")
    draft = _draft(["inv-alpha", "inv-beta"])

    with pytest.raises(ComposeInterrogationIntegrityError):
        build_interrogation_preview(
            draft.compose_id or "",
            "Question?",
            expected_fingerprint="0" * 64,
        )

    member_path = os.path.join(
        artifact_env["arts"], "composes", draft.compose_id or "", "members", "0.html"
    )
    with open(member_path, encoding="utf-8") as handle:
        content = handle.read()
    with open(member_path, "w", encoding="utf-8") as handle:
        handle.write(content.replace('"investigation_id": "inv-alpha"', '"investigation_id": "inv-x"'))

    with pytest.raises(ComposeInterrogationIntegrityError):
        build_interrogation_preview(
            draft.compose_id or "",
            "Question?",
            expected_fingerprint=draft.selection_fingerprint,
        )


def test_interrogation_preview_holds_compose_lock_through_member_reads(artifact_env, monkeypatch):
    promote_insight(text="Alpha evidence.", investigation_id="inv-alpha", source_document_id="doc")
    promote_insight(text="Beta evidence.", investigation_id="inv-beta", source_document_id="doc")
    draft = _draft(["inv-alpha", "inv-beta"])
    lock_held = False
    original_load = interrogation_module._load_validated_member

    @contextmanager
    def observed_lock():
        nonlocal lock_held
        lock_held = True
        try:
            yield
        finally:
            lock_held = False

    def observed_load(*args, **kwargs):
        assert lock_held is True
        return original_load(*args, **kwargs)

    monkeypatch.setattr(interrogation_module, "compose_lock", observed_lock)
    monkeypatch.setattr(interrogation_module, "_load_validated_member", observed_load)
    build_interrogation_preview(
        draft.compose_id or "",
        "Question?",
        expected_fingerprint=draft.selection_fingerprint,
    )
    assert lock_held is False
