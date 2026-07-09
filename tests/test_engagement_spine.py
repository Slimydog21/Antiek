"""Real-path tests for the research↔reading engagement spine.

Drives shipped functions: spawn_from_highlight, twin note write/read,
merge_spawn_outputs (into_parent + draft_combined). No mocked unit-under-test;
assertions check real return values and store persistence.
"""

from __future__ import annotations

import os
import sys

import pytest

_REPO = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
if _REPO not in sys.path:
    sys.path.insert(0, _REPO)

from substrate.engagement_spine import (  # noqa: E402
    HighlightSelection,
    InMemoryEngagementStore,
    complete_spawn,
    get_spawn,
    list_spawns_for_asset,
    list_twin_notes,
    merge_spawn_outputs,
    record_twin_insight,
    record_twin_question,
    spawn_from_highlight,
)
from substrate.engagement_spine.store import FileEngagementStore as _FileStore  # noqa: E402


@pytest.fixture
def store():
    return InMemoryEngagementStore()


@pytest.fixture
def file_store(tmp_path):
    return _FileStore(tmp_path / "engagement")


def test_spawn_from_highlight_reserves_investigation(store):
    sel = HighlightSelection(
        asset_id="book-bayes-1",
        selection_text="Bayes theorem updates prior belief with evidence.",
        region_id="r-page-12-a",
        page=12,
    )
    spawn = spawn_from_highlight(sel, store=store, model_id="glm-5.2")
    assert spawn.status == "reserved"
    assert spawn.parent_asset_id == "book-bayes-1"
    assert "Bayes theorem" in spawn.selection_text
    assert spawn.investigation_id.startswith("inv_")
    assert spawn.spawn_id.startswith("spn_")
    assert spawn.model_id == "glm-5.2"
    assert "Deep-research" in spawn.goal

    # Persisted
    again = get_spawn(spawn.spawn_id, store=store)
    assert again is not None
    assert again.spawn_id == spawn.spawn_id
    assert again.investigation_id == spawn.investigation_id


def test_spawn_idempotent_on_same_region(store):
    sel = HighlightSelection(
        asset_id="asset-a",
        selection_text="same passage",
        region_id="region-1",
    )
    a = spawn_from_highlight(sel, store=store)
    b = spawn_from_highlight(sel, store=store)
    assert a.spawn_id == b.spawn_id
    listed = list_spawns_for_asset("asset-a", store=store)
    assert len(listed) == 1


def test_spawn_rejects_empty_selection(store):
    with pytest.raises(ValueError, match="selection_text"):
        spawn_from_highlight(
            HighlightSelection(asset_id="a", selection_text="  "),
            store=store,
        )


def test_twin_insight_and_question_write_read(store):
    ins = record_twin_insight(
        "doc-42",
        "Attention is all you need reframes sequence modeling.",
        store=store,
        investigation_id="inv_x",
    )
    q = record_twin_question(
        "doc-42",
        "What fails when context windows exceed training distribution?",
        store=store,
        source_spawn_id="spn_abc",
    )
    assert ins.kind == "insight"
    assert q.kind == "question"
    assert ins.note_id.startswith("twin_")
    notes = list_twin_notes("doc-42", store=store)
    texts = {n.text for n in notes}
    assert "Attention is all you need reframes sequence modeling." in texts
    assert "What fails when context windows exceed training distribution?" in texts
    # Content-addressed dedup on re-record
    ins2 = record_twin_insight(
        "doc-42",
        "Attention is all you need reframes sequence modeling.",
        store=store,
    )
    assert ins2.note_id == ins.note_id
    assert len(list_twin_notes("doc-42", store=store)) == 2


