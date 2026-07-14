"""Evaluation and hardening gates for multimedia assets.

SPR-08 defines the multimedia ship bar. These gates are deterministic and
provider-free: they evaluate manifests, optional scene/playback models, cost
rows, and retry posture before an asset is treated as ready.
"""

from __future__ import annotations

from collections.abc import Iterable, Mapping
from typing import Any, Literal

from pydantic import BaseModel, ConfigDict, Field

from substrate.contracts.multimedia import MultimediaAssetContract, MultimediaStatus
from substrate.multimedia.ship_cost_snapshot import (
    MultimediaShipCostEvidenceUnavailable,
    MultimediaShipCostSnapshotV1,
    verify_multimedia_ship_cost_snapshot,
)

GateStatus = Literal["pass", "fail", "manual"]
ShipStatus = Literal["pass", "blocked", "manual_review"]
FindingSeverity = Literal["info", "warning", "error"]


class _HardeningBase(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid")


class GateFinding(_HardeningBase):
    code: str
    severity: FindingSeverity
    message: str
    target_id: str | None = None


class GateResult(_HardeningBase):
    gate_id: str
    status: GateStatus
    findings: tuple[GateFinding, ...] = Field(default_factory=tuple)


class MultimediaHardeningReport(_HardeningBase):
    asset_id: str
    revision_id: str
    ship_status: ShipStatus
    gates: tuple[GateResult, ...]
    residual_risks: tuple[str, ...] = Field(default_factory=tuple)
    cost_snapshot: MultimediaShipCostSnapshotV1 | None = None

    @property
    def failed_gate_ids(self) -> tuple[str, ...]:
        return tuple(gate.gate_id for gate in self.gates if gate.status == "fail")

    @property
    def manual_gate_ids(self) -> tuple[str, ...]:
        return tuple(gate.gate_id for gate in self.gates if gate.status == "manual")


def evaluate_multimedia_asset(
    asset: MultimediaAssetContract,
    *,
    acknowledged_unsourced_line_ids: tuple[str, ...] = (),
    cost_snapshot: MultimediaShipCostSnapshotV1 | None = None,
    snapshot_key: bytes | None = None,
    owner_id: str | None = None,
    scenes: Iterable[Any] = (),
    retry_attempts: int = 0,
    max_retry_attempts: int = 2,
) -> MultimediaHardeningReport:
    """Run the multimedia ship gates over an asset/revision.

    Optional ``scenes`` may be ``VideoScene`` objects or dictionaries with
    ``visual_label``/``asset_prompt``/``scene_id`` keys. The evaluator accepts
    both so tests can include intentionally invalid visual rows that the
    production ``VideoScene`` model would reject at construction time.
    """

    gates = (
        _grounding_gate(asset, acknowledged_unsourced_line_ids, scenes),
        _cost_gate(
            asset,
            cost_snapshot=cost_snapshot,
            snapshot_key=snapshot_key,
            owner_id=owner_id,
        ),
        _playback_gate(asset),
        _provider_safety_gate(asset, retry_attempts, max_retry_attempts),
        _rights_publication_gate(),
    )
    if any(gate.status == "fail" for gate in gates):
        ship_status: ShipStatus = "blocked"
    elif any(gate.status == "manual" for gate in gates):
        ship_status = "manual_review"
    else:
        ship_status = "pass"
    return MultimediaHardeningReport(
        asset_id=asset.asset_id,
        revision_id=asset.revision_id,
        ship_status=ship_status,
        gates=gates,
        residual_risks=(
            "Public publishing approval is out of scope for this automated gate.",
            "Custom voice likeness/licensing requires operator review before release.",
        ),
        cost_snapshot=(cost_snapshot if gates[1].status == "pass" else None),
    )


def _grounding_gate(
    asset: MultimediaAssetContract,
    acknowledged_unsourced_line_ids: tuple[str, ...],
    scenes: Iterable[Any],
) -> GateResult:
    findings: list[GateFinding] = []
    acknowledged = set(acknowledged_unsourced_line_ids)
    for line in asset.manifest.script_lines:
        if line.kind == "factual" and not line.citations and line.line_id not in acknowledged:
            findings.append(
                GateFinding(
                    code="unsourced_factual_claim",
                    severity="error",
                    target_id=line.line_id,
                    message="Unsourced factual script line requires citation or explicit acknowledgement.",
                )
            )
    for scene in scenes:
        label = _get(scene, "visual_label")
        prompt = str(_get(scene, "asset_prompt") or "").lower()
        scene_id = str(_get(scene, "scene_id") or "")
        if label == "generated" and "archival" in prompt and "not archival" not in prompt:
            findings.append(
                GateFinding(
                    code="generated_archival_claim",
                    severity="error",
                    target_id=scene_id or None,
                    message="Generated visuals cannot be labeled or prompted as real archival footage.",
                )
            )
    return GateResult(
        gate_id="grounding_and_disclosure",
        status="fail" if findings else "pass",
        findings=tuple(findings),
    )


def _cost_gate(
    asset: MultimediaAssetContract,
    *,
    cost_snapshot: MultimediaShipCostSnapshotV1 | None,
    snapshot_key: bytes | None,
    owner_id: str | None,
) -> GateResult:
    if cost_snapshot is None or snapshot_key is None or owner_id is None:
        finding = GateFinding(
            code="cost_evidence_unavailable",
            severity="error",
            message="Authoritative direct-provider cost evidence is unavailable.",
        )
        return GateResult(gate_id="cost_and_budget", status="fail", findings=(finding,))
    try:
        verify_multimedia_ship_cost_snapshot(
            cost_snapshot,
            snapshot_key=snapshot_key,
            owner_id=owner_id,
            asset_id=asset.asset_id,
            revision_id=asset.revision_id,
        )
    except (MultimediaShipCostEvidenceUnavailable, TypeError, ValueError):
        finding = GateFinding(
            code="cost_evidence_invalid",
            severity="error",
            message="Direct-provider cost evidence failed integrity or identity validation.",
        )
        return GateResult(gate_id="cost_and_budget", status="fail", findings=(finding,))
    return GateResult(gate_id="cost_and_budget", status="pass")


def _playback_gate(asset: MultimediaAssetContract) -> GateResult:
    findings: list[GateFinding] = []
    file_kinds = {file.kind for file in asset.manifest.files}
    has_chapters = any(segment.media_kind == "chapter" for segment in asset.manifest.segments)
    has_voiceover = any(segment.media_kind == "voiceover" for segment in asset.manifest.segments)
    has_motion = any(segment.media_kind == "motion" for segment in asset.manifest.segments)

    if asset.kind in {"information_video", "documentary_video"}:
        if asset.manifest.captions_file_id is None or "caption" not in file_kinds:
            findings.append(
                GateFinding(
                    code="missing_captions",
                    severity="error",
                    message="Video assets require caption files before they are ship-ready.",
                )
            )
        if asset.manifest.transcript_file_id is None and "transcript" not in file_kinds:
            findings.append(
                GateFinding(
                    code="missing_transcript",
                    severity="error",
                    message="Video assets require a transcript or linked transcript file.",
                )
            )
        if not has_motion:
            findings.append(
                GateFinding(
                    code="missing_video_timeline",
                    severity="error",
                    message="Video assets require motion timeline segments for playback navigation.",
                )
            )
    if asset.kind == "audio_experience":
        if "audio" not in file_kinds:
            findings.append(
                GateFinding(
                    code="missing_audio",
                    severity="error",
                    message="Audio experiences require audio files.",
                )
            )
        if asset.manifest.transcript_file_id is None and "transcript" not in file_kinds:
            findings.append(
                GateFinding(
                    code="missing_transcript",
                    severity="error",
                    message="Audio experiences require transcripts for source inspection and fallback.",
                )
            )
        if not (has_chapters or has_voiceover):
            findings.append(
                GateFinding(
                    code="missing_chapters",
                    severity="error",
                    message="Audio experiences require chapter or voiceover segments.",
                )
            )
    return GateResult(
        gate_id="playback_and_accessibility",
        status="fail" if findings else "pass",
        findings=tuple(findings),
    )


def _provider_safety_gate(
    asset: MultimediaAssetContract,
    retry_attempts: int,
    max_retry_attempts: int,
) -> GateResult:
    findings: list[GateFinding] = []
    if retry_attempts > max_retry_attempts:
        findings.append(
            GateFinding(
                code="retry_budget_exceeded",
                severity="error",
                message=f"Retry attempts {retry_attempts} exceed max retry budget {max_retry_attempts}.",
            )
        )
    failed_calls = tuple(call for call in asset.manifest.provider_calls if call.status == "failed")
    if failed_calls and asset.status == MultimediaStatus.READY:
        findings.append(
            GateFinding(
                code="failed_provider_call_marked_ready",
                severity="error",
                message="Assets with failed provider calls must be partial or failed, not ready.",
            )
        )
    partial_files = bool(asset.manifest.files) and any(call.status == "failed" for call in asset.manifest.provider_calls)
    if partial_files and asset.status == MultimediaStatus.READY:
        findings.append(
            GateFinding(
                code="partial_output_marked_ready",
                severity="error",
                message="Partial provider output must be labeled partial/failed rather than ready.",
            )
        )
    return GateResult(
        gate_id="provider_safety_retry",
        status="fail" if findings else "pass",
        findings=tuple(findings),
    )


def _rights_publication_gate() -> GateResult:
    return GateResult(
        gate_id="rights_and_publication",
        status="manual",
        findings=(
            GateFinding(
                code="manual_publication_review",
                severity="warning",
                message="Public publishing rights, third-party media licenses, and custom voice permissions are manual gates.",
            ),
        ),
    )


def _get(row: Any, key: str) -> Any:
    if isinstance(row, Mapping):
        return row.get(key)
    return getattr(row, key, None)


__all__ = [
    "GateFinding",
    "GateResult",
    "GateStatus",
    "MultimediaHardeningReport",
    "ShipStatus",
    "evaluate_multimedia_asset",
]
