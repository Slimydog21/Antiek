"""Owner-bound, receipt-verified playback for local AudibleRun publications."""

from __future__ import annotations

import hashlib
from collections.abc import Callable
from dataclasses import dataclass
from pathlib import Path

from .audible_experience_receipt import AudibleExperienceReceipt
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
        self, *, asset_id: str, revision_id: str, owner_digest: str
    ) -> AudioPlaybackMetadata:
        receipt = self._receipt(asset_id, revision_id, owner_digest)
        production = receipt.production.manifest
        run = receipt.audible_run.manifest
        return AudioPlaybackMetadata(
            asset_id=asset_id,
            revision_id=revision_id,
            receipt_sha256=hashlib.sha256(receipt.to_json().encode("ascii")).hexdigest(),
            audio_sha256=production.output_sha256,
            audio_size_bytes=_verified_size(
                production.output_path, production.output_sha256
            ),
            duration_seconds=production.duration_seconds,
            chapter_ids=tuple(chapter.chapter_id for chapter in run.chapters),
            retention_marker_count=len(run.retention_markers),
            learned_claim_count=len(run.learned_claims),
            source_count=len(
                {
                    source_id
                    for span in run.transcript_spans
                    for source_id in span.source_chunk_ids
                }
            ),
            learned_claims=tuple(
                AudioLearnedClaimMetadata(
                    chapter_id=claim.chapter_id,
                    claim_text=claim.claim_text,
                    source_count=len(claim.source_chunk_ids),
                    follow_up_prompt=claim.follow_up_prompt,
                )
                for claim in run.learned_claims
            ),
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
    "AudioLearnedClaimMetadata",
    "UnsatisfiableMediaRange",
    "VerifiedAudioPlaybackRuntime",
    "VerifiedPlaybackError",
]
