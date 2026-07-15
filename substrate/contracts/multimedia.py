"""Multimedia asset contract -- graph-backed generated information media.

Multimedia is Antiek's generated-media product category: Asianometry-like
explainers, Ken Burns-style documentary reels, and audio-first experiences for
gym/run listening. This module deliberately defines the durable substrate
contract only. Provider adapters (Krea, TTS, video assembly) consume this shape
later; they do not get to invent their own file manifests, cost ledgers, or
provenance maps.

Existing contract anchors this reuses rather than forks:

* ``substrate/books/meta_reading.py`` and
  ``ReadMetaReadingGeneratedPayload``: saved, reopenable Read assets are event
  truth, not client-side blobs.
* ``substrate/contracts/voice_pipeline.py``: capture/ASR/distill has one owner;
  multimedia can cite transcripts but must not create a second voice-note
  pipeline.
* ``services/antiek_format/SPEC.md`` and ``manifest.schema.json``: generated
  binary integrity is sha256-in-manifest, matching voice-block audio.
* ``DispatchCallPayload`` / ``substrate.coordination.cost_view``: realized LLM
  spend is already canonical; multimedia adds provider-render cost rows because
  image/video/TTS providers are not necessarily dispatch calls.

The contract is Python-first for SPR-01. UI/codegen can opt in when the
workstation sprint lands.
"""

from __future__ import annotations

import hashlib
from enum import StrEnum
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator


class MultimediaStatus(StrEnum):
    """Lifecycle states for one generated media asset."""

    REQUESTED = "requested"
    PLANNED = "planned"
    SCRIPT_READY = "script_ready"
    RENDERING = "rendering"
    READY = "ready"
    FAILED = "failed"
    SUPERSEDED = "superseded"
    ARCHIVED = "archived"


ALLOWED_STATUS_TRANSITIONS: dict[MultimediaStatus, frozenset[MultimediaStatus]] = {
    MultimediaStatus.REQUESTED: frozenset({
        MultimediaStatus.PLANNED,
        MultimediaStatus.FAILED,
        MultimediaStatus.ARCHIVED,
    }),
    MultimediaStatus.PLANNED: frozenset({
        MultimediaStatus.SCRIPT_READY,
        MultimediaStatus.FAILED,
        MultimediaStatus.ARCHIVED,
    }),
    MultimediaStatus.SCRIPT_READY: frozenset({
        MultimediaStatus.RENDERING,
        MultimediaStatus.FAILED,
        MultimediaStatus.ARCHIVED,
    }),
    MultimediaStatus.RENDERING: frozenset({
        MultimediaStatus.READY,
        MultimediaStatus.FAILED,
        MultimediaStatus.ARCHIVED,
    }),
    MultimediaStatus.READY: frozenset({
        MultimediaStatus.SUPERSEDED,
        MultimediaStatus.ARCHIVED,
    }),
    MultimediaStatus.FAILED: frozenset({
        MultimediaStatus.REQUESTED,
        MultimediaStatus.ARCHIVED,
    }),
    MultimediaStatus.SUPERSEDED: frozenset({MultimediaStatus.ARCHIVED}),
    MultimediaStatus.ARCHIVED: frozenset(),
}


RoutePolicy = Literal["cheapest", "balanced", "highest_quality"]
AssetKind = Literal["information_video", "documentary_video", "audio_experience"]
MediaFileKind = Literal["audio", "image", "video", "caption", "transcript", "manifest"]
ScriptLineKind = Literal["factual", "transition", "narration", "opinion", "instruction"]
ProviderCallStatus = Literal["planned", "running", "succeeded", "failed", "skipped"]


