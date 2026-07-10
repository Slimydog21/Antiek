"""Usage-driven suite rewrite: propose → approve/promote gate only."""

from __future__ import annotations

import hashlib
from dataclasses import dataclass
from typing import Any, Literal

from .store import BenchStore
from .suite import SuiteDefinition, SuiteItem, SuiteRegistry, TaskClass, active_suite

ProposalStatus = Literal["proposed", "approved", "rejected"]


@dataclass(frozen=True)
class SuiteProposal:
    proposal_id: str
    base_suite_version: str
    proposed_suite_version: str
    rationale: str
    added_item_ids: tuple[str, ...]
    status: ProposalStatus
    suite: SuiteDefinition

    def to_dict(self) -> dict[str, Any]:
        return {
            "proposal_id": self.proposal_id,
            "base_suite_version": self.base_suite_version,
            "proposed_suite_version": self.proposed_suite_version,
            "rationale": self.rationale,
            "added_item_ids": list(self.added_item_ids),
            "status": self.status,
            "suite": {
                "suite_version": self.suite.suite_version,
                "label": self.suite.label,
                "items": [
                    {
                        "item_id": i.item_id,
                        "task_class": i.task_class,
                        "prompt": i.prompt,
                        "expected_keywords": list(i.expected_keywords),
                    }
                    for i in self.suite.items
                ],
            },
        }


def _proposal_id(base: str, usage_fingerprint: str) -> str:
    digest = hashlib.sha256(f"prop:v1:{base}:{usage_fingerprint}".encode()).hexdigest()[
        :16
    ]
    return f"prop_{digest}"


def _fingerprint_usage(events: list[dict[str, Any]]) -> str:
    parts = []
    for e in events:
        parts.append(
            f"{e.get('task_class', '')}:{e.get('outcome', '')}:{e.get('prompt_hint', '')}"
        )
    return hashlib.sha256("|".join(parts).encode()).hexdigest()[:16]


def propose_suite_delta(
    usage_events: list[dict[str, Any]] | tuple[dict[str, Any], ...],
    *,
    store: BenchStore,
    registry: SuiteRegistry | None = None,
    base_suite: SuiteDefinition | None = None,
) -> SuiteProposal:
    """Propose a new suite version from usage patterns — does NOT activate it.

    Each usage event may include:
    * ``task_class`` — distill | synthesize | wrestle | book_qa
    * ``outcome`` — ``worked`` | ``failed``
    * ``prompt_hint`` — optional new prompt seed for failed paths
    """
    events = list(usage_events)
    if not events:
        raise ValueError("usage_events must be non-empty")

    base = base_suite if base_suite is not None else active_suite(registry=registry)
    fp = _fingerprint_usage(events)
    # Build additive items from failed outcomes with prompt hints
    new_items: list[SuiteItem] = list(base.items)
    added: list[str] = []
    for i, ev in enumerate(events):
        outcome = str(ev.get("outcome") or "").lower()
        if outcome != "failed":
            continue
        tc_raw = str(ev.get("task_class") or "distill")
        if tc_raw not in ("distill", "synthesize", "wrestle", "book_qa"):
            tc_raw = "distill"
        tc: TaskClass = tc_raw  # type: ignore[assignment]
        hint = str(ev.get("prompt_hint") or "").strip()
        if not hint:
            hint = f"Regress failed {tc} case from usage week pattern {i}"
        item_id = f"usage-{tc}-{fp[:6]}-{i}"
        if any(x.item_id == item_id for x in new_items):
            continue
        keywords = tuple(
            w.lower() for w in hint.replace(",", " ").split() if len(w) > 3
        )[:6]
        if not keywords:
            keywords = (tc, "usage")
        new_items.append(
            SuiteItem(
                item_id=item_id,
                task_class=tc,
                prompt=hint,
                expected_keywords=keywords,
            )
        )
        added.append(item_id)

    # Residual (acx): title-only Write seeds (has_body=false → failed) feed
    # recursive rewrite — surface count so operators audit body honesty.
    title_only_failed = sum(
        1
        for ev in events
        if str(ev.get("outcome") or "").lower() == "failed"
        and ev.get("has_body") is False
    )
    if not added:
        # Still form a proposal that re-states base (no-op delta) so operator sees honesty
        rationale = "No failed usage events; proposal is a no-op snapshot of the base suite."
    else:
        rationale = (
            f"Ingested {len(events)} usage events; added {len(added)} items "
            f"from failed outcomes for task classes present in usage."
        )
    if title_only_failed:
        rationale = (
            f"{rationale} · title-only Write seeds (has_body=false): "
            f"{title_only_failed} (body honesty → suite rewrite)"
        )

    proposed_version = f"{base.suite_version}+usage-{fp[:8]}"
    suite = SuiteDefinition(
        suite_version=proposed_version,
        label=base.label,
        items=tuple(new_items),
    )
    pid = _proposal_id(base.suite_version, fp)
    proposal = SuiteProposal(
        proposal_id=pid,
        base_suite_version=base.suite_version,
        proposed_suite_version=proposed_version,
        rationale=rationale,
        added_item_ids=tuple(added),
        status="proposed",
        suite=suite,
    )
    store.put_proposal(pid, proposal.to_dict())
    return proposal


def approve_and_promote(
    proposal_id: str,
    *,
    store: BenchStore,
    registry: SuiteRegistry | None = None,
    approve: bool = True,
) -> SuiteDefinition:
    """Explicit gate: only approved proposals register+promote the new suite.

    Unapproved / rejected proposals must leave ``registry.active_version`` unchanged.
    When ``registry`` is None, uses the process-default suite registry (same as
    ``active_suite()``) after ensuring the core suite is registered.
    """
    from .suite import active_suite

    reg = registry if registry is not None else _process_registry()
    # Ensure a baseline active suite exists when using the process default.
    if registry is None:
        active_suite(registry=reg)

    row = store.get_proposal(proposal_id)
    if row is None:
        raise KeyError(f"unknown proposal_id: {proposal_id}")
    if not approve:
        row = dict(row)
        row["status"] = "rejected"
        store.put_proposal(proposal_id, row)
        return reg.active()

    suite_data = row.get("suite") or {}
    items = []
    for it in suite_data.get("items") or []:
        items.append(
            SuiteItem(
                item_id=str(it["item_id"]),
                task_class=it["task_class"],
                prompt=str(it["prompt"]),
                expected_keywords=tuple(it.get("expected_keywords") or ()),
            )
        )
    suite = SuiteDefinition(
        suite_version=str(suite_data.get("suite_version") or row["proposed_suite_version"]),
        label=str(suite_data.get("label") or "antiek-bench-core"),
        items=tuple(items),
    )
    reg.register(suite)
    promoted = reg.promote(suite.suite_version)
    row = dict(row)
    row["status"] = "approved"
    store.put_proposal(proposal_id, row)
    return promoted


def _process_registry() -> SuiteRegistry:
    from .suite import _DEFAULT_REGISTRY

    return _DEFAULT_REGISTRY
