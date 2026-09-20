"""SPR-08 multimedia evaluation and hardening tests."""

from __future__ import annotations

import pytest

from substrate.contracts.multimedia import (
    CostRow,
    GeneratedFile,
    MultimediaAssetContract,
    MultimediaManifest,
    ProviderCall,
    ScriptLine,
    SourceCitation,
)
from substrate.multimedia.audio_assembly import assemble_audio_experience
from substrate.multimedia.hardening import MultimediaHardeningReport, evaluate_multimedia_asset
from substrate.multimedia.planner import EvidenceChunk, MultimediaPlanRequest, build_multimedia_plan
from substrate.multimedia.tts import FakeTTSProvider
from substrate.multimedia.video import assemble_video_documentary, build_video_scenes

SHA = "e" * 64


def _plan():
    evidence = (
        EvidenceChunk(
            chunk_id="chunk-history",
            document_id="doc-widebody",
            text="Widebody history changed long-haul airline capacity and economics.",
        ),
        EvidenceChunk(
            chunk_id="chunk-engine",
            document_id="doc-engine",
            text="High-bypass engines made long-haul widebody flights more viable.",
        ),
    )
    return build_multimedia_plan(
        MultimediaPlanRequest(
            topic="widebody aircraft",
            target_minutes=20,
            mode="audio",
            route_policy="cheapest",
            selected_arc_ids=("history", "mechanism"),
        ),
        evidence,
    )


def _audio_asset(status: str = "ready") -> MultimediaAssetContract:
    audio = assemble_audio_experience(_plan(), FakeTTSProvider(), asset_id="mm-hard-audio", revision_id="rev-audio")
    return MultimediaAssetContract(
        asset_id="mm-hard-audio",
        kind="audio_experience",
        title="Widebody aircraft audio",
        user_prompt="Make an audio explainer about widebody aircraft.",
        status=status,
        route_policy="cheapest",
        requested_duration_minutes=20,
        revision_id="rev-audio",
        manifest=audio.manifest,
    )


def _video_asset() -> MultimediaAssetContract:
    plan = _plan()
    audio = assemble_audio_experience(plan, FakeTTSProvider(), asset_id="mm-hard-video", revision_id="rev-audio")
    video = assemble_video_documentary(plan, audio, asset_id="mm-hard-video", revision_id="rev-video")
    return MultimediaAssetContract(
        asset_id="mm-hard-video",
        kind="documentary_video",
        title="Widebody aircraft video",
        user_prompt="Make a video explainer about widebody aircraft.",
        status="ready",
        route_policy="cheapest",
        requested_duration_minutes=20,
        revision_id="rev-video",
        manifest=video.manifest,
    )


def test_audio_without_authoritative_cost_evidence_is_blocked_and_keeps_manual_residuals():
    report = evaluate_multimedia_asset(_audio_asset())

    assert report.ship_status == "blocked"
    assert report.failed_gate_ids == ("cost_and_budget",)
    assert report.manual_gate_ids == ("rights_and_publication",)
    assert any("Custom voice" in risk for risk in report.residual_risks)


def test_legacy_hardening_report_without_either_cost_authority_still_reopens():
    payload = evaluate_multimedia_asset(_audio_asset()).model_dump(mode="json")
    payload.pop("cost_snapshot")
    payload.pop("local_zero_cost_evidence")

    reopened = MultimediaHardeningReport.model_validate(payload)

    assert reopened.cost_snapshot is None
    assert reopened.local_zero_cost_evidence is None


def test_unsourced_factual_claim_fails_without_acknowledgement():
    line = ScriptLine(
        line_id="line-unsourced",
        sequence=0,
        text="This aircraft fact has no evidence.",
        unsourced_reason="operator has not attached evidence yet",
    )
    manifest = MultimediaManifest(
        asset_id="mm-unsourced",
        revision_id="rev-1",
        route_policy="balanced",
        script_lines=(line,),
    )
    asset = MultimediaAssetContract(
        asset_id="mm-unsourced",
        kind="audio_experience",
        title="Unsourced audio",
        user_prompt="Make an audio brief.",
        status="planned",
        route_policy="balanced",
        requested_duration_minutes=15,
        revision_id="rev-1",
        manifest=manifest,
    )

    report = evaluate_multimedia_asset(asset)

    assert "grounding_and_disclosure" in report.failed_gate_ids
    assert "playback_and_accessibility" in report.failed_gate_ids

    acknowledged = evaluate_multimedia_asset(asset, acknowledged_unsourced_line_ids=("line-unsourced",))
    assert "grounding_and_disclosure" not in acknowledged.failed_gate_ids


def test_generated_visual_claiming_archival_truth_fails_disclosure_gate():
    asset = _audio_asset(status="planned")

    report = evaluate_multimedia_asset(
        asset,
        scenes=(
            {
                "scene_id": "scene-bad",
                "visual_label": "generated",
                "asset_prompt": "Generate archival photograph of the first flight.",
            },
        ),
    )

    assert "grounding_and_disclosure" in report.failed_gate_ids
    grounding = next(gate for gate in report.gates if gate.gate_id == "grounding_and_disclosure")
    assert any(finding.code == "generated_archival_claim" for finding in grounding.findings)


