"""Reproducible weekly comparison of operator, bench, and ND shadow selectors."""

from __future__ import annotations

import hashlib
import html
import json
import math
import re
from collections import Counter
from collections.abc import Iterable
from dataclasses import asdict, dataclass, replace
from decimal import Decimal
from typing import Any, cast

from ..judged.anchors import AnchorSet, calibrate_against_anchors
from ..judged.calibration import compare_position_swap
from ..judged.disagreement import compute_disagreement
from ..judged.join import PrivateJoinEnvelope, verify_private_join
from ..judged.journal import EVIDENCE_SCHEMA_VERSION, EvidenceRecord
from ..judged.rubric import rubric_for
from ..judged.runner import JUDGE_POLICY_VERSION
from ..judged.verdict import VerdictPolicy, build_qualitative_verdict
from ..suite import SuiteDefinition, TaskClass
from .journal import Journal, LiveCallRecord, charged_cost
from .nd_shadow import NDShadowJournal
from .wedge_config import REQUIRED_TASK_CLASSES, validate_live_suite

JUDGED_JOIN_MANIFEST_SCHEMA_VERSION = 1
WEEKLY_VERDICT_SCHEMA_VERSION = 3
JUDGED_WEEKLY_SCHEMA_VERSION = WEEKLY_VERDICT_SCHEMA_VERSION
NOT_MEASURED = "NOT MEASURED"
_SHA256_REFERENCE = re.compile(r"sha256:[0-9a-f]{64}\Z")


@dataclass(frozen=True)
class JudgedCandidateJoin:
    model_id: str
    provider_id: str
    live_call_id: str
    live_response_hash: str
    blinded_label: str
    candidate_hash: str


@dataclass(frozen=True)
class JudgedItemJoin:
    task_class: str
    live_item_id: str
    live_prompt_hash: str
    item_id_hash: str
    candidates: tuple[JudgedCandidateJoin, JudgedCandidateJoin]
    rubric_version: str
    rubric_fingerprint: str
    task_context_hash: str
    allowed_judges: tuple[str, ...]
    evidence_ids: tuple[str, ...]
    position_swaps: tuple[tuple[str, str], ...]
    private_envelopes: tuple[PrivateJoinEnvelope, ...]


def judged_join_mapping_digest(
    week_id: str,
    suite_version: str,
    blinding_policy_version: str,
    items: tuple[JudgedItemJoin, ...],
) -> str:
    material = json.dumps(
        {
            "week_id": week_id,
            "suite_version": suite_version,
            "blinding_policy_version": blinding_policy_version,
            "items": [asdict(item) for item in items],
        },
        sort_keys=True,
        separators=(",", ":"),
    )
    return "sha256:" + hashlib.sha256(material.encode()).hexdigest()


