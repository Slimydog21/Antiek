"""Real-path tests for highlight→floating deep-research session residual."""

from __future__ import annotations

import multiprocessing
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
    get_spawn,
)
from substrate.floating_session import (  # noqa: E402
    complete_session_research,
    get_session,
    list_sessions_for_asset,
    merge_sessions,
    open_from_highlight,
    project_session_html,
    set_view_mode,
)
from substrate.floating_session.store import (  # noqa: E402
    FileSessionStore,
    InMemorySessionStore,
)


def _file_view_cas_worker(root, session_id, target, barrier, queue):
    store = FileSessionStore(root)
    barrier.wait()
    _row, applied = store.compare_and_set_view(session_id, "initial", target)
    queue.put((target, applied))


@pytest.fixture
def eng():
    return InMemoryEngagementStore()


@pytest.fixture
def sessions():
    return InMemorySessionStore()


def test_open_from_highlight_reserves_spawn(eng, sessions):
    sel = HighlightSelection(
        asset_id="book-1",
        selection_text="Attention is content-addressable memory.",
        region_id="r-p12",
        page=12,
    )
    s = open_from_highlight(
        sel,
        engagement_store=eng,
        session_store=sessions,
        model_id="glm-5.2",
        view_mode="floating",
    )
    assert s.session_id.startswith("fsess_")
    assert s.spawn_id.startswith("spn_")
    assert s.investigation_id.startswith("inv_")
    assert s.parent_asset_id == "book-1"
    assert s.view_mode == "floating"
    assert s.model_id == "glm-5.2"
    assert s.status == "reserved"
    spawn = get_spawn(s.spawn_id, store=eng)
    assert spawn is not None
    assert spawn.spawn_id == s.spawn_id


def test_open_idempotent_same_region(eng, sessions):
    sel = HighlightSelection(
        asset_id="a1",
        selection_text="same passage",
        region_id="region-x",
    )
    a = open_from_highlight(sel, engagement_store=eng, session_store=sessions)
    b = open_from_highlight(sel, engagement_store=eng, session_store=sessions)
    assert a.session_id == b.session_id
    assert a.spawn_id == b.spawn_id
    listed = list_sessions_for_asset("a1", session_store=sessions)
    assert len(listed) == 1


def test_file_session_store_rejects_filename_identity_substitution(tmp_path):
    store = FileSessionStore(tmp_path)
    requested = "fsess_0123456789abcdef"
    substituted = "fsess_fedcba9876543210"
    path = tmp_path / "sessions" / f"{requested}.json"
    path.write_text(
        '{"session_id":"' + substituted + '","parent_asset_id":"asset"}',
        encoding="utf-8",
    )
    with pytest.raises(ValueError, match="identity conflicts"):
        store.get_session(requested)
    store._index_path("__operator__", "asset").write_text(
        f'["{requested}"]', encoding="utf-8"
    )
    with pytest.raises(ValueError, match="identity conflicts"):
        store.list_sessions("asset")


def test_set_view_mode_floating_full(eng, sessions):
    sel = HighlightSelection(asset_id="a", selection_text="passage", region_id="r1")
    s = open_from_highlight(sel, engagement_store=eng, session_store=sessions, view_mode="floating")
    full = set_view_mode(s.session_id, "full", session_store=sessions)
    assert full.view_mode == "full"
    assert full.session_id == s.session_id
    assert full.spawn_id == s.spawn_id
    back = set_view_mode(s.session_id, "floating", session_store=sessions)
    assert back.view_mode == "floating"
    # Spawn intact
    assert get_spawn(s.spawn_id, store=eng) is not None


def test_merge_into_parent_and_draft(eng, sessions):
    sel = HighlightSelection(
        asset_id="doc-m",
        selection_text="Bayes updates priors with evidence.",
        region_id="r-bayes",
    )
    s = open_from_highlight(sel, engagement_store=eng, session_store=sessions)
    complete_session_research(
        s.session_id,
        session_store=sessions,
        engagement_store=eng,
        output_text="Posterior is proportional to likelihood times prior.",
        insights=["Bayesian update is multiplicative in odds form"],
        questions=["How does this scale to hierarchical models?"],
    )
    draft = merge_sessions(
        "doc-m",
        [s.session_id],
        session_store=sessions,
        engagement_store=eng,
        mode="draft_combined",
        parent_title="Bayes notes",
        parent_body="Original body.",
    )
    assert draft["mode"] == "draft_combined"
    assert draft["document_id"].startswith("draft_")
    assert s.spawn_id in draft["source_spawn_ids"]
    assert s.session_id in draft["source_session_ids"]

    parent = merge_sessions(
        "doc-m",
        [s.session_id],
        session_store=sessions,
        engagement_store=eng,
        mode="into_parent",
        parent_title="Bayes notes",
        parent_body="Original body.",
    )
    assert parent["mode"] == "into_parent"
    assert parent["document_id"] == "doc-m"


