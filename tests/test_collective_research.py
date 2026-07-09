"""Collective multi-spawn deep-research merge residual."""

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
    collective_research_html,
    merge_spawns_collective,
    record_twin_insight,
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


def test_merge_two_spawns_collective(store):
    record_twin_insight("asset-a", "Finding A about transformers.", store=store)
    record_twin_insight("asset-b", "Finding B about residual nets.", store=store)
    s1 = spawn_from_highlight_with_references(
        HighlightSelection(
            asset_id="asset-a",
            selection_text="transformers",
            region_id="a1",
        ),
        store=store,
        references=["https://arxiv.org/abs/1706.03762"],
        research_tier="fast",
    )
    s2 = spawn_from_highlight_with_references(
        HighlightSelection(
            asset_id="asset-b",
            selection_text="residual",
            region_id="b1",
        ),
        store=store,
        references=["https://arxiv.org/abs/1512.03385"],
        research_tier="wrestle",
    )
    rec = _Rec()
    unit = merge_spawns_collective(
        [s1.spawn_id, s2.spawn_id],
        store=store,
        promote_insight_fn=rec.promote_insight,
        promote_question_fn=rec.promote_question,
    )
    assert unit.collective_id.startswith("col_")
    assert set(unit.spawn_ids) == {s1.spawn_id, s2.spawn_id}
    assert set(unit.asset_ids) == {"asset-a", "asset-b"}
    assert len(unit.twin_units) >= 2
    assert len(unit.source_references) == 2
    # Residual (ke): depth-max of member tiers for continue-as-unit.
    assert unit.research_tiers == ("fast", "wrestle")
    assert unit.recommended_research_tier == "wrestle"
    d = unit.to_dict()
    assert d["recommended_research_tier"] == "wrestle"
    assert d["research_tiers"] == ["fast", "wrestle"]
    block = unit.prompt_block()
    assert "recommended_research_tier: wrestle" in block
    assert "Finding A" in block and "Finding B" in block
    assert "1706.03762" in block or "arxiv" in block
    html = collective_research_html(unit)
    assert unit.collective_id in html or "Collective" in html
    assert unit.view_format == "html"


def test_collective_id_stable_regardless_of_order(store):
    s1 = spawn_from_highlight_with_references(
        HighlightSelection(asset_id="x", selection_text="one", region_id="r1"),
        store=store,
        references=["2401.00001"],
    )
    s2 = spawn_from_highlight_with_references(
        HighlightSelection(asset_id="y", selection_text="two", region_id="r2"),
        store=store,
        references=["https://z.substack.com/p/post"],
    )
    rec = _Rec()
    a = merge_spawns_collective(
        [s1.spawn_id, s2.spawn_id],
        store=store,
        promote_insight_fn=rec.promote_insight,
        promote_question_fn=rec.promote_question,
        include_twin_promote=False,
    )
    b = merge_spawns_collective(
        [s2.spawn_id, s1.spawn_id],
        store=store,
        promote_insight_fn=rec.promote_insight,
        promote_question_fn=rec.promote_question,
        include_twin_promote=False,
    )
    assert a.collective_id == b.collective_id
    assert {r.ref_id for r in a.source_references} == {
        r.ref_id for r in b.source_references
    }


def test_collective_rejects_empty_and_missing(store):
    with pytest.raises(ValueError):
        merge_spawns_collective([], store=store)
    with pytest.raises(KeyError):
        merge_spawns_collective(["spn_nope"], store=store)