@dataclass(frozen=True)
class JudgedJoinManifest:
    week_id: str
    suite_version: str
    blinding_policy_version: str
    items: tuple[JudgedItemJoin, ...]
    mapping_digest: str
    schema_version: int = JUDGED_JOIN_MANIFEST_SCHEMA_VERSION

    def __post_init__(self) -> None:
        if self.schema_version != JUDGED_JOIN_MANIFEST_SCHEMA_VERSION:
            raise ValueError("unsupported judged join manifest schema")
        if not self.blinding_policy_version.strip():
            raise ValueError("blinding policy version is required")
        keys: set[tuple[str, str]] = set()
        item_hashes: set[str] = set()
        for item in self.items:
            key = (item.task_class, item.live_item_id)
            if key in keys:
                raise ValueError("judged manifest items must be unique")
            keys.add(key)
            if item.item_id_hash in item_hashes:
                raise ValueError("judged manifest item hashes must be unique")
            item_hashes.add(item.item_id_hash)
            if (
                _SHA256_REFERENCE.fullmatch(item.live_prompt_hash) is None
                or _SHA256_REFERENCE.fullmatch(item.item_id_hash) is None
                or len(item.candidates) != 2
                or len({candidate.model_id for candidate in item.candidates}) != 2
                or len({candidate.candidate_hash for candidate in item.candidates}) != 2
                or any(
                    not candidate.provider_id
                    or not candidate.live_call_id.startswith("lc_")
                    or not candidate.live_response_hash
                    or candidate.blinded_label not in {"A", "B"}
                    or _SHA256_REFERENCE.fullmatch(candidate.candidate_hash) is None
                    for candidate in item.candidates
                )
                or tuple(candidate.blinded_label for candidate in item.candidates) != ("A", "B")
                or _SHA256_REFERENCE.fullmatch(item.task_context_hash) is None
                or _SHA256_REFERENCE.fullmatch(item.rubric_fingerprint) is None
                or not item.allowed_judges
                or len({judge.strip().casefold() for judge in item.allowed_judges})
                != len(item.allowed_judges)
                or any(not judge.strip() for judge in item.allowed_judges)
                or len(item.evidence_ids) != len(item.allowed_judges) * 2
                or len(set(item.evidence_ids)) != len(item.evidence_ids)
                or len(item.position_swaps) != len(item.allowed_judges)
                or {evidence_id for pair in item.position_swaps for evidence_id in pair}
                != set(item.evidence_ids)
                or {envelope.evidence_id for envelope in item.private_envelopes}
                != set(item.evidence_ids)
            ):
                raise ValueError("invalid judged manifest item")
        expected_digest = judged_join_mapping_digest(
            self.week_id,
            self.suite_version,
            self.blinding_policy_version,
            self.items,
        )
        if self.mapping_digest != expected_digest:
            raise ValueError("judged manifest mapping digest does not match")


@dataclass(frozen=True)
class JudgedAxisResult:
    axis: str
    candidate_scores: tuple[tuple[str, float], ...]
    sample_size: int


@dataclass(frozen=True)
class JudgedTaskLayer:
    status: str
    axes: tuple[JudgedAxisResult, ...]
    winner: str | None
    suppression_reasons: tuple[str, ...]
    disagreement: tuple[dict[str, Any], ...]
    calibration: tuple[dict[str, Any], ...]
    sample_size: int
    expected_sample_size: int
    rubric_version: str | None
    policy_version: str | None
    anchor_version: str | None
    evidence_schema_version: int
    input_digest: str
    schema_version: int = JUDGED_WEEKLY_SCHEMA_VERSION


def _percentile(values: list[int], percentile: float) -> int | None:
    if not values:
        return None
    ordered = sorted(values)
    index = max(0, math.ceil(percentile * len(ordered)) - 1)
    return ordered[index]


@dataclass(frozen=True)
class ModelTaskMetrics:
    model_id: str
    task_class: str
    sample_size: int
    expected_samples: int
    complete: bool
    keyword_proxy_quality: float | None
    actual_cost_usd: str
    p50_latency_ms: int | None
    p95_latency_ms: int | None
    success_count: int
    failure_count: int
    timeout_count: int
    availability: float


@dataclass(frozen=True)
class TaskVerdict:
    task_class: str
    bench_winner: str | None
    winner_suppressed_reason: str | None
    operator_driver: str | None
    nd_modal_suggestion: str | None
    nd_sample_size: int
    nd_disagreement_count: int | None
    models: tuple[ModelTaskMetrics, ...]
    judged: JudgedTaskLayer | None = None


@dataclass(frozen=True)
class WeeklyVerdict:
    week_id: str
    suite_version: str
    task_verdicts: tuple[TaskVerdict, ...]
    budget_spent_usd: str
    budget_reserved_usd: str
    budget_cap_usd: str
    budget_over_cap: bool
    input_digest: str
    judged_manifest_digest: str | None = None
    operator_acknowledgment_required: bool = True
    auto_promotion: bool = False
    view_format: str = "html"
    schema_version: int = WEEKLY_VERDICT_SCHEMA_VERSION

    def to_dict(self) -> dict[str, Any]:
        payload = asdict(self)
        if self.judged_manifest_digest is None:
            payload.pop("judged_manifest_digest")
            for task in payload["task_verdicts"]:
                task.pop("judged")
        return payload


