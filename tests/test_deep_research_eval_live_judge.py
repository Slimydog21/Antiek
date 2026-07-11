"""Offline tests for the live ``JudgeFn`` adapter (``live_judge.py``).

Every test runs against a STUBBED provider — no real network. Coverage:

1. Happy path: valid rubric JSON → JudgeFn output parses to MEASURED
   ``JudgeScores``; and end-to-end through ``run_eval`` on a 1-query stub
   dataset → MEASURED.
2. Model-pin refusal: constructing with a non-``JUDGE_MODEL_ID`` model raises.
3. Fail-closed: provider raises / returns malformed / returns empty →
   JudgeFn returns a parser-rejected string → ``run_eval`` marks NOT_MEASURED,
   run incomplete, judge_scores None — NEVER a fabricated score.
4. The adapter calls the provider with EXACTLY ``JUDGE_MODEL_ID``.
5. Raw pass-through: a valid-but-unusual response reaches the parser unmodified.
6. Truncation guard: valid JSON + ``finish_reason="max_tokens"`` → NOT_MEASURED;
   the same JSON + a known-complete finish_reason → MEASURED.
7. Hostile-repr exception: a provider raising an exception whose ``__repr__`` /
   ``__str__`` raises → JudgeFn still returns the sentinel str, run does not crash.
"""

from __future__ import annotations

import json

import pytest

from substrate.deep_research_eval import (
    AXES,
    JUDGE_MODEL_ID,
    Query,
    QueryDataset,
    ResearchReport,
    SourceRef,
    build_judge_prompt,
    parse_judge_response,
    run_eval,
)
from substrate.deep_research_eval.live_judge import (
    LIVE_JUDGE_ERROR_SENTINEL,
    LiveJudge,
    build_live_judge,
)
from substrate.dispatch.base import NormalizedUsage, RawProviderResponse


# --------------------------------------------------------------------------- #
# Stub provider: records the model it was called with; configurable behaviour. #
# --------------------------------------------------------------------------- #
class StubProvider:
    """Minimal object satisfying the dispatch ``Provider`` protocol for tests.

    ``behaviour`` decides what ``call`` does: return a fixed text, or raise.
    Every ``call`` records the ``model`` argument for pin assertions.
    """

    name = "anthropic"

    def __init__(
        self,
        *,
        text: str | None = None,
        raises: Exception | None = None,
        finish_reason: str | None = "stop",
    ):
        self._text = text
        self._raises = raises
        self._finish_reason = finish_reason
        self.calls: list[dict[str, object]] = []

    def call(
        self,
        *,
        model: str,
        prompt: str,
        max_tokens: int,
        temperature: float,
    ) -> RawProviderResponse:
        self.calls.append(
            {"model": model, "prompt": prompt, "max_tokens": max_tokens, "temperature": temperature}
        )
        if self._raises is not None:
            raise self._raises
        assert self._text is not None
        return RawProviderResponse(
            text=self._text,
            raw_usage={"input_tokens": 10, "output_tokens": 5},
            finish_reason=self._finish_reason,
            latency_ms=1,
        )

    def normalize_usage(self, raw_usage: dict[str, object]) -> NormalizedUsage:
        return NormalizedUsage(input_tokens=0, output_tokens=0)


def _query() -> Query:
    return Query(
        query_id="q1",
        question="What is the capital of testing?",
        provenance="unit-test",
        domain="test",
        query_class="factual",
        expected_coverage=("alpha", "beta"),
    )


def _report() -> ResearchReport:
    return ResearchReport(
        answer_text="A grounded report covering alpha and beta in full.",
        sources=(SourceRef(url="https://example.org/1", title="s1"),),
        tool_calls=3,
        tokens_in=1000,
        tokens_out=200,
    )


def _one_query_dataset() -> QueryDataset:
    """Construct a 1-query dataset directly (bypasses the 20-query file loader —
    ``run_eval`` only iterates ``dataset.queries``)."""
    return QueryDataset(
        dataset_id="stub_ds",
        version="0.0.1",
        frozen=True,
        content_digest="0" * 64,
        queries=(_query(),),
    )


