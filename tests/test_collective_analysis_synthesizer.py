"""Collective analysis synthesizer (full LLM-synthesis mode) — contract tests.

Pins the hard-to-vary honesty invariants for ask #3's full mode (the sibling of
the #1833 draft writer). The module is pure except for ONE injected
``SynthesisCaller``; tests inject a deterministic recording fake -- no network.
"""

from __future__ import annotations

import os
import sys

_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if _ROOT not in sys.path:
    sys.path.insert(0, _ROOT)

import pytest  # noqa: E402

from substrate.collective_analysis_synthesizer import (  # noqa: E402
    CollectiveSynthesisError,
    SynthesisBrief,
    SynthesisResult,
    build_synthesis_brief,
    synthesize_collective_analysis,
)
from substrate.research_artifact.schema import (  # noqa: E402
    ArtifactInsight,
    ArtifactQuestion,
    ResearchArtifactBody,
)


def _body(
    *,
    investigation_id: str,
    problem_question: str = "What is X?",
    insights: list[str] | None = None,
    open_questions: list[str] | None = None,
    synthesis_excerpt: str | None = None,
    synthesis_withheld: bool = False,
    source_event_ids: list[str] | None = None,
) -> ResearchArtifactBody:
    return ResearchArtifactBody(
        investigation_id=investigation_id,
        problem_question=problem_question,
        insights=[
            ArtifactInsight(node_id=f"n-{investigation_id}-{i}", text=t)
            for i, t in enumerate(insights or [])
        ],
        open_questions=[
            ArtifactQuestion(node_id=f"q-{investigation_id}-{i}", text=t)
            for i, t in enumerate(open_questions or [])
        ],
        synthesis_excerpt=synthesis_excerpt,
        synthesis_withheld=synthesis_withheld,
        source_event_ids=source_event_ids or [],
    )


class _RecordingCaller:
    """A deterministic fake SynthesisCaller that records its invocations."""

    def __init__(self, text: str = "Integrated analysis across all instances.", model_id: str = ""):
        self._text = text
        self._model_id = model_id
        self.calls = 0

    def __call__(self, brief: SynthesisBrief, *, model_id: str) -> SynthesisResult:
        self.calls += 1
        return SynthesisResult(
            synthesis_text=self._text,
            model_id=self._model_id or model_id,
        )


# --- build_synthesis_brief: fail-closed validation ---


def test_empty_instances_rejected() -> None:
    with pytest.raises(CollectiveSynthesisError):
        build_synthesis_brief(parent_asset_id="asset-1", instances=[])


def test_empty_parent_asset_id_rejected() -> None:
    with pytest.raises(CollectiveSynthesisError):
        build_synthesis_brief(
            parent_asset_id="   ", instances=[_body(investigation_id="inv-1")]
        )


def test_incomplete_instance_rejected_full_mode_contract() -> None:
    # Full synthesis requires all instances complete; draft tolerates partial.
    bodies = [_body(investigation_id="inv-1"), _body(investigation_id="inv-2")]
    with pytest.raises(CollectiveSynthesisError, match="incomplete"):
        build_synthesis_brief(
            parent_asset_id="asset-1",
            instances=bodies,
            instance_complete_flags={"inv-2": False},
        )


def test_brief_hash_is_deterministic() -> None:
    bodies = [_body(investigation_id="inv-1", insights=["a"]), _body(investigation_id="inv-2")]
    one = build_synthesis_brief(parent_asset_id="asset-1", instances=bodies)
    two = build_synthesis_brief(parent_asset_id="asset-1", instances=bodies)

    assert one.brief_hash == two.brief_hash
    assert one.instances == two.instances


def test_brief_hash_changes_with_inputs() -> None:
    a = build_synthesis_brief(
        parent_asset_id="asset-1", instances=[_body(investigation_id="inv-1")]
    )
    b = build_synthesis_brief(
        parent_asset_id="asset-1", instances=[_body(investigation_id="inv-2")]
    )

    assert a.brief_hash != b.brief_hash