def _metrics(
    model_id: str,
    task_class: TaskClass,
    records: list[LiveCallRecord],
    expected_items: dict[str, str],
) -> ModelTaskMetrics:
    rows = [
        row for row in records if row.requested_model == model_id and row.task_class == task_class
    ]
    successes = [row for row in rows if row.status == "ok"]
    failures = [row for row in rows if row.status == "failed"]
    timeouts = [row for row in rows if row.status == "timeout"]
    expected = len(expected_items)
    actual_items = {row.item_id: row.prompt_hash for row in rows}
    complete = (
        len(rows) == expected
        and actual_items == expected_items
        and all(
            row.status in {"ok", "failed", "timeout"}
            and (row.status != "ok" or row.keyword_score is not None)
            for row in rows
        )
    )
    quality = None
    if complete:
        quality = round(
            sum(
                float(row.keyword_score or Decimal("0")) if row.status == "ok" else 0.0
                for row in rows
            )
            / expected,
            6,
        )
    latencies = [row.latency_ms for row in successes]
    return ModelTaskMetrics(
        model_id=model_id,
        task_class=task_class,
        sample_size=len(rows),
        expected_samples=expected,
        complete=complete,
        keyword_proxy_quality=quality,
        actual_cost_usd=str(sum((row.cost_usd for row in rows), Decimal("0"))),
        p50_latency_ms=_percentile(latencies, 0.50),
        p95_latency_ms=_percentile(latencies, 0.95),
        success_count=len(successes),
        failure_count=len(failures),
        timeout_count=len(timeouts),
        availability=round(len(successes) / expected, 6),
    )


