"""Regression: the thought-partner grounding must surface the retrieved
chunk text to the model, not empty strings.

search() (substrate/graph/search.py:260) emits each hit with a
``"chunk_text"`` key. The production thought-partner context mapper
(app.py:_retrieve_thought_partner_context) previously read ``hit.get("text")``
— a key that does not exist in the hit dict — so every retrieved note mapped
to an empty ``note_text`` and GLM-5.2 never saw the operator's library
content even when retrieval ranked the right chunks. CK-1 ("ask your library")
was silently starved.

This guard calls the REAL production mapper with the REAL search() hit-dict
shape (keyed on ``chunk_text``), patching only search() + the embedding model
+ connect_read so no graph or model is needed. It fails against the buggy
``hit.get("text")`` (empty note_text) and passes against the fixed
``hit.get("chunk_text")``."""

from __future__ import annotations

import os
import sys

_REPO = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
if _REPO not in sys.path:
    sys.path.insert(0, _REPO)

import importlib  # noqa: E402

import interfaces.research.api.app as app_mod  # noqa: E402


def _real_shaped_hits() -> list[dict]:
    """The actual shape search() emits — keyed on ``chunk_text`` (graph/search.py:260)."""
    return [
        {
            "chunk_id": "chunk-abc",
            "section_path": None,
            "chunk_text": "The photonic interconnect reduces mesh latency.",
            "token_count": 8,
            "document_id": "doc-1",
            "chunk_index": 0,
            "document_title": "Photonics notes",
            "source_tier": 3,
            "document_type": "article",
            "similarity": 0.61,
        }
    ]


def test_production_mapper_surfaces_chunk_text_as_note_text(monkeypatch):
    """The load-bearing assertion: the REAL production mapper must thread
    search()'s ``chunk_text`` into ``note_text``. Fails on the buggy
    ``hit.get("text")`` (which maps to ""), passes on ``hit.get("chunk_text")``."""

    class _StubEmbedding:
        pass

    captured: dict = {}

    search_mod = importlib.import_module("substrate.graph.search")
    monkeypatch.setattr(search_mod, "SentenceTransformerEmbedding", lambda: _StubEmbedding())

    def _fake_search(con, text, *, model, top_k, policy_tag, **_kw):
        captured["policy_tag"] = policy_tag
        return {"results": _real_shaped_hits()}

    monkeypatch.setattr(search_mod, "search", _fake_search)

    db_lock_mod = importlib.import_module("runtime.db_lock")

    def _fake_connect_read(_db_path):
        class _Ctx:
            def __enter__(self_):
                return None

            def __exit__(self_, *a):
                return False

        return _Ctx()

    monkeypatch.setattr(db_lock_mod, "connect_read", _fake_connect_read)

    notes = app_mod._retrieve_thought_partner_context("photonics", "operator_only")

    assert notes, "production mapper returned no notes from a non-empty hit list"
    assert notes[0]["note_text"] == "The photonic interconnect reduces mesh latency.", (
        "the production mapper dropped chunk_text — note_text was empty, so the "
        "model receives blank grounding even when retrieval ranked the right "
        "chunks (the CK-1 regression)."
    )
    assert notes[0]["note_id"] == "chunk-abc"
    assert notes[0]["source_event_ids"] == ["doc-1"]
    assert captured.get("policy_tag") == "operator_only"
