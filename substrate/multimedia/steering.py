"""Steering and revision planning for multimedia assets.

SPR-07 turns a text or corrected voice prompt into structured, reviewable
revision intent. It deliberately stops before paid regeneration: the result is
a child manifest with lineage, affected targets, reused-segment proof, and cost
delta estimates. Provider workers can consume that plan later without guessing
what the operator meant.
"""

from __future__ import annotations

import hashlib
import re
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field, model_validator

from substrate.contracts.multimedia import (
    CostRow,
    MultimediaAssetContract,
    MultimediaManifest,
    MultimediaStatus,
    PromptRecord,
    ProviderCall,
    RoutePolicy,
)
from substrate.multimedia.provider_router import (
    BudgetExceeded,
    GenerationKind,
    MediaGenerationRequest,
    route_media_request,
)

SteeringOperationKind = Literal[
    "shorten",
    "lengthen",
    "deepen",
    "skip",
    "reorder",
    "change_tone",
    "change_tier",
    "regenerate_scene",
]
SteeringTargetKind = Literal["asset", "chapter", "scene", "segment", "script_span"]
SteeringIntentStatus = Literal["ready", "needs_clarification"]


class _SteeringBase(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid")


class SteeringTranscript(_SteeringBase):
    """Voice steering capture after ASR, before applying an edit."""

    transcript_id: str
    raw_text: str = Field(min_length=1)
    corrected_text: str | None = None
    confidence: float | None = Field(default=None, ge=0, le=1)

    @property
    def text_for_parser(self) -> str:
        return (self.corrected_text or self.raw_text).strip()


class SteeringOperation(_SteeringBase):
    operation_id: str
    kind: SteeringOperationKind
    target_kind: SteeringTargetKind
    target_id: str
    value: str | None = None
    reason: str

    @model_validator(mode="after")
    def targets_are_explicit(self) -> SteeringOperation:
        if not self.target_id.strip():
            raise ValueError("steering operations require an explicit target_id")
        return self


class SteeringIntent(_SteeringBase):
    steering_event_id: str
    prompt: str = Field(min_length=1)
    status: SteeringIntentStatus
    operations: tuple[SteeringOperation, ...] = Field(default_factory=tuple)
    clarifications: tuple[str, ...] = Field(default_factory=tuple)
    transcript: SteeringTranscript | None = None

    @model_validator(mode="after")
    def ready_requires_operations(self) -> SteeringIntent:
        if self.status == "ready" and not self.operations:
            raise ValueError("ready steering intents require operations")
        if self.status == "needs_clarification" and not self.clarifications:
            raise ValueError("clarification intents require clarification text")
        return self


class SegmentReuse(_SteeringBase):
    segment_id: str
    reused: bool
    reason: str
    file_ids: tuple[str, ...] = Field(default_factory=tuple)
    file_sha256s: tuple[str, ...] = Field(default_factory=tuple)


class RevisionChange(_SteeringBase):
    operation_id: str
    target_id: str
    changed_segment_ids: tuple[str, ...]
    estimated_cost_delta_usd: float = Field(ge=0)
    explanation: str


class RevisionPlan(_SteeringBase):
    parent_asset_id: str
    parent_revision_id: str
    revision_id: str
    steering_event_id: str
    route_policy: RoutePolicy
    intent: SteeringIntent
    affected_segment_ids: tuple[str, ...]
    segment_reuse: tuple[SegmentReuse, ...]
    changes: tuple[RevisionChange, ...]
    estimated_cost_delta_usd: float = Field(ge=0)
    manifest: MultimediaManifest

    @model_validator(mode="after")
    def affected_segments_are_explained(self) -> RevisionPlan:
        changed = {segment for change in self.changes for segment in change.changed_segment_ids}
        if changed != set(self.affected_segment_ids):
            raise ValueError("affected_segment_ids must match revision changes")
        return self


_TOKEN_RE = re.compile(r"[a-z0-9][a-z0-9-]{2,}")
_MINUTE_RE = re.compile(r"\b(1[5-9]|[2-3][0-9]|4[0-5])\s*(?:min|mins|minute|minutes)\b")
_CHAPTER_RE = re.compile(r"\bchapter\s+(\d+)\b")
_SCENE_RE = re.compile(r"\bscene\s+([a-z0-9_.:-]+)\b")
_SEGMENT_RE = re.compile(r"\b(?:segment|seg)\s+([a-z0-9_.:-]+)\b")
_REORDER_RE = re.compile(r"\b(?:reorder|rearrange|swap|move)\b")


def parse_steering_prompt(
    prompt: str,
    manifest: MultimediaManifest,
    *,
    transcript: SteeringTranscript | None = None,
) -> SteeringIntent:
    """Parse steering text into operations with manifest targets.

    The parser is intentionally conservative. If it cannot identify either an
    operation or a target, it returns a clarification intent rather than
    inventing edits against paid media.
    """

    source_text = transcript.text_for_parser if transcript is not None else prompt
    text = source_text.strip()
    lower = text.lower()
    steering_event_id = _stable_id("steer", manifest.asset_id, manifest.revision_id, text)
    targets = _resolve_targets(lower, manifest)
    op_kinds = _operation_kinds(lower)
    clarifications: list[str] = []

    if not op_kinds:
        clarifications.append(
            "Say whether to shorten, lengthen, deepen, skip, reorder, change tone, change tier, or regenerate a scene."
        )
    if not targets and any(kind not in {"shorten", "lengthen", "change_tier", "change_tone"} for kind in op_kinds):
        clarifications.append(
            "Name the chapter, scene, segment, or script span to change before regeneration."
        )
    if clarifications:
        return SteeringIntent(
            steering_event_id=steering_event_id,
            prompt=text,
            status="needs_clarification",
            clarifications=tuple(clarifications),
            transcript=transcript,
        )

    if not targets:
        targets = (("asset", manifest.asset_id),)

    operations: list[SteeringOperation] = []
    for kind in op_kinds:
        operation_targets = targets
        if kind in {"change_tier"} or (kind in {"shorten", "lengthen"} and _value_for(kind, lower)):
            operation_targets = (("asset", manifest.asset_id),)
        for target_kind, target_id in operation_targets:
            value = _value_for(kind, lower)
            operations.append(
                SteeringOperation(
                    operation_id=_stable_id("op", steering_event_id, kind, target_id, value or ""),
                    kind=kind,
                    target_kind=target_kind,
                    target_id=target_id,
                    value=value,
                    reason=_reason_for(kind, target_id, value),
                )
            )
    return SteeringIntent(
        steering_event_id=steering_event_id,
        prompt=text,
        status="ready",
        operations=tuple(operations),
        transcript=transcript,
    )


def plan_revision(
    parent: MultimediaAssetContract,
    intent: SteeringIntent,
    *,
    revision_id: str | None = None,
    budget_usd: float | None = None,
) -> RevisionPlan:
    """Build a child manifest revision plan without executing regeneration."""

    if intent.status != "ready":
        raise ValueError("cannot plan a revision from a clarification intent")
    new_revision_id = revision_id or _stable_id("rev", parent.revision_id, intent.steering_event_id)
    route_policy = _route_policy_after(parent.route_policy, intent)
    affected = _affected_segments(parent.manifest, intent)
    reuse = tuple(
        _segment_reuse(segment_id, segment_id not in affected, parent.manifest)
        for segment_id in (segment.segment_id for segment in parent.manifest.segments)
    )
    changes = tuple(
        _revision_change(parent.manifest, operation, affected, route_policy, budget_usd)
        for operation in intent.operations
    )
    changed_by_operation = tuple(change for change in changes if change.changed_segment_ids)
    estimated = round(
        sum(
            _estimate_segment_cost(parent.manifest, segment_id, route_policy, budget_usd)
            for segment_id in affected
        ),
        4,
    )
    if budget_usd is not None and estimated > budget_usd:
        raise BudgetExceeded(
            f"steering revision estimated ${estimated:.4f} exceeds budget "
            f"${budget_usd:.4f}; downgrade the route tier or narrow the affected scope"
        )
    prompt_record = PromptRecord(
        prompt_id=f"prompt-{intent.steering_event_id}",
        purpose="revision",
        prompt_sha256=hashlib.sha256(intent.prompt.encode("utf-8")).hexdigest(),
        provider_hint="antiek-steering",
    )
    provider_calls, cost_rows = _planned_provider_cost_rows(
        intent=intent,
        affected_segment_ids=affected,
        route_policy=route_policy,
        estimated_cost_delta_usd=estimated,
    )
    manifest = parent.manifest.model_copy(
        update={
            "revision_id": new_revision_id,
            "route_policy": route_policy,
            "prompts": parent.manifest.prompts + (prompt_record,),
            "provider_calls": parent.manifest.provider_calls + provider_calls,
            "cost_rows": parent.manifest.cost_rows + cost_rows,
        }
    )
    return RevisionPlan(
        parent_asset_id=parent.asset_id,
        parent_revision_id=parent.revision_id,
        revision_id=new_revision_id,
        steering_event_id=intent.steering_event_id,
        route_policy=route_policy,
        intent=intent,
        affected_segment_ids=affected,
        segment_reuse=reuse,
        changes=changed_by_operation,
        estimated_cost_delta_usd=estimated,
        manifest=manifest,
    )


def build_revision_asset(parent: MultimediaAssetContract, plan: RevisionPlan) -> MultimediaAssetContract:
    """Create the child asset contract row for a planned steering revision."""

    return parent.model_copy(
        update={
            "status": MultimediaStatus.PLANNED,
            "route_policy": plan.route_policy,
            "revision_id": plan.revision_id,
            "parent_revision_id": plan.parent_revision_id,
            "steering_event_id": plan.steering_event_id,
            "manifest": plan.manifest,
            "failure_reason": None,
        }
    )


def _operation_kinds(lower: str) -> tuple[SteeringOperationKind, ...]:
    kinds: list[SteeringOperationKind] = []
    if "shorten" in lower or "shorter" in lower or _MINUTE_RE.search(lower):
        kinds.append("shorten")
    if "lengthen" in lower or "longer" in lower or "expand" in lower:
        kinds.append("lengthen")
    if "deeper" in lower or "go deep" in lower or "more detail" in lower or "more concrete" in lower:
        kinds.append("deepen")
    if "remove" in lower or "skip" in lower or "cut " in lower or "omit" in lower:
        kinds.append("skip")
    if _REORDER_RE.search(lower):
        kinds.append("reorder")
    if "tone" in lower or "style" in lower or "more casual" in lower or "more formal" in lower:
        kinds.append("change_tone")
    if "cheapest" in lower or "balanced" in lower or "highest quality" in lower or "highest-quality" in lower:
        kinds.append("change_tier")
    if "regenerate" in lower or "rerender" in lower or "re-render" in lower:
        kinds.append("regenerate_scene")
    return tuple(dict.fromkeys(kinds))


def _resolve_targets(
    lower: str,
    manifest: MultimediaManifest,
) -> tuple[tuple[SteeringTargetKind, str], ...]:
    targets: list[tuple[SteeringTargetKind, str]] = []
    by_sequence = {segment.sequence + 1: segment.segment_id for segment in manifest.segments}

    for match in _CHAPTER_RE.finditer(lower):
        seq = int(match.group(1))
        if seq in by_sequence:
            targets.append(("chapter", by_sequence[seq]))
    for regex, kind in ((_SEGMENT_RE, "segment"), (_SCENE_RE, "scene")):
        for match in regex.finditer(lower):
            raw = match.group(1)
            candidate = raw if raw.startswith(("seg-", "scene-")) else f"seg-{raw}"
            if any(segment.segment_id == candidate for segment in manifest.segments):
                targets.append((kind, candidate))  # type: ignore[arg-type]
    if targets:
        return tuple(dict.fromkeys(targets))

    tokens = {token for token in _TOKEN_RE.findall(lower) if token not in {"chapter", "scene", "segment"}}
    for segment in manifest.segments:
        haystack = " ".join([
            segment.segment_id,
            segment.title,
            " ".join(segment.source_chunk_ids),
            " ".join(segment.script_line_ids),
        ]).lower()
        if tokens and any(token in haystack for token in tokens):
            targets.append(("segment", segment.segment_id))

    return tuple(dict.fromkeys(targets))


def _affected_segments(
    manifest: MultimediaManifest,
    intent: SteeringIntent,
) -> tuple[str, ...]:
    segment_ids = tuple(segment.segment_id for segment in manifest.segments)
    affected: list[str] = []
    global_kinds = {"shorten", "lengthen", "change_tier", "change_tone"}
    for operation in intent.operations:
        if operation.target_kind == "asset" or operation.target_id == manifest.asset_id:
            if operation.kind in global_kinds:
                affected.extend(segment_ids)
            continue
        if operation.target_id in segment_ids:
            affected.append(operation.target_id)
    return tuple(dict.fromkeys(affected))


def _route_policy_after(current: RoutePolicy, intent: SteeringIntent) -> RoutePolicy:
    for operation in intent.operations:
        if operation.kind != "change_tier" or operation.value is None:
            continue
        if operation.value in {"cheapest", "balanced", "highest_quality"}:
            return operation.value  # type: ignore[return-value]
    return current


def _value_for(kind: SteeringOperationKind, lower: str) -> str | None:
    if kind in {"shorten", "lengthen"}:
        match = _MINUTE_RE.search(lower)
        if match:
            return f"{match.group(1)} minutes"
    if kind == "change_tier":
        if "cheapest" in lower:
            return "cheapest"
        if "highest quality" in lower or "highest-quality" in lower:
            return "highest_quality"
        if "balanced" in lower:
            return "balanced"
    if kind == "change_tone":
        if "casual" in lower:
            return "casual"
        if "formal" in lower:
            return "formal"
        if "style" in lower:
            return "style change"
    return None


def _reason_for(kind: SteeringOperationKind, target_id: str, value: str | None) -> str:
    suffix = f" to {value}" if value else ""
    return f"{kind.replace('_', ' ')} {target_id}{suffix}"


def _segment_reuse(segment_id: str, reused: bool, manifest: MultimediaManifest) -> SegmentReuse:
    segment = next(segment for segment in manifest.segments if segment.segment_id == segment_id)
    files_by_id = {file.file_id: file for file in manifest.files}
    files = tuple(file_id for file_id in segment.file_ids if file_id in files_by_id)
    hashes = tuple(files_by_id[file_id].sha256 for file_id in files)
    return SegmentReuse(
        segment_id=segment_id,
        reused=reused,
        reason="unaffected by steering intent" if reused else "targeted for regeneration",
        file_ids=files,
        file_sha256s=hashes,
    )


def _revision_change(
    manifest: MultimediaManifest,
    operation: SteeringOperation,
    affected_segment_ids: tuple[str, ...],
    route_policy: RoutePolicy,
    budget_usd: float | None,
) -> RevisionChange:
    changed = tuple(segment_id for segment_id in affected_segment_ids if _operation_targets_segment(operation, segment_id, manifest))
    cost = sum(_estimate_segment_cost(manifest, segment_id, route_policy, budget_usd) for segment_id in changed)
    return RevisionChange(
        operation_id=operation.operation_id,
        target_id=operation.target_id,
        changed_segment_ids=changed,
        estimated_cost_delta_usd=round(cost, 4),
        explanation=f"{operation.reason}; unchanged segments are reused by file hash",
    )


def _operation_targets_segment(
    operation: SteeringOperation,
    segment_id: str,
    manifest: MultimediaManifest,
) -> bool:
    if operation.target_kind == "asset" or operation.target_id == manifest.asset_id:
        return True
    return operation.target_id == segment_id


def _estimate_segment_cost(
    manifest: MultimediaManifest,
    segment_id: str,
    route_policy: RoutePolicy,
    budget_usd: float | None,
) -> float:
    segment = next(segment for segment in manifest.segments if segment.segment_id == segment_id)
    duration = segment.duration_seconds or 5.0
    has_video_or_motion = segment.media_kind in {"motion", "still", "caption"}
    kind: GenerationKind = "image_to_video" if has_video_or_motion else "video"
    request = MediaGenerationRequest(
        kind=kind,
        prompt=f"Revision regeneration for {segment.title}",
        route_policy=route_policy,
        duration_seconds=min(duration, 30.0),
        budget_usd=budget_usd,
        dry_run=True,
    )
    return route_media_request(request).estimated_cost_usd


def _planned_provider_cost_rows(
    *,
    intent: SteeringIntent,
    affected_segment_ids: tuple[str, ...],
    route_policy: RoutePolicy,
    estimated_cost_delta_usd: float,
) -> tuple[tuple[ProviderCall, ...], tuple[CostRow, ...]]:
    if not affected_segment_ids:
        return (), ()
    call_id = _stable_id("call", intent.steering_event_id, ",".join(affected_segment_ids), route_policy)
    call = ProviderCall(
        call_id=call_id,
        provider="planned_regeneration",
        model="multimedia-steering",
        prompt_id=f"prompt-{intent.steering_event_id}",
        route_policy=route_policy,
        status="planned",
        input_units=len(intent.prompt),
        output_units=len(affected_segment_ids),
        unit_type="affected_segments",
        cost_usd=estimated_cost_delta_usd,
    )
    row = CostRow(
        cost_id=f"cost-{call_id}",
        call_id=call_id,
        provider="planned_regeneration",
        route_policy=route_policy,
        cost_usd=estimated_cost_delta_usd,
        billable_units=len(affected_segment_ids),
        unit_type="affected_segments",
    )
    return (call,), (row,)


def _stable_id(prefix: str, *parts: str) -> str:
    digest = hashlib.sha256("\x1f".join(parts).encode("utf-8")).hexdigest()[:16]
    return f"{prefix}-{digest}"


__all__ = [
    "RevisionChange",
    "RevisionPlan",
    "SegmentReuse",
    "SteeringIntent",
    "SteeringIntentStatus",
    "SteeringOperation",
    "SteeringOperationKind",
    "SteeringTargetKind",
    "SteeringTranscript",
    "build_revision_asset",
    "parse_steering_prompt",
    "plan_revision",
]