def test_merge_into_parent_and_draft(store):
    asset = "paper-transformers"
    spawn = spawn_from_highlight(
        HighlightSelection(
            asset_id=asset,
            selection_text="Multi-head attention allows joint subspaces.",
            region_id="mh-1",
            goal_hint="Explain multi-head attention tradeoffs",
        ),
        store=store,
    )
    spawn = complete_spawn(
        spawn.spawn_id,
        store=store,
        output_text="Multi-head attention projects queries/keys/values into h subspaces.",
        insights=["Parallel subspaces improve representation capacity."],
        questions=["How many heads before diminishing returns?"],
    )
    assert spawn.status == "complete"

    record_twin_insight(
        asset,
        "Subspace diversity is the core bet of multi-head attention.",
        store=store,
        source_spawn_id=spawn.spawn_id,
    )

    merged = merge_spawn_outputs(
        asset,
        [spawn.spawn_id],
        store=store,
        mode="into_parent",
        parent_title="Attention paper notes",
        parent_body="Original reading notes on transformers.",
    )
    assert merged.mode == "into_parent"
    assert merged.document_id == asset
    assert merged.source_spawn_ids == (spawn.spawn_id,)
    assert merged.sections_merged >= 2
    content_text = str(merged.doc_model)
    assert "Multi-head attention" in content_text
    assert "Subspace diversity" in content_text or "Twin" in content_text

    draft = merge_spawn_outputs(
        asset,
        [spawn.spawn_id],
        store=store,
        mode="draft_combined",
        parent_title="Attention paper notes",
        parent_body="Original reading notes on transformers.",
    )
    assert draft.mode == "draft_combined"
    assert draft.document_id.startswith("draft_")
    assert draft.document_id != asset
    assert "[Draft]" in draft.doc_model["title"]
    # Parent document still present from into_parent merge
    parent_doc = store.get_document(asset)
    assert parent_doc is not None
    assert parent_doc["document_id"] == asset
    draft_doc = store.get_document(draft.document_id)
    assert draft_doc is not None
    assert draft_doc["mode"] == "draft_combined"


def test_merge_rejects_incomplete_spawn(store):
    spawn = spawn_from_highlight(
        HighlightSelection(asset_id="a1", selection_text="text", region_id="r"),
        store=store,
    )
    with pytest.raises(ValueError, match="only complete"):
        merge_spawn_outputs("a1", [spawn.spawn_id], store=store)


def test_merge_multiple_spawns_collective(store):
    """Collective deep research: merge several completed subagents."""
    asset = "topic-kg"
    ids = []
    for i, text in enumerate(
        [
            "Knowledge graphs need provenance edges.",
            "Twin notes compound into retrieval substrate.",
        ]
    ):
        s = spawn_from_highlight(
            HighlightSelection(
                asset_id=asset,
                selection_text=text,
                region_id=f"r-{i}",
            ),
            store=store,
        )
        complete_spawn(
            s.spawn_id,
            store=store,
            output_text=f"Analysis of: {text}",
            insights=[f"Insight {i}"],
        )
        ids.append(s.spawn_id)
    result = merge_spawn_outputs(
        asset,
        ids,
        store=store,
        mode="draft_combined",
        parent_body="KG reading base",
    )
    assert len(result.source_spawn_ids) == 2
    blob = str(result.doc_model)
    assert "Insight 0" in blob
    assert "Insight 1" in blob


def test_file_store_persists_spawn_and_twins(file_store):
    s = spawn_from_highlight(
        HighlightSelection(
            asset_id="persist-me",
            selection_text="durable selection",
            region_id="r-d",
        ),
        store=file_store,
    )
    record_twin_question("persist-me", "Does durability hold after reload?", store=file_store)
    # Re-open store on same root
    reopened = _FileStore(file_store.root)
    loaded = get_spawn(s.spawn_id, store=reopened)
    assert loaded is not None
    assert loaded.selection_text == "durable selection"
    twins = list_twin_notes("persist-me", store=reopened)
    assert any("durability" in t.text for t in twins)


def test_goal_hint_overrides_default_goal(store):
    s = spawn_from_highlight(
        HighlightSelection(
            asset_id="x",
            selection_text="passage",
            goal_hint="Compare to retrieval-augmented generation",
        ),
        store=store,
    )
    assert s.goal == "Compare to retrieval-augmented generation"