def test_multi_session_collective_merge(eng, sessions):
    s1 = open_from_highlight(
        HighlightSelection(asset_id="doc-c", selection_text="first highlight", region_id="r1"),
        engagement_store=eng,
        session_store=sessions,
    )
    s2 = open_from_highlight(
        HighlightSelection(asset_id="doc-c", selection_text="second highlight", region_id="r2"),
        engagement_store=eng,
        session_store=sessions,
    )
    for s in (s1, s2):
        complete_session_research(
            s.session_id,
            session_store=sessions,
            engagement_store=eng,
            output_text=f"Research for {s.session_id}",
            insights=[f"Insight {s.spawn_id}"],
            questions=[f"Question {s.spawn_id}?"],
        )
    merged = merge_sessions(
        "doc-c",
        [s1.session_id, s2.session_id],
        session_store=sessions,
        engagement_store=eng,
        mode="draft_combined",
        parent_title="Collective analysis",
    )
    assert len(merged["source_spawn_ids"]) == 2
    assert s1.spawn_id in merged["source_spawn_ids"]
    assert s2.spawn_id in merged["source_spawn_ids"]
    assert merged["sections_merged"] >= 1


def test_project_session_html_not_pdf(eng, sessions):
    s = open_from_highlight(
        HighlightSelection(
            asset_id="doc-h",
            selection_text="HTML-first reading asset passage.",
            region_id="r-html",
        ),
        engagement_store=eng,
        session_store=sessions,
        model_id="composer-2.5",
    )
    html = project_session_html(s.session_id, session_store=sessions, engagement_store=eng)
    assert s.session_id in html or s.spawn_id in html
    assert "doc-h" in html or "HTML-first" in html
    assert not html.lstrip().lower().startswith("%pdf")

    complete_session_research(
        s.session_id,
        session_store=sessions,
        engagement_store=eng,
        output_text="Merged research prose about HTML vision.",
        insights=["HTML is agent-controllable"],
        questions=["What breaks PDF-first workflows?"],
    )
    merge = merge_sessions(
        "doc-h",
        [s.session_id],
        session_store=sessions,
        engagement_store=eng,
        mode="draft_combined",
        parent_title="HTML vision",
    )
    html2 = project_session_html(
        s.session_id,
        session_store=sessions,
        engagement_store=eng,
        merge_result=merge,
    )
    assert len(html2) > 40
    assert not html2.lstrip().lower().startswith("%pdf")
    assert "HTML" in html2 or "vision" in html2.lower() or s.spawn_id in html2


def test_get_session_refreshes_status(eng, sessions):
    s = open_from_highlight(
        HighlightSelection(asset_id="x", selection_text="t", region_id="r"),
        engagement_store=eng,
        session_store=sessions,
    )
    complete_session_research(
        s.session_id,
        session_store=sessions,
        engagement_store=eng,
        output_text="done",
    )
    again = get_session(s.session_id, session_store=sessions, engagement_store=eng)
    assert again is not None
    assert again.status == "complete"


def test_complete_session_records_twin_notes(eng, sessions):
    from substrate.engagement_spine import list_twin_notes

    s = open_from_highlight(
        HighlightSelection(
            asset_id="doc-twin",
            selection_text="passage for twin deposit",
            region_id="r-twin",
        ),
        engagement_store=eng,
        session_store=sessions,
    )
    complete_session_research(
        s.session_id,
        session_store=sessions,
        engagement_store=eng,
        output_text="analysis body",
        insights=["Twin insight from session complete"],
        questions=["Twin question from session complete?"],
    )
    twins = list_twin_notes("doc-twin", store=eng)
    texts = {t.text for t in twins}
    assert "Twin insight from session complete" in texts
    assert "Twin question from session complete?" in texts
    assert all(t.source_spawn_id == s.spawn_id for t in twins)


