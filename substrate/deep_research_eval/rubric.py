"""I-9 judge contract: pinned judge identity, single-call prompt, strict parser.

Fail-closed semantics: a malformed/missing judge response parses to ``None``
and the runner records the query as ``NOT_MEASURED`` — never a default or
partial score. Changing ``JUDGE_MODEL_ID`` or ``RUBRIC_VERSION`` changes the
comparability key, so scores across pins are never silently compared (I-9).
"""

from __future__ import annotations

import json
import math
from dataclasses import dataclass

from .dataset import Query

# Pinned judge identity (v1 pins — bumping either breaks comparability by design).
JUDGE_MODEL_ID = "anthropic/claude-opus-4-8"
RUBRIC_VERSION = "1.0.0"

# The five judged axes, each scored 0..1.
AXES: tuple[str, ...] = (
    "factual_accuracy",
    "citation_accuracy",
    "completeness",
    "source_quality",
    "tool_efficiency",
)


@dataclass(frozen=True)
class SourceRef:
    url: str
    title: str = ""


@dataclass(frozen=True)
class ResearchReport:
    """Provider output contract: one deep-research run over one query."""

    answer_text: str
    sources: tuple[SourceRef, ...]
    tool_calls: int
    tokens_in: int
    tokens_out: int


@dataclass(frozen=True)
class JudgeScores:
    factual_accuracy: float
    citation_accuracy: float
    completeness: float
    source_quality: float
    tool_efficiency: float

    def as_dict(self) -> dict[str, float]:
        return {
            "factual_accuracy": self.factual_accuracy,
            "citation_accuracy": self.citation_accuracy,
            "completeness": self.completeness,
            "source_quality": self.source_quality,
            "tool_efficiency": self.tool_efficiency,
        }

    def mean(self) -> float:
        values = self.as_dict()
        return sum(values.values()) / len(values)


def build_judge_prompt(query: Query, report: ResearchReport) -> str:
    """Single-call judge prompt: query + report + sources + coverage anchors."""
    anchors_block = "\n".join(f"- {anchor}" for anchor in query.expected_coverage)
    sources_lines = [
        f"- {source.url}" + (f" ({source.title})" if source.title else "")
        for source in report.sources
    ]
    sources_block = "\n".join(sources_lines) if sources_lines else "- (none provided)"
    return (
        f"You are the pinned deep-research judge (rubric v{RUBRIC_VERSION}).\n"
        "Score the research report below on five axes, each a number in [0, 1].\n\n"
        f"Question:\n{query.question}\n\n"
        "Expected coverage anchors (a competent report must address these):\n"
        f"{anchors_block}\n\n"
        f"Report:\n{report.answer_text}\n\n"
        f"Sources cited:\n{sources_block}\n\n"
        f"Tool calls used: {report.tool_calls}; "
        f"tokens in/out: {report.tokens_in}/{report.tokens_out}.\n\n"
        "Respond with STRICT JSON only — a single object with exactly these keys:\n"
        f"{json.dumps(list(AXES))}\n"
        "Each value must be a number between 0 and 1. No prose, no markdown, no extra keys."
    )


def parse_judge_response(raw: str) -> JudgeScores | None:
    """Strict parser. Any deviation returns ``None`` (caller marks NOT_MEASURED).

    Deviations that fail closed: non-JSON, non-object, missing or extra keys,
    booleans, non-numeric values, NaN/inf, values outside [0, 1].
    """
    try:
        data = json.loads(raw)
    except (json.JSONDecodeError, TypeError):
        return None
    if not isinstance(data, dict) or set(data) != set(AXES):
        return None
    values: dict[str, float] = {}
    for axis in AXES:
        value = data[axis]
        if isinstance(value, bool) or not isinstance(value, int | float):
            return None
        number = float(value)
        if not math.isfinite(number) or not 0.0 <= number <= 1.0:
            return None
        values[axis] = number
    return JudgeScores(
        factual_accuracy=values["factual_accuracy"],
        citation_accuracy=values["citation_accuracy"],
        completeness=values["completeness"],
        source_quality=values["source_quality"],
        tool_efficiency=values["tool_efficiency"],
    )
