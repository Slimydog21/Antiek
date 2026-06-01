"""AFF SPR-09 M1 — the frozen question set is immutable and well-formed."""

from __future__ import annotations

import copy
import json

import pytest

from compounding.benchmark.question_set import (
    OVERLAP_CLASSES,
    QUESTION_SET_PATH,
    compute_frozen_sha,
    load_question_set,
)


def test_frozen():
    """M1 acceptance: two loads of the same path return the identical
    ``frozen_sha`` (the set is frozen, not merely labelled frozen), every
    question has a valid overlap_class, and the high_overlap +
    zero_overlap_control cells are both non-empty."""
    a = load_question_set()
    b = load_question_set()
    assert a.frozen_sha == b.frozen_sha
    assert a.frozen_sha.startswith("sha256:")

    for q in a.questions:
        assert q.overlap_class in OVERLAP_CLASSES

    assert a.by_class("high_overlap"), "high_overlap cell must be non-empty (headline)"
    assert a.by_class("zero_overlap_control"), "control cell must be non-empty (validity gate)"
    assert a.by_class("partial_overlap"), "partial cell must be non-empty (dose-response)"


def test_recorded_sha_matches_content():
    """The recorded sha is content-addressed: recomputing it over the raw
    questions reproduces the stored value."""
    with open(QUESTION_SET_PATH, encoding="utf-8") as f:
        raw = json.load(f)
    assert compute_frozen_sha(raw["questions"]) == raw["frozen_sha"]


def test_twelve_questions_three_cells():
    """§2: 12 questions across 3 cells (5 high-overlap incl. 1 internal-probe,
    3 partial, 4 zero-overlap control)."""
    qs = load_question_set()
    assert len(qs) == 12
    assert len(qs.by_class("high_overlap")) == 5
    assert len(qs.by_class("partial_overlap")) == 3
    assert len(qs.by_class("zero_overlap_control")) == 4
    # The internal-probe is high_overlap but NOT pooled into the headline.
    assert len(qs.headline_questions()) == 4
    internal = [q for q in qs.by_class("high_overlap") if not q.headline_pooled]
    assert len(internal) == 1 and internal[0].question_id == "Q-HI-I1"


def test_control_questions_have_no_seed():
    """The zero-overlap control questions name no seeded units — nothing in the
    graph can accelerate them, so they must stay flat."""
    for q in load_question_set().control_questions():
        assert q.seeded_unit_ids == ()


def test_edited_question_set_fails_to_load(tmp_path):
    """A hand-edit to the JSON that does NOT re-freeze the sha is caught at load
    — the set cannot be silently mutated."""
    from compounding.benchmark.question_set import QUESTION_SET_PATH

    with open(QUESTION_SET_PATH, encoding="utf-8") as f:
        raw = json.load(f)
    tampered = copy.deepcopy(raw)
    tampered["questions"][0]["text"] = tampered["questions"][0]["text"] + " (tampered)"
    path = tmp_path / "tampered.json"
    path.write_text(json.dumps(tampered))
    with pytest.raises(ValueError, match="sha mismatch"):
        load_question_set(str(path))


def test_missing_overlap_class_rejected(tmp_path):
    """A set missing a whole overlap class is rejected (the validity control +
    headline both depend on their cells being present)."""
    with open(QUESTION_SET_PATH, encoding="utf-8") as f:
        raw = json.load(f)
    only_high = copy.deepcopy(raw)
    only_high["questions"] = [q for q in only_high["questions"] if q["overlap_class"] == "high_overlap"]
    only_high["frozen_sha"] = compute_frozen_sha(only_high["questions"])
    path = tmp_path / "only_high.json"
    path.write_text(json.dumps(only_high))
    with pytest.raises(ValueError, match="missing overlap classes"):
        load_question_set(str(path))
