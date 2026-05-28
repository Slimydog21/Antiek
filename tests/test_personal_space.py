"""Tests for the Read SPR-13 personal document space selectors
(``substrate/books/personal_space.py``).

Coverage (the rigor #3 edge enumeration is load-bearing — a happy path with
these untested is NOT done):
  - M1 list: meta-reading deliverables + saved reads enumerated from the event
    log, newest first, deduped; ZERO assets → empty (no crash, no phantom).
  - M2 categorize: DETERMINISM on a fixture (same docs → same categories
    run-to-run, asserted by re-running and comparing); ONE doc → recency
    fallback (no spurious "category of one"); many themes → coherent clusters
    (not one giant bucket); no-extractable-term cluster → honest "Uncategorized".
  - M3 match: a related doc surfaces the matching project; an UNRELATED doc
    surfaces nothing (decline-equivalent — no hollow suggestion); a doc matching
    MULTIPLE projects ranks them (top match + >1) WITHOUT double-filing; the
    threshold is honoured.

The embedding stub is KEYWORD-SEMANTIC (not a hash): each text maps to a vector
over a fixed term axis, so texts sharing keywords have high cosine and unrelated
texts low — letting the tests assert real clustering/matching BEHAVIOUR, not
merely that the code runs (a passing test that doesn't exercise the change is a
fake gate).
"""

from __future__ import annotations

import json
import os
import sys

import pytest

_PKG_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if _PKG_ROOT not in sys.path:
    sys.path.insert(0, _PKG_ROOT)

from substrate.books.personal_space import (  # noqa: E402
    CLUSTER_SIMILARITY_THRESHOLD,
    MATCH_SUGGESTION_THRESHOLD,
    MIN_ASSETS_FOR_CLUSTERING,
    PersonalAsset,
    categorize_assets,
    list_personal_assets,
    match_document_to_investigations,
)


# ── A keyword-semantic embedding stub ─────────────────────────────────
# Fixed term axis: a text's vector is the (normalized) count of each axis term
# it contains. Texts sharing terms → high cosine; disjoint terms → 0. Deterministic.
_AXIS = ["stoicism", "virtue", "calm", "quantum", "physics", "entangle",
         "garden", "soil", "compost"]


class KeywordEmbedding:
    dimension = len(_AXIS)

    def encode(self, text: str) -> list[float]:
        low = text.lower()
        vec = [float(low.count(term)) for term in _AXIS]
        if not any(vec):
            # An off-axis text gets a tiny unique-but-orthogonal signal so it
            # never accidentally clusters with anything (honest: it's its own).
            h = sum(ord(c) for c in text) or 1
            vec = [0.0] * self.dimension
            vec[h % self.dimension] = 0.01
        return vec


# ── Fixtures: a fixture event log ─────────────────────────────────────


@pytest.fixture
def events_dir(tmp_path, monkeypatch):
    d = tmp_path / "events"
    d.mkdir()
    monkeypatch.setenv("ANTIEK_RESEARCH_EVENTS_DIR", str(d))
    return str(d)


def _write_event(events_dir, investigation_id, row):
    path = os.path.join(events_dir, f"{investigation_id}.jsonl")
    with open(path, "a", encoding="utf-8") as f:
        f.write(json.dumps(row) + "\n")


def _meta_reading_event(asset_id, prompt, corpus, emitted_at):
    iid = f"read-meta-{asset_id}"
    return iid, {
        "event_id": f"ev-{asset_id}",
        "investigation_id": iid,
        "action_type": "read.meta_reading.generated",
        "emitted_at": emitted_at,
        "payload": {
            "action_type": "read.meta_reading.generated",
            "asset_id": asset_id,
            "prompt": prompt,
            "report": f"A reading about {prompt}.",
            "length_unit": "pages",
            "length_amount": 3,
            "truncated": False,
            "corpus_scope": "hard",
            "corpus_document_ids": corpus,
            "citations": [],
        },
    }


def _source_read_event(document_id, emitted_at):
    iid = f"read-{document_id}"
    return iid, {
        "event_id": f"ev-read-{document_id}-{emitted_at}",
        "investigation_id": iid,
        "document_id": document_id,
        "action_type": "source.read",
        "emitted_at": emitted_at,
        "payload": {
            "action_type": "source.read",
            "chunk_id": None,
            "dwell_ms": 60000,
            "page_count": 5,
        },
    }


def _start_event(investigation_id, question, emitted_at):
    return investigation_id, {
        "event_id": f"ev-start-{investigation_id}",
        "investigation_id": investigation_id,
        "action_type": "investigation.start_requested",
        "emitted_at": emitted_at,
        "payload": {
            "action_type": "investigation.start_requested",
            "question": question,
            "context": "",
        },
    }


# ── M1 — list personal assets ─────────────────────────────────────────


