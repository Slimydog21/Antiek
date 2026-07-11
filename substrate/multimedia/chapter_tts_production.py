"""Deterministic authority boundary for synchronous chapter TTS production.

The paid execution state machine is built on the request produced here. Keeping
request preparation pure makes it possible to quote, approve, and sign the exact
provider call before any budget claim or network-capable callback is reachable.
"""

from __future__ import annotations

import hashlib
import json
import math
import re
from dataclasses import dataclass
from datetime import datetime
from typing import Literal

from .execution_authorization import (
    MultimediaExecutionAuthorizationV2,
    verify_async_execution_authorization,
)
from .narration import normalize_script
from .planner import MultimediaPlan

_ID = re.compile(r"^[A-Za-z0-9][A-Za-z0-9._:-]{0,127}$")
_MAX_TEXT_BYTES = 256 * 1024


@dataclass(frozen=True)
class PreparedChapterTTSRequest:
    """The canonical, provider-independent body authorized for one TTS call."""

    schema_version: Literal["antiek.chapter-tts-request.v1"]
    asset_id: str
    revision_id: str
    chapter_id: str
    title: str
    route_policy: str
    provider: str
    model: str
    endpoint_capability: Literal["text-to-speech"]
    voice: str
    speed: float
    sample_rate_hz: int
    channels: Literal[1, 2]
    text: str
    script_line_ids: tuple[str, ...]
    paragraph_ids: tuple[str, ...]
    source_chunk_ids: tuple[str, ...]

    @property
    def body_json(self) -> str:
        return json.dumps(
            {
                "asset_id": self.asset_id,
                "channels": self.channels,
                "chapter_id": self.chapter_id,
                "endpoint_capability": self.endpoint_capability,
                "model": self.model,
                "paragraph_ids": list(self.paragraph_ids),
                "provider": self.provider,
                "revision_id": self.revision_id,
                "route_policy": self.route_policy,
                "sample_rate_hz": self.sample_rate_hz,
                "schema_version": self.schema_version,
                "script_line_ids": list(self.script_line_ids),
                "source_chunk_ids": list(self.source_chunk_ids),
                "speed": self.speed,
                "text": self.text,
                "title": self.title,
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


def prepare_chapter_tts_request(
    plan: MultimediaPlan,
    *,
    asset_id: str,
    revision_id: str,
    provider: str,
    model: str,
    voice: str = "narrator",
    speed: float = 1.0,
    sample_rate_hz: int = 24_000,
    channels: Literal[1, 2] = 1,
) -> PreparedChapterTTSRequest:
    """Prepare exactly one spoken chapter or fail before paid execution.

    A multi-chapter plan is rejected in v1 because sequential synchronous calls
    cannot be made crash-safe without a parent authorization-set receipt.
    """
    asset_id = _identifier("asset_id", asset_id)
    revision_id = _identifier("revision_id", revision_id)
    provider = _identifier("provider", provider)
    model = _identifier("model", model)
    voice = _identifier("voice", voice)
    if not math.isfinite(speed) or speed < 0.25 or speed > 4:
        raise ValueError("speed must be finite and in [0.25, 4]")
    if not 8_000 <= sample_rate_hz <= 48_000 or channels not in {1, 2}:
        raise ValueError("chapter TTS audio shape is invalid")

    chapter_ids = {chapter.chapter_id for chapter in plan.chapters}
    paragraphs = normalize_script(
        tuple(
            line
            for line in plan.script_lines
            if line.line_id.split("-line-", 1)[0] in chapter_ids
        )
    )
    grouped: dict[str, list[object]] = {}
    for paragraph in paragraphs:
        grouped.setdefault(paragraph.line_id.split("-line-", 1)[0], []).append(paragraph)
    spoken = tuple(chapter for chapter in plan.chapters if grouped.get(chapter.chapter_id))
    if len(spoken) != 1:
        raise ValueError("chapter TTS v1 requires exactly one non-empty spoken chapter")

    chapter = spoken[0]
    rows = grouped[chapter.chapter_id]
    text = " ".join(str(row.text) for row in rows)
    if not text or len(text.encode("utf-8")) > _MAX_TEXT_BYTES:
        raise ValueError("chapter TTS text is empty or exceeds its byte ceiling")
    source_ids = tuple(
        dict.fromkeys(
            (
                *(chunk for row in rows for chunk in row.source_chunk_ids),
                *chapter.source_chunk_ids,
            )
        )
    )
    return PreparedChapterTTSRequest(
        schema_version="antiek.chapter-tts-request.v1",
        asset_id=asset_id,
        revision_id=revision_id,
        chapter_id=_identifier("chapter_id", chapter.chapter_id),
        title=chapter.title,
        route_policy=plan.request.route_policy,
        provider=provider,
        model=model,
        endpoint_capability="text-to-speech",
        voice=voice,
        speed=round(float(speed), 3),
        sample_rate_hz=sample_rate_hz,
        channels=channels,
        text=text,
        script_line_ids=tuple(str(row.line_id) for row in rows),
        paragraph_ids=tuple(str(row.para_id) for row in rows),
        source_chunk_ids=source_ids,
    )


def verify_chapter_tts_authorization(
    authorization: MultimediaExecutionAuthorizationV2,
    prepared: PreparedChapterTTSRequest,
    *,
    signing_key: bytes,
    operator_id: str,
    catalog_version: str,
    catalog_digest: str,
    quote_id: str,
    recovery_authority_id: str,
    recovery_verification_key_digest: str,
    approved_ceiling_microdollars: int,
    now: datetime,
) -> None:
    """Verify the signature and every execution-time binding against the body."""
    verify_async_execution_authorization(
        authorization,
        signing_key=signing_key,
        operator_id=operator_id,
        asset_id=prepared.asset_id,
        revision_id=prepared.revision_id,
        provider=prepared.provider,
        route_policy=prepared.route_policy,
        model=prepared.model,
        endpoint_capability=prepared.endpoint_capability,
        catalog_version=catalog_version,
        catalog_digest=catalog_digest,
        quote_id=quote_id,
        recovery_authority_id=recovery_authority_id,
        recovery_verification_key_digest=recovery_verification_key_digest,
        approved_ceiling_microdollars=approved_ceiling_microdollars,
        request_body_digest=prepared.body_digest,
        now=now,
    )


def _identifier(field: str, value: str) -> str:
    if not isinstance(value, str) or not _ID.fullmatch(value):
        raise ValueError(f"{field} is not a bounded identifier")
    return value


__all__ = [
    "PreparedChapterTTSRequest",
    "prepare_chapter_tts_request",
    "verify_chapter_tts_authorization",
]

