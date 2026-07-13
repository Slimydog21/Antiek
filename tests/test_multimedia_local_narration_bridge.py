from __future__ import annotations

from dataclasses import replace

import pytest

from substrate.contracts.multimedia import ScriptLine
from substrate.multimedia.chapter_tts_production import prepare_chapter_tts_request
from substrate.multimedia.local_narration_bridge import (
    LocalNarrationBridgeError,
    compile_local_narration_inputs,
)
from substrate.multimedia.local_tts import LocalTTSArtifact
from substrate.multimedia.planner import ChapterPlan, MultimediaPlan, MultimediaPlanRequest


def _plan() -> MultimediaPlan:
    return MultimediaPlan(
        request=MultimediaPlanRequest(
            topic="Aircraft production", target_minutes=15, route_policy="cheapest"
        ),
        suggestions=(),
        chosen_arc_ids=(),
        chapters=(
            ChapterPlan(
                chapter_id="chapter-1", title="Flow", minutes=7.5,
                purpose="Explain flow", arc_id="flow", source_chunk_ids=("chunk-1",),
            ),
            ChapterPlan(
                chapter_id="chapter-2", title="Control", minutes=7.5,
                purpose="Explain control", arc_id="control", source_chunk_ids=("chunk-2",),
            ),
        ),
        script_lines=(
            ScriptLine(
                line_id="chapter-1-line-0", sequence=0, text="Factories coordinate flow.",
                kind="factual", citations=(), unsourced_reason="fixture",
            ),
            ScriptLine(
                line_id="chapter-2-line-0", sequence=1, text="Inspection controls quality.",
                kind="factual", citations=(), unsourced_reason="fixture",
            ),
        ),
        scenes=(),
        unsourced_line_ids=("chapter-1-line-0", "chapter-2-line-0"),
    )


def _requests(plan: MultimediaPlan):  # noqa: ANN202
    return tuple(
        prepare_chapter_tts_request(
            plan,
            asset_id="asset-1",
            revision_id="revision-1",
            provider="local_executable_tts",
            model="macos-say-v1",
            voice="narrator",
            chapter_id=chapter.chapter_id,
        )
        for chapter in plan.chapters
    )


class Resolver:
    def __init__(self, requests) -> None:  # noqa: ANN001
        self.calls: list[str] = []
        self.rows = {
            request.body_digest: LocalTTSArtifact(
                request_id=f"mmlocaltts_{index:064x}",
                request_body_digest=request.body_digest,
                config_digest="c" * 64,
                output_path=f"/private/audio/chapter-{index}.wav",
                output_sha256=f"{index + 1:064x}",
                duration_seconds=float(index + 1),
                sample_rate_hz=request.sample_rate_hz,
                channels=request.channels,
                synthesizer_digest="s" * 64,
                probe_digest="p" * 64,
                created_at="2026-07-13T00:00:00Z",
            )
            for index, request in enumerate(requests)
        }

    def reopen(self, request):  # noqa: ANN001, ANN201
        self.calls.append(request.body_digest)
        return self.rows[request.body_digest]


def test_compiles_verified_ordered_zero_cost_canonical_inputs() -> None:
    plan = _plan()
    requests = _requests(plan)
    resolver = Resolver(requests)
    first = compile_local_narration_inputs(plan, requests, resolver=resolver)
    second = compile_local_narration_inputs(plan, requests, resolver=resolver)
    assert first == second
    assert first.cost_usd == 0.0
    assert tuple(row.chapter_id for row in first.chapters) == ("chapter-1", "chapter-2")
    assert tuple(row.start_offset_seconds for row in first.chapters) == (0.0, 1.0)
    assert tuple(row.duration_seconds for row in first.generated_files) == (1.0, 2.0)
    assert set(first.chapter_paths) == set(first.request_ids)
    assert resolver.calls == [request.body_digest for request in requests] * 2


@pytest.mark.parametrize("mutation", ["missing", "reordered", "foreign", "text", "shape"])
def test_rejects_incomplete_reordered_or_drifted_requests(mutation: str) -> None:
    plan = _plan()
    requests = _requests(plan)
    resolver = Resolver(requests)
    if mutation == "missing":
        changed = requests[:1]
    elif mutation == "reordered":
        changed = tuple(reversed(requests))
    elif mutation == "foreign":
        changed = (requests[0], replace(requests[1], revision_id="revision-2"))
    elif mutation == "text":
        changed = (replace(requests[0], text="drift"), requests[1])
    else:
        changed = (requests[0], replace(requests[1], channels=2))
    with pytest.raises(LocalNarrationBridgeError):
        compile_local_narration_inputs(plan, changed, resolver=resolver)


@pytest.mark.parametrize("field,value", [("duration_seconds", 0.0), ("channels", 2)])
def test_rejects_resolver_artifact_drift(field: str, value: object) -> None:
    plan = _plan()
    requests = _requests(plan)
    resolver = Resolver(requests)
    digest = requests[0].body_digest
    resolver.rows[digest] = replace(resolver.rows[digest], **{field: value})
    with pytest.raises(LocalNarrationBridgeError, match="artifact conflicts"):
        compile_local_narration_inputs(plan, requests, resolver=resolver)


def test_resolver_failure_is_fail_closed() -> None:
    plan = _plan()
    requests = _requests(plan)
    resolver = Resolver(requests)
    del resolver.rows[requests[1].body_digest]
    with pytest.raises(LocalNarrationBridgeError, match="unavailable"):
        compile_local_narration_inputs(plan, requests, resolver=resolver)
