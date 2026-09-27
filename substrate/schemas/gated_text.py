"""GatedText: the one shape of every rights-bearing text a route returns.

THREAD-CONTRACT §1.2 (rev 6, origin rev 8.2, ``unsourced`` rev 8.8) and §2.10,
signed rev 8.10. It binds as ``excerpt``, ``answer``, ``context[]``,
``content`` and ``insert``. LB-3, W2 and every later consumer import these
types; nobody redefines them.

The shape is discriminated, and the validators hold it exactly as signed:

- ``served``: ``text`` is set and ``reason`` is null;
- ``cite_only``: ``text`` is null and ``reason`` is ``unresolved`` or
  ``not_servable``. A citation stands in for the words;
- ``withheld``: ``text`` is null and ``reason`` is any of the three. Nothing
  stands in for the words.

Each ``SourceRef`` carries its own ``gate`` and ``reason`` under the same
discipline. A ref is a pointer, so it never carries text. Two further rules
follow from "nothing stands in" and are enforced here:

- a ``withheld`` ref is opaque: it names neither the document nor the passage
  (LB-9 D7, where the owner overlay drops both);
- an ``anchor`` points into the ref's own ``document_id``.

``SourceAnchor`` is the pointer part of the §1.4 ``BranchAnchor``:
``document_id``, ``source_locator``, ``region_id`` and ``page_index``. It
leaves out ``quote``, ``prefix`` and ``suffix``, which are words, so a
cite-only or withheld ref cannot carry them. Every ``SourceAnchor`` is a valid
``BranchAnchor``; ``BranchAnchor`` itself ships with the wave-5 export branch
(event schema v41), which is not on main.
"""

from __future__ import annotations

import re
from collections.abc import Iterable
from typing import Literal, get_args

from pydantic import BaseModel, ConfigDict, Field, model_validator

Gate = Literal["served", "cite_only", "withheld"]
GateReason = Literal["unresolved", "not_servable", "lineage_unreconciled"]
TextOrigin = Literal["source", "operator", "generated", "unsourced"]

GATES: tuple[Gate, ...] = get_args(Gate)
GATE_REASONS: tuple[GateReason, ...] = get_args(GateReason)
TEXT_ORIGINS: tuple[TextOrigin, ...] = get_args(TextOrigin)

#: The reasons a citation can stand in for (``cite_only``). A thread whose
#: history is not reconciled has no citation that stands in for it.
CITE_ONLY_REASONS: frozenset[GateReason] = frozenset({"unresolved", "not_servable"})

#: Mixed sources (§1.2 rev 6): the most restrictive gate wins, and among the
#: parts at that gate the reason earliest in this order wins.
GATE_ORDER: tuple[Gate, ...] = ("withheld", "cite_only", "served")
REASON_PRECEDENCE: tuple[GateReason, ...] = ("lineage_unreconciled", "unresolved", "not_servable")

_SHA256 = re.compile(r"[0-9a-f]{64}")


def _check_gate_reason(gate: Gate, reason: GateReason | None, owner: str) -> None:
    if gate == "served" and reason is not None:
        raise ValueError(f"{owner}: a served gate carries no reason")
    if gate == "cite_only" and reason not in CITE_ONLY_REASONS:
        raise ValueError(
            f"{owner}: a cite_only gate needs reason unresolved or not_servable, not {reason!r}"
        )
    if gate == "withheld" and reason is None:
        raise ValueError(f"{owner}: a withheld gate needs a reason")


class _GatedModel(BaseModel):
    """Frozen, and ``extra='forbid'`` as the typed payloads are
    (``substrate.schemas.events._PayloadBase``): a stray field such as a
    title is refused rather than carried to a client."""

    model_config = ConfigDict(extra="forbid", frozen=True)


class SourceTextLocator(_GatedModel):
    """A character span of the document's canonical text, keyed to that
    text's hash (the §1.4 ``source_locator``)."""

    start: int = Field(ge=0)
    end: int = Field(ge=0)
    text_sha256: str

    @model_validator(mode="after")
    def _span(self) -> SourceTextLocator:
        if self.end <= self.start:
            raise ValueError("source_locator: end must be greater than start")
        if not _SHA256.fullmatch(self.text_sha256):
            raise ValueError("source_locator: text_sha256 must be 64 lowercase hex digits")
        return self


class SourceAnchor(_GatedModel):
    """Where in ``document_id`` a source ref points; pointer fields only."""

    document_id: str = Field(min_length=1)
    source_locator: SourceTextLocator | None = None
    region_id: str | None = None
    page_index: int | None = Field(default=None, ge=0)


class SourceRef(_GatedModel):
    """One pointer a text came from (an event, chunk, edge, node or
    synthesis pin), with the document it resolves to when it resolves, and
    its own gate. The operator sees from these which source held a text
    back (§2.10)."""

    kind: str = Field(min_length=1)
    id: str = Field(min_length=1)
    document_id: str | None = None
    anchor: SourceAnchor | None = None
    gate: Gate
    reason: GateReason | None = None

    @model_validator(mode="after")
    def _discriminated(self) -> SourceRef:
        _check_gate_reason(self.gate, self.reason, "source_ref")
        if self.gate == "withheld" and (self.document_id is not None or self.anchor is not None):
            raise ValueError(
                "source_ref: a withheld ref is opaque; it carries no document_id or anchor"
            )
        if self.anchor is not None and self.anchor.document_id != self.document_id:
            raise ValueError("source_ref: the anchor must point into the ref's own document_id")
        return self


class GatedText(_GatedModel):
    """A rights-bearing text and the gate that decided whether it is shown."""

    text: str | None = None
    gate: Gate
    reason: GateReason | None = None
    origin: TextOrigin
    source_refs: list[SourceRef] = Field(default_factory=list)

    @model_validator(mode="after")
    def _discriminated(self) -> GatedText:
        _check_gate_reason(self.gate, self.reason, "gated_text")
        if self.gate == "served" and self.text is None:
            raise ValueError("gated_text: a served gate needs text")
        if self.gate != "served" and self.text is not None:
            raise ValueError(f"gated_text: a {self.gate} gate carries no text")
        return self


def most_restrictive(
    parts: Iterable[tuple[Gate, GateReason | None]],
) -> tuple[Gate, GateReason | None]:
    """The gate and reason of a text drawn from several parts (§1.2 rev 6):
    ``withheld`` over ``cite_only`` over ``served``; among the parts at the
    winning gate, ``lineage_unreconciled`` over ``unresolved`` over
    ``not_servable``. No parts is no evidence, which the caller decides, so
    it is refused rather than read as served."""
    collected = list(parts)
    if not collected:
        raise ValueError("most_restrictive: no parts to combine")
    gate = min((g for g, _ in collected), key=GATE_ORDER.index)
    if gate == "served":
        return "served", None
    reasons = [r for g, r in collected if g == gate and r is not None]
    if not reasons:
        raise ValueError(f"most_restrictive: a {gate} part has no reason")
    return gate, min(reasons, key=REASON_PRECEDENCE.index)


__all__ = [
    "CITE_ONLY_REASONS",
    "GATES",
    "GATE_ORDER",
    "GATE_REASONS",
    "REASON_PRECEDENCE",
    "TEXT_ORIGINS",
    "Gate",
    "GateReason",
    "GatedText",
    "SourceAnchor",
    "SourceRef",
    "SourceTextLocator",
    "TextOrigin",
    "most_restrictive",
]
