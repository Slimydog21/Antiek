"""SPR-01 multimedia asset contract tests.

The point is schema durability before paid providers exist: no Krea key, TTS
key, or video renderer is required to prove the asset/manifest contract.
"""

from __future__ import annotations

import hashlib

import pytest
from pydantic import ValidationError

from substrate.contracts.multimedia import (
    EvidenceDerivation,
    EvidenceSpan,
    GeneratedFile,
    MultimediaAssetContract,
    MultimediaManifest,
    ProviderCall,
    ScriptLine,
    SourceCitation,
    can_transition,
)

SHA = "a" * 64


def _asset() -> MultimediaAssetContract:
    prompt = {
        "prompt_id": "prompt-script",
        "purpose": "script",
        "prompt_sha256": SHA,
        "provider_hint": "openai",
    }
    video_prompt = {
        "prompt_id": "prompt-video",
        "purpose": "video",
        "prompt_sha256": "b" * 64,
        "provider_hint": "krea",
    }
    line = ScriptLine(
        line_id="line-1",
        sequence=0,
        text="The Boeing 747's high-bypass engines changed long-haul economics.",
        citations=(SourceCitation(chunk_id="chunk-1", document_id="doc-1"),),
    )
    manifest = MultimediaManifest(
        asset_id="mm-1",
        revision_id="rev-1",
        route_policy="balanced",
        prompts=(prompt, video_prompt),
        script_lines=(line,),
        files=(
            GeneratedFile(
                file_id="file-video",
                kind="video",
                storage_uri="s3://antiek/multimedia/mm-1/rev-1/video.mp4",
                sha256="c" * 64,
                mime="video/mp4",
                provider="krea",
                prompt_id="prompt-video",
                duration_seconds=120.0,
                width_px=1920,
                height_px=1080,
            ),
        ),
        provider_calls=(
            ProviderCall(
                call_id="call-krea-1",
                provider="krea",
                model="video",
                prompt_id="prompt-video",
                route_policy="balanced",
                status="planned",
            ),
        ),
        cost_rows=(
            {
                "cost_id": "cost-1",
                "call_id": "call-krea-1",
                "provider": "krea",
                "route_policy": "balanced",
                "cost_usd": 0.0,
                "billable_units": 0,
                "unit_type": "planned_call",
            },
        ),
        segments=(
            {
                "segment_id": "seg-1",
                "sequence": 0,
                "title": "747 economics",
                "media_kind": "motion",
                "script_line_ids": ("line-1",),
                "file_ids": ("file-video",),
                "source_chunk_ids": ("chunk-1",),
                "duration_seconds": 120.0,
            },
        ),
        claim_to_chunk=(
            {
                "claim_id": "claim-1",
                "script_line_id": "line-1",
                "chunk_ids": ("chunk-1",),
            },
        ),
    )
    return MultimediaAssetContract(
        asset_id="mm-1",
        kind="information_video",
        title="Why the 747 changed long-haul travel",
        user_prompt="Make a short Asianometry-like explainer about the 747.",
        status="planned",
        route_policy="balanced",
        requested_duration_minutes=15,
        revision_id="rev-1",
        manifest=manifest,
    )


def test_multimedia_asset_round_trips_json():
    asset = _asset()

    reparsed = MultimediaAssetContract.model_validate_json(asset.model_dump_json())

    assert reparsed == asset
    assert reparsed.manifest.files[0].sha256 == "c" * 64
    assert reparsed.manifest.provider_calls[0].provider == "krea"


def test_missing_required_fields_fail_loudly():
    data = _asset().model_dump()
    del data["manifest"]["files"][0]["sha256"]

    with pytest.raises(ValidationError) as exc:
        MultimediaAssetContract.model_validate(data)

    assert "sha256" in str(exc.value)


def test_factual_script_line_requires_citation_or_unsourced_marker():
    with pytest.raises(ValidationError, match="factual script lines require"):
        ScriptLine(line_id="line-bad", sequence=0, text="The claim is stated.")

    line = ScriptLine(
        line_id="line-unsourced",
        sequence=1,
        text="This is framing narration stated without source support.",
        unsourced_reason="operator framing, not a factual source claim",
    )
    assert line.unsourced_reason is not None


def test_text_bound_citation_rejects_script_text_drift():
    text = "The reviewed source states this exact claim."
    body = text.encode("utf-8")
    citation = SourceCitation(
        chunk_id="chunk-1",
        document_id="doc-1",
        quote_sha256="a" * 64,
    )
    derivation = EvidenceDerivation(
        method="verbatim_span",
        recipe_version="antiek.evidence-narration.v1",
        spans=(
            EvidenceSpan(
                chunk_id="chunk-1",
                document_id="doc-1",
                authority_kind="operator_excerpt",
                chunk_sha256="a" * 64,
                start_utf8_byte=0,
                end_utf8_byte=len(body),
                span_sha256=hashlib.sha256(body).hexdigest(),
                exact_text=text,
            ),
        ),
        output_sha256=hashlib.sha256(body).hexdigest(),
    )
    ScriptLine(
        line_id="line-1",
        sequence=0,
        text=text,
        citations=(citation,),
        evidence_derivation=derivation,
    )

    with pytest.raises(ValidationError, match="evidence derivation"):
        ScriptLine(
            line_id="line-1",
            sequence=0,
            text="A substituted claim.",
            citations=(citation,),
            evidence_derivation=derivation,
        )


def test_generated_files_require_duration_or_dimensions():
    with pytest.raises(ValidationError, match="duration_seconds or width_px"):
        GeneratedFile(
            file_id="file-bad",
            kind="image",
            storage_uri="s3://antiek/multimedia/file.png",
            sha256=SHA,
            mime="image/png",
            provider="krea",
        )


def test_manifest_references_must_resolve():
    data = _asset().model_dump()
    data["manifest"]["segments"][0]["file_ids"] = ("missing-file",)

    with pytest.raises(ValidationError, match="references missing files"):
        MultimediaAssetContract.model_validate(data)


def test_revision_requires_steering_event():
    data = _asset().model_dump()
    data["revision_id"] = "rev-2"
    data["parent_revision_id"] = "rev-1"
    data["manifest"]["revision_id"] = "rev-2"

    with pytest.raises(ValidationError, match="steering_event_id"):
        MultimediaAssetContract.model_validate(data)


def test_lifecycle_transition_table():
    assert can_transition("requested", "planned")
    assert can_transition("script_ready", "rendering")
    assert can_transition("ready", "superseded")
    assert not can_transition("ready", "rendering")
    assert not can_transition("archived", "requested")


def test_contract_needs_no_provider_api_key(monkeypatch):
    monkeypatch.delenv("KREA_API_KEY", raising=False)
    monkeypatch.delenv("OPENAI_API_KEY", raising=False)

    asset = _asset()

    assert asset.manifest.provider_calls[0].status == "planned"
    assert asset.manifest.cost_rows[0].cost_usd == 0.0


def test_provider_field_rejects_secret_like_values():
    with pytest.raises(ValidationError, match="not carry a secret"):
        ProviderCall(call_id="call-1", provider="krea_api_key_live", model="video")
