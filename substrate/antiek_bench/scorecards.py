"""Antiek-bench weekly model-quality scorecards.

This module is intentionally offline-only. It writes scorecards from provided
measurements or mock fixtures; it never calls model providers, routers, or
third-party benchmarking services.
"""

from __future__ import annotations

import json
import os
from datetime import UTC, datetime
from pathlib import Path
from typing import Any, Literal

from pydantic import BaseModel, Field, model_validator

TaskClass = Literal[
    "research_question",
    "reading_highlight",
    "merge_synthesis",
    "midnight_oil_plan",
    "multimedia_script",
    "verification",
]


class AntiekBenchScorecardEntry(BaseModel):
    task_class: TaskClass
    provider: str
    model: str
    quality_score: float = Field(ge=0.0, le=1.0)
    groundedness: float = Field(ge=0.0, le=1.0)
    citation_precision: float = Field(ge=0.0, le=1.0)
    insight_density: float = Field(ge=0.0, le=1.0)
    synthesis_coherence: float = Field(ge=0.0, le=1.0)
    verifier_disagreement: float = Field(ge=0.0, le=1.0)
    estimated_cost_usd: float | None = Field(default=None, ge=0.0)
    actual_cost_usd: float | None = Field(default=None, ge=0.0)
    latency_ms: int | None = Field(default=None, ge=0)
    time_to_first_useful_token_ms: int | None = Field(default=None, ge=0)
    provider_errors: int = Field(default=0, ge=0)
    fallback_rate: float = Field(default=0.0, ge=0.0, le=1.0)
    retry_rate: float = Field(default=0.0, ge=0.0, le=1.0)
    malformed_output_rate: float = Field(default=0.0, ge=0.0, le=1.0)
    acceptable_answers: int = Field(default=0, ge=0)
    route_receipt_ids: list[str] = Field(default_factory=list)

    @property
    def cost_per_acceptable_answer(self) -> float | None:
        cost = self.actual_cost_usd if self.actual_cost_usd is not None else self.estimated_cost_usd
        if cost is None or self.acceptable_answers <= 0:
            return None
        return round(cost / self.acceptable_answers, 8)


class AntiekBenchScorecard(BaseModel):
    schema_version: int = 1
    scorecard_id: str
    generated_at: str
    week_id: str
    mock_run: bool
    entries: list[AntiekBenchScorecardEntry] = Field(min_length=1)
    notes: list[str] = Field(default_factory=list)

    @model_validator(mode="after")
    def _requires_two_task_classes_for_mock(self) -> AntiekBenchScorecard:
        if self.mock_run:
            classes = {entry.task_class for entry in self.entries}
            if len(classes) < 2:
                raise ValueError("mock Antiek-bench scorecards must cover at least two task classes")
        return self

    def best_by_task_class(self) -> dict[str, AntiekBenchScorecardEntry]:
        best: dict[str, AntiekBenchScorecardEntry] = {}
        for entry in self.entries:
            current = best.get(entry.task_class)
            if current is None or _entry_rank(entry) > _entry_rank(current):
                best[entry.task_class] = entry
        return best


class FixtureProposal(BaseModel):
    fixture_id: str
    task_class: TaskClass
    action: Literal["add", "retire"]
    evidence_route_receipt_ids: list[str] = Field(default_factory=list)
    reason: str


class WeeklyFixtureProposal(BaseModel):
    schema_version: int = 1
    generated_at: str
    week_id: str
    proposals: list[FixtureProposal]


def antiek_bench_dir() -> Path:
    raw = os.environ.get("ANTIEK_BENCH_DIR")
    if raw:
        return Path(raw)
    home = Path(os.environ.get("ANTIEK_HOME", Path.home() / ".antiek"))
    return home / "antiek_bench"


def latest_scorecard_path(base_dir: Path | None = None) -> Path:
    return (base_dir or antiek_bench_dir()) / "latest_scorecard.json"


def latest_proposal_path(base_dir: Path | None = None) -> Path:
    return (base_dir or antiek_bench_dir()) / "latest_fixture_proposal.json"


