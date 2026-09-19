"""Thought Partner library grounding uses SERVABLE hybrid when env-gated."""

from __future__ import annotations

import importlib
import os
import sys

import pytest

_REPO = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
if _REPO not in sys.path:
    sys.path.insert(0, _REPO)

import interfaces.research.api.app as app_mod  # noqa: E402
from substrate.graph.retrieval_adapters.turbopuffer import (  # noqa: E402
    probe_turbopuffer_health,
)
from substrate.graph.retrieval_substrate import (  # noqa: E402
    resolve_reuse_substrate_kind,
    resolve_servable_hybrid_kind,
)


def test_resolve_alias_matches_reuse():
    assert resolve_servable_hybrid_kind is resolve_reuse_substrate_kind


def test_probe_turbopuffer_health_honest_defaults(monkeypatch, tmp_path):
    monkeypatch.delenv("ANTIEK_TURBOPUFFER_SERVABLE", raising=False)
    monkeypatch.delenv("ANTIEK_TURBOPUFFER_SHADOW_ENABLED", raising=False)
    monkeypatch.delenv("TURBOPUFFER_API_KEY", raising=False)
    monkeypatch.setenv("ANTIEK_TURBOPUFFER_MANIFEST_DIR", str(tmp_path))
    snap = probe_turbopuffer_health()
    assert snap["hybrid_ready"] is False
    assert snap["production_default_mount"] is False
    assert snap["thought_partner_hybrid_wired"] is True
    assert snap["duckdb_is_sot"] is True
    assert snap["resolved_kind"] == "brute_force"


def test_probe_hybrid_ready_needs_pointer(monkeypatch, tmp_path):
    monkeypatch.setenv("ANTIEK_TURBOPUFFER_SERVABLE", "1")
    monkeypatch.setenv("TURBOPUFFER_API_KEY", "test-key")
    monkeypatch.setenv("ANTIEK_TURBOPUFFER_MANIFEST_DIR", str(tmp_path))
    assert probe_turbopuffer_health()["hybrid_ready"] is False
    (tmp_path / "active.json").write_text(
        '{"active_namespace":"ns","content_hash":"abc","context":{}}',
        encoding="utf-8",
    )
    snap = probe_turbopuffer_health()
    assert snap["active_pointer_file"] is True
    assert snap["hybrid_ready"] is True
    assert snap["resolved_kind"] == "turbopuffer"
    assert snap["production_default_mount"] is False


def test_retrieve_tp_uses_hybrid_query_when_env(monkeypatch):
    """attribution_eligible + env → substrate.query; not bare search()."""

    class _StubEmbedding:
        pass

    class _Sub:
        def query(self, text, *, top_k=5, policy_tag="attribution_eligible", **_kw):
            assert policy_tag == "attribution_eligible"
            return {
                "results": [
                    {
                        "chunk_id": "c1",
                        "chunk_text": "SERVABLE hybrid hit",
                        "document_id": "d1",
                        "similarity": 0.9,
                    }
                ],
                "status": "servable",
            }

    search_mod = importlib.import_module("substrate.graph.search")
    monkeypatch.setattr(search_mod, "SentenceTransformerEmbedding", lambda: _StubEmbedding())

    def _boom(*_a, **_k):
        raise AssertionError("bare search() must not run when hybrid resolved")

    monkeypatch.setattr(search_mod, "search", _boom)

    db_lock_mod = importlib.import_module("runtime.db_lock")

    class _Ctx:
        def __enter__(self):
            return object()

        def __exit__(self, *a):
            return False

    monkeypatch.setattr(db_lock_mod, "connect_read", lambda _p: _Ctx())
    monkeypatch.setattr(
        app_mod,  # patched via substrate.graph modules used inside fn
        "_retrieve_thought_partner_context",
        app_mod._retrieve_thought_partner_context,
    )

    rs = importlib.import_module("substrate.graph.retrieval_substrate")
    monkeypatch.setattr(rs, "resolve_reuse_substrate_kind", lambda: "turbopuffer")
    monkeypatch.setattr(rs, "make_substrate_from_con", lambda *a, **k: _Sub())

    # Re-import path: function closes over imports at call time — patch modules
    # that the function imports inside the body.
    notes = app_mod._retrieve_thought_partner_context(
        "corpus question", "attribution_eligible",
    )
    assert notes[0]["note_text"] == "SERVABLE hybrid hit"
    assert notes[0]["note_id"] == "c1"


def test_retrieve_tp_operator_only_still_maps_via_hybrid_adapter(monkeypatch):
    """operator_only uses hybrid substrate; adapter must receive that policy."""

    class _StubEmbedding:
        pass

    seen = {}

    class _Sub:
        def query(self, text, *, top_k=5, policy_tag="attribution_eligible", **_kw):
            seen["policy_tag"] = policy_tag
            return {
                "results": [
                    {
                        "chunk_id": "priv",
                        "chunk_text": "private duckdb path",
                        "document_id": "d2",
                        "similarity": 0.5,
                    }
                ],
                "status": "duckdb — non_servable_policy",
            }

    search_mod = importlib.import_module("substrate.graph.search")
    monkeypatch.setattr(search_mod, "SentenceTransformerEmbedding", lambda: _StubEmbedding())
    db_lock_mod = importlib.import_module("runtime.db_lock")

    class _Ctx:
        def __enter__(self):
            return object()

        def __exit__(self, *a):
            return False

    monkeypatch.setattr(db_lock_mod, "connect_read", lambda _p: _Ctx())
    rs = importlib.import_module("substrate.graph.retrieval_substrate")
    monkeypatch.setattr(rs, "resolve_reuse_substrate_kind", lambda: "turbopuffer")
    monkeypatch.setattr(rs, "make_substrate_from_con", lambda *a, **k: _Sub())

    notes = app_mod._retrieve_thought_partner_context("q", "operator_only")
    assert seen["policy_tag"] == "operator_only"
    assert notes[0]["note_text"] == "private duckdb path"
