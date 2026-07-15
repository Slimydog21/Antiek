"""Owner-bound, receipt-verified playback for local AudibleRun publications."""

from __future__ import annotations

import hashlib
import math
from collections.abc import Callable
from dataclasses import dataclass
from pathlib import Path

from .audible_experience_receipt import AudibleExperienceReceipt
from .planner import MultimediaPlan
from .verified_playback import (
    MediaByteRange,
    UnsatisfiableMediaRange,
    VerifiedPlaybackError,
    _capture_verified_file,
    _parse_range,
    _read_stream_exact,
    _verified_size,
)


@dataclass(frozen=True)
class AudioLearnedClaimMetadata:
    chapter_id: str
    claim_text: str
    source_count: int
    follow_up_prompt: str
    line_id: str = ""
    evidence_sources: tuple[AudioEvidenceSourceMetadata, ...] = ()
    source_chunk_ids: tuple[str, ...] = ()
    evidence_status: str = "unavailable_legacy"


@dataclass(frozen=True)
class AudioEvidenceSourceMetadata:
    chunk_id: str
    document_id: str
    locator: str | None
    authority_kind: str
    chunk_sha256: str
    start_utf8_byte: int
    end_utf8_byte: int
    span_sha256: str
    exact_text: str


@dataclass(frozen=True)
class AudioChapterPlaybackMetadata:
    chapter_id: str
    title: str
    sequence: int
    start_offset_seconds: float
    end_offset_seconds: float


@dataclass(frozen=True)
class AudioPlaybackMetadata:
    asset_id: str
    revision_id: str
    receipt_sha256: str
    audio_sha256: str
    audio_size_bytes: int
    duration_seconds: float
    chapter_ids: tuple[str, ...]
    retention_marker_count: int
    learned_claim_count: int
    source_count: int
    learned_claims: tuple[AudioLearnedClaimMetadata, ...]
    chapters: tuple[AudioChapterPlaybackMetadata, ...] = ()


def validate_audio_chapters(
    chapters: tuple[AudioChapterPlaybackMetadata, ...],
    *,
    chapter_ids: tuple[str, ...],
    duration_seconds: float,
) -> tuple[AudioChapterPlaybackMetadata, ...]:
    """Validate one complete, ordered projection against its verified authority."""
    if not chapters or not math.isfinite(duration_seconds) or duration_seconds <= 0:
        raise VerifiedPlaybackError("audio chapter timeline is invalid")
    if tuple(row.chapter_id for row in chapters) != chapter_ids:
        raise VerifiedPlaybackError("audio chapter order conflicts")
    if len(set(chapter_ids)) != len(chapter_ids):
        raise VerifiedPlaybackError("audio chapter ids are duplicated")
    expected_start = 0.0
    for expected_sequence, chapter in enumerate(chapters):
        if (
            not chapter.chapter_id
            or not chapter.title
            or chapter.sequence != expected_sequence
            or not chapter.title.strip()
            or not math.isfinite(chapter.start_offset_seconds)
            or not math.isfinite(chapter.end_offset_seconds)
            or chapter.start_offset_seconds < 0
            or chapter.end_offset_seconds <= chapter.start_offset_seconds
            or abs(chapter.start_offset_seconds - expected_start) > 0.001
        ):
            raise VerifiedPlaybackError("audio chapter timeline is invalid")
        expected_start = chapter.end_offset_seconds
    if abs(expected_start - duration_seconds) > 0.001:
        raise VerifiedPlaybackError("audio chapter duration conflicts")
    return chapters


