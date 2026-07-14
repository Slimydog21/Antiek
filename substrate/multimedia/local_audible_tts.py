"""Canonical cheapest-local speech requests for exact AudibleRun spans."""

from __future__ import annotations

import hashlib
import json
import math
import re
from collections.abc import Mapping
from dataclasses import dataclass
from typing import Literal

from .audible_run import prepare_audible_run_plan
from .narration import normalize_script
from .planner import CanonicalEvidenceChunk, MultimediaPlan

_ID = re.compile(r"^[A-Za-z0-9][A-Za-z0-9._:-]{0,127}$")
_MAX_TEXT_BYTES = 256 * 1024


@dataclass(frozen=True)
class PreparedAudibleSpanTTSRequest:
    """The exact local speech body for one measured transcript span."""

    schema_version: Literal["antiek.audible-span-tts-request.v1"]
    asset_id: str
    revision_id: str
    chapter_id: str
    paragraph_id: str
    line_id: str
    sequence: int
    route_policy: Literal["cheapest"]
    provider: Literal["local_executable_tts"]
    model: Literal["macos-say-v1"]
    endpoint_capability: Literal["text-to-speech"]
    voice: str
    speed: float
    sample_rate_hz: int
    channels: Literal[1, 2]
    text: str
    source_chunk_ids: tuple[str, ...]
    marker_kind: Literal["content", "signpost", "remember", "recap"]

    @property
    def body_json(self) -> str:
        return json.dumps(
            {
                "asset_id": self.asset_id,
                "channels": self.channels,
                "chapter_id": self.chapter_id,
                "endpoint_capability": self.endpoint_capability,
                "line_id": self.line_id,
                "marker_kind": self.marker_kind,
                "model": self.model,
                "paragraph_id": self.paragraph_id,
                "provider": self.provider,
                "revision_id": self.revision_id,
                "route_policy": self.route_policy,
                "sample_rate_hz": self.sample_rate_hz,
                "schema_version": self.schema_version,
                "sequence": self.sequence,
                "source_chunk_ids": list(self.source_chunk_ids),
                "speed": self.speed,
                "text": self.text,
                "voice": self.voice,
            },
            sort_keys=True,
            separators=(",", ":"),
            ensure_ascii=True,
            allow_nan=False,
        )

    @property
    def body_digest(self) -> str:
        return hashlib.sha256(self.body_json.encode("ascii")).hexdigest()


def prepare_local_audible_span_requests(
    plan: MultimediaPlan,
    *,
    asset_id: str,
    revision_id: str,
    voice: str = "narrator",
    speed: float = 1.0,
    sample_rate_hz: int = 24_000,
    channels: Literal[1, 2] = 1,
    canonical_chunks: Mapping[str, CanonicalEvidenceChunk] | None = None,
) -> tuple[PreparedAudibleSpanTTSRequest, ...]:
    """Expand a plan into the exact cheapest-local calls needed by AudibleRun."""
    asset_id = _identifier("asset_id", asset_id)
    revision_id = _identifier("revision_id", revision_id)
    voice = _identifier("voice", voice)
    if plan.request.route_policy != "cheapest":
        raise ValueError("local audible production requires cheapest routing")
    if not math.isfinite(speed) or not 0.25 <= speed <= 4:
        raise ValueError("speed must be finite and in [0.25, 4]")
    if not 8_000 <= sample_rate_hz <= 48_000 or channels not in {1, 2}:
        raise ValueError("audible span audio shape is invalid")

    run_plan = prepare_audible_run_plan(plan, canonical_chunks=canonical_chunks)
    chapter_ids = {chapter.chapter_id for chapter in run_plan.chapters}
    paragraphs = normalize_script(
        tuple(
            line
            for line in run_plan.script_lines
            if line.line_id.split("-line-", 1)[0] in chapter_ids
        )
    )
    requests: list[PreparedAudibleSpanTTSRequest] = []
    for sequence, paragraph in enumerate(paragraphs):
        text = str(paragraph.text)
        if not text or len(text.encode("utf-8")) > _MAX_TEXT_BYTES:
            raise ValueError("audible span text is empty or exceeds its byte ceiling")
        requests.append(
            PreparedAudibleSpanTTSRequest(
                schema_version="antiek.audible-span-tts-request.v1",
                asset_id=asset_id,
                revision_id=revision_id,
                chapter_id=_identifier(
                    "chapter_id", paragraph.line_id.split("-line-", 1)[0]
                ),
                paragraph_id=_identifier("paragraph_id", str(paragraph.para_id)),
                line_id=_identifier("line_id", str(paragraph.line_id)),
                sequence=sequence,
                route_policy="cheapest",
                provider="local_executable_tts",
                model="macos-say-v1",
                endpoint_capability="text-to-speech",
                voice=voice,
                speed=round(float(speed), 3),
                sample_rate_hz=sample_rate_hz,
                channels=channels,
                text=text,
                source_chunk_ids=tuple(paragraph.source_chunk_ids),
                marker_kind=_marker_kind(str(paragraph.line_id)),
            )
        )
    if not requests:
        raise ValueError("local audible production requires spoken spans")
    return tuple(requests)


def _identifier(name: str, value: str) -> str:
    if not isinstance(value, str) or not _ID.fullmatch(value):
        raise ValueError(f"{name} is invalid")
    return value


def _marker_kind(line_id: str) -> Literal["content", "signpost", "remember", "recap"]:
    for marker in ("signpost", "remember", "recap"):
        if line_id.endswith(f"-run-{marker}"):
            return marker
    return "content"


__all__ = ["PreparedAudibleSpanTTSRequest", "prepare_local_audible_span_requests"]
