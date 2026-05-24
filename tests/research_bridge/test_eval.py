"""Eval-precision tests against synthetic labels.

The eval module is used by SPR-06 to compute the S3 gate. We test
that the matching logic is correct against known data, and that the
report's s3_gate_passed() predicate fires at the right threshold.
"""

from __future__ import annotations

from pathlib import Path

import pytest

from substrate.research_bridge.eval import (
    LabelledPaste,
    SubstringJudge,
    load_labelled_pastes,
    score_against_labels,
)


def test_perfect_match() -> None:
    labels = [
        LabelledPaste(
            document_id="doc-1",
            operator_label="t1",
            expected_insights=("Prime Intellect leads substrate",),
            expected_open_questions=("Will compute marketplace land",),
        )
    ]
    def extracted_for(doc: str):
        return (
            ["Prime Intellect leads substrate"],
            ["Will compute marketplace land"],
        )
    rep = score_against_labels(labels, extracted_for_doc=extracted_for, judge=SubstringJudge)
    assert rep.insight_precision == 1.0
    assert rep.insight_recall == 1.0
    assert rep.question_precision == 1.0
    assert rep.question_recall == 1.0
    assert rep.s3_gate_passed()


def test_zero_extracted_zero_labelled() -> None:
    labels = [LabelledPaste(document_id="doc-1", operator_label=None)]
    def extracted_for(doc: str):
        return ([], [])
    rep = score_against_labels(labels, extracted_for_doc=extracted_for, judge=SubstringJudge)
    # No items either side → precision = 0, recall = 0 (by safe-div).
    assert rep.insight_precision == 0.0
    assert rep.question_recall == 0.0
    # Aggregate question precision of 0 fails the gate.
    assert not rep.s3_gate_passed()


def test_partial_match() -> None:
    labels = [
        LabelledPaste(
            document_id="doc-1",
            operator_label="t1",
            expected_open_questions=(
                "Will Compute Marketplace commit",
                "How fast does verifier toolkit consolidate",
                "What is Anthropic's internal verifier timeline",
            ),
        )
    ]
    def extracted_for(doc: str):
        # 2 of 3 matched semantically, 1 spurious.
        return (
            [],
            [
                "Will Compute Marketplace commit",  # exact match
                "How fast does verifier toolkit consolidate",  # exact match
                "Stock is at fair value",  # spurious
            ],
        )
    rep = score_against_labels(labels, extracted_for_doc=extracted_for, judge=SubstringJudge)
    assert rep.question_precision == pytest.approx(2 / 3)
    assert rep.question_recall == pytest.approx(2 / 3)


def test_aggregate_precision_across_pastes() -> None:
    labels = [
        LabelledPaste(
            document_id="doc-1", operator_label="A",
            expected_open_questions=("Q one", "Q two"),
        ),
        LabelledPaste(
            document_id="doc-2", operator_label="B",
            expected_open_questions=("Q three", "Q four"),
        ),
    ]
    def extracted_for(doc: str):
        if doc == "doc-1":
            return ([], ["Q one", "noise"])
        return ([], ["Q three", "Q four", "noise"])
    rep = score_against_labels(labels, extracted_for_doc=extracted_for, judge=SubstringJudge)
    # 3 matched / 5 extracted across both docs
    assert rep.question_precision == pytest.approx(3 / 5)
    # 3 matched / 4 labelled
    assert rep.question_recall == pytest.approx(3 / 4)


def test_s3_gate_threshold() -> None:
    labels = [
        LabelledPaste(
            document_id="doc-1", operator_label=None,
            expected_open_questions=("a", "b", "c", "d"),
        )
    ]
    def extracted(doc):
        # 2/4 match, plus 1 noise → precision = 2/3
        return ([], ["a", "b", "z"])
    rep = score_against_labels(labels, extracted_for_doc=extracted, judge=SubstringJudge)
    # precision = 2/3 ≈ 0.667
    assert rep.s3_gate_passed(floor=0.5)
    assert rep.s3_gate_passed(floor=0.66)
    assert not rep.s3_gate_passed(floor=0.7)


def test_load_labelled_pastes_yaml(tmp_path: Path) -> None:
    yaml_path = tmp_path / "labels.yaml"
    yaml_path.write_text(
        """
pastes:
  - document_id: doc-abc
    operator_label: test paste
    expected_insights:
      - "insight one"
      - "insight two"
    expected_open_questions:
      - "question one"
""",
        encoding="utf-8",
    )
    pastes = load_labelled_pastes(yaml_path)
    assert len(pastes) == 1
    assert pastes[0].document_id == "doc-abc"
    assert pastes[0].operator_label == "test paste"
    assert pastes[0].expected_insights == ("insight one", "insight two")
    assert pastes[0].expected_open_questions == ("question one",)


