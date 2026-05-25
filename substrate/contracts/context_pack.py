"""Context-pack contract — assembled-context shape (DRW SPR-04).

Owned by **DRW SPR-04** (``substrate/context_pack/``, which is live —
``ContextPack`` / ``AssembledLayer`` / ``LayerKind`` ship today). Read cites
this layer when it spins research from a reading session. The contract mirrors
the *assembled* shape a consumer reads, not the assembler's internals (token
counters, truncation strategy) — those stay DRW's.

This is a COMMITTED contract: the implementation exists, so the shape is
pinned, not provisional.
"""

from __future__ import annotations

from typing import Literal

from pydantic import BaseModel, ConfigDict

# Mirrors ``substrate.context_pack.LayerKind`` ordering intent — the canonical
# render order is owned by the assembler; the contract restates the kinds a
# consumer may encounter.
LayerKindName = Literal[
    "instruction", "claim", "insight", "question", "source", "history", "scratch"
]


class AssembledLayerContract(BaseModel):
    """One rendered layer of an assembled context pack: its kind, the source
    that produced it, and whether it was truncated to fit the budget."""

    model_config = ConfigDict(frozen=True, extra="forbid")

    kind: LayerKindName
    source: str
    tokens: int
    truncated: bool = False


class ContextPackContract(BaseModel):
    """The assembled context handed to a dispatch call: ordered layers within
    a token budget. A consumer reads ``layers`` + ``total_tokens``; it does not
    re-run assembly."""

    model_config = ConfigDict(frozen=True, extra="forbid")

    layers: tuple[AssembledLayerContract, ...]
    total_tokens: int
    budget_tokens: int
