"""Versioned human-anchor calibration derived from judge evidence."""

from __future__ import annotations

from collections import defaultdict
from collections.abc import Iterable
from dataclasses import dataclass

from .journal import EvidenceRecord

ANCHOR_SCHEMA_VERSION = 1


@dataclass(frozen=True)
class AnchorItem:
    item_id_hash: str
    rubric_version: str
    candidate_hashes: tuple[str, str]
    scores: tuple[tuple[str, int], ...]


@dataclass(frozen=True)
class AnchorSet:
    version: str
    source: str
    reverser: str
    items: tuple[AnchorItem, ...]
    schema_version: int = ANCHOR_SCHEMA_VERSION

    def __post_init__(self) -> None:
        if self.schema_version != ANCHOR_SCHEMA_VERSION:
            raise ValueError("unsupported anchor schema version")
        if not self.version.strip() or not self.source.strip() or not self.reverser.strip():
            raise ValueError("anchor version, source, and reverser are required")
        keys = {
            (item.item_id_hash, item.rubric_version, tuple(sorted(item.candidate_hashes)))
            for item in self.items
        }
        if len(keys) != len(self.items):
            raise ValueError("anchor items must be unique within a version")
        for item in self.items:
            if len(item.candidate_hashes) != 2 or item.candidate_hashes != tuple(
                sorted(item.candidate_hashes)
            ):
                raise ValueError("anchor candidate hashes must be a canonical pair")
            values = dict(item.scores)
            if len(values) != len(item.scores) or not values:
                raise ValueError("anchor axes must be non-empty and unique")
            if any(
                not isinstance(score, int)
                or isinstance(score, bool)
                or not 1 <= score <= 5
                for score in values.values()
            ):
                raise ValueError("anchor scores must be integers from 1 through 5")


@dataclass(frozen=True)
class AnchorCalibration:
    evidence_ids: tuple[str, ...]
    calibrated: bool
    anchor_version: str | None
    signed_axis_errors: tuple[tuple[str, float], ...]
    matched_anchor_count: int
    evidence_sample_size: int
    missing_anchor_count: int


def calibrate_against_anchors(
    records: Iterable[EvidenceRecord], anchors: AnchorSet | None
) -> AnchorCalibration:
    """Calculate judge-minus-human signed error; candidate means are untouched."""
    rows = tuple(records)
    if anchors is None or not anchors.items:
        return AnchorCalibration(
            tuple(sorted(row.evidence_id for row in rows)), False, None, (), 0, 0, 0
        )
    by_key = {
        (item.item_id_hash, item.rubric_version, item.candidate_hashes): item
        for item in anchors.items
    }
    errors: dict[str, list[int]] = defaultdict(list)
    matched: set[tuple[str, str, tuple[str, str]]] = set()
    for row in rows:
        if row.status != "ok":
            continue
        ordered = sorted(row.candidate_hashes)
        canonical_pair = (ordered[0], ordered[1])
        key = (row.item_id_hash, row.rubric_version, canonical_pair)
        anchor = by_key.get(key)
        if anchor is None:
            continue
        reversed_order = row.candidate_hashes != canonical_pair
        observed = {
            axis: 6 - score if reversed_order else score for axis, score in row.scores
        }
        expected = dict(anchor.scores)
        if observed.keys() != expected.keys():
            raise ValueError("anchor axis set does not match evidence")
        matched.add(key)
        for axis, score in observed.items():
            errors[axis].append(score - expected[axis])
    signed = tuple(
        (axis, sum(values) / len(values)) for axis, values in sorted(errors.items())
    )
    return AnchorCalibration(
        evidence_ids=tuple(sorted(row.evidence_id for row in rows)),
        calibrated=bool(matched) and len(matched) == len(anchors.items),
        anchor_version=anchors.version,
        signed_axis_errors=signed,
        matched_anchor_count=len(matched),
        evidence_sample_size=sum(len(values) for values in errors.values()) // max(len(errors), 1),
        missing_anchor_count=len(anchors.items) - len(matched),
    )
