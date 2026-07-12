"""Real-path tests for the research↔reading engagement spine.

Drives shipped functions: spawn_from_highlight, twin note write/read,
merge_spawn_outputs (into_parent + draft_combined). No mocked unit-under-test;
assertions check real return values and store persistence.
"""

from __future__ import annotations

import os
import sys
import threading

import pytest

_REPO = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
if _REPO not in sys.path:
    sys.path.insert(0, _REPO)

from substrate.engagement_spine import (  # noqa: E402
    HighlightSelection,
    InMemoryEngagementStore,
    complete_spawn,
    converge_reviewed_twins,
    get_spawn,
    list_spawns_for_asset,
    list_twin_notes,
    merge_spawn_outputs,
    record_twin_insight,
    record_twin_question,
    seed_twins_for_asset,
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
    assert spawn.research_tier == "deep"  # default when omitted (ji)
    assert "Deep-research" in spawn.goal

    # Persisted
    again = get_spawn(spawn.spawn_id, store=store)
    assert again is not None
    assert again.spawn_id == spawn.spawn_id
    assert again.investigation_id == spawn.investigation_id
    assert again.research_tier == "deep"


def test_spawn_records_research_tier_wrestle(store):
    """Residual (ji): closed research_tier persists on reserved spawn."""
    sel = HighlightSelection(
        asset_id="book-wrestle-1",
        selection_text="Long-horizon claim to wrestle with.",
        region_id="r-wrestle-1",
    )
    spawn = spawn_from_highlight(
        sel, store=store, model_id="glm-5.2", research_tier="wrestle"
    )
    assert spawn.research_tier == "wrestle"
    again = get_spawn(spawn.spawn_id, store=store)
    assert again is not None
    assert again.research_tier == "wrestle"
    # Unknown tier coerces to deep (normalize), force_new for new row.
    coerced = spawn_from_highlight(
        HighlightSelection(
            asset_id="book-wrestle-1",
            selection_text="Other passage",
            region_id="r-coerce",
        ),
        store=store,
        research_tier="turbo",  # type: ignore[arg-type]
    )
    assert coerced.research_tier == "deep"


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


def test_file_twin_identity_is_collision_free_and_restart_safe(file_store, tmp_path):
    record_twin_insight("project/a", "Slash identity.", store=file_store)
    record_twin_question("project_a", "Underscore identity?", store=file_store)

    restarted = _FileStore(tmp_path / "engagement")
    assert [note.text for note in list_twin_notes("project/a", store=restarted)] == [
        "Slash identity."
    ]
    assert [note.text for note in list_twin_notes("project_a", store=restarted)] == [
        "Underscore identity?"
    ]

    record_twin_insight("project/a", "Slash identity.", store=restarted)
    assert len(list_twin_notes("project/a", store=restarted)) == 1
    assert len(list((tmp_path / "engagement" / "twins").glob("asset-*.json"))) == 2


def test_file_twin_writes_serialize_across_store_instances(tmp_path, monkeypatch):
    root = tmp_path / "engagement"
    first = _FileStore(root)
    second = _FileStore(root)
    entered = threading.Event()
    release = threading.Event()
    original_load = first._load_twins_for_write

    def paused_load(asset_id, path):
        notes = original_load(asset_id, path)
        entered.set()
        assert release.wait(timeout=2)
        return notes

    monkeypatch.setattr(first, "_load_twins_for_write", paused_load)
    writer_one = threading.Thread(
        target=record_twin_insight,
        args=("shared/asset", "First process note."),
        kwargs={"store": first},
    )
    writer_two = threading.Thread(
        target=record_twin_insight,
        args=("shared/asset", "Second process note."),
        kwargs={"store": second},
    )
    writer_one.start()
    assert entered.wait(timeout=2)
    writer_two.start()
    assert writer_two.is_alive()
    release.set()
    writer_one.join(timeout=2)
    writer_two.join(timeout=2)
    assert not writer_one.is_alive() and not writer_two.is_alive()
    assert {note.text for note in list_twin_notes("shared/asset", store=first)} == {
        "First process note.",
        "Second process note.",
    }


def test_file_twin_legacy_read_requires_exact_embedded_asset_id(tmp_path):
    root = tmp_path / "engagement"
    store = _FileStore(root)
    legacy = root / "twins" / "project_a.json"
    legacy.write_text(
        '[{"asset_id":"project/a","kind":"insight","note_id":"legacy",'
        '"text":"Legacy slash identity."}]',
        encoding="utf-8",
    )

    assert [note.text for note in list_twin_notes("project/a", store=store)] == [
        "Legacy slash identity."
    ]
    assert list_twin_notes("project_a", store=store) == []
    long_identity = "opaque/" + "x" * 400
    assert list_twin_notes(long_identity, store=store) == []
    record_twin_question(long_identity, "Does the long identity persist?", store=store)
    assert len(list_twin_notes(long_identity, store=store)) == 1


def test_twin_seed_repairs_a_partial_notebook_without_duplicates(file_store):
    record_twin_insight("canonical/partial", "Reviewed insight.", store=file_store)
    repaired = seed_twins_for_asset(
        "canonical/partial",
        store=file_store,
        title="Canonical partial",
        body_text="Exact reviewed body.",
        force_offline=True,
    )
    assert repaired["seeded"] is True
    assert repaired["insight_count"] == 1
    assert repaired["question_count"] == 1

    replayed = seed_twins_for_asset(
        "canonical/partial",
        store=file_store,
        title="Canonical partial",
        body_text="Exact reviewed body.",
        force_offline=True,
    )
    assert replayed["seeded"] is False
    assert replayed["note_count"] == 2


def test_partial_live_seed_reports_offline_when_missing_kind_uses_fallback(
    file_store, monkeypatch
):
    monkeypatch.setenv("ANTIEK_TWIN_SEED_LIVE", "1")
    record_twin_insight("canonical/live-partial", "Existing insight.", store=file_store)
    repaired = seed_twins_for_asset(
        "canonical/live-partial",
        store=file_store,
        title="Partial live",
        body_text="Reviewed body.",
        live_fn=lambda _title, _body: [("insight", "Unused live insight.")],
    )
    assert repaired["live_seed"] is False
    assert repaired["seed_source"] == "engagement_spine.twin.seed_twins_for_asset"


def test_canonical_twin_revision_replaces_only_generated_notes(file_store):
    record_twin_question("canonical/revised", "Operator question?", store=file_store)
    exact_generated_text = (
        "Asset identity: Reviewed research. Opening: Revision two conclusion."
    )
    record_twin_insight("canonical/revised", exact_generated_text, store=file_store)
    converge_reviewed_twins(
        "canonical/revised",
        store=file_store,
        title="Reviewed research",
        body_text="Revision one conclusion.",
        review_sha256="1" * 64,
    )
    converge_reviewed_twins(
        "canonical/revised",
        store=file_store,
        title="Reviewed research",
        body_text="Revision two conclusion.",
        review_sha256="2" * 64,
    )
    notes = list_twin_notes("canonical/revised", store=file_store)
    assert any(note.text == "Operator question?" for note in notes)
    exact_matches = [note for note in notes if note.text == exact_generated_text]
    assert len(exact_matches) == 2
    assert {note.origin for note in exact_matches} == {None, "canonical_review_seed"}
    generated = [
        note for note in notes if note.origin == "canonical_review_seed"
    ]
    assert len(generated) == 2
    assert all(note.source_revision_sha256 == "2" * 64 for note in generated)
    assert any("Revision two conclusion." in note.text for note in generated)
    assert all("Revision one conclusion." not in note.text for note in generated)


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
