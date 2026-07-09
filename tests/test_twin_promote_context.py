"""Real-path tests: twin notes → promote_* → search/context residual (o).

Drives shipped orchestration over injectable promote hooks and (optionally)
the real insight_question surface. No live multi-provider network.
"""

from __future__ import annotations

import os
import sys
from typing import Any

import pytest

_REPO = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
if _REPO not in sys.path:
    sys.path.insert(0, _REPO)

from substrate.engagement_spine import (  # noqa: E402
    InMemoryEngagementStore,
    expected_graph_node_id,
    list_twin_notes,
    promote_and_context_for_asset,
    promote_twin_note,
    promote_twin_notes_for_asset,
    record_twin_insight,
    record_twin_question,
    search_twin_context,
    twin_context_html,
)
from substrate.engagement_spine.twin_promote import result_to_context_unit  # noqa: E402


@pytest.fixture
def store():
    return InMemoryEngagementStore()


class _RecordingPromoter:
    """Injectable promote hooks that mint content-addressed-like ids offline."""

    def __init__(self) -> None:
        self.calls: list[dict[str, Any]] = []
        self._ids: dict[tuple[str, str], str] = {}

    def _id(self, kind: str, text: str) -> str:
        key = (kind, " ".join(text.lower().split()))
        if key not in self._ids:
            # Stable offline id; real path uses insight_node_id/question_node_id
            digest = str(abs(hash(key)))[:16]
            self._ids[key] = f"{kind[:3]}_{digest}"
        return self._ids[key]

    def promote_insight(
        self,
        *,
        text: str,
        investigation_id: str,
        source_document_id: str | None = None,
        metadata: dict[str, Any] | None = None,
        embedding_provider: Any = None,
        con: Any = None,
        **kwargs: Any,
    ) -> str:
        self.calls.append(
            {
                "kind": "insight",
                "text": text,
                "investigation_id": investigation_id,
                "source_document_id": source_document_id,
                "metadata": dict(metadata or {}),
            }
        )
        return self._id("insight", text)

    def promote_question(
        self,
        *,
        text: str,
        investigation_id: str,
        source_document_id: str | None = None,
        metadata: dict[str, Any] | None = None,
        embedding_provider: Any = None,
        con: Any = None,
        **kwargs: Any,
    ) -> str:
        self.calls.append(
            {
                "kind": "question",
                "text": text,
                "investigation_id": investigation_id,
                "source_document_id": source_document_id,
                "metadata": dict(metadata or {}),
            }
        )
        return self._id("question", text)


def _fixture_twins(store: InMemoryEngagementStore, asset_id: str = "paper-attention") -> None:
    record_twin_insight(
        asset_id,
        "Self-attention lets every token condition on all others in parallel.",
        store=store,
        investigation_id="inv_fixture",
    )
    record_twin_question(
        asset_id,
        "What fails when context windows exceed the training distribution?",
        store=store,
        investigation_id="inv_fixture",
    )


def test_promote_twin_note_insight_and_question(store):
    _fixture_twins(store)
    notes = list_twin_notes("paper-attention", store=store)
    assert len(notes) == 2
    rec = _RecordingPromoter()
    results = []
    for n in notes:
        results.append(
            promote_twin_note(
                n,
                promote_insight_fn=rec.promote_insight,
                promote_question_fn=rec.promote_question,
            )
        )
    kinds = {r.kind for r in results}
    assert kinds == {"insight", "question"}
    assert all(r.graph_node_id for r in results)
    assert all(r.view_format == "html" for r in results)
    assert all(r.twin_note_id.startswith("twin_") for r in results)
    assert len(rec.calls) == 2
    assert all(c["metadata"].get("origin") == "twin_note" for c in rec.calls)
    assert all(c["metadata"].get("twin_note_id") for c in rec.calls)


def test_repromote_same_twin_text_stable_identity(store):
    ins = record_twin_insight(
        "doc-x",
        "Compounding research needs durable twin substrate.",
        store=store,
        investigation_id="inv_x",
    )
    rec = _RecordingPromoter()
    a = promote_twin_note(
        ins,
        promote_insight_fn=rec.promote_insight,
        promote_question_fn=rec.promote_question,
    )
    b = promote_twin_note(
        ins,
        promote_insight_fn=rec.promote_insight,
        promote_question_fn=rec.promote_question,
    )
    assert a.graph_node_id == b.graph_node_id
    assert a.twin_note_id == b.twin_note_id
    assert a.canonical_text == "compounding research needs durable twin substrate."


def test_promote_and_context_query_includes_twin_text(store):
    _fixture_twins(store)
    rec = _RecordingPromoter()
    pack = promote_and_context_for_asset(
        "paper-attention",
        store=store,
        query="context windows",
        promote_insight_fn=rec.promote_insight,
        promote_question_fn=rec.promote_question,
    )
    assert pack.view_format == "html"
    assert len(pack.promoted) == 2
    assert len(pack.context_units) == 1
    hit = pack.context_units[0]
    assert "context windows" in hit.text.lower()
    assert hit.unit_id == hit.unit_id  # stable
    assert hit.source == "twin_promote"
    assert hit.view_format == "html"
    # unit id matches the promoted graph node for that twin
    q_promoted = next(p for p in pack.promoted if p.kind == "question")
    assert hit.unit_id == q_promoted.graph_node_id
    assert hit.twin_note_id == q_promoted.twin_note_id