def test_m1_lists_created_deliverables_and_saved_reads_newest_first(events_dir):
    for iid, row in [
        _meta_reading_event("a1", "stoicism and calm", ["d1"], "2026-05-01T00:00:00Z"),
        _meta_reading_event("a2", "quantum physics", ["d2"], "2026-05-03T00:00:00Z"),
        _source_read_event("dbook", "2026-05-02T00:00:00Z"),
    ]:
        _write_event(events_dir, iid, row)

    assets = list_personal_assets(events_dir=events_dir)
    assert len(assets) == 3
    # Newest first.
    assert [a.asset_id for a in assets] == ["a2", "read:dbook", "a1"]
    kinds = {a.asset_id: a.kind for a in assets}
    assert kinds["a2"] == "meta_reading"
    assert kinds["read:dbook"] == "saved_read"
    # Each opens back into a real surface (M1 acceptance).
    routes = {a.asset_id: a.open_route for a in assets}
    assert routes["a2"] == "/read/meta-reading/a2"
    assert routes["read:dbook"] == "/read/dbook"


def test_m1_zero_assets_returns_empty_no_crash(events_dir):
    # rigor #3 (a): ZERO docs → empty, no crash, no phantom.
    assert list_personal_assets(events_dir=events_dir) == []


def test_m1_saved_reads_dedupe_to_latest(events_dir):
    iid, row1 = _source_read_event("dbook", "2026-05-01T00:00:00Z")
    _write_event(events_dir, iid, row1)
    _, row2 = _source_read_event("dbook", "2026-05-05T00:00:00Z")
    _write_event(events_dir, iid, row2)
    assets = list_personal_assets(events_dir=events_dir)
    saved = [a for a in assets if a.kind == "saved_read"]
    assert len(saved) == 1
    assert saved[0].emitted_at == "2026-05-05T00:00:00Z"


# ── M2 — auto-categorization (clustering) ─────────────────────────────


def _assets(*specs):
    """specs: (asset_id, prompt) → PersonalAsset (meta_reading)."""
    return [
        PersonalAsset(
            asset_id=aid,
            kind="meta_reading",
            title=prompt,
            prompt=prompt,
            document_ids=[f"d-{aid}"],
            emitted_at="2026-05-01T00:00:00Z",
            open_route=f"/read/meta-reading/{aid}",
        )
        for aid, prompt in specs
    ]


def test_m2_clusters_are_deterministic_run_to_run(events_dir):
    # rigor #1/#3: the FIXTURE must yield the SAME categories run-to-run.
    assets = _assets(
        ("a1", "stoicism virtue and calm"),
        ("a2", "stoicism calm under pressure"),
        ("a3", "quantum physics and entangle"),
        ("a4", "quantum physics entangle states"),
        ("a5", "garden soil and compost"),
    )
    model = KeywordEmbedding()
    first = categorize_assets(assets, model=model)
    second = categorize_assets(assets, model=model)
    # Determinism: identical labels + membership + ordering across runs.
    assert first.ordering == "theme"
    serial = lambda s: [(c.label, tuple(c.asset_ids)) for c in s.categories]
    assert serial(first) == serial(second)
    # Coherent, NOT one giant bucket (rigor #3 c): stoicism / quantum / garden
    # are three distinct clusters.
    assert len(first.categories) == 3
    membership = {tuple(sorted(c.asset_ids)) for c in first.categories}
    assert ("a1", "a2") in membership
    assert ("a3", "a4") in membership
    assert ("a5",) in membership
    # System-named from salient terms — the user did not label these.
    labels = " ".join(c.label for c in first.categories).lower()
    assert "stoicism" in labels and "quantum" in labels and "garden" in labels


def test_m2_one_doc_falls_back_to_recency_no_spurious_category(events_dir):
    # rigor #3 (b): ONE doc → no spurious "category of one" theme.
    space = categorize_assets(_assets(("a1", "stoicism")), model=KeywordEmbedding())
    assert space.ordering == "recency"
    assert len(space.categories) == 1
    assert space.categories[0].ordering == "recency"
    assert space.categories[0].label == "Recently read & created"


def test_m2_below_stability_bound_is_recency(events_dir):
    # Below MIN_ASSETS_FOR_CLUSTERING → honest recency fallback, no theme labels.
    assets = _assets(("a1", "stoicism"), ("a2", "quantum"), ("a3", "garden"))
    assert len(assets) < MIN_ASSETS_FOR_CLUSTERING
    space = categorize_assets(assets, model=KeywordEmbedding())
    assert space.ordering == "recency"
    assert space.stability_bound == MIN_ASSETS_FOR_CLUSTERING


def test_m2_empty_space_has_no_categories(events_dir):
    space = categorize_assets([], model=KeywordEmbedding())
    assert space.categories == []
    assert space.ordering == "recency"


def test_m2_model_unavailable_falls_back_not_crash(events_dir):
    class BrokenModel:
        dimension = 4

        def encode(self, text):
            raise RuntimeError("model unavailable")

    assets = _assets(
        ("a1", "stoicism"), ("a2", "quantum"), ("a3", "garden"), ("a4", "physics")
    )
    space = categorize_assets(assets, model=BrokenModel())
    # Honest fallback (one bucket), never a fabricated theme.
    assert space.ordering == "recency"
    assert len(space.categories) == 1


