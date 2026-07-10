"""Usage-driven suite rewrite: propose → approve/promote gate only."""

from __future__ import annotations

import hashlib
import json
from dataclasses import dataclass
from threading import RLock
from typing import Any, Literal

from .store import BenchStore
from .suite import SuiteDefinition, SuiteItem, SuiteRegistry, TaskClass, active_suite

ProposalStatus = Literal["proposed", "approving", "approved", "rejected", "stale"]
_APPROVAL_LOCK = RLock()


class ProposalIntegrityError(ValueError):
    pass


class ProposalMigrationRequiredError(ProposalIntegrityError):
    pass


class ProposalStateError(RuntimeError):
    pass


class StaleSuiteProposalError(ProposalStateError):
    pass


@dataclass(frozen=True)
class SuiteProposal:
    proposal_id: str
    base_suite_version: str
    proposed_suite_version: str
    rationale: str
    added_item_ids: tuple[str, ...]
    status: ProposalStatus
    suite: SuiteDefinition
    proposal_digest: str
    # Residual (acy): structured count of title-only Write seed failures
    # (has_body=false → failed) for Settings / recursive rewrite audit.
    title_only_write_seed_count: int = 0
    # Residual (adp): full body honesty matrix on proposal (parity usage summary).
    with_body_write_seed_count: int = 0
    body_unknown_write_seed_count: int = 0

    def to_dict(self) -> dict[str, Any]:
        return {
            "proposal_id": self.proposal_id,
            "base_suite_version": self.base_suite_version,
            "proposed_suite_version": self.proposed_suite_version,
            "rationale": self.rationale,
            "added_item_ids": list(self.added_item_ids),
            "status": self.status,
            "proposal_digest": self.proposal_digest,
            # Residual (acy): body honesty aggregate (parity rationale acx).
            "title_only_write_seed_count": int(self.title_only_write_seed_count),
            # Residual (adp): with_body + unknown for full rewrite audit matrix.
            "with_body_write_seed_count": int(self.with_body_write_seed_count),
            "body_unknown_write_seed_count": int(self.body_unknown_write_seed_count),
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


def _proposal_digest(
    *,
    proposal_id: str,
    base_suite_version: str,
    proposed_suite_version: str,
    suite: SuiteDefinition,
) -> str:
    material = json.dumps(
        {
            "proposal_id": proposal_id,
            "base_suite_version": base_suite_version,
            "proposed_suite_version": proposed_suite_version,
            "suite": {
                "suite_version": suite.suite_version,
                "label": suite.label,
                "items": [
                    {
                        "item_id": item.item_id,
                        "task_class": item.task_class,
                        "prompt": item.prompt,
                        "expected_keywords": item.expected_keywords,
                    }
                    for item in suite.items
                ],
            },
        },
        sort_keys=True,
        separators=(",", ":"),
    )
    return "sha256:" + hashlib.sha256(material.encode()).hexdigest()


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
    # Residual (adp): with_body + unknown counts (full matrix; parity usage summary).
    with_body_n = sum(1 for ev in events if ev.get("has_body") is True)
    body_unknown_n = sum(
        1 for ev in events if "has_body" not in ev or ev.get("has_body") is None
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
    if with_body_n or body_unknown_n:
        rationale = (
            f"{rationale} · body honesty matrix: with_body={with_body_n} · "
            f"title_only={title_only_failed} · unknown={body_unknown_n}"
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
        proposal_digest=_proposal_digest(
            proposal_id=pid,
            base_suite_version=base.suite_version,
            proposed_suite_version=proposed_version,
            suite=suite,
        ),
        title_only_write_seed_count=int(title_only_failed),
        with_body_write_seed_count=int(with_body_n),
        body_unknown_write_seed_count=int(body_unknown_n),
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
    reg = registry if registry is not None else _process_registry()
    if registry is None:
        active_suite(registry=reg)
    with _APPROVAL_LOCK:
        return _approve_locked(
            proposal_id, store=store, registry=reg, approve=approve
        )


def _approve_locked(
    proposal_id: str,
    *,
    store: BenchStore,
    registry: SuiteRegistry,
    approve: bool,
) -> SuiteDefinition:
    reg = registry

    row = store.get_proposal(proposal_id)
    if row is None:
        raise KeyError(f"unknown proposal_id: {proposal_id}")
    status = str(row.get("status") or "")
    active = reg.active()
    if status == "approved":
        if not approve:
            raise ProposalStateError("approved proposal cannot be rejected")
        return active
    if status not in {"proposed", "approving"}:
        raise ProposalStateError(f"proposal is terminal: {status or 'unknown'}")
    if not approve:
        if status == "approving":
            raise ProposalStateError("approving proposal cannot be rejected")
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
    expected_digest = _proposal_digest(
        proposal_id=proposal_id,
        base_suite_version=str(row.get("base_suite_version") or ""),
        proposed_suite_version=str(row.get("proposed_suite_version") or ""),
        suite=suite,
    )
    if not row.get("proposal_digest"):
        raise ProposalMigrationRequiredError(
            "legacy proposal requires explicit digest migration before approval"
        )
    if row.get("proposal_digest") != expected_digest or suite.suite_version != row.get(
        "proposed_suite_version"
    ):
        raise ProposalIntegrityError("proposal payload does not match its immutable digest")
    registered_suite = reg.get(suite.suite_version)
    if status == "approving" and registered_suite == suite:
        completed = dict(row)
        completed["status"] = "approved"
        store.put_proposal(proposal_id, completed)
        return reg.active()
    if status == "proposed":
        intent = dict(row)
        intent["status"] = "approving"
        store.put_proposal(proposal_id, intent)
        row = intent
    promoted = reg.register_and_promote_if_active(
        str(row.get("base_suite_version") or ""), suite
    )
    if promoted is None:
        current = reg.active()
        row = dict(row)
        row["status"] = "stale"
        row["stale_active_suite_version"] = current.suite_version
        store.put_proposal(proposal_id, row)
        raise StaleSuiteProposalError(
            f"proposal base {row.get('base_suite_version')} is not active {current.suite_version}"
        )
    row = dict(row)
    row["status"] = "approved"
    store.put_proposal(proposal_id, row)
    return promoted


def _process_registry() -> SuiteRegistry:
    from .suite import _DEFAULT_REGISTRY

    return _DEFAULT_REGISTRY
