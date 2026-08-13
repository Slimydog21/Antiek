"""Deterministic, lossless manifests for oversized twin sources."""

from __future__ import annotations

import hashlib
import json
import re
from dataclasses import asdict, dataclass

from substrate.twin_note_taker import MAX_CONTENT_CHARS, MIN_CONTENT_CHARS, AssetContent

SEGMENTATION_SCHEMA = "antiek.twin-segmentation.v1"
SEGMENTATION_ALGORITHM = "ordered-newline-v1"
TARGET_SEGMENT_CHARS = 180_000
_SHA256_RE = re.compile(r"[0-9a-f]{64}")


class TwinSegmentationError(ValueError):
    """The source cannot be represented by the pinned segmentation contract."""


def _canonical_json(value: object) -> str:
    return json.dumps(value, sort_keys=True, separators=(",", ":"), ensure_ascii=False)


def _sha(value: str) -> str:
    return hashlib.sha256(value.encode("utf-8")).hexdigest()


@dataclass(frozen=True)
class TwinSegment:
    index: int
    start_char: int
    end_char: int
    content_sha256: str

    @property
    def length(self) -> int:
        return self.end_char - self.start_char


@dataclass(frozen=True)
class TwinSegmentationManifest:
    schema: str
    algorithm: str
    account_id: str
    asset_id: str
    title_sha256: str
    content_class_sha256: str
    source_events_sha256: str
    body_sha256: str
    body_chars: int
    segments: tuple[TwinSegment, ...]
    parent_source_hash: str
    aggregate_obligation_id: str

    def to_json(self) -> str:
        return _canonical_json(asdict(self))

    @classmethod
    def from_json(cls, value: str) -> TwinSegmentationManifest:
        try:
            raw = json.loads(value)
            raw["segments"] = tuple(TwinSegment(**item) for item in raw["segments"])
            manifest = cls(**raw)
        except (KeyError, TypeError, ValueError, json.JSONDecodeError) as exc:
            raise TwinSegmentationError("segmentation manifest is malformed") from exc
        if manifest.to_json() != value:
            raise TwinSegmentationError("segmentation manifest is not canonical")
        if manifest.schema != SEGMENTATION_SCHEMA or manifest.algorithm != SEGMENTATION_ALGORITHM:
            raise TwinSegmentationError("segmentation manifest has unsupported semantics")
        commitments = (
            manifest.title_sha256,
            manifest.content_class_sha256,
            manifest.source_events_sha256,
            manifest.body_sha256,
            *(segment.content_sha256 for segment in manifest.segments),
        )
        if any(not _SHA256_RE.fullmatch(value) for value in commitments):
            raise TwinSegmentationError("segmentation manifest has malformed commitments")
        if not manifest.segments or manifest.body_chars <= MAX_CONTENT_CHARS:
            raise TwinSegmentationError(
                "segmentation manifest does not describe an oversized source"
            )
        cursor = 0
        for index, segment in enumerate(manifest.segments):
            if (
                segment.index != index
                or segment.start_char != cursor
                or not 0 < segment.length <= MAX_CONTENT_CHARS
            ):
                raise TwinSegmentationError("segmentation manifest ranges are invalid")
            cursor = segment.end_char
        if cursor != manifest.body_chars:
            raise TwinSegmentationError("segmentation manifest coverage is incomplete")
        expected_parent = _parent_hash_from_commitments(
            manifest.account_id,
            manifest.asset_id,
            manifest.title_sha256,
            manifest.content_class_sha256,
            manifest.source_events_sha256,
            manifest.body_sha256,
        )
        if manifest.parent_source_hash != expected_parent:
            raise TwinSegmentationError("segmentation parent identity is invalid")
        if manifest.aggregate_obligation_id != _aggregate_id(
            manifest.account_id, manifest.asset_id, expected_parent
        ):
            raise TwinSegmentationError("segmentation aggregate identity is invalid")
        return manifest

    @property
    def manifest_hash(self) -> str:
        return _sha(self.to_json())


def _parent_hash_from_commitments(
    account_id: str,
    asset_id: str,
    title_sha256: str,
    content_class_sha256: str,
    source_events_sha256: str,
    body_sha256: str,
) -> str:
    commitment = {
        "account_id": account_id,
        "asset_id": asset_id,
        "body_sha256": body_sha256,
        "content_class_sha256": content_class_sha256,
        "source_events_sha256": source_events_sha256,
        "title_sha256": title_sha256,
    }
    return _sha(_canonical_json(commitment))