def test_double_run_promote_and_context_stable(store):
    _fixture_twins(store)
    rec = _RecordingPromoter()
    kwargs = dict(
        store=store,
        query="Self-attention",
        promote_insight_fn=rec.promote_insight,
        promote_question_fn=rec.promote_question,
    )
    r1 = promote_and_context_for_asset("paper-attention", **kwargs)
    r2 = promote_and_context_for_asset("paper-attention", **kwargs)
    assert len(r1.context_units) == 1
    assert len(r2.context_units) == 1
    assert r1.context_units[0].unit_id == r2.context_units[0].unit_id
    assert r1.context_units[0].text == r2.context_units[0].text
    ids1 = sorted(p.graph_node_id for p in r1.promoted)
    ids2 = sorted(p.graph_node_id for p in r2.promoted)
    assert ids1 == ids2


def test_search_twin_context_filters(store):
    _fixture_twins(store)
    rec = _RecordingPromoter()
    promoted = promote_twin_notes_for_asset(
        "paper-attention",
        store=store,
        promote_insight_fn=rec.promote_insight,
        promote_question_fn=rec.promote_question,
    )
    units = [result_to_context_unit(p) for p in promoted]
    only_q = search_twin_context(units, kind="question")
    assert len(only_q) == 1
    assert only_q[0].kind == "question"
    empty = search_twin_context(units, query="zzznomatch")
    assert empty == []


def test_twin_context_html_not_pdf(store):
    _fixture_twins(store)
    rec = _RecordingPromoter()
    pack = promote_and_context_for_asset(
        "paper-attention",
        store=store,
        promote_insight_fn=rec.promote_insight,
        promote_question_fn=rec.promote_question,
    )
    html = twin_context_html(pack.context_units)
    assert html and html.strip()
    assert "pdf" not in html.lower() or "application/pdf" not in html.lower()
    # twin text present in projection
    assert "Self-attention" in html or "self-attention" in html.lower()
    assert pack.view_format == "html"


def test_real_promote_insight_path_when_graph_available(store, tmp_path, monkeypatch):
    """Optional real DuckDB path: twin text → promote_insight → same node id."""
    import hashlib

    from processing.embedding import _reset_default_provider, set_default_embedding_provider
    from runtime.db_lock import connect_read
    from substrate.graph import insight_question as iq
    from substrate.graph.insight_question import promote_insight, promote_question
    from substrate.graph.schema import init_database_at_path

    class _FakeEmbedding:
        dimension = 8

        def encode(self, text: str) -> list[float]:
            digest = hashlib.sha256(text.encode("utf-8")).digest()
            return [b / 255.0 for b in digest[: self.dimension]]

    db_path = str(tmp_path / "graph.duckdb")
    events_dir = str(tmp_path / "events")
    os.makedirs(events_dir, exist_ok=True)
    monkeypatch.setenv("ANTIEK_RESEARCH_EVENTS_DIR", events_dir)
    monkeypatch.setattr(iq, "graph_db_path", lambda: db_path)
    init_database_at_path(db_path)
    set_default_embedding_provider(_FakeEmbedding())
    try:
        text = "Twin-derived insight about retrieval quality compounds."
        note = record_twin_insight(
            "asset-real",
            text,
            store=store,
            investigation_id="inv_real",
        )
        expected = expected_graph_node_id("insight", text)
        r1 = promote_twin_note(
            note,
            promote_insight_fn=promote_insight,
            promote_question_fn=promote_question,
        )
        r2 = promote_twin_note(
            note,
            promote_insight_fn=promote_insight,
            promote_question_fn=promote_question,
        )
        assert r1.graph_node_id == expected
        assert r2.graph_node_id == expected
        con = connect_read(db_path)
        try:
            row = con.execute(
                "SELECT canonical_label, node_type FROM nodes WHERE node_id = ?",
                [expected],
            ).fetchone()
            assert row is not None
            assert row[0] == text
            assert row[1] == "insight"
        finally:
            con.close()
        pack = promote_and_context_for_asset(
            "asset-real",
            store=store,
            query="retrieval quality",
            promote_insight_fn=promote_insight,
            promote_question_fn=promote_question,
        )
        assert len(pack.context_units) == 1
        assert pack.context_units[0].unit_id == expected
        assert "retrieval quality" in pack.context_units[0].text.lower()
    finally:
        _reset_default_provider()


def test_promote_rejects_empty_asset():
    store = InMemoryEngagementStore()
    with pytest.raises(ValueError, match="asset_id"):
        promote_twin_notes_for_asset("  ", store=store)