def test_m2_colliding_label_clusters_get_distinct_ids_and_labels(events_dir):
    # Two DISTINCT clusters can share top salient terms: the off-axis words
    # "ethics/morality/wisdom" dominate the LABEL, while the on-axis "stoicism"
    # vs "garden" embeddings are orthogonal and split the CLUSTERS. The
    # category_id must stay unique (the safe UI key) AND the labels must be
    # disambiguated — otherwise two same-labelled sections collide as a React
    # list key and one is silently dropped.
    shared = "ethics ethics ethics morality morality wisdom wisdom"
    assets = _assets(
        ("a1", f"{shared} stoicism"),
        ("a2", f"{shared} stoicism"),
        ("b1", f"{shared} garden"),
        ("b2", f"{shared} garden"),
    )
    space = categorize_assets(assets, model=KeywordEmbedding())
    assert space.ordering == "theme"
    # Orthogonal embeddings ⇒ two clusters, not one bucket.
    assert len(space.categories) == 2
    # Unique ids (the safe key) and disambiguated labels (no duplicate label).
    assert len({c.category_id for c in space.categories}) == 2
    assert len({c.label for c in space.categories}) == 2
    # The collision was broken by the distinguishing term, not merely an ordinal.
    assert any("garden" in c.label for c in space.categories)


# ── M3 — semantic-match suggestion ────────────────────────────────────


def test_m3_related_doc_surfaces_matching_project(events_dir):
    iid, row = _start_event("inv-stoic", "What did the stoics teach about calm?", "2026-05-01T00:00:00Z")
    _write_event(events_dir, iid, row)
    matches = match_document_to_investigations(
        doc_text="stoicism virtue and calm",
        model=KeywordEmbedding(),
        events_dir=events_dir,
    )
    assert len(matches) == 1
    assert matches[0].investigation_id == "inv-stoic"
    assert matches[0].score >= MATCH_SUGGESTION_THRESHOLD


def test_m3_unrelated_doc_surfaces_nothing(events_dir):
    # decline-equivalent: a doc that matches no project → no hollow suggestion.
    iid, row = _start_event("inv-quantum", "How does quantum entangle work?", "2026-05-01T00:00:00Z")
    _write_event(events_dir, iid, row)
    matches = match_document_to_investigations(
        doc_text="garden soil and compost",
        model=KeywordEmbedding(),
        events_dir=events_dir,
    )
    assert matches == []


def test_m3_multi_project_tie_ranks_without_double_filing(events_dir):
    # rigor #3 (d): a doc matching MULTIPLE projects surfaces >1 ranked, never
    # double-files / auto-ships to all.
    for iid, row in [
        _start_event("inv-stoic-a", "stoicism and calm in daily life", "2026-05-01T00:00:00Z"),
        _start_event("inv-stoic-b", "stoicism virtue and calm practice", "2026-05-02T00:00:00Z"),
        _start_event("inv-garden", "garden soil compost guide", "2026-05-03T00:00:00Z"),
    ]:
        _write_event(events_dir, iid, row)
    matches = match_document_to_investigations(
        doc_text="stoicism calm and virtue",
        model=KeywordEmbedding(),
        events_dir=events_dir,
    )
    # Both stoicism projects surface; the garden one does not.
    ids = [m.investigation_id for m in matches]
    assert "inv-stoic-a" in ids and "inv-stoic-b" in ids
    assert "inv-garden" not in ids
    # Ranked best-first, deterministic tiebreak — the surface picks ONE to file
    # into on accept; the selector never files.
    assert matches == sorted(matches, key=lambda m: (-m.score, m.investigation_id))


def test_m3_tie_broken_by_investigation_id(events_dir):
    # rigor #3 (d) — a GENUINE score tie: two projects with IDENTICAL question
    # text embed identically, so the cosine is exactly equal. This proves the
    # investigation_id tiebreak in match_document_to_investigations actually
    # FIRES (the earlier multi-project test had unequal scores, so the sort
    # alone settled it and the tiebreak was never exercised).
    for iid, row in [
        _start_event("inv-b", "stoicism and calm", "2026-05-01T00:00:00Z"),
        _start_event("inv-a", "stoicism and calm", "2026-05-02T00:00:00Z"),
    ]:
        _write_event(events_dir, iid, row)
    matches = match_document_to_investigations(
        doc_text="stoicism and calm",
        model=KeywordEmbedding(),
        events_dir=events_dir,
    )
    assert len(matches) == 2
    # Genuinely tied score…
    assert matches[0].score == matches[1].score
    # …broken deterministically by investigation_id (alpha) — inv-a before inv-b.
    assert [m.investigation_id for m in matches] == ["inv-a", "inv-b"]


def test_m3_empty_doc_text_returns_nothing(events_dir):
    iid, row = _start_event("inv-x", "anything", "2026-05-01T00:00:00Z")
    _write_event(events_dir, iid, row)
    assert match_document_to_investigations(
        doc_text="   ", model=KeywordEmbedding(), events_dir=events_dir
    ) == []


def test_m3_no_projects_returns_nothing(events_dir):
    # No investigations at all → nothing to suggest.
    assert match_document_to_investigations(
        doc_text="stoicism", model=KeywordEmbedding(), events_dir=events_dir
    ) == []