def project_audio_learned_claims(
    claims: tuple[object, ...],
    *,
    plan: MultimediaPlan,
) -> tuple[AudioLearnedClaimMetadata, ...]:
    """Cross-bind receipt claims to exact evidence carried by a trusted plan."""
    lines = {line.line_id: line for line in plan.script_lines}
    if len(lines) != len(plan.script_lines):
        raise VerifiedPlaybackError("audio claim evidence is invalid")
    projected: list[AudioLearnedClaimMetadata] = []
    seen_lines: set[str] = set()
    for claim in claims:
        line_id = getattr(claim, "line_id", None)
        chapter_id = getattr(claim, "chapter_id", None)
        claim_text = getattr(claim, "claim_text", None)
        source_chunk_ids = getattr(claim, "source_chunk_ids", None)
        follow_up_prompt = getattr(claim, "follow_up_prompt", None)
        if not isinstance(line_id, str):
            raise VerifiedPlaybackError("audio claim evidence conflicts")
        line = lines.get(line_id)
        if (
            line is None
            or line_id in seen_lines
            or not isinstance(chapter_id, str)
            or line_id.split("-line-", 1)[0] != chapter_id
            or line.kind != "factual"
            or line.text != claim_text
            or not isinstance(source_chunk_ids, tuple)
            or tuple(citation.chunk_id for citation in line.citations) != source_chunk_ids
            or not isinstance(follow_up_prompt, str)
            or not follow_up_prompt.strip()
            or line.evidence_derivation is None
            or len(line.evidence_derivation.spans) != 1
            or len(line.citations) != 1
        ):
            raise VerifiedPlaybackError("audio claim evidence conflicts")
        citation = line.citations[0]
        span = line.evidence_derivation.spans[0]
        exact_bytes = span.exact_text.encode("utf-8")
        if (
            span.chunk_id != citation.chunk_id
            or span.document_id != citation.document_id
            or span.chunk_sha256 != citation.quote_sha256
            or span.exact_text != claim_text
            or span.end_utf8_byte - span.start_utf8_byte != len(exact_bytes)
            or hashlib.sha256(exact_bytes).hexdigest() != span.span_sha256
            or hashlib.sha256(claim_text.encode("utf-8")).hexdigest()
            != line.evidence_derivation.output_sha256
        ):
            raise VerifiedPlaybackError("audio claim evidence conflicts")
        seen_lines.add(line_id)
        projected.append(
            AudioLearnedClaimMetadata(
                chapter_id=chapter_id,
                claim_text=claim_text,
                source_count=1,
                follow_up_prompt=follow_up_prompt,
                line_id=line_id,
                evidence_sources=(
                    AudioEvidenceSourceMetadata(
                        chunk_id=span.chunk_id,
                        document_id=span.document_id,
                        locator=citation.locator,
                        authority_kind=span.authority_kind,
                        chunk_sha256=span.chunk_sha256,
                        start_utf8_byte=span.start_utf8_byte,
                        end_utf8_byte=span.end_utf8_byte,
                        span_sha256=span.span_sha256,
                        exact_text=span.exact_text,
                    ),
                ),
                source_chunk_ids=source_chunk_ids,
                evidence_status="verified_exact",
            )
        )
    if len(projected) != len(claims):
        raise VerifiedPlaybackError("audio claim evidence is incomplete")
    return tuple(projected)


def project_legacy_audio_learned_claims(
    claims: tuple[object, ...], *, plan: MultimediaPlan
) -> tuple[AudioLearnedClaimMetadata, ...]:
    """Preserve valid pre-exact-extract receipts without claiming excerpt authority."""
    lines = {line.line_id: line for line in plan.script_lines}
    projected: list[AudioLearnedClaimMetadata] = []
    seen_lines: set[str] = set()
    for claim in claims:
        line_id = getattr(claim, "line_id", None)
        chapter_id = getattr(claim, "chapter_id", None)
        claim_text = getattr(claim, "claim_text", None)
        source_chunk_ids = getattr(claim, "source_chunk_ids", None)
        follow_up_prompt = getattr(claim, "follow_up_prompt", None)
        if not isinstance(line_id, str):
            raise VerifiedPlaybackError("legacy audio claim evidence conflicts")
        line = lines.get(line_id)
        if (
            line is None
            or line_id in seen_lines
            or not isinstance(chapter_id, str)
            or line_id.split("-line-", 1)[0] != chapter_id
            or line.kind != "factual"
            or line.text != claim_text
            or not isinstance(source_chunk_ids, tuple)
            or not source_chunk_ids
            or len(set(source_chunk_ids)) != len(source_chunk_ids)
            or tuple(citation.chunk_id for citation in line.citations) != source_chunk_ids
            or not isinstance(follow_up_prompt, str)
            or not follow_up_prompt.strip()
            or line.evidence_derivation is not None
        ):
            raise VerifiedPlaybackError("legacy audio claim evidence conflicts")
        seen_lines.add(line_id)
        projected.append(
            AudioLearnedClaimMetadata(
                chapter_id=chapter_id,
                claim_text=claim_text,
                source_count=len(source_chunk_ids),
                follow_up_prompt=follow_up_prompt,
                line_id=line_id,
                source_chunk_ids=source_chunk_ids,
                evidence_status="unavailable_legacy",
            )
        )
    return tuple(projected)


def project_audio_claims_for_plan(
    claims: tuple[object, ...], *, plan: MultimediaPlan
) -> tuple[AudioLearnedClaimMetadata, ...]:
    """Select one uniform evidence contract and reject malformed migration states."""
    lines = {line.line_id: line for line in plan.script_lines}
    if len(lines) != len(plan.script_lines):
        raise VerifiedPlaybackError("audio claim evidence is invalid")
    derivations: list[bool] = []
    for claim in claims:
        line_id = getattr(claim, "line_id", None)
        line = lines.get(line_id) if isinstance(line_id, str) else None
        if line is None:
            raise VerifiedPlaybackError("audio claim evidence conflicts")
        derivations.append(line.evidence_derivation is not None)
    if all(derivations):
        return project_audio_learned_claims(claims, plan=plan)
    if not any(derivations):
        return project_legacy_audio_learned_claims(claims, plan=plan)
    raise VerifiedPlaybackError("audio claim evidence is partially migrated")