# --- authority gate: no ack -> withheld, zero dispatch ---


def test_no_operator_ack_withholds_and_never_dispatches() -> None:
    brief = build_synthesis_brief(
        parent_asset_id="asset-1", instances=[_body(investigation_id="inv-1")]
    )
    caller = _RecordingCaller()

    result = synthesize_collective_analysis(
        brief=brief, caller=caller, model_id="test-model", operator_ack=False
    )

    assert result.synthesis_withheld is True
    assert result.synthesis_excerpt is None
    assert result.operator_ack is False
    assert caller.calls == 0  # the caller is the only dispatch seam; never hit
    assert "not available" in result.combined_html  # render_html guard


# --- acked synthesis: content produced ---


def test_acked_synthesis_produces_analysis_with_prose() -> None:
    brief = build_synthesis_brief(
        parent_asset_id="asset-1",
        instances=[_body(investigation_id="inv-1")],
    )
    caller = _RecordingCaller(text="A unified synthesis of the findings.")

    result = synthesize_collective_analysis(
        brief=brief, caller=caller, model_id="test-model", operator_ack=True
    )

    assert result.synthesis_withheld is False
    assert result.synthesis_excerpt == "A unified synthesis of the findings."
    assert result.operator_ack is True
    assert caller.calls == 1
    assert "A unified synthesis of the findings." in result.combined_html


def test_empty_model_id_rejected() -> None:
    brief = build_synthesis_brief(
        parent_asset_id="asset-1", instances=[_body(investigation_id="inv-1")]
    )
    with pytest.raises(CollectiveSynthesisError):
        synthesize_collective_analysis(
            brief=brief, caller=_RecordingCaller(), model_id="  ", operator_ack=True
        )


def test_caller_empty_result_withheld_honestly() -> None:
    brief = build_synthesis_brief(
        parent_asset_id="asset-1", instances=[_body(investigation_id="inv-1")]
    )
    caller = _RecordingCaller(text="   ")  # whitespace-only -> no real content

    result = synthesize_collective_analysis(
        brief=brief, caller=caller, model_id="test-model", operator_ack=True
    )

    assert caller.calls == 1  # dispatched (acked) but produced nothing honest
    assert result.synthesis_withheld is True
    assert result.synthesis_excerpt is None  # never invents prose


def test_caller_model_id_passthrough() -> None:
    brief = build_synthesis_brief(
        parent_asset_id="asset-1", instances=[_body(investigation_id="inv-1")]
    )
    caller = _RecordingCaller(model_id="actually-used-model")

    result = synthesize_collective_analysis(
        brief=brief, caller=caller, model_id="requested-model", operator_ack=True
    )

    assert result.model_id == "actually-used-model"


# --- provenance: real, never fabricated ---


def test_merged_source_event_ids_are_union_of_all_instances() -> None:
    brief = build_synthesis_brief(
        parent_asset_id="asset-1",
        instances=[
            _body(investigation_id="inv-1", source_event_ids=["e-1", "e-2"]),
            _body(investigation_id="inv-2", source_event_ids=["e-2", "e-3"]),
        ],
    )
    # Every merged event id traces to a real source instance; union, deduped.
    # Assert via the body builder (the HTML's machine channel carries the list).
    from substrate.collective_analysis_synthesizer import _merge_body

    merged = _merge_body(brief, synthesis_excerpt="x", synthesis_withheld=False)
    assert set(merged.source_event_ids) == {"e-1", "e-2", "e-3"}
    assert merged.source_event_ids.count("e-2") == 1  # deduped


def test_no_fabricated_event_ids() -> None:
    brief = build_synthesis_brief(
        parent_asset_id="asset-1",
        instances=[_body(investigation_id="inv-1", source_event_ids=[])],
    )
    from substrate.collective_analysis_synthesizer import _merge_body

    merged = _merge_body(brief, synthesis_excerpt="x", synthesis_withheld=False)
    assert merged.source_event_ids == []  # nothing invented from thin air


