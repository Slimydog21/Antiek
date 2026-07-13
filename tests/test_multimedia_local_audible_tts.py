from __future__ import annotations

from dataclasses import replace

import pytest

from substrate.multimedia.local_audible_tts import prepare_local_audible_span_requests
from substrate.multimedia.planner import EvidenceChunk, MultimediaPlanRequest, build_multimedia_plan


def _plan(*, route_policy: str = "cheapest"):
    plan = build_multimedia_plan(
        MultimediaPlanRequest(
            topic="jet engine history", target_minutes=15, route_policy=route_policy
        ),
        evidence=(
            EvidenceChunk(
                chunk_id="chunk-whittle",
                document_id="doc-engines",
                text="Frank Whittle patented a turbojet design in 1930.",
                title="Early turbojets",
                section_path="history/whittle",
            ),
        ),
    )
    authority = next(line.citations for line in plan.script_lines if line.citations)
    authority_ids = tuple(citation.chunk_id for citation in authority)
    lines = []
    for line in plan.script_lines:
        values = line.model_dump(mode="python")
        if line.kind == "factual" and not line.citations:
            values.update(citations=authority, unsourced_reason=None)
        lines.append(type(line).model_validate(values))
    chapters = []
    for chapter in plan.chapters:
        values = chapter.model_dump(mode="python")
        values["source_chunk_ids"] = tuple(
            dict.fromkeys((*chapter.source_chunk_ids, *authority_ids))
        )
        chapters.append(type(chapter).model_validate(values))
    values = plan.model_dump(mode="python")
    values.update(script_lines=tuple(lines), chapters=tuple(chapters), unsourced_line_ids=())
    return type(plan).model_validate(values)


def test_prepares_one_canonical_request_per_transformed_span() -> None:
    requests = prepare_local_audible_span_requests(
        _plan(), asset_id="asset-1", revision_id="revision-1"
    )

    assert requests
    assert tuple(request.sequence for request in requests) == tuple(range(len(requests)))
    assert len({request.paragraph_id for request in requests}) == len(requests)
    assert all(
        request.route_policy == "cheapest"
        and request.provider == "local_executable_tts"
        and request.model == "macos-say-v1"
        for request in requests
    )
    kinds = {request.marker_kind for request in requests}
    assert {"content", "signpost", "remember", "recap"} <= kinds
    assert all(
        request.source_chunk_ids
        for request in requests
        if request.marker_kind in {"remember", "recap"}
    )
    assert all(len(request.body_digest) == 64 for request in requests)


def test_request_body_binds_span_identity_and_source_authority() -> None:
    request = prepare_local_audible_span_requests(
        _plan(), asset_id="asset-1", revision_id="revision-1"
    )[-1]

    assert replace(request, paragraph_id="different").body_digest != request.body_digest
    assert replace(request, source_chunk_ids=("different",)).body_digest != request.body_digest
    assert replace(request, text=request.text + " Changed.").body_digest != request.body_digest


def test_refuses_non_cheapest_route_and_invalid_audio_shape() -> None:
    with pytest.raises(ValueError, match="cheapest"):
        prepare_local_audible_span_requests(
            _plan(route_policy="balanced"), asset_id="asset-1", revision_id="revision-1"
        )
    with pytest.raises(ValueError, match="audio shape"):
        prepare_local_audible_span_requests(
            _plan(),
            asset_id="asset-1",
            revision_id="revision-1",
            sample_rate_hz=7_999,
        )