def build_weekly_verdict(
    *,
    week_id: str,
    wedge_id: str,
    suite: SuiteDefinition,
    call_journal: Journal,
    shadow_journal: NDShadowJournal,
    operator_driver: str | None,
    budget_cap_usd: Decimal,
    candidate_model_ids: tuple[str, str] | None = None,
    judged_manifest: JudgedJoinManifest | None = None,
    judged_records: Iterable[EvidenceRecord] = (),
    judged_anchors: AnchorSet | None = None,
    judged_policy: VerdictPolicy | None = None,
    judged_join_signing_key: bytes | None = None,
) -> WeeklyVerdict:
    validate_live_suite(suite)
    if budget_cap_usd <= 0:
        raise ValueError("budget_cap_usd must be positive")
    records = [
        row
        for row in call_journal.replay().values()
        if row.week_id == week_id
        and row.suite_version == suite.suite_version
        and row.wedge_id == wedge_id
    ]
    model_ids = (
        tuple(sorted(candidate_model_ids))
        if candidate_model_ids is not None
        else tuple(sorted({row.requested_model for row in records}))
    )
    if len(model_ids) != 2 or len(set(model_ids)) != 2:
        raise ValueError("weekly verdict requires exactly two measured models")
    expected_shadows = {
        (
            "sha256:" + hashlib.sha256(item.item_id.encode()).hexdigest(),
            item.task_class,
            "sha256:" + hashlib.sha256(item.prompt.encode()).hexdigest(),
        )
        for item in suite.items
    }
    shadows = [
        row
        for row in shadow_journal.list_records()
        if row.week_id == week_id
        and row.suite_version == suite.suite_version
        and len(row.candidates) == len(model_ids)
        and set(row.candidates) == set(model_ids)
        and (row.item_id_hash, row.task_class, row.prompt_hash) in expected_shadows
    ]
    charged = sum((charged_cost(row) for row in records), Decimal("0"))
    spent = sum((row.cost_usd for row in records), Decimal("0"))
    budget_over_cap = charged > budget_cap_usd
    evidence_rows = tuple(judged_records)
    manifest_digest: str | None = None
    if judged_manifest is not None:
        manifest_digest = judged_manifest.mapping_digest
    task_verdicts: list[TaskVerdict] = []
    for raw_task_class in sorted(REQUIRED_TASK_CLASSES):
        task_class = cast(TaskClass, raw_task_class)
        expected_items = {
            item.item_id: "sha256:" + hashlib.sha256(item.prompt.encode()).hexdigest()
            for item in suite.items_for(task_class)
        }
        model_metrics = tuple(
            _metrics(model_id, task_class, records, expected_items) for model_id in model_ids
        )
        winner: str | None = None
        suppressed: str | None = None
        if budget_over_cap:
            suppressed = "budget_cap_exceeded"
        elif not all(metric.complete for metric in model_metrics):
            suppressed = "incomplete_or_budget_truncated_class"
        else:
            ranked = sorted(
                model_metrics,
                key=lambda metric: metric.keyword_proxy_quality or 0.0,
                reverse=True,
            )
            if ranked[0].keyword_proxy_quality == ranked[1].keyword_proxy_quality:
                suppressed = "quality_tie"
            else:
                winner = ranked[0].model_id
        task_shadows = [
            row for row in shadows if row.task_class == task_class and row.status == "ok"
        ]
        counts = Counter(row.recommendation for row in task_shadows)
        modal: str | None = None
        if counts:
            top = counts.most_common()
            if len(top) == 1 or top[0][1] > top[1][1]:
                modal = top[0][0]
        disagreement = (
            sum(row.recommendation != winner for row in task_shadows)
            if winner is not None
            else None
        )
        task_verdicts.append(
            TaskVerdict(
                task_class=task_class,
                bench_winner=winner,
                winner_suppressed_reason=suppressed,
                operator_driver=operator_driver,
                nd_modal_suggestion=modal,
                nd_sample_size=len(task_shadows),
                nd_disagreement_count=disagreement,
                models=model_metrics,
                judged=_build_judged_task_layer(
                    week_id=week_id,
                    suite=suite,
                    task_class=task_class,
                    model_ids=model_ids,
                    live_records=records,
                    budget_over_cap=budget_over_cap,
                    manifest=judged_manifest,
                    evidence_rows=evidence_rows,
                    anchors=judged_anchors,
                    policy=judged_policy,
                    signing_key=judged_join_signing_key,
                )
                if judged_manifest is not None
                else None,
            )
        )
    canonical_inputs = json.dumps(
        {
            "calls": [row.to_dict() for row in sorted(records, key=lambda item: item.call_id)],
            "shadows": [row.to_dict() for row in sorted(shadows, key=lambda item: item.shadow_id)],
            "suite": suite.suite_version,
            "wedge_id": wedge_id,
        },
        sort_keys=True,
        separators=(",", ":"),
    )
    return WeeklyVerdict(
        week_id=week_id,
        suite_version=suite.suite_version,
        task_verdicts=tuple(task_verdicts),
        budget_spent_usd=str(spent),
        budget_reserved_usd=str(charged - spent),
        budget_cap_usd=str(budget_cap_usd),
        budget_over_cap=budget_over_cap,
        input_digest="sha256:" + hashlib.sha256(canonical_inputs.encode()).hexdigest(),
        judged_manifest_digest=manifest_digest,
        operator_acknowledgment_required=True,
        schema_version=WEEKLY_VERDICT_SCHEMA_VERSION,
    )


def _digest(value: Any) -> str:
    raw = json.dumps(value, sort_keys=True, separators=(",", ":"), default=str)
    return "sha256:" + hashlib.sha256(raw.encode()).hexdigest()


def _not_measured(
    reasons: Iterable[str],
    *,
    policy: VerdictPolicy | None,
    rubric_version: str | None = None,
    anchor_version: str | None = None,
    expected_sample_size: int = 0,
    input_identity: Any = None,
) -> JudgedTaskLayer:
    ordered = tuple(dict.fromkeys(reasons))
    return JudgedTaskLayer(
        status=NOT_MEASURED,
        axes=(),
        winner=None,
        suppression_reasons=ordered,
        disagreement=(),
        calibration=(),
        sample_size=0,
        expected_sample_size=expected_sample_size,
        rubric_version=rubric_version,
        policy_version=policy.version if policy else None,
        anchor_version=anchor_version,
        evidence_schema_version=EVIDENCE_SCHEMA_VERSION,
        input_digest=_digest(
            {"status": NOT_MEASURED, "reasons": ordered, "inputs": input_identity}
        ),
    )


