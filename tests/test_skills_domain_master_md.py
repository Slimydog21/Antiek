"""Tests for skills/domain/master_md.py (Sprint 6 day 4-5).

Coverage:

1. ``slugify``: normalizes, handles empty / unicode-noise / cap length.
2. ``build_master_md``: includes the synthesis_id marker, header,
   sections, all subsections from the thesis dict; tolerates missing
   keys; handles non-dict thesis defensively.
3. ``existing_marker_matches``: True when marker present, False on
   missing file, False on mismatched id.
4. ``generate_master_md`` writes the file atomically (no stray .tmp);
   round-tripping the same id is idempotent (no re-write); emits
   the right typed payload in each branch.
5. Idempotency: second call returns the existing path AND emits a
   ``MasterMdSkippedPayload`` event with ``reason=idempotent_match``.
6. Atomic-write contract: the .tmp file does not survive the call.
"""

from __future__ import annotations

import os
import sys

import pytest

_HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, os.path.dirname(_HERE))

from skills.domain.master_md import (  # noqa: E402
    SYNTHESIS_ID_MARKER,
    build_master_md,
    existing_marker_matches,
    generate_master_md,
    slugify,
)
from substrate.event_log import trajectory  # noqa: E402
from substrate.schemas import (  # noqa: E402
    ActionType,
    Event,
    MasterMdSkippedPayload,
    MasterMdWrittenPayload,
)


@pytest.fixture
def events_dir(tmp_path, monkeypatch):
    monkeypatch.setenv("ANTIEK_RESEARCH_EVENTS_DIR", str(tmp_path / "events"))
    return tmp_path / "events"


@pytest.fixture
def research_root(tmp_path, monkeypatch):
    root = tmp_path / "research"
    monkeypatch.setenv("ANTIEK_RESEARCH_DIR", str(root))
    return root


# ---------------------------------------------------------------------------
# 1. slugify
# ---------------------------------------------------------------------------


def test_slugify_lowercases_and_replaces_separators():
    assert slugify("Will TSMC dominate N2?") == "will-tsmc-dominate-n2"


def test_slugify_empty_returns_untitled():
    assert slugify("") == "untitled"


def test_slugify_only_punctuation_returns_untitled():
    assert slugify("!!!???") == "untitled"


def test_slugify_caps_length():
    long = "a" * 200
    assert len(slugify(long, max_len=32)) == 32


def test_slugify_collapses_repeated_hyphens():
    assert slugify("a---b---c") == "a-b-c"


# ---------------------------------------------------------------------------
# 2. build_master_md
# ---------------------------------------------------------------------------


def _full_row() -> dict:
    return {
        "synthesis_id": "syn-build",
        "investigation_id": "inv-build",
        "synthesis_timestamp": "2026-05-17T12:00:00Z",
        "target_question": "Will X happen?",
        "status": "passed",
        "implicit_recommendation": "proceed",
        "thesis": {
            "thesis_summary": "X is likely.",
            "implicit_recommendation": "proceed",
            "thesis_components": [
                {
                    "claim": "Primary driver is Y",
                    "confidence": "high",
                    "confidence_basis": "two SEC filings",
                    "supporting_chunk_ids": ["c1", "c2"],
                },
            ],
            "falsification_conditions": [
                {"condition": "Y reverses", "specific_observable": "ARR<50%"},
            ],
            "execution_risks": [
                {"risk": "talent flight", "severity": "moderate"},
            ],
            "constraint_compliance": {
                "hard_constraints_satisfied": True,
                "soft_constraints_violated": [],
                "violations_justified": [],
            },
        },
    }


def test_build_master_md_includes_synthesis_marker_at_top():
    body = build_master_md(_full_row())
    assert body.startswith(SYNTHESIS_ID_MARKER + "syn-build -->")


def test_build_master_md_renders_all_section_headers():
    body = build_master_md(_full_row())
    for header in (
        "# Will X happen?",
        "## Thesis Summary",
        "## Thesis Components",
        "## Falsification Conditions",
        "## Execution Risks",
        "## Implicit Recommendation",
        "## Constraint Compliance",
    ):
        assert header in body


def test_build_master_md_renders_thesis_component_details():
    body = build_master_md(_full_row())
    assert "Primary driver is Y" in body
    assert "high" in body
    assert "two SEC filings" in body
    assert "`c1`" in body and "`c2`" in body


def test_build_master_md_handles_missing_thesis_keys():
    row = {"synthesis_id": "syn-min"}
    body = build_master_md(row)
    assert "syn-min" in body
    assert "_No thesis components recorded._" in body
    assert "_No falsification conditions recorded._" in body
    assert "_No execution risks recorded._" in body
    assert "_No constraint compliance recorded._" in body


