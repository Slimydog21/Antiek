"""Deterministic, lossless manifests for oversized twin sources."""

from __future__ import annotations

import hashlib
import json
from dataclasses import asdict, dataclass

from substrate.twin_note_taker import MAX_CONTENT_CHARS, MIN_CONTENT_CHARS, AssetContent

SEGMENTATION_SCHEMA = "antiek.twin-segmentation.v1"
SEGMENTATION_ALGORITHM = "ordered-newline-v1"
TARGET_SEGMENT_CHARS = 180_000


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
        return manifest

    @property
    def manifest_hash(self) -> str:
        return _sha(self.to_json())


def _parent_source_hash(account_id: str, asset: AssetContent) -> str:
    commitment = {
        "account_id": account_id,
        "asset_id": asset.asset_id,
        "body_sha256": _sha(asset.content_text),
        "content_class_sha256": _sha(asset.content_class),
        "source_events_sha256": _sha(_canonical_json(asset.source_event_ids)),
        "title_sha256": _sha(asset.title),
    }
    return _sha(_canonical_json(commitment))


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
    segments: list[TwinSegment] = []
    start = 0
    while start < len(asset.content_text):
        end = _segment_end(asset.content_text, start)
        if end <= start or end - start > MAX_CONTENT_CHARS:
            raise TwinSegmentationError("segmentation algorithm made an invalid range")
        segments.append(TwinSegment(len(segments), start, end, _sha(asset.content_text[start:end])))
        start = end
    parent_hash = _parent_source_hash(account_id, asset)
    obligation_material = _canonical_json(
        [SEGMENTATION_SCHEMA, SEGMENTATION_ALGORITHM, account_id, asset.asset_id, parent_hash]
    )
    return TwinSegmentationManifest(
        schema=SEGMENTATION_SCHEMA,
        algorithm=SEGMENTATION_ALGORITHM,
        account_id=account_id,
        asset_id=asset.asset_id,
        title_sha256=_sha(asset.title),
        content_class_sha256=_sha(asset.content_class),
        source_events_sha256=_sha(_canonical_json(asset.source_event_ids)),
        body_sha256=_sha(asset.content_text),
        body_chars=len(asset.content_text),
        segments=tuple(segments),
        parent_source_hash=parent_hash,
        aggregate_obligation_id="aggregate_" + _sha(obligation_material),
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