def _valid_judge_text() -> str:
    return json.dumps({axis: 0.9 for axis in AXES})


# 1. Happy path — parser MEASURED, and end-to-end run_eval MEASURED.
def test_happy_path_measured() -> None:
    provider = StubProvider(text=_valid_judge_text())
    judge = build_live_judge(provider)

    prompt = build_judge_prompt(_query(), _report())
    raw = judge(prompt)
    scores = parse_judge_response(raw)
    assert scores is not None
    assert scores.factual_accuracy == 0.9

    run = run_eval(
        _one_query_dataset(), lambda _q: _report(), judge,
        run_id_seed="seed", week_id="2026-W28",
    )
    assert run.measured_count == 1
    assert run.complete is True
    assert run.scores[0].status == "MEASURED"
    assert run.scores[0].judge_scores is not None
    assert run.judge_model_id == JUDGE_MODEL_ID


# 2. Model-pin refusal — a non-pinned model raises at construction.
def test_model_pin_refused_at_construction() -> None:
    provider = StubProvider(text=_valid_judge_text())
    with pytest.raises(ValueError, match="pinned"):
        build_live_judge(provider, model="anthropic/claude-sonnet-4-5")
    with pytest.raises(ValueError, match="pinned"):
        LiveJudge(provider=provider, model="some-other-model")
    # The pin itself is accepted.
    assert isinstance(build_live_judge(provider, model=JUDGE_MODEL_ID), LiveJudge)


# 3a. Fail-closed: provider RAISES → NOT_MEASURED, no score. (red-proof)
def test_fail_closed_provider_raises() -> None:
    provider = StubProvider(raises=RuntimeError("boom: upstream 500"))
    judge = build_live_judge(provider)

    raw = judge(build_judge_prompt(_query(), _report()))
    assert isinstance(raw, str)
    assert raw.startswith(LIVE_JUDGE_ERROR_SENTINEL)
    # Red-proof: the sentinel is NOT parseable → parser returns None (no score).
    assert parse_judge_response(raw) is None

    run = run_eval(
        _one_query_dataset(), lambda _q: _report(), judge,
        run_id_seed="seed", week_id="2026-W28",
    )
    assert run.measured_count == 0
    assert run.complete is False
    assert run.scores[0].status == "NOT_MEASURED"
    assert run.scores[0].judge_scores is None
    # Never a fabricated aggregate: mean over MEASURED is 0.0 only because the
    # run is incomplete — no query contributed a score.
    assert run.mean_judge_score == 0.0


# 3b. Fail-closed: provider returns MALFORMED (non-JSON) → NOT_MEASURED.
def test_fail_closed_malformed_response() -> None:
    provider = StubProvider(text="sure, about 0.9 overall {not json")
    judge = build_live_judge(provider)
    run = run_eval(
        _one_query_dataset(), lambda _q: _report(), judge,
        run_id_seed="seed", week_id="2026-W28",
    )
    assert run.scores[0].status == "NOT_MEASURED"
    assert run.scores[0].judge_scores is None
    assert run.complete is False


# 3c. Fail-closed: provider returns EMPTY / whitespace → NOT_MEASURED.
def test_fail_closed_empty_response() -> None:
    for empty in ("", "   \n\t"):
        provider = StubProvider(text=empty)
        judge = build_live_judge(provider)
        raw = judge(build_judge_prompt(_query(), _report()))
        assert raw.startswith(LIVE_JUDGE_ERROR_SENTINEL)
        assert parse_judge_response(raw) is None


# 4. The adapter calls the provider with EXACTLY JUDGE_MODEL_ID.
def test_provider_called_with_pinned_model() -> None:
    provider = StubProvider(text=_valid_judge_text())
    judge = build_live_judge(provider)
    judge(build_judge_prompt(_query(), _report()))
    assert len(provider.calls) == 1
    assert provider.calls[0]["model"] == JUDGE_MODEL_ID