class _ContractBase(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid", use_enum_values=True)


class SourceCitation(_ContractBase):
    """Reference to graph truth. Carries ids and locators, never source body."""

    chunk_id: str
    document_id: str
    locator: str | None = None
    quote_sha256: str | None = Field(default=None, pattern="^[0-9a-f]{64}$")


class EvidenceSpan(_ContractBase):
    """Exact UTF-8 byte range selected from one immutable graph chunk."""

    chunk_id: str
    document_id: str
    authority_kind: Literal["canonical_graph", "operator_excerpt"]
    chunk_sha256: str = Field(pattern="^[0-9a-f]{64}$")
    start_utf8_byte: int = Field(ge=0)
    end_utf8_byte: int = Field(gt=0)
    span_sha256: str = Field(pattern="^[0-9a-f]{64}$")
    exact_text: str = Field(min_length=1, max_length=700)

    @model_validator(mode="after")
    def range_and_text_digest_agree(self) -> EvidenceSpan:
        body = self.exact_text.encode("utf-8")
        if self.end_utf8_byte <= self.start_utf8_byte:
            raise ValueError("evidence span byte range must be increasing")
        if self.end_utf8_byte - self.start_utf8_byte != len(body):
            raise ValueError("evidence span byte range must match exact_text")
        if hashlib.sha256(body).hexdigest() != self.span_sha256:
            raise ValueError("evidence span digest must match exact_text")
        return self


class EvidenceDerivation(_ContractBase):
    """Versioned deterministic recipe from canonical source bytes to narration."""

    method: Literal["verbatim_span"]
    recipe_version: Literal["antiek.evidence-narration.v1"]
    spans: tuple[EvidenceSpan, ...] = Field(min_length=1, max_length=1)
    output_sha256: str = Field(pattern="^[0-9a-f]{64}$")


class ScriptLine(_ContractBase):
    """One script line with factual grounding.

    Every factual line must either cite one or more chunks or explicitly mark
    why it is unsourced. The explicit unsourced marker is a review surface, not
    a loophole; later gates can reject it.
    """

    line_id: str
    sequence: int = Field(ge=0)
    text: str = Field(min_length=1)
    kind: ScriptLineKind = "factual"
    citations: tuple[SourceCitation, ...] = Field(default_factory=tuple)
    evidence_derivation: EvidenceDerivation | None = None
    unsourced_reason: str | None = None

    @model_validator(mode="after")
    def factual_lines_are_grounded(self) -> ScriptLine:
        if self.kind == "factual" and not self.citations and not self.unsourced_reason:
            raise ValueError(
                "factual script lines require cited chunks or an explicit unsourced_reason"
            )
        if self.evidence_derivation is not None:
            expected = hashlib.sha256(self.text.encode("utf-8")).hexdigest()
            derivation = self.evidence_derivation
            if derivation.output_sha256 != expected:
                raise ValueError("evidence derivation must bind the exact script text")
            if derivation.spans[0].exact_text != self.text:
                raise ValueError("verbatim evidence span must reproduce the script text")
            citation_keys = tuple((row.chunk_id, row.document_id) for row in self.citations)
            span_keys = tuple((row.chunk_id, row.document_id) for row in derivation.spans)
            if citation_keys != span_keys:
                raise ValueError("citations must equal evidence derivation authority")
            if tuple(row.quote_sha256 for row in self.citations) != tuple(
                row.chunk_sha256 for row in derivation.spans
            ):
                raise ValueError("citation chunk digest must equal evidence derivation digest")
        return self


class PromptRecord(_ContractBase):
    """Prompt metadata without storing provider secrets."""

    prompt_id: str
    purpose: Literal["outline", "script", "image", "video", "audio", "revision", "routing"]
    prompt_sha256: str = Field(pattern="^[0-9a-f]{64}$")
    provider_hint: str | None = None
    model_hint: str | None = None


class GeneratedFile(_ContractBase):
    """One generated or assembled file with integrity metadata."""

    file_id: str
    kind: MediaFileKind
    storage_uri: str = Field(min_length=1)
    sha256: str = Field(pattern="^[0-9a-f]{64}$")
    mime: str = Field(min_length=1)
    provider: str
    prompt_id: str | None = None
    duration_seconds: float | None = Field(default=None, ge=0)
    width_px: int | None = Field(default=None, ge=1)
    height_px: int | None = Field(default=None, ge=1)

    @model_validator(mode="after")
    def has_media_shape(self) -> GeneratedFile:
        has_duration = self.duration_seconds is not None
        has_dimensions = self.width_px is not None and self.height_px is not None
        if not (has_duration or has_dimensions):
            raise ValueError("generated files require duration_seconds or width_px+height_px")
        return self


class ProviderCall(_ContractBase):
    """One non-secret provider/render call planned or made for an asset."""

    call_id: str
    provider: str
    model: str | None = None
    prompt_id: str | None = None
    route_policy: RoutePolicy = "balanced"
    status: ProviderCallStatus = "planned"
    input_units: float = Field(default=0, ge=0)
    output_units: float = Field(default=0, ge=0)
    unit_type: str | None = None
    cost_usd: float = Field(default=0, ge=0)
    latency_ms: int | None = Field(default=None, ge=0)
    error_code: str | None = None

    @field_validator("provider")
    @classmethod
    def provider_is_not_secret(cls, value: str) -> str:
        lowered = value.lower()
        if "key" in lowered or "secret" in lowered or "token" in lowered:
            raise ValueError("provider field must name a provider, not carry a secret")
        return value


class CostRow(_ContractBase):
    """Provider spend that is not already a DispatchCallPayload."""

    cost_id: str
    call_id: str
    provider: str
    route_policy: RoutePolicy
    cost_usd: float = Field(ge=0)
    billable_units: float = Field(default=0, ge=0)
    unit_type: str | None = None
    currency: Literal["USD"] = "USD"


class MediaSegment(_ContractBase):
    """A timeline/chapter segment for video, audio, captions, or images."""

    segment_id: str
    sequence: int = Field(ge=0)
    title: str
    media_kind: Literal["chapter", "voiceover", "still", "motion", "caption"]
    script_line_ids: tuple[str, ...] = Field(default_factory=tuple)
    file_ids: tuple[str, ...] = Field(default_factory=tuple)
    source_chunk_ids: tuple[str, ...] = Field(default_factory=tuple)
    duration_seconds: float | None = Field(default=None, ge=0)


class ClaimToChunk(_ContractBase):
    """Reviewable grounding map from a script claim to supporting chunks."""

    claim_id: str
    script_line_id: str
    chunk_ids: tuple[str, ...] = Field(min_length=1)


class MultimediaManifest(_ContractBase):
    """Replayable manifest for one asset revision."""

    asset_id: str
    revision_id: str
    route_policy: RoutePolicy
    prompts: tuple[PromptRecord, ...] = Field(default_factory=tuple)
    script_lines: tuple[ScriptLine, ...] = Field(default_factory=tuple)
    segments: tuple[MediaSegment, ...] = Field(default_factory=tuple)
    files: tuple[GeneratedFile, ...] = Field(default_factory=tuple)
    provider_calls: tuple[ProviderCall, ...] = Field(default_factory=tuple)
    cost_rows: tuple[CostRow, ...] = Field(default_factory=tuple)
    claim_to_chunk: tuple[ClaimToChunk, ...] = Field(default_factory=tuple)
    transcript_file_id: str | None = None
    captions_file_id: str | None = None

    @model_validator(mode="after")
    def references_resolve(self) -> MultimediaManifest:
        prompt_ids = {p.prompt_id for p in self.prompts}
        line_ids = {line.line_id for line in self.script_lines}
        file_ids = {file.file_id for file in self.files}
        call_ids = {call.call_id for call in self.provider_calls}

        for file in self.files:
            if file.prompt_id is not None and file.prompt_id not in prompt_ids:
                raise ValueError(f"file {file.file_id} references missing prompt_id")
        for call in self.provider_calls:
            if call.prompt_id is not None and call.prompt_id not in prompt_ids:
                raise ValueError(f"call {call.call_id} references missing prompt_id")
        for row in self.cost_rows:
            if row.call_id not in call_ids:
                raise ValueError(f"cost row {row.cost_id} references missing call_id")
        for segment in self.segments:
            missing_lines = set(segment.script_line_ids) - line_ids
            missing_files = set(segment.file_ids) - file_ids
            if missing_lines:
                raise ValueError(f"segment {segment.segment_id} references missing script lines")
            if missing_files:
                raise ValueError(f"segment {segment.segment_id} references missing files")
        for claim in self.claim_to_chunk:
            if claim.script_line_id not in line_ids:
                raise ValueError(f"claim {claim.claim_id} references missing script_line_id")
        for file_id in (self.transcript_file_id, self.captions_file_id):
            if file_id is not None and file_id not in file_ids:
                raise ValueError(f"manifest references missing file_id {file_id}")
        return self


class MultimediaAssetContract(_ContractBase):
    """Canonical graph-backed multimedia asset row plus revision manifest."""

    asset_id: str
    kind: AssetKind
    title: str
    user_prompt: str
    status: MultimediaStatus = MultimediaStatus.REQUESTED
    route_policy: RoutePolicy = "balanced"
    requested_duration_minutes: int = Field(ge=1, le=180)
    owner_user_id: str = "__operator__"
    investigation_id: str | None = None
    parent_asset_id: str | None = None
    revision_id: str
    parent_revision_id: str | None = None
    steering_event_id: str | None = None
    manifest: MultimediaManifest
    failure_reason: str | None = None

    @model_validator(mode="after")
    def revision_and_manifest_are_consistent(self) -> MultimediaAssetContract:
        if self.parent_revision_id and not self.steering_event_id:
            raise ValueError("revisions must link to a steering_event_id")
        if self.manifest.asset_id != self.asset_id:
            raise ValueError("manifest.asset_id must match asset_id")
        if self.manifest.revision_id != self.revision_id:
            raise ValueError("manifest.revision_id must match revision_id")
        if self.manifest.route_policy != self.route_policy:
            raise ValueError("manifest.route_policy must match route_policy")
        if self.status == MultimediaStatus.FAILED and not self.failure_reason:
            raise ValueError("failed assets require failure_reason")
        return self


def can_transition(from_status: MultimediaStatus | str, to_status: MultimediaStatus | str) -> bool:
    """Return whether a lifecycle transition is allowed by the contract."""

    src = MultimediaStatus(from_status)
    dst = MultimediaStatus(to_status)
    return dst in ALLOWED_STATUS_TRANSITIONS[src]


__all__ = [
    "ALLOWED_STATUS_TRANSITIONS",
    "AssetKind",
    "ClaimToChunk",
    "CostRow",
    "GeneratedFile",
    "MediaFileKind",
    "MediaSegment",
    "MultimediaAssetContract",
    "MultimediaManifest",
    "MultimediaStatus",
    "PromptRecord",
    "ProviderCall",
    "ProviderCallStatus",
    "RoutePolicy",
    "ScriptLine",
    "ScriptLineKind",
    "SourceCitation",
    "can_transition",
]