def _aggregate_id(account_id: str, asset_id: str, parent_hash: str) -> str:
    material = _canonical_json(
        [SEGMENTATION_SCHEMA, SEGMENTATION_ALGORITHM, account_id, asset_id, parent_hash]
    )
    return "aggregate_" + _sha(material)


def _segment_end(body: str, start: int) -> int:
    hard_end = min(start + MAX_CONTENT_CHARS, len(body))
    if hard_end == len(body):
        return hard_end
    target_end = min(start + TARGET_SEGMENT_CHARS, hard_end)
    newline = body.rfind("\n", start + MIN_CONTENT_CHARS, target_end + 1)
    return newline + 1 if newline >= 0 else target_end


def build_segmentation_manifest(
    *, account_id: str, asset: AssetContent
) -> TwinSegmentationManifest:
    """Commit an oversized exact source to stable, contiguous character ranges."""
    if not account_id:
        raise TwinSegmentationError("account_id is required")
    if len(asset.content_text) <= MAX_CONTENT_CHARS:
        raise TwinSegmentationError("segmentation requires an oversized source")
    if len(asset.content_text.strip()) < MIN_CONTENT_CHARS:
        raise TwinSegmentationError("oversized source has no substantive content")
    ranges: list[tuple[int, int]] = []
    start = 0
    while start < len(asset.content_text):
        end = _segment_end(asset.content_text, start)
        if end <= start or end - start > MAX_CONTENT_CHARS:
            raise TwinSegmentationError("segmentation algorithm made an invalid range")
        ranges.append((start, end))
        start = end
    if len(ranges) > 1 and len(asset.content_text[ranges[-1][0] :].strip()) < MIN_CONTENT_CHARS:
        previous_start, previous_end = ranges[-2]
        final_end = ranges[-1][1]
        candidate = max(previous_start + MIN_CONTENT_CHARS, previous_end - MIN_CONTENT_CHARS)
        if (
            final_end - candidate > MAX_CONTENT_CHARS
            or len(asset.content_text[previous_start:candidate].strip()) < MIN_CONTENT_CHARS
            or len(asset.content_text[candidate:final_end].strip()) < MIN_CONTENT_CHARS
        ):
            raise TwinSegmentationError("source cannot form substantive bounded segments")
        ranges[-2:] = [(previous_start, candidate), (candidate, final_end)]
    if any(len(asset.content_text[start:end].strip()) < MIN_CONTENT_CHARS for start, end in ranges):
        raise TwinSegmentationError("source cannot form substantive bounded segments")
    segments = tuple(
        TwinSegment(index, start, end, _sha(asset.content_text[start:end]))
        for index, (start, end) in enumerate(ranges)
    )
    title_sha = _sha(asset.title)
    class_sha = _sha(asset.content_class)
    events_sha = _sha(_canonical_json(asset.source_event_ids))
    body_sha = _sha(asset.content_text)
    parent_hash = _parent_hash_from_commitments(
        account_id, asset.asset_id, title_sha, class_sha, events_sha, body_sha
    )
    return TwinSegmentationManifest(
        schema=SEGMENTATION_SCHEMA,
        algorithm=SEGMENTATION_ALGORITHM,
        account_id=account_id,
        asset_id=asset.asset_id,
        title_sha256=title_sha,
        content_class_sha256=class_sha,
        source_events_sha256=events_sha,
        body_sha256=body_sha,
        body_chars=len(asset.content_text),
        segments=segments,
        parent_source_hash=parent_hash,
        aggregate_obligation_id=_aggregate_id(account_id, asset.asset_id, parent_hash),
    )


def verify_segmentation_manifest(
    manifest: TwinSegmentationManifest, *, account_id: str, asset: AssetContent
) -> None:
    """Re-derive from exact bytes; persisted commitments alone are never source authority."""
    expected = build_segmentation_manifest(account_id=account_id, asset=asset)
    if manifest != expected:
        raise TwinSegmentationError("source bytes conflict with segmentation manifest")


__all__ = [
    "SEGMENTATION_ALGORITHM",
    "SEGMENTATION_SCHEMA",
    "TARGET_SEGMENT_CHARS",
    "TwinSegment",
    "TwinSegmentationError",
    "TwinSegmentationManifest",
    "build_segmentation_manifest",
    "verify_segmentation_manifest",
]
