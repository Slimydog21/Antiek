"""OutlineBlock contract — the Write composition primitive.

Owned by **Write SPR-01** (``substrate/write/outline_block.py``). A lego block
is a unit of meaning placed in an outline section. It either references an
insight/question/claim **graph node** (so it traces back to a source document
— the provenance moat) or is explicitly **user-originated**. There is no third
option: a block never carries a fabricated citation to a source it did not
come from.

The defining invariant — ``graph_node ⟺ node_id present`` — is restated here
as a model validator so the *contract itself* rejects an orphan-prose block
(a graph-provenance block without a node) or a fabricated citation (a
user-originated block carrying a node_id). The live implementation enforces
the same invariant at three layers (the module, the typed payload, the DB
CHECK constraint, per ``outline_block.py`` L34-39); this is the interface
mirror downstream builds against.

Field shapes verified against ``substrate/write/outline_block.py`` L76-93:
``block_kind`` ∈ 6 kinds, ``provenance_kind`` ∈ 4 kinds, ``_NODE_BACKED`` =
{graph_node}.
"""

from __future__ import annotations

from typing import Literal, Optional

from pydantic import BaseModel, ConfigDict, model_validator

BlockKind = Literal[
    "insight", "open_question", "operator_note", "claim",
    "user_authored", "synthesized",
]
# block_kind says *what* a block is; provenance_kind says *how it traces to
# truth*. They are orthogonal discriminators.
ProvenanceKind = Literal["graph_node", "user_authored", "synthesized", "brainstorm"]

# The single provenance kind that resolves to a graph node (and therefore
# requires a node_id). The complement is user-originated — a node_id there
# would be a fabricated citation. Mirrors ``outline_block._NODE_BACKED``.
NODE_BACKED_PROVENANCE: frozenset[str] = frozenset({"graph_node"})


class OutlineBlockContract(BaseModel):
    """A leaf composition unit in a deliverable outline. Either node-backed
    (traces node → document → chunks) or user-originated (content set,
    node_id null). The validator makes the no-orphan invariant part of the
    contract, not just the implementation."""

    model_config = ConfigDict(frozen=True, extra="forbid")

    outline_block_id: str
    section_id: str
    block_kind: BlockKind
    provenance_kind: ProvenanceKind
    # node-backed → node_id set, content null; user-originated → reversed.
    node_id: Optional[str] = None
    content: Optional[str] = None

    @model_validator(mode="after")
    def _no_orphan_prose(self) -> "OutlineBlockContract":
        """``graph_node ⟺ node_id present``. This is shape validation, not
        business logic — it is the contract's defining guarantee."""
        node_backed = self.provenance_kind in NODE_BACKED_PROVENANCE
        if node_backed and not self.node_id:
            raise ValueError(
                "graph_node provenance requires a node_id "
                "(no orphan-prose block traces to a source it lacks)"
            )
        if not node_backed and self.node_id:
            raise ValueError(
                f"{self.provenance_kind!r} provenance must not carry a node_id "
                "(a node_id on user-originated content is a fabricated citation)"
            )
        return self
