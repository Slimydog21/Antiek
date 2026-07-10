"""Deterministic candidate blinding and order swap for judge evidence.

Creates opaque A/B labels with salted content hashes.  Provider and model
identities live in a private join map that never enters the judge request or
the evidence journal.  Candidate order is a first-class field: the caller
creates two passes with swapped order to measure position bias.
"""

from __future__ import annotations

import hashlib
import json
from dataclasses import dataclass, field
from typing import Any


def _content_hash(content: str, salt: str) -> str:
    """SHA-256 of salted content; salt is discarded after hashing."""
    material = json.dumps([salt, content], separators=(",", ":"))
    return "sha256:" + hashlib.sha256(material.encode()).hexdigest()


@dataclass(frozen=True)
class BlindedCandidate:
    """One candidate body labeled only by its position."""

    blinded_id: str
    content_hash: str
    content: str

    def __post_init__(self) -> None:
        if self.blinded_id not in {"A", "B"}:
            raise ValueError("blinded_id must be A or B")
        if not self.content_hash.startswith("sha256:"):
            raise ValueError("content_hash must be a SHA-256 reference")

    @property
    def content_binding(self) -> str:
        """Bind the supplied body to its salted hash, even for manual instances."""
        material = json.dumps([self.content_hash, self.content], separators=(",", ":"))
        return "sha256:" + hashlib.sha256(material.encode()).hexdigest()


@dataclass(frozen=True)
class BlindedJudgeRequest:
    """Judge input with blinded candidates, rubric, and task context.

    Provider/model IDs never appear here.  The join map in BlindingContext
    maps blinded_id → physical identity; it is never serialized into the
    journal or sent to the judge.
    """

    task_class: str
    item_id: str
    task_context: str
    candidates: tuple[BlindedCandidate, BlindedCandidate]
    rubric_version: str

    def __post_init__(self) -> None:
        if len(self.candidates) != 2:
            raise ValueError("exactly two candidates required")
        ids = {c.blinded_id for c in self.candidates}
        if len(ids) != 2:
            raise ValueError("candidate blinded_ids must be distinct")
        if not self.task_class.strip():
            raise ValueError("task_class must not be blank")
        if not self.item_id.strip():
            raise ValueError("item_id must not be blank")
        if not self.task_context.strip():
            raise ValueError("task_context must not be blank")
        if not self.rubric_version.strip():
            raise ValueError("rubric_version must not be blank")

    def to_dict(self) -> dict[str, Any]:
        """Serialize without identity leakage; deterministic key order."""
        return {
            "task_class": self.task_class,
            "item_id": self.item_id,
            "task_context": self.task_context,
            "candidates": [
                {
                    "blinded_id": c.blinded_id,
                    "content_hash": c.content_hash,
                    "content": c.content,
                }
                for c in self.candidates
            ],
            "rubric_version": self.rubric_version,
        }


def blind_candidates(
    content_a: str,
    content_b: str,
    *,
    salt: str,
    order: tuple[str, str] = ("A", "B"),
) -> tuple[BlindedCandidate, BlindedCandidate]:
    """Create two blinded candidates in the specified order.

    The salt is used for hashing and not stored.  ``order`` controls which
    content maps to which label; swapping order produces a distinct judge
    request for position-bias measurement.
    """
    if set(order) != {"A", "B"}:
        raise ValueError("order must contain the two distinct labels A and B")
    if not salt:
        raise ValueError("salt must not be blank")
    contents = {"A": content_a, "B": content_b}
    positions = ("A", "B")
    cands = tuple(
        BlindedCandidate(
            blinded_id=position,
            content_hash=_content_hash(contents[source], salt),
            content=contents[source],
        )
        for position, source in zip(positions, order, strict=True)
    )
    return cands[0], cands[1]


@dataclass
class BlindingContext:
    """Private join map: blinded_id → physical identity.  Never serialized."""

    join_map: dict[str, dict[str, str]] = field(default_factory=dict)

    def register(self, blinded_id: str, provider: str, model: str) -> None:
        self.join_map[blinded_id] = {"provider": provider, "model": model}

    def lookup(self, blinded_id: str) -> dict[str, str] | None:
        identity = self.join_map.get(blinded_id)
        return dict(identity) if identity is not None else None