def test_load_labelled_missing_file(tmp_path: Path) -> None:
    with pytest.raises(FileNotFoundError):
        load_labelled_pastes(tmp_path / "nope.yaml")


def test_substring_judge() -> None:
    assert SubstringJudge("Prime Intellect leads", "Prime Intellect leads substrate")
    assert SubstringJudge("Prime Intellect leads substrate", "Prime Intellect leads")
    assert not SubstringJudge("Compute marketplace", "Verifier toolkit timeline")
    assert not SubstringJudge("", "anything")


# ---------------------------------------------------------------------------
# LLM semantic judge (SPR-02 M5 — the real S3 read)
# ---------------------------------------------------------------------------


def test_llm_judge_matches_semantic_paraphrase() -> None:
    """The whole point: zero substring overlap, same meaning → match.
    The fake LLM returns YES; the judge surfaces True."""
    from substrate.research_bridge import LlmCallResult
    from substrate.research_bridge.eval import build_llm_judge

    calls = []

    def fake_llm(prompt: str) -> LlmCallResult:
        calls.append(prompt)
        return LlmCallResult(text="YES", model_id="fake")

    judge = build_llm_judge(fake_llm)
    extracted = "How quickly does verifier-tooling parity arrive?"
    labelled = "Will the verifier toolkit consolidate?"
    # Substring judge would say NO here; the LLM judge says YES.
    assert SubstringJudge(extracted, labelled) is False
    assert judge(extracted, labelled) is True
    assert len(calls) == 1


def test_llm_judge_parses_no() -> None:
    from substrate.research_bridge import LlmCallResult
    from substrate.research_bridge.eval import build_llm_judge

    judge = build_llm_judge(lambda _p: LlmCallResult(text="NO, these differ.", model_id="fake"))
    assert judge("apples", "oranges") is False


def test_llm_judge_unparseable_is_no() -> None:
    """Unparseable response → NO (safe direction; never inflate precision)."""
    from substrate.research_bridge import LlmCallResult
    from substrate.research_bridge.eval import build_llm_judge

    judge = build_llm_judge(lambda _p: LlmCallResult(text="I'm not sure about that.", model_id="fake"))
    assert judge("a", "b") is False


def test_llm_judge_empty_inputs_short_circuit() -> None:
    """Empty inputs return False WITHOUT calling the LLM."""
    from substrate.research_bridge import LlmCallResult
    from substrate.research_bridge.eval import build_llm_judge

    calls = []

    def fake_llm(prompt: str) -> LlmCallResult:
        calls.append(prompt)
        return LlmCallResult(text="YES", model_id="fake")

    judge = build_llm_judge(fake_llm)
    assert judge("", "something") is False
    assert judge("something", "  ") is False
    assert len(calls) == 0


def test_llm_judge_error_is_no_not_crash() -> None:
    """A judge call that raises must not crash the eval run — treat as NO."""
    from substrate.research_bridge.eval import build_llm_judge

    def angry_llm(_prompt: str):
        raise RuntimeError("503 from provider")

    judge = build_llm_judge(angry_llm)
    assert judge("a", "b") is False


def test_llm_judge_drives_real_precision() -> None:
    """End-to-end: the LLM judge recovers matches the substring judge
    misses, lifting question precision above the S3 floor."""
    from substrate.research_bridge import LlmCallResult
    from substrate.research_bridge.eval import build_llm_judge

    labels = [LabelledPaste(
        document_id="doc-1", operator_label="t1",
        expected_open_questions=(
            "Will the verifier toolkit consolidate?",
            "Does Anthropic ship an internal verifier product?",
        ),
    )]

    # Extracted paraphrases — no substring overlap with the labels.
    def extracted_for(_doc):
        return ([], [
            "How quickly does verifier-tooling parity arrive?",
            "When will Anthropic productise its internal verifier work?",
        ])

    # Fake judge that says YES for the two real paraphrase pairs.
    def fake_llm(prompt: str) -> LlmCallResult:
        verifier_pair = "verifier-tooling parity" in prompt and "verifier toolkit consolidate" in prompt
        anthropic_pair = "productise its internal verifier" in prompt and "internal verifier product" in prompt
        return LlmCallResult(text="YES" if (verifier_pair or anthropic_pair) else "NO", model_id="fake")

    judge = build_llm_judge(fake_llm)
    # Substring judge → 0 precision.
    sub = score_against_labels(labels, extracted_for_doc=extracted_for, judge=SubstringJudge)
    assert sub.question_precision == 0.0
    # LLM judge → 2/2 matched, precision 1.0, gate passes.
    llm = score_against_labels(labels, extracted_for_doc=extracted_for, judge=judge)
    assert llm.question_precision == 1.0
    assert llm.s3_gate_passed()
