"""Session complete → twin → promote → context pack flywheel."""

from __future__ import annotations

import os
import sys
from typing import Any

_REPO = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
if _REPO not in sys.path:
    sys.path.insert(0, _REPO)

from substrate.engagement_spine import (  # noqa: E402
    HighlightSelection,
    InMemoryEngagementStore,
    list_twin_notes,
)
from substrate.floating_session import (  # noqa: E402
    complete_session_with_context_flywheel,
    open_from_highlight_with_references,
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


def test_flywheel_complete_promote_context():
    eng = InMemoryEngagementStore()
    sess = InMemorySessionStore()
    session = open_from_highlight_with_references(
        HighlightSelection(
            asset_id="paper",
            selection_text="Self-attention passage",
            region_id="fly-1",
        ),
        engagement_store=eng,
        session_store=sess,
        references=["https://arxiv.org/abs/1706.03762"],
        research_tier="wrestle",
    )
    assert session.research_tier == "wrestle"
    rec = _Rec()
    result = complete_session_with_context_flywheel(
        session.session_id,
        session_store=sess,
        engagement_store=eng,
        output_text="Full analysis of attention.",
        insights=["Attention is content-addressed routing."],
        questions=["How does multi-head diversify subspaces?"],
        promote_insight_fn=rec.promote_insight,
        promote_question_fn=rec.promote_question,
    )
    assert result.session.status == "complete"
    assert result.view_format == "html"
    twins = list_twin_notes("paper", store=eng)
    assert len(twins) == 2
    assert len(result.context.twin_units) == 2
    assert len(result.context.source_references) == 1
    assert result.context.source_references[0].kind == "arxiv"
    block = result.context.prompt_block()
    assert "content-addressed routing" in block
    assert "1706.03762" in block or "arxiv" in block
    # Double-run promote identity stable
    result2 = complete_session_with_context_flywheel(
        session.session_id,
        session_store=sess,
        engagement_store=eng,
        output_text="Full analysis of attention.",
        insights=["Attention is content-addressed routing."],
        questions=["How does multi-head diversify subspaces?"],
        promote_insight_fn=rec.promote_insight,
        promote_question_fn=rec.promote_question,
    )
    ids1 = sorted(u.unit_id for u in result.context.twin_units)
    ids2 = sorted(u.unit_id for u in result2.context.twin_units)
    assert ids1 == ids2
    d = result.to_dict()
    assert d["session_id"] == session.session_id
    assert "prompt_block" in d
    # Residual (jt): flywheel dict surfaces session research_tier for bench.
    assert d["research_tier"] == "wrestle"
    assert result.session.research_tier == "wrestle"


def test_flywheel_research_tier_default_deep_when_omitted():
    eng = InMemoryEngagementStore()
    sess = InMemorySessionStore()
    session = open_from_highlight_with_references(
        HighlightSelection(
            asset_id="paper-d",
            selection_text="Default tier passage",
            region_id="fly-deep",
        ),
        engagement_store=eng,
        session_store=sess,
    )
    result = complete_session_with_context_flywheel(
        session.session_id,
        session_store=sess,
        engagement_store=eng,
        output_text="Done.",
        insights=["i"],
        questions=["q"],
    )
    assert result.to_dict()["research_tier"] == "deep"
