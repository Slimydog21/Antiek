"""Compose twin promote + source refs into research context pack."""

from __future__ import annotations

import os
import sys
from typing import Any

import pytest

_REPO = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
if _REPO not in sys.path:
    sys.path.insert(0, _REPO)

from substrate.engagement_spine import (  # noqa: E402
    HighlightSelection,
    InMemoryEngagementStore,
    assemble_research_context,
    record_twin_insight,
    record_twin_question,
    research_context_html,
    spawn_from_highlight_with_references,
)


class _Rec:
    def __init__(self) -> None:
        self.m: dict[tuple[str, str], str] = {}

    def _id(self, k: str, t: str) -> str:
        key = (k, " ".join(t.lower().split()))
        if key not in self.m:
            self.m[key] = f"{k[0]}_{abs(hash(key)) % 10**12}"
        return self.m[key]

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
        return self._id("question", text)


@pytest.fixture
def store():
    return InMemoryEngagementStore()


def test_assemble_research_context_combines_twins_and_refs(store):
    asset = "paper-attention"
    record_twin_insight(
        asset,
        "Self-attention parallelizes token conditioning.",
        store=store,
        investigation_id="inv_ctx",
    )
    record_twin_question(
        asset,
        "What fails at long context?",
        store=store,
        investigation_id="inv_ctx",
    )
    spawn = spawn_from_highlight_with_references(
        HighlightSelection(
            asset_id=asset,
            selection_text="Attention is all you need.",
            region_id="att-1",
        ),
        store=store,
        references=[
            "https://arxiv.org/abs/1706.03762",
            "https://research.substack.com/p/attention",
        ],
    )
    rec = _Rec()
    pack = assemble_research_context(
        asset,
        store=store,
        spawn_id=spawn.spawn_id,
        promote_insight_fn=rec.promote_insight,
        promote_question_fn=rec.promote_question,
    )
    assert pack.view_format == "html"
    assert pack.spawn_id == spawn.spawn_id
    assert len(pack.twin_units) == 2
    assert len(pack.source_references) == 2
    kinds = {r.kind for r in pack.source_references}
    assert "arxiv" in kinds and "substack" in kinds
    block = pack.prompt_block()
    assert "Self-attention" in block
    assert "1706.03762" in block or "arxiv" in block
    html = research_context_html(pack)
    assert "Self-attention" in html
    assert pack.to_dict()["twin_count"] == 2
    assert pack.to_dict()["ref_count"] == 2


def test_assemble_double_run_stable(store):
    asset = "doc-x"
    record_twin_insight(asset, "Stable twin unit text.", store=store)
    spawn = spawn_from_highlight_with_references(
        HighlightSelection(asset_id=asset, selection_text="s", region_id="r"),
        store=store,
        references=["2402.03300"],
    )
    rec = _Rec()
    kwargs = dict(
        store=store,
        spawn_id=spawn.spawn_id,
        promote_insight_fn=rec.promote_insight,
        promote_question_fn=rec.promote_question,
    )
    a = assemble_research_context(asset, **kwargs)
    b = assemble_research_context(asset, **kwargs)
    assert [u.unit_id for u in a.twin_units] == [u.unit_id for u in b.twin_units]
    assert [r.ref_id for r in a.source_references] == [
        r.ref_id for r in b.source_references
    ]


def test_query_filters_twins(store):
    asset = "doc-y"
    record_twin_insight(asset, "Alpha finding about retrieval.", store=store)
    record_twin_insight(asset, "Beta finding about latency.", store=store)
    rec = _Rec()
    pack = assemble_research_context(
        asset,
        store=store,
        query="retrieval",
        promote_insight_fn=rec.promote_insight,
        promote_question_fn=rec.promote_question,
    )
    assert len(pack.twin_units) == 1
    assert "retrieval" in pack.twin_units[0].text.lower()