def test_build_master_md_handles_non_dict_thesis():
    """Defensive: a corrupt thesis_json that deserializes to a list
    must not raise — fall back to "empty" sections."""
    row = {"synthesis_id": "syn-bad", "thesis": ["not", "a", "dict"]}
    body = build_master_md(row)
    assert "syn-bad" in body
    assert "## Thesis Summary" in body


# ---------------------------------------------------------------------------
# 3. existing_marker_matches
# ---------------------------------------------------------------------------


def test_existing_marker_matches_finds_marker(tmp_path):
    p = tmp_path / "M.md"
    p.write_text(f"{SYNTHESIS_ID_MARKER}xyz -->\n# rest\n")
    assert existing_marker_matches(p, "xyz") is True


def test_existing_marker_matches_rejects_mismatched_id(tmp_path):
    p = tmp_path / "M.md"
    p.write_text(f"{SYNTHESIS_ID_MARKER}xyz -->\n")
    assert existing_marker_matches(p, "different") is False


def test_existing_marker_matches_missing_file_returns_false(tmp_path):
    assert existing_marker_matches(tmp_path / "absent.md", "x") is False


# ---------------------------------------------------------------------------
# 4-6. generate_master_md
# ---------------------------------------------------------------------------


def test_generate_master_md_writes_file_and_emits_written(
    events_dir, research_root,
):
    row = _full_row()
    path = generate_master_md(row, topic_slug="my-topic")
    assert path.exists()
    body = path.read_text()
    assert "syn-build" in body
    # No stray .tmp file
    assert not path.with_suffix(path.suffix + ".tmp").exists()

    rows = trajectory(row["investigation_id"])
    written = [r for r in rows if r["action_type"] == ActionType.MASTER_MD_WRITTEN.value]
    assert len(written) == 1
    e = Event.model_validate(written[0])
    assert isinstance(e.payload, MasterMdWrittenPayload)
    assert e.payload.synthesis_id == "syn-build"
    assert e.payload.topic_slug == "my-topic"
    assert e.payload.byte_count == path.stat().st_size
    assert e.payload.path == str(path)


def test_generate_master_md_idempotent_emits_skipped(
    events_dir, research_root,
):
    row = _full_row()
    p1 = generate_master_md(row, topic_slug="topic")
    body1 = p1.read_text()
    mtime1 = p1.stat().st_mtime_ns

    p2 = generate_master_md(row, topic_slug="topic")
    assert p2 == p1
    assert p2.read_text() == body1
    # File not rewritten — mtime unchanged
    assert p2.stat().st_mtime_ns == mtime1

    rows = trajectory(row["investigation_id"])
    skipped = [r for r in rows if r["action_type"] == ActionType.MASTER_MD_SKIPPED.value]
    assert len(skipped) == 1
    e = Event.model_validate(skipped[0])
    assert isinstance(e.payload, MasterMdSkippedPayload)
    assert e.payload.reason == "idempotent_match"


def test_generate_master_md_auto_derives_slug_from_question(
    events_dir, research_root,
):
    row = _full_row()
    # No explicit topic_slug → derived from target_question.
    path = generate_master_md(row)
    # The slugified question lives between research_root and MASTER.md
    rel = path.relative_to(research_root)
    assert rel.parts[0] == "will-x-happen"


def test_generate_master_md_output_dir_overrides_slug(
    events_dir, research_root, tmp_path,
):
    custom = tmp_path / "custom-out"
    path = generate_master_md(_full_row(), output_dir=str(custom))
    assert path.parent.resolve() == custom.resolve()


def test_generate_master_md_creates_nested_dirs(events_dir, research_root):
    """Parent dir does not exist yet — generate_master_md must mkdir -p."""
    row = _full_row()
    assert not research_root.exists()
    path = generate_master_md(row, topic_slug="fresh")
    assert path.exists()


def test_generate_master_md_no_question_falls_back_to_untitled(
    events_dir, research_root,
):
    """When ``target_question`` is missing, ``slugify("")`` returns
    "untitled" (truthy), short-circuiting the investigation_id and
    final fallbacks. This preserves upstream behavior verbatim — the
    investigation_id fallback in the source is effectively dead
    code, but we keep the chain for forward-additivity if slugify's
    empty-return contract ever changes."""
    row = {"synthesis_id": "s", "investigation_id": "inv-x"}
    path = generate_master_md(row)
    rel = path.relative_to(research_root)
    assert rel.parts[0] == "untitled"
