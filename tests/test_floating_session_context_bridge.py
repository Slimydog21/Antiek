"""Floating session bridge to twin/source-ref/collective research context."""

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
    record_twin_insight,
)
from substrate.floating_session import (  # noqa: E402
    attach_session_source_references,
    open_from_highlight_with_references,
    session_research_context,
    sessions_collective_research,
)
from substrate.floating_session.store import InMemorySessionStore  # noqa: E402


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
def stores():
    return InMemoryEngagementStore(), InMemorySessionStore()


def test_open_with_refs_and_session_context(stores):
    eng, sess = stores
    record_twin_insight("book-1", "Key claim about attention.", store=eng)
    session = open_from_highlight_with_references(
        HighlightSelection(
            asset_id="book-1",
            selection_text="Attention passage",
            region_id="p1",
        ),
        engagement_store=eng,
        session_store=sess,
        references=["https://arxiv.org/abs/1706.03762"],
        model_id="test-model",
        research_tier="wrestle",
    )
    assert session.session_id.startswith("fsess_")
    assert session.model_id == "test-model"
    assert session.research_tier == "wrestle"  # residual (ji)
    rec = _Rec()
    pack = session_research_context(
        session.session_id,
        session_store=sess,
        engagement_store=eng,
        promote_insight_fn=rec.promote_insight,
        promote_question_fn=rec.promote_question,
    )
    assert len(pack.twin_units) == 1
    assert len(pack.source_references) == 1
    assert pack.source_references[0].kind == "arxiv"
    assert "Key claim" in pack.prompt_block()


def test_attach_more_refs_and_collective(stores):
    eng, sess = stores
    s1 = open_from_highlight_with_references(
        HighlightSelection(asset_id="a", selection_text="one", region_id="r1"),
        engagement_store=eng,
        session_store=sess,
        references=["2401.00001"],
    )
    s2 = open_from_highlight_with_references(
        HighlightSelection(asset_id="b", selection_text="two", region_id="r2"),
        engagement_store=eng,
        session_store=sess,
        references=["https://x.substack.com/p/y"],
    )
    attach_session_source_references(
        s1.session_id,
        ["https://example.com/extra"],
        session_store=sess,
        engagement_store=eng,
    )
    rec = _Rec()
    unit = sessions_collective_research(
        [s1.session_id, s2.session_id],
        session_store=sess,
        engagement_store=eng,
        promote_insight_fn=rec.promote_insight,
        promote_question_fn=rec.promote_question,
        include_twin_promote=False,
    )
    assert unit.collective_id.startswith("col_")
    assert len(unit.spawn_ids) == 2
    kinds = {r.kind for r in unit.source_references}
    assert "arxiv" in kinds
    assert "substack" in kinds
    assert "url" in kinds


def test_double_run_session_open_stable(stores):
    eng, sess = stores
    sel = HighlightSelection(asset_id="z", selection_text="stable", region_id="rz")
    a = open_from_highlight_with_references(
        sel,
        engagement_store=eng,
        session_store=sess,
        references=["1706.03762"],
    )
    b = open_from_highlight_with_references(
        sel,
        engagement_store=eng,
        session_store=sess,
        references=["1706.03762"],
    )
    assert a.session_id == b.session_id
    assert a.spawn_id == b.spawn_id