def _build_judged_task_layer(
    *,
    week_id: str,
    suite: SuiteDefinition,
    task_class: TaskClass,
    model_ids: tuple[str, ...],
    live_records: list[LiveCallRecord],
    budget_over_cap: bool,
    manifest: JudgedJoinManifest,
    evidence_rows: tuple[EvidenceRecord, ...],
    anchors: AnchorSet | None,
    policy: VerdictPolicy | None,
    signing_key: bytes | None,
) -> JudgedTaskLayer:
    reasons: list[str] = []
    if manifest.week_id != week_id or manifest.suite_version != suite.suite_version:
        reasons.append("manifest_identity_mismatch")
    if manifest.blinding_policy_version != JUDGE_POLICY_VERSION:
        reasons.append("blinding_policy_mismatch")
    if budget_over_cap:
        reasons.append("budget_cap_exceeded")
    if policy is None:
        reasons.append("missing_policy")
    if anchors is None or not anchors.items:
        reasons.append("missing_anchor_calibration")
    if signing_key is None:
        reasons.append("missing_private_join_key")
    joins = tuple(item for item in manifest.items if item.task_class == task_class)
    suite_items = {item.item_id: item for item in suite.items_for(task_class)}
    if not joins:
        reasons.append("no_live_judged_evidence")
    if {item.live_item_id for item in joins} != set(suite_items):
        reasons.append("incomplete_manifest_coverage")
    expected_anchor_keys = {
        (
            item.item_id_hash,
            item.rubric_version,
            tuple(sorted(candidate.candidate_hash for candidate in item.candidates)),
        )
        for item in joins
    }
    joined_item_hashes = {item.item_id_hash for item in joins}
    observed_anchor_keys = (
        {
            (item.item_id_hash, item.rubric_version, item.candidate_hashes)
            for item in anchors.items
            if item.item_id_hash in joined_item_hashes
        }
        if anchors is not None
        else set()
    )
    if observed_anchor_keys != expected_anchor_keys:
        reasons.append("incomplete_anchor_coverage")
    sources: list[EvidenceRecord] = []
    swaps: list[tuple[EvidenceRecord, EvidenceRecord]] = []
    expected_total = 0
    rubric_versions: set[str] = set()
    accepted_rows: list[EvidenceRecord] = []
    for join in joins:
        suite_item = suite_items.get(join.live_item_id)
        prompt_hash = (
            "sha256:" + hashlib.sha256(suite_item.prompt.encode()).hexdigest() if suite_item else ""
        )
        matching_live_rows = [
            row
            for row in live_records
            if row.task_class == task_class
            and row.item_id == join.live_item_id
            and row.prompt_hash == join.live_prompt_hash
            and row.status == "ok"
        ]
        live_bindings = {
            row.requested_model: (
                row.actual_provider,
                row.actual_model,
                row.call_id,
                row.response_hash,
                row.route_receipt_id,
            )
            for row in matching_live_rows
        }
        candidate_models = tuple(candidate.model_id for candidate in join.candidates)
        candidate_bindings = {
            candidate.model_id: (
                candidate.provider_id,
                candidate.model_id,
                candidate.live_call_id,
                candidate.live_response_hash,
            )
            for candidate in join.candidates
        }
        if (
            suite_item is None
            or prompt_hash != join.live_prompt_hash
            or candidate_models != model_ids
            or len(matching_live_rows) != len(model_ids)
            or any(not binding[3] or not binding[4] for binding in live_bindings.values())
            or {model: binding[:4] for model, binding in live_bindings.items()}
            != candidate_bindings
            or join.rubric_version != rubric_for(suite_item.task_class).version
            or join.rubric_fingerprint != rubric_for(suite_item.task_class).fingerprint
        ):
            reasons.append("manifest_live_join_mismatch")
            continue
        rubric_versions.add(join.rubric_version)
        expected_total += len(join.allowed_judges) * 2
        pair = tuple(candidate.candidate_hash for candidate in join.candidates)
        expected_ids = set(join.evidence_ids)
        declared_rows = [row for row in evidence_rows if row.evidence_id in expected_ids]
        matches = [
            row
            for row in declared_rows
            if (
                row.week_id,
                row.suite_version,
                row.item_id_hash,
                row.task_class,
                row.rubric_version,
                row.task_context_hash,
                row.rubric_fingerprint,
                row.schema_version,
            )
            == (
                week_id,
                suite.suite_version,
                join.item_id_hash,
                task_class,
                join.rubric_version,
                join.task_context_hash,
                join.rubric_fingerprint,
                EVIDENCE_SCHEMA_VERSION,
            )
        ]
        by_id = {row.evidence_id: row for row in matches}
        observed_judges = {row.judge_model.strip().casefold() for row in matches}
        expected_judges = {judge.strip().casefold() for judge in join.allowed_judges}
        if (
            len(declared_rows) != len(expected_ids)
            or len(matches) != len(expected_ids)
            or set(by_id) != expected_ids
            or observed_judges != expected_judges
        ):
            reasons.append("incomplete_judge_panel")
            continue
        if any(row.status != "ok" for row in matches):
            reasons.append("failed_judge_evidence")
            continue
        if signing_key is None:
            continue
        envelopes_by_id = {envelope.evidence_id: envelope for envelope in join.private_envelopes}
        expected_private_bindings = {
            (
                candidate.provider_id,
                candidate.model_id,
                candidate.live_call_id,
                candidate.live_response_hash,
                candidate.candidate_hash,
            )
            for candidate in join.candidates
        }
        live_pair = (matching_live_rows[0], matching_live_rows[1])
        envelope_invalid = False
        for evidence_id, row in by_id.items():
            envelope = envelopes_by_id[evidence_id]
            envelope_bindings = {
                (
                    binding.provider_id,
                    binding.model_id,
                    binding.live_call_id,
                    binding.live_response_hash,
                    binding.blinded_candidate_hash,
                )
                for binding in envelope.bindings
            }
            try:
                verify_private_join(
                    envelope=envelope,
                    evidence=row,
                    live_records=live_pair,
                    signing_key=signing_key,
                )
            except ValueError:
                envelope_invalid = True
                break
            if envelope_bindings != expected_private_bindings:
                envelope_invalid = True
                break
        if envelope_invalid:
            reasons.append("invalid_private_join_envelope")
            continue
        for first_id, reverse_id in join.position_swaps:
            first, reversed_row = by_id[first_id], by_id[reverse_id]
            if (
                first.candidate_hashes != pair
                or reversed_row.candidate_hashes != tuple(reversed(pair))
                or first.judge_model.strip().casefold()
                != reversed_row.judge_model.strip().casefold()
            ):
                reasons.append("invalid_position_swap")
                continue
            try:
                compare_position_swap(first, reversed_row)
            except ValueError:
                reasons.append("invalid_position_swap")
                continue
            sources.append(first)
            swaps.append((first, reversed_row))
            accepted_rows.extend((first, reversed_row))
    if len(rubric_versions) > 1:
        reasons.append("mixed_rubric_versions")
    if not sources or reasons:
        declared_rubrics = {join.rubric_version for join in joins}
        return _not_measured(
            reasons or ("no_live_judged_evidence",),
            policy=policy,
            rubric_version=(next(iter(declared_rubrics)) if len(declared_rubrics) == 1 else None),
            anchor_version=anchors.version if anchors else None,
            expected_sample_size=sum(len(join.allowed_judges) * 2 for join in joins),
            input_identity={
                "manifest_items": tuple(join.item_id_hash for join in joins),
                "evidence_ids": tuple(sorted(row.evidence_id for row in evidence_rows)),
            },
        )
    assert policy is not None
    # Sprint 2 expects judge identities to be unique within one item. Compute and
    # interpret each item independently, then expose the structured views together.
    verdicts = []
    directional_model_winners: set[str] = set()
    verdict_model_winners: set[str] = set()
    disagreement_payload: list[dict[str, Any]] = []
    calibration_payload: list[dict[str, Any]] = []
    for join in joins:
        item_sources = [row for row in sources if row.item_id_hash == join.item_id_hash]
        item_swaps = [pair for pair in swaps if pair[0].item_id_hash == join.item_id_hash]
        disagreement = compute_disagreement(item_sources, expected_judges=join.allowed_judges)
        candidate_to_model = {
            candidate.candidate_hash: candidate.model_id for candidate in join.candidates
        }
        item_winners = {winner for _, winner in disagreement.judge_winners if winner is not None}
        if len(item_winners) == 1:
            directional_model_winners.add(candidate_to_model[next(iter(item_winners))])
        item_anchors = (
            replace(
                anchors,
                items=tuple(
                    item for item in anchors.items if item.item_id_hash == join.item_id_hash
                ),
            )
            if anchors is not None
            else None
        )
        calibration = calibrate_against_anchors(item_sources, item_anchors)
        item_verdict = build_qualitative_verdict(
            records=item_sources,
            disagreement=disagreement,
            swaps=item_swaps,
            calibration=calibration,
            anchors=item_anchors,
            candidate_models=model_ids,
            policy=policy,
        )
        verdicts.append(item_verdict)
        if item_verdict.winner is not None:
            verdict_model_winners.add(candidate_to_model[item_verdict.winner])
        disagreement_payload.append(
            {
                "axes": tuple(asdict(axis) for axis in disagreement.axes),
                "winner_disagreement": disagreement.winner_disagreement,
                "failure_count": disagreement.failure_count,
                "effective_sample_size": disagreement.effective_sample_size,
                "expected_sample_size": disagreement.expected_sample_size,
                "missing_judge_count": len(disagreement.missing_judges),
                "mixed_rubric_versions": disagreement.mixed_rubric_versions,
                "condorcet_cycle": disagreement.condorcet_cycle,
            }
        )
        calibration_payload.append(
            {
                "calibrated": calibration.calibrated,
                "signed_axis_errors": calibration.signed_axis_errors,
                "matched_anchor_count": calibration.matched_anchor_count,
                "evidence_sample_size": calibration.evidence_sample_size,
                "missing_anchor_count": calibration.missing_anchor_count,
            }
        )
    suppressions: tuple[str, ...] = tuple(
        dict.fromkeys(reason for verdict in verdicts for reason in verdict.suppression_reasons)
    )
    if len(directional_model_winners) > 1:
        suppressions = (*suppressions, "cross_item_winner_disagreement")
    winner_model = (
        next(iter(verdict_model_winners))
        if len(verdict_model_winners) == 1 and not suppressions
        else None
    )
    models_by_item = {
        join.item_id_hash: {
            candidate.candidate_hash: candidate.model_id for candidate in join.candidates
        }
        for join in joins
    }
    axes: list[JudgedAxisResult] = []
    for axis in rubric_for(task_class).axes:
        values: dict[str, list[int]] = {model: [] for model in model_ids}
        for row in sources:
            score = dict(row.scores)[axis]
            item_models = models_by_item[row.item_id_hash]
            values[item_models[row.candidate_hashes[0]]].append(score)
            values[item_models[row.candidate_hashes[1]]].append(6 - score)
        axes.append(
            JudgedAxisResult(
                axis=axis,
                candidate_scores=tuple(
                    (model, round(sum(scores) / len(scores), 6))
                    for model, scores in values.items()
                    if scores
                ),
                sample_size=sum(len(scores) for scores in values.values()) // 2,
            )
        )
    private_evidence_digest_input = tuple(
        {
            "evidence_id": row.evidence_id,
            "item_id_hash": row.item_id_hash,
            "judge_model": row.judge_model,
            "candidate_hashes": row.candidate_hashes,
            "blinded_order": row.blinded_order,
            "status": row.status,
            "scores": row.scores,
            "schema_version": row.schema_version,
        }
        for row in accepted_rows
    )
    return JudgedTaskLayer(
        status="MEASURED",
        axes=tuple(axes),
        winner=winner_model,
        suppression_reasons=suppressions,
        disagreement=tuple(disagreement_payload),
        calibration=tuple(calibration_payload),
        sample_size=len(accepted_rows),
        expected_sample_size=expected_total,
        rubric_version=next(iter(rubric_versions)),
        policy_version=policy.version if policy else None,
        anchor_version=anchors.version if anchors else None,
        evidence_schema_version=EVIDENCE_SCHEMA_VERSION,
        input_digest=_digest(private_evidence_digest_input),
    )