def test_video_without_transcript_fails_accessibility_even_with_captions():
    asset = _video_asset()
    scenes = build_video_scenes(_plan(), assemble_audio_experience(_plan(), FakeTTSProvider(), asset_id="x", revision_id="r"))

    report = evaluate_multimedia_asset(asset, scenes=scenes)

    assert "playback_and_accessibility" in report.failed_gate_ids
    playback = next(gate for gate in report.gates if gate.gate_id == "playback_and_accessibility")
    assert any(finding.code == "missing_transcript" for finding in playback.findings)


def test_manifest_cost_rows_cannot_satisfy_authoritative_cost_gate():
    call = ProviderCall(
        call_id="call-krea",
        provider="krea",
        model="video",
        status="succeeded",
        route_policy="highest_quality",
        cost_usd=2.0,
    )
    line = ScriptLine(
        line_id="line-1",
        sequence=0,
        text="A cited claim.",
        citations=(SourceCitation(chunk_id="chunk-1", document_id="doc-1"),),
    )
    manifest = MultimediaManifest(
        asset_id="mm-cost",
        revision_id="rev-1",
        route_policy="highest_quality",
        script_lines=(line,),
        provider_calls=(call,),
        files=(
            GeneratedFile(
                file_id="aud-1",
                kind="audio",
                storage_uri="memory://audio.mp3",
                sha256=SHA,
                mime="audio/mpeg",
                provider="krea",
                duration_seconds=30,
            ),
            GeneratedFile(
                file_id="txt-1",
                kind="transcript",
                storage_uri="memory://audio.txt",
                sha256=SHA,
                mime="text/plain",
                provider="krea",
                duration_seconds=30,
            ),
        ),
        segments=(
            {
                "segment_id": "seg-audio",
                "sequence": 0,
                "title": "Audio",
                "media_kind": "voiceover",
                "script_line_ids": ("line-1",),
                "file_ids": ("aud-1", "txt-1"),
                "source_chunk_ids": ("chunk-1",),
                "duration_seconds": 30,
            },
        ),
        transcript_file_id="txt-1",
    )
    asset = MultimediaAssetContract(
        asset_id="mm-cost",
        kind="audio_experience",
        title="Costly audio",
        user_prompt="Make audio.",
        status="ready",
        route_policy="highest_quality",
        requested_duration_minutes=15,
        revision_id="rev-1",
        manifest=manifest,
    )

    report = evaluate_multimedia_asset(asset)

    assert "cost_and_budget" in report.failed_gate_ids
    cost_gate = next(gate for gate in report.gates if gate.gate_id == "cost_and_budget")
    assert {finding.code for finding in cost_gate.findings} == {"cost_evidence_unavailable"}


def test_cost_ledger_survives_failed_jobs_and_provider_retry_policy_blocks_ready_partial():
    asset = _audio_asset()
    failed_call = ProviderCall(
        call_id="call-failed",
        provider="krea",
        model="video",
        status="failed",
        route_policy="balanced",
        cost_usd=0.01,
        error_code="rate_limited",
    )
    failed_row = CostRow(
        cost_id="cost-failed",
        call_id="call-failed",
        provider="krea",
        route_policy="balanced",
        cost_usd=0.01,
        billable_units=1,
        unit_type="failed_job",
    )
    manifest = asset.manifest.model_copy(
        update={
            "provider_calls": asset.manifest.provider_calls + (failed_call,),
            "cost_rows": asset.manifest.cost_rows + (failed_row,),
        }
    )
    partial_ready = asset.model_copy(update={"manifest": manifest})

    report = evaluate_multimedia_asset(partial_ready, retry_attempts=3, max_retry_attempts=2)

    assert "cost_and_budget" in report.failed_gate_ids
    assert "provider_safety_retry" in report.failed_gate_ids
    provider_gate = next(gate for gate in report.gates if gate.gate_id == "provider_safety_retry")
    assert {finding.code for finding in provider_gate.findings} >= {
        "failed_provider_call_marked_ready",
        "partial_output_marked_ready",
        "retry_budget_exceeded",
    }


def test_caller_cost_floats_are_rejected():
    asset = _audio_asset()
    expensive_call = ProviderCall(
        call_id="call-pricey",
        provider="krea",
        model="video",
        status="succeeded",
        route_policy="balanced",
        cost_usd=50.0,
    )
    pricey_row = CostRow(
        cost_id="cost-pricey",
        call_id="call-pricey",
        provider="krea",
        route_policy="balanced",
        cost_usd=50.0,
        billable_units=1,
        unit_type="second",
    )
    manifest = asset.manifest.model_copy(
        update={
            "provider_calls": asset.manifest.provider_calls + (expensive_call,),
            "cost_rows": asset.manifest.cost_rows + (pricey_row,),
        }
    )
    expensive = asset.model_copy(update={"manifest": manifest})
    with pytest.raises(TypeError):
        evaluate_multimedia_asset(expensive, budget_usd=10.0, actual_cost_usd=1.0)
