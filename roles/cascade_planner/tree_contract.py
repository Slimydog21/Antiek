"""DRW SPR-05 M3 + M6 — the editable sub-question tree contract.

The cascade planner's output is a *tree the user edits and approves before
anything launches* — the glass-box control that is the product's whole
differentiator. This module is the typed data contract the frontend
(SPR-09) renders and edits, plus the approval state machine SPR-06 checks
before launching.

The contract round-trips: ``to_dict``/``from_dict`` is the wire shape the
frontend reads and writes, and ``persist`` (separate module) maps it onto
SPR-01 question nodes + ``decomposes_into`` edges so the tree is reloadable.

Approval state machine (documented for the maintainer who asks "why was
this plan launchable?"):

    draft ──approve──▶ approved ──edit──▶ draft (re-opened)
      ▲                                     │
      └─────────────── edit ────────────────┘

An edit to an approved plan **re-opens the gate** — re-approval is required.
``is_launchable`` is True only in ``approved``.
"""

from __future__ import annotations

import uuid
from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Any, Dict, List, Optional


def _new_local_id() -> str:
    return "pn-" + uuid.uuid4().hex[:12]


def _now() -> str:
    return datetime.now(timezone.utc).isoformat().replace("+00:00", "Z")


@dataclass
class PlanNode:
    """One node in the editable plan tree. ``graph_node_id`` is None until
    persisted, then carries the SPR-01 question node id."""

    question: str
    rationale: str = ""
    focus_boundary: str = ""
    budget_usd: Optional[float] = None
    max_depth: Optional[int] = None
    children: List["PlanNode"] = field(default_factory=list)
    local_id: str = field(default_factory=_new_local_id)
    graph_node_id: Optional[str] = None

    @property
    def is_leaf(self) -> bool:
        return not self.children

    def iter_leaves(self):
        if self.is_leaf:
            yield self
        for c in self.children:
            yield from c.iter_leaves()

    def iter_all(self):
        yield self
        for c in self.children:
            yield from c.iter_all()

    def find(self, local_id: str) -> Optional["PlanNode"]:
        for n in self.iter_all():
            if n.local_id == local_id:
                return n
        return None

    def to_dict(self) -> Dict[str, Any]:
        return {
            "local_id": self.local_id,
            "question": self.question,
            "rationale": self.rationale,
            "focus_boundary": self.focus_boundary,
            "budget_usd": self.budget_usd,
            "max_depth": self.max_depth,
            "graph_node_id": self.graph_node_id,
            "children": [c.to_dict() for c in self.children],
        }

    @staticmethod
    def from_dict(d: Dict[str, Any]) -> "PlanNode":
        return PlanNode(
            question=d["question"], rationale=d.get("rationale", ""),
            focus_boundary=d.get("focus_boundary", ""),
            budget_usd=d.get("budget_usd"), max_depth=d.get("max_depth"),
            local_id=d.get("local_id") or _new_local_id(),
            graph_node_id=d.get("graph_node_id"),
            children=[PlanNode.from_dict(c) for c in d.get("children", [])],
        )


@dataclass
class ApprovalState:
    state: str = "draft"           # "draft" | "approved"
    approved_at: Optional[str] = None
    approved_by: Optional[str] = None
    plan_version: int = 1          # bumps on every edit; approval pins a version

    @property
    def is_launchable(self) -> bool:
        return self.state == "approved"

    def to_dict(self) -> Dict[str, Any]:
        return {"state": self.state, "approved_at": self.approved_at,
                "approved_by": self.approved_by, "plan_version": self.plan_version}

    @staticmethod
    def from_dict(d: Dict[str, Any]) -> "ApprovalState":
        return ApprovalState(state=d.get("state", "draft"),
                             approved_at=d.get("approved_at"),
                             approved_by=d.get("approved_by"),
                             plan_version=int(d.get("plan_version", 1)))


@dataclass
class PlanTree:
    """A cascade plan: a root problem decomposing into focused sub-questions.
    ``seed_kind`` records what seeded it (problem / gap / note_challenge) for
    the compounding-loop provenance."""

    root: PlanNode
    seed_kind: str = "problem"     # "problem" | "gap" | "note_challenge"
    seed_provenance: Dict[str, Any] = field(default_factory=dict)
    approval: ApprovalState = field(default_factory=ApprovalState)
    root_investigation_id: Optional[str] = None

    # -- edit operations (each re-opens the approval gate) --------------

    def _touch(self) -> None:
        """Any structural edit bumps the version and re-opens approval."""
        self.approval.plan_version += 1
        if self.approval.state == "approved":
            self.approval.state = "draft"
            self.approval.approved_at = None
            self.approval.approved_by = None

    def add_child(self, parent_local_id: str, question: str, **kw) -> Optional[PlanNode]:
        parent = self.root.find(parent_local_id)
        if parent is None:
            return None
        node = PlanNode(question=question, **kw)
        parent.children.append(node)
        self._touch()
        return node

    def remove(self, local_id: str) -> bool:
        if local_id == self.root.local_id:
            return False  # cannot remove the root
        for n in self.root.iter_all():
            for i, c in enumerate(n.children):
                if c.local_id == local_id:
                    del n.children[i]
                    self._touch()
                    return True
        return False

    def reword(self, local_id: str, question: str) -> bool:
        n = self.root.find(local_id)
        if n is None:
            return False
        n.question = question
        self._touch()
        return True

    def set_budget(self, local_id: str, *, budget_usd: Optional[float] = None,
                   max_depth: Optional[int] = None) -> bool:
        n = self.root.find(local_id)
        if n is None:
            return False
        if budget_usd is not None:
            n.budget_usd = budget_usd
        if max_depth is not None:
            n.max_depth = max_depth
        self._touch()
        return True

    def split(self, local_id: str, into: List[str]) -> bool:
        """Replace one over-broad node with N focused children under it."""
        n = self.root.find(local_id)
        if n is None or not into:
            return False
        n.children.extend(PlanNode(question=q) for q in into)
        self._touch()
        return True

    def merge(self, local_ids: List[str], merged_question: str) -> bool:
        """Merge sibling nodes into one. They must share a parent."""
        parent = None
        for cand in self.root.iter_all():
            ids = {c.local_id for c in cand.children}
            if set(local_ids) <= ids and local_ids:
                parent = cand
                break
        if parent is None:
            return False
        ids = set(local_ids)
        merged_children: List[PlanNode] = []
        kept: List[PlanNode] = []
        for c in parent.children:
            if c.local_id in ids:
                merged_children.extend(c.children)  # absorb the merged nodes' children
            else:
                kept.append(c)
        kept.append(PlanNode(question=merged_question, children=merged_children))
        parent.children = kept
        self._touch()
        return True

    # -- serialization --------------------------------------------------

    def to_dict(self) -> Dict[str, Any]:
        return {
            "root": self.root.to_dict(),
            "seed_kind": self.seed_kind,
            "seed_provenance": self.seed_provenance,
            "approval": self.approval.to_dict(),
            "root_investigation_id": self.root_investigation_id,
        }

    @staticmethod
    def from_dict(d: Dict[str, Any]) -> "PlanTree":
        return PlanTree(
            root=PlanNode.from_dict(d["root"]),
            seed_kind=d.get("seed_kind", "problem"),
            seed_provenance=d.get("seed_provenance", {}),
            approval=ApprovalState.from_dict(d.get("approval", {})),
            root_investigation_id=d.get("root_investigation_id"),
        )

    @property
    def leaves(self) -> List[PlanNode]:
        return list(self.root.iter_leaves())