def write_scorecard(scorecard: AntiekBenchScorecard, *, base_dir: Path | None = None) -> Path:
    out_dir = base_dir or antiek_bench_dir()
    out_dir.mkdir(parents=True, exist_ok=True)
    path = latest_scorecard_path(out_dir)
    payload = scorecard.model_dump(mode="json")
    _assert_no_sensitive_payload(payload)
    path.write_text(json.dumps(payload, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    return path


def read_latest_scorecard(*, base_dir: Path | None = None) -> AntiekBenchScorecard | None:
    path = latest_scorecard_path(base_dir)
    if not path.is_file():
        return None
    return AntiekBenchScorecard.model_validate_json(path.read_text(encoding="utf-8"))


def run_mock_weekly_scorecard(
    *,
    base_dir: Path | None = None,
    route_receipts: list[dict[str, Any]] | None = None,
    week_id: str | None = None,
) -> tuple[AntiekBenchScorecard, WeeklyFixtureProposal]:
    """Write a deterministic mock scorecard and weekly fixture proposal."""
    now = datetime.now(UTC)
    week = week_id or f"{now.isocalendar().year}-W{now.isocalendar().week:02d}"
    receipt_ids = _receipt_ids(route_receipts or [])
    generated_at = now.isoformat().replace("+00:00", "Z")
    entries = [
        AntiekBenchScorecardEntry(
            task_class="research_question",
            provider="zai",
            model="glm-5.2",
            quality_score=0.82,
            groundedness=0.84,
            citation_precision=0.78,
            insight_density=0.86,
            synthesis_coherence=0.83,
            verifier_disagreement=0.12,
            estimated_cost_usd=0.014,
            actual_cost_usd=0.013,
            latency_ms=4200,
            time_to_first_useful_token_ms=900,
            acceptable_answers=3,
            route_receipt_ids=receipt_ids[:3],
        ),
        AntiekBenchScorecardEntry(
            task_class="reading_highlight",
            provider="deepseek",
            model="deepseek-v4-pro",
            quality_score=0.76,
            groundedness=0.8,
            citation_precision=0.74,
            insight_density=0.72,
            synthesis_coherence=0.77,
            verifier_disagreement=0.16,
            estimated_cost_usd=0.006,
            actual_cost_usd=0.006,
            latency_ms=2300,
            time_to_first_useful_token_ms=650,
            acceptable_answers=4,
            route_receipt_ids=receipt_ids[3:6],
        ),
    ]
    scorecard = AntiekBenchScorecard(
        scorecard_id=f"antiek-bench-{week}",
        generated_at=generated_at,
        week_id=week,
        mock_run=True,
        entries=entries,
        notes=[
            "mock scorecard: no provider calls; replace with ratified weekly run before routing policy changes"
        ],
    )
    out_dir = base_dir or antiek_bench_dir()
    write_scorecard(scorecard, base_dir=out_dir)
    proposal = WeeklyFixtureProposal(
        generated_at=generated_at,
        week_id=week,
        proposals=[
            FixtureProposal(
                fixture_id=f"{week}-research-route-receipt",
                task_class="research_question",
                action="add",
                evidence_route_receipt_ids=receipt_ids[:3] or receipt_ids,
                reason="route receipts show recurring research-question usage; add representative fixture",
            ),
            FixtureProposal(
                fixture_id=f"{week}-stale-reading-fixture",
                task_class="reading_highlight",
                action="retire",
                evidence_route_receipt_ids=receipt_ids[3:6] or receipt_ids,
                reason="reading-highlight fixture lacks recent route receipt evidence; retire or refresh",
            ),
        ],
    )
    proposal_payload = proposal.model_dump(mode="json")
    _assert_no_sensitive_payload(proposal_payload)
    latest_proposal_path(out_dir).write_text(
        json.dumps(proposal_payload, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )
    return scorecard, proposal


def _entry_rank(entry: AntiekBenchScorecardEntry) -> tuple[float, float, float]:
    reliability_penalty = entry.provider_errors + entry.fallback_rate + entry.retry_rate
    cost = entry.cost_per_acceptable_answer
    cost_rank = 1.0 / (1.0 + cost) if cost is not None else 0.0
    return (entry.quality_score, cost_rank, -reliability_penalty)


def _receipt_ids(receipts: list[dict[str, Any]]) -> list[str]:
    ids: list[str] = []
    for receipt in receipts:
        rid = receipt.get("route_receipt_id")
        if isinstance(rid, str) and rid:
            ids.append(rid)
    if ids:
        return ids
    return ["mock-route-receipt-research-1", "mock-route-receipt-reading-1"]


def _assert_no_sensitive_payload(payload: Any) -> None:
    text = json.dumps(payload, sort_keys=True).lower()
    forbidden = ("api_key", "apikey", "authorization", "bearer ", "sk-", "raw_prompt", "full_prompt")
    found = [token for token in forbidden if token in text]
    if found:
        raise ValueError(f"Antiek-bench artifact contains forbidden sensitive token(s): {found}")
