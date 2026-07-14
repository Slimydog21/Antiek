"""Receipt-verified playback for authorized paid narration."""

from __future__ import annotations

import hashlib
from dataclasses import dataclass

from .paid_audio_receipt import PaidAudioReceipt, paid_audio_receipt_path
from .verified_audio_playback import (
    AudioChapterPlaybackMetadata,
    AudioLearnedClaimMetadata,
    AudioPlaybackMetadata,
    validate_audio_chapters,
)
from .verified_playback import (
    MediaByteRange,
    VerifiedPlaybackError,
    _capture_verified_file,
    _parse_range,
    _read_stream_exact,
    _verified_size,
)


@dataclass(frozen=True, repr=False)
class VerifiedPaidAudioPlaybackRuntime:
    receipt_root: str
    receipt_key: bytes
    narration_key: bytes

    def _receipt(self, asset_id: str, revision_id: str, owner_digest: str) -> PaidAudioReceipt:
        try:
            receipt = PaidAudioReceipt.reopen_from_file(
                paid_audio_receipt_path(self.receipt_root, asset_id, revision_id),
                receipt_key=self.receipt_key,
                narration_key=self.narration_key,
            )
        except (OSError, ValueError, RuntimeError) as exc:
            raise VerifiedPlaybackError("verified paid audio playback is unavailable") from exc
        if (
            receipt.asset_id != asset_id
            or receipt.revision_id != revision_id
            or receipt.owner_digest != owner_digest
        ):
            raise VerifiedPlaybackError("verified paid audio playback identity conflicts")
        return receipt

    def metadata(self, *, asset_id: str, revision_id: str, owner_digest: str) -> AudioPlaybackMetadata:
        receipt = self._receipt(asset_id, revision_id, owner_digest)
        manifest = receipt.narration.manifest
        chapter_ids = tuple(row.chapter_id for row in receipt.chapters)
        titles = {row.chapter_id: row.title for row in receipt.transformed_plan.chapters}
        start = 0.0
        projected: list[AudioChapterPlaybackMetadata] = []
        for sequence, source in enumerate(manifest.sources):
            end = round(start + source.duration_seconds, 3)
            projected.append(
                AudioChapterPlaybackMetadata(
                    chapter_id=source.chapter_id,
                    title=titles[source.chapter_id],
                    sequence=sequence,
                    start_offset_seconds=start,
                    end_offset_seconds=end,
                )
            )
            start = end
        chapters = validate_audio_chapters(
            tuple(projected),
            chapter_ids=chapter_ids,
            duration_seconds=manifest.duration_seconds,
        )
        return AudioPlaybackMetadata(
            asset_id=asset_id,
            revision_id=revision_id,
            receipt_sha256=hashlib.sha256(receipt.to_json().encode("ascii")).hexdigest(),
            audio_sha256=manifest.output_sha256,
            audio_size_bytes=_verified_size(manifest.output_path, manifest.output_sha256),
            duration_seconds=manifest.duration_seconds,
            chapter_ids=chapter_ids,
            retention_marker_count=len(receipt.retention_markers),
            learned_claim_count=len(receipt.learned_claims),
            source_count=len(receipt.source_chunk_ids),
            learned_claims=tuple(
                AudioLearnedClaimMetadata(
                    chapter_id=row.chapter_id,
                    claim_text=row.claim_text,
                    source_count=len(row.source_chunk_ids),
                    follow_up_prompt=row.follow_up_prompt,
                )
                for row in receipt.learned_claims
            ),
            chapters=chapters,
        )

    def read(
        self, *, asset_id: str, revision_id: str, owner_digest: str, range_header: str | None
    ) -> MediaByteRange:
        receipt = self._receipt(asset_id, revision_id, owner_digest)
        manifest = receipt.narration.manifest
        snapshot, size = _capture_verified_file(manifest.output_path, manifest.output_sha256)
        close = True
        try:
            start, end = _parse_range(range_header, size)
            if range_header is None and size > 8 * 1024 * 1024:
                payload, stream, close = None, snapshot, False
            else:
                snapshot.seek(start)
                payload = _read_stream_exact(snapshot, end - start + 1)
                stream = None
        finally:
            if close:
                snapshot.close()
        return MediaByteRange(
            payload=payload,
            stream=stream,
            start=start,
            end=end,
            total=size,
            sha256=manifest.output_sha256,
            receipt_sha256=hashlib.sha256(receipt.to_json().encode("ascii")).hexdigest(),
            media_type="audio/wav",
        )


__all__ = ["VerifiedPaidAudioPlaybackRuntime"]