# 5. Raw pass-through: a valid-but-unusual response is handed over unmodified.
def test_raw_pass_through_unmodified() -> None:
    # Valid JSON, but with unusual whitespace/formatting the adapter must NOT
    # touch. parse_judge_response accepts it; the adapter returns it byte-for-byte.
    unusual = "  {\n  " + ",\n  ".join(f'"{axis}" : 0.5' for axis in AXES) + "\n}  \n"
    provider = StubProvider(text=unusual)
    judge = build_live_judge(provider)
    raw = judge(build_judge_prompt(_query(), _report()))
    assert raw == unusual  # no pre-parsing, no fix-up
    scores = parse_judge_response(raw)
    assert scores is not None
    assert scores.completeness == 0.5


# 6. Truncation guard: valid JSON but finish_reason="max_tokens" → NOT_MEASURED;
#    a success finish_reason with the same JSON → MEASURED. (red-proof)
def test_truncated_response_fails_closed() -> None:
    # Valid, parseable rubric JSON — but the provider declares it truncated.
    truncated = StubProvider(text=_valid_judge_text(), finish_reason="max_tokens")
    judge = build_live_judge(truncated)
    raw = judge(build_judge_prompt(_query(), _report()))
    # Red-proof: the JSON itself WOULD parse, so only the finish_reason guard
    # keeps a partial judgment from scoring.
    assert parse_judge_response(_valid_judge_text()) is not None
    assert raw.startswith(LIVE_JUDGE_ERROR_SENTINEL)
    assert parse_judge_response(raw) is None

    run = run_eval(
        _one_query_dataset(), lambda _q: _report(), judge,
        run_id_seed="seed", week_id="2026-W28",
    )
    assert run.scores[0].status == "NOT_MEASURED"
    assert run.scores[0].judge_scores is None
    assert run.complete is False
    assert run.mean_judge_score == 0.0

    # Same JSON, but a known-complete finish_reason → MEASURED.
    for good in ("stop", "end_turn", "stop_sequence"):
        complete = build_live_judge(StubProvider(text=_valid_judge_text(), finish_reason=good))
        scores = parse_judge_response(complete(build_judge_prompt(_query(), _report())))
        assert scores is not None, f"finish_reason={good!r} must be accepted"

    # None finish_reason is also untrustworthy → fails closed.
    none_fr = build_live_judge(StubProvider(text=_valid_judge_text(), finish_reason=None))
    assert parse_judge_response(none_fr(build_judge_prompt(_query(), _report()))) is None


# 7. Hostile __repr__/__str__ must not escape the fail-closed handler. (red-proof)
def test_hostile_exception_repr_does_not_crash() -> None:
    class HostileError(Exception):
        def __repr__(self) -> str:
            raise RuntimeError("repr blew up")

        def __str__(self) -> str:
            raise RuntimeError("str blew up")

    provider = StubProvider(raises=HostileError())
    judge = build_live_judge(provider)
    # The JudgeFn must still return a str (never raise) despite the hostile repr.
    raw = judge(build_judge_prompt(_query(), _report()))
    assert isinstance(raw, str)
    assert raw.startswith(LIVE_JUDGE_ERROR_SENTINEL)
    assert parse_judge_response(raw) is None

    # And the full run completes (does not crash) with that query NOT_MEASURED.
    run = run_eval(
        _one_query_dataset(), lambda _q: _report(), judge,
        run_id_seed="seed", week_id="2026-W28",
    )
    assert run.scores[0].status == "NOT_MEASURED"
    assert run.scores[0].judge_scores is None
    assert run.complete is False


def test_hostile_str_raising_base_exception_does_not_escape() -> None:
    # A hostile __str__ may raise ANY BaseException (e.g. KeyboardInterrupt),
    # not just Exception. Formatting an already-caught provider error must never
    # let that second exception escape the JudgeFn (which must always return str).
    class BaseHostileError(Exception):
        def __str__(self) -> str:
            raise KeyboardInterrupt("escape via __str__")

    provider = StubProvider(raises=BaseHostileError())
    judge = build_live_judge(provider)
    raw = judge(build_judge_prompt(_query(), _report()))  # must not raise
    assert isinstance(raw, str)
    assert raw.startswith(LIVE_JUDGE_ERROR_SENTINEL)
    assert "BaseHostileError" in raw
    assert parse_judge_response(raw) is None