@dataclass(frozen=True)
class VerifiedAudioPlaybackRuntime:
    receipt_path_resolver: Callable[[str, str], str | Path]
    receipt_key: bytes
    production_integrity_key: bytes

    def __post_init__(self) -> None:
        if (
            not callable(self.receipt_path_resolver)
            or not isinstance(self.receipt_key, bytes)
            or len(self.receipt_key) < 32
            or not isinstance(self.production_integrity_key, bytes)
            or len(self.production_integrity_key) < 32
        ):
            raise ValueError("audio playback configuration is invalid")

    def metadata(
        self,
        *,
        asset_id: str,
        revision_id: str,
        owner_digest: str,
        plan: MultimediaPlan | None = None,
    ) -> AudioPlaybackMetadata:
        receipt = self._receipt(asset_id, revision_id, owner_digest)
        production = receipt.production.manifest
        run = receipt.audible_run.manifest
        chapter_ids = tuple(chapter.chapter_id for chapter in run.chapters)
        chapters = validate_audio_chapters(
            tuple(
                AudioChapterPlaybackMetadata(
                    chapter_id=chapter.chapter_id,
                    title=chapter.title,
                    sequence=chapter.sequence,
                    start_offset_seconds=chapter.start_offset_seconds,
                    end_offset_seconds=chapter.end_offset_seconds,
                )
                for chapter in run.chapters
            ),
            chapter_ids=chapter_ids,
            duration_seconds=production.duration_seconds,
        )
        return AudioPlaybackMetadata(
            asset_id=asset_id,
            revision_id=revision_id,
            receipt_sha256=hashlib.sha256(receipt.to_json().encode("ascii")).hexdigest(),
            audio_sha256=production.output_sha256,
            audio_size_bytes=_verified_size(
                production.output_path, production.output_sha256
            ),
            duration_seconds=production.duration_seconds,
            chapter_ids=chapter_ids,
            retention_marker_count=len(run.retention_markers),
            learned_claim_count=len(run.learned_claims),
            source_count=len(
                {
                    source_id
                    for span in run.transcript_spans
                    for source_id in span.source_chunk_ids
                }
            ),
            learned_claims=(
                project_audio_claims_for_plan(run.learned_claims, plan=plan)
                if plan is not None
                else tuple(
                    AudioLearnedClaimMetadata(
                        chapter_id=claim.chapter_id,
                        claim_text=claim.claim_text,
                        source_count=len(claim.source_chunk_ids),
                        follow_up_prompt=claim.follow_up_prompt,
                        line_id=claim.line_id,
                        source_chunk_ids=claim.source_chunk_ids,
                    )
                    for claim in run.learned_claims
                )
            ),
            chapters=chapters,
        )

    def read(
        self,
        *,
        asset_id: str,
        revision_id: str,
        owner_digest: str,
        range_header: str | None,
    ) -> MediaByteRange:
        receipt = self._receipt(asset_id, revision_id, owner_digest)
        production = receipt.production.manifest
        receipt_sha256 = hashlib.sha256(receipt.to_json().encode("ascii")).hexdigest()
        snapshot, size = _capture_verified_file(
            production.output_path, production.output_sha256
        )
        close_snapshot = True
        try:
            start, end = _parse_range(range_header, size)
            if range_header is None and size > 8 * 1024 * 1024:
                payload = None
                stream = snapshot
                close_snapshot = False
            else:
                snapshot.seek(start)
                payload = _read_stream_exact(snapshot, end - start + 1)
                stream = None
        finally:
            if close_snapshot:
                snapshot.close()
        return MediaByteRange(
            payload=payload,
            stream=stream,
            start=start,
            end=end,
            total=size,
            sha256=production.output_sha256,
            receipt_sha256=receipt_sha256,
            media_type="audio/wav",
        )

    def _receipt(
        self, asset_id: str, revision_id: str, owner_digest: str
    ) -> AudibleExperienceReceipt:
        try:
            path = self.receipt_path_resolver(asset_id, revision_id)
            receipt = AudibleExperienceReceipt.reopen_from_file(
                path,
                signing_key=self.receipt_key,
                production_integrity_key=self.production_integrity_key,
            )
        except (OSError, ValueError, RuntimeError) as exc:
            raise VerifiedPlaybackError("verified audio playback is unavailable") from exc
        if (
            receipt.asset_id != asset_id
            or receipt.revision_id != revision_id
            or receipt.owner_digest != owner_digest
        ):
            raise VerifiedPlaybackError("verified audio playback identity conflicts")
        return receipt


__all__ = [
    "AudioPlaybackMetadata",
    "AudioChapterPlaybackMetadata",
    "AudioEvidenceSourceMetadata",
    "AudioLearnedClaimMetadata",
    "UnsatisfiableMediaRange",
    "VerifiedAudioPlaybackRuntime",
    "VerifiedPlaybackError",
    "validate_audio_chapters",
    "project_audio_learned_claims",
    "project_audio_claims_for_plan",
    "project_legacy_audio_learned_claims",
]