def test_identical_insight_text_deduped_to_one_node() -> None:
    brief = build_synthesis_brief(
        parent_asset_id="asset-1",
        instances=[
            _body(investigation_id="inv-1", insights=["shared finding"]),
            _body(investigation_id="inv-2", insights=["shared finding", "unique"]),
        ],
    )
    from substrate.collective_analysis_synthesizer import _merge_body

    merged = _merge_body(brief, synthesis_excerpt="x", synthesis_withheld=False)
    texts = [ins.text for ins in merged.insights]
    assert texts.count("shared finding") == 1  # content-addressed dedup
    assert "unique" in texts
    assert len(merged.insights) == 2


def test_merged_insights_reattributed_to_source_instance() -> None:
    brief = build_synthesis_brief(
        parent_asset_id="asset-1",
        instances=[
            _body(investigation_id="inv-1", insights=["finding from inv-1"]),
            _body(investigation_id="inv-2", insights=["finding from inv-2"]),
        ],
    )
    from substrate.collective_analysis_synthesizer import _merge_body

    merged = _merge_body(brief, synthesis_excerpt="x", synthesis_withheld=False)
    by_text = {ins.text: ins.source_document_id for ins in merged.insights}
    assert by_text["finding from inv-1"] == "inv-1"
    assert by_text["finding from inv-2"] == "inv-2"


# --- idempotency ---


def test_idempotent_output_for_same_inputs_and_caller() -> None:
    bodies = [
        _body(investigation_id="inv-1", insights=["a"], source_event_ids=["e-1"]),
        _body(investigation_id="inv-2", insights=["b"], source_event_ids=["e-2"]),
    ]
    brief = build_synthesis_brief(parent_asset_id="asset-1", instances=bodies, findings=["focus"])
    caller = _RecordingCaller(text="same synthesis")

    one = synthesize_collective_analysis(
        brief=brief, caller=caller, model_id="m", operator_ack=True
    )
    two = synthesize_collective_analysis(
        brief=brief, caller=caller, model_id="m", operator_ack=True
    )

    assert one.content_hash == two.content_hash
    assert one.combined_html == two.combined_html
    assert one.analysis_id == two.analysis_id


# --- HTML-native + escaped (ask #6) ---


def test_synthesis_prose_is_html_escaped_in_output() -> None:
    brief = build_synthesis_brief(
        parent_asset_id="asset-1", instances=[_body(investigation_id="inv-1")]
    )
    malicious = "<script>alert(1)</script>"
    caller = _RecordingCaller(text=malicious)

    result = synthesize_collective_analysis(
        brief=brief, caller=caller, model_id="m", operator_ack=True
    )

    # The exact malicious payload must be absent; its escaped form present.
    # (render_html ships its own legit copy-button <script>, so we match the
    # full payload, not the bare tag.)
    assert "<script>alert(1)</script>" not in result.combined_html
    assert "&lt;script&gt;alert(1)&lt;/script&gt;" in result.combined_html


def test_findings_rendered_as_agent_notes() -> None:
    brief = build_synthesis_brief(
        parent_asset_id="asset-1",
        instances=[_body(investigation_id="inv-1")],
        findings=["steer toward cost analysis"],
    )
    result = synthesize_collective_analysis(
        brief=brief, caller=_RecordingCaller(), model_id="m", operator_ack=True
    )

    assert "steer toward cost analysis" in result.combined_html


def test_withheld_renders_honest_guard_not_blank() -> None:
    brief = build_synthesis_brief(
        parent_asset_id="asset-1", instances=[_body(investigation_id="inv-1")]
    )
    result = synthesize_collective_analysis(
        brief=brief, caller=_RecordingCaller(), model_id="m", operator_ack=False
    )

    assert result.synthesis_withheld is True
    assert "Synthesis not available" in result.combined_html