def test_complete_session_can_skip_twin_record(eng, sessions):
    from substrate.engagement_spine import list_twin_notes

    s = open_from_highlight(
        HighlightSelection(
            asset_id="doc-notwin",
            selection_text="no twin",
            region_id="r-notwin",
        ),
        engagement_store=eng,
        session_store=sessions,
    )
    complete_session_research(
        s.session_id,
        session_store=sessions,
        engagement_store=eng,
        output_text="x",
        insights=["should not record"],
        record_twins=False,
    )
    assert list_twin_notes("doc-notwin", store=eng) == []


def test_status_refresh_cannot_clobber_concurrent_view_cas():
    store = InMemorySessionStore()
    session_id = "fsess_0123456789abcdef"
    store.put_session(
        {
            "session_id": session_id,
            "parent_asset_id": "asset-race",
            "spawn_id": "spawn-race",
            "status": "reserved",
            "view_mode": "floating",
        }
    )
    barrier = threading.Barrier(3)

    def refresh_status() -> None:
        barrier.wait()
        store.update_status(session_id, "complete")

    def expand_view() -> None:
        barrier.wait()
        store.compare_and_set_view(session_id, "floating", "full")

    workers = [
        threading.Thread(target=refresh_status),
        threading.Thread(target=expand_view),
    ]
    for worker in workers:
        worker.start()
    barrier.wait()
    for worker in workers:
        worker.join()

    assert store.get_session(session_id) == {
        "session_id": session_id,
        "parent_asset_id": "asset-race",
        "spawn_id": "spawn-race",
        "status": "complete",
        "view_mode": "full",
    }


def test_file_session_view_cas_is_cross_process(tmp_path):
    store = FileSessionStore(tmp_path)
    session_id = "fsess_abcdef0123456789"
    store.put_session(
        {
            "session_id": session_id,
            "parent_asset_id": "asset-process-race",
            "spawn_id": "spawn-process-race",
            "status": "reserved",
            "view_mode": "initial",
        }
    )
    ctx = multiprocessing.get_context("spawn")
    barrier = ctx.Barrier(3)
    queue = ctx.Queue()
    workers = [
        ctx.Process(
            target=_file_view_cas_worker,
            args=(tmp_path, session_id, target, barrier, queue),
        )
        for target in ("floating", "full")
    ]
    for worker in workers:
        worker.start()
    barrier.wait()
    results = [queue.get(timeout=5) for _ in workers]
    for worker in workers:
        worker.join(timeout=5)
        assert worker.exitcode == 0

    assert sorted(applied for _target, applied in results) == [False, True]
    assert store.get_session(session_id)["view_mode"] in {"floating", "full"}


def test_owner_index_never_deserializes_foreign_malformed_session(tmp_path):
    store = FileSessionStore(tmp_path)
    alice_id = "fsess_1111111111111111"
    store.put_session(
        {
            "session_id": alice_id,
            "parent_asset_id": "shared-asset",
            "spawn_id": "alice-spawn",
            "owner_id": "alice",
            "status": "reserved",
            "view_mode": "floating",
        }
    )
    bob_id = "fsess_2222222222222222"
    (tmp_path / "sessions" / f"{bob_id}.json").write_text(
        "not-json", encoding="utf-8"
    )
    store._index_path("bob", "shared-asset").write_text(
        f'["{bob_id}"]', encoding="utf-8"
    )

    rows = store.list_sessions("shared-asset", "alice")
    assert [row["session_id"] for row in rows] == [alice_id]


def test_replayed_open_repairs_crash_between_session_row_and_owner_index(
    tmp_path, monkeypatch
):
    engagement = InMemoryEngagementStore()
    sessions = FileSessionStore(tmp_path)
    selection = HighlightSelection(
        asset_id="repair-asset",
        selection_text="recover the durable reopen index",
        region_id="repair-region",
    )
    real_index = sessions._index_session
    calls = 0

    def crash_once(row):
        nonlocal calls
        calls += 1
        if calls == 1:
            raise RuntimeError("injected row-before-index crash")
        return real_index(row)

    monkeypatch.setattr(sessions, "_index_session", crash_once)
    with pytest.raises(RuntimeError, match="row-before-index"):
        open_from_highlight(
            selection,
            engagement_store=engagement,
            session_store=sessions,
            owner_id="alice",
        )

    recovered = open_from_highlight(
        selection,
        engagement_store=engagement,
        session_store=sessions,
        owner_id="alice",
    )
    listed = sessions.list_sessions("repair-asset", "alice")
    assert [row["session_id"] for row in listed] == [recovered.session_id]