def project_weekly_verdict_html(verdict: WeeklyVerdict) -> str:
    payload = verdict.to_dict()
    acknowledgment = str(verdict.operator_acknowledgment_required).lower()
    rows: list[str] = []
    for task in verdict.task_verdicts:
        judged_status = task.judged.status if task.judged else NOT_MEASURED
        judged_axes = (
            "; ".join(
                f"{axis.axis}: "
                + ", ".join(f"{model}={score}" for model, score in axis.candidate_scores)
                for axis in task.judged.axes
            )
            if task.judged and task.judged.axes
            else NOT_MEASURED
        )
        judged_uncertainty = (
            ", ".join(task.judged.suppression_reasons) or "none"
            if task.judged
            else "no_live_judged_evidence"
        )
        for metric in task.models:
            rows.append(
                "<tr>"
                f"<td>{html.escape(task.task_class)}</td>"
                f"<td>{html.escape(metric.model_id)}</td>"
                f"<td>{metric.keyword_proxy_quality if metric.keyword_proxy_quality is not None else 'unmeasured'}</td>"
                f"<td>{html.escape(metric.actual_cost_usd)}</td>"
                f"<td>{metric.p50_latency_ms if metric.p50_latency_ms is not None else 'n/a'} / {metric.p95_latency_ms if metric.p95_latency_ms is not None else 'n/a'}</td>"
                f"<td>{metric.availability:.3f}</td>"
                f"<td>{metric.success_count}/{metric.failure_count}/{metric.timeout_count}</td>"
                f"<td>{metric.sample_size}/{metric.expected_samples}</td>"
                f"<td>{html.escape(task.operator_driver or 'none')}</td>"
                f"<td>{html.escape(task.bench_winner or task.winner_suppressed_reason or 'none')}</td>"
                f"<td>{html.escape(task.nd_modal_suggestion or 'none')} ({task.nd_sample_size})</td>"
                f"<td>{task.nd_disagreement_count if task.nd_disagreement_count is not None else 'n/a'}</td>"
                f"<td>{html.escape(judged_status)}</td>"
                f"<td>{html.escape(judged_axes)}</td>"
                f"<td>{html.escape(judged_uncertainty)}</td>"
                "</tr>"
            )
    safe_json = json.dumps(payload, sort_keys=True).replace("<", "\\u003c")
    return f"""<!doctype html>
<html lang="en"><head><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1">
<title>Antiek-bench weekly verdict {html.escape(verdict.week_id)}</title>
<style>body{{font:14px/1.45 system-ui;margin:0;color:#202124;background:#fafafa}}main{{max-width:1180px;margin:auto;padding:24px}}h1{{font-size:24px}}table{{width:100%;border-collapse:collapse;background:#fff}}th,td{{border:1px solid #c9c9c9;padding:7px;text-align:left;vertical-align:top}}th{{background:#f1f1ed}}footer{{margin-top:20px;border-top:2px solid #222;padding-top:12px}}</style></head>
<body><main><h1>Antiek-bench weekly verdict</h1>
<p>Week {html.escape(verdict.week_id)} · suite {html.escape(verdict.suite_version)} · budget actual/reserved/cap {html.escape(verdict.budget_spent_usd)} / {html.escape(verdict.budget_reserved_usd)} / {html.escape(verdict.budget_cap_usd)} USD</p>
<table><thead><tr><th>Task</th><th>Model</th><th>Deterministic: keyword proxy quality</th><th>Cost USD</th><th>p50 / p95 ms</th><th>Availability</th><th>OK / fail / timeout</th><th>Samples</th><th>Operator driver</th><th>Bench winner</th><th>ND shadow modal</th><th>ND disagreements</th><th>Qualitative status</th><th>Qualitative axes (no composite)</th><th>Disagreement / calibration suppressions</th></tr></thead><tbody>{"".join(rows)}</tbody></table>
<footer>Advisory evidence only. auto_promotion=false. operator_acknowledgment_required={acknowledgment} before any future recommendation export. No export authority is provided. The operator controls model and suite changes. Keyword overlap is a proxy, not judged answer quality.</footer>
<script type="application/json" id="antiek-bench-verdict">{safe_json}</script></main></body></html>"""
