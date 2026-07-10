"""Usage-driven suite rewrite: propose → approve/promote gate only."""

from __future__ import annotations

import hashlib
import json
import re
from dataclasses import dataclass
from threading import RLock
from typing import Any, Literal

from .store import BenchStore
from .suite import SuiteDefinition, SuiteItem, SuiteRegistry, TaskClass, active_suite

ProposalStatus = Literal["proposed", "approving", "approved", "rejected", "stale"]
_APPROVAL_LOCK = RLock()
USAGE_SEED_POLICY_VERSION = "usage-seed-v1"
MAX_USAGE_ITEMS_PER_TASK = 2
_UNSAFE_SEED = re.compile(
    r"(?i)([a-z][a-z0-9+.-]*://|mailto:|www\.|[\w.+-]+@[\w.-]+\.[a-z]{2,}|"
    r"\+?\d[\d ()-]{7,}\d|api[_ -]?key|client[_ -]?secret|password|bearer\s+|"
    r"sk-[a-z0-9]|AKIA[0-9A-Z]{16}|gh[pousr]_[a-z0-9]{20,}|xox[baprs]-|"
    r"eyJ[a-z0-9_-]{10,}\.|-----BEGIN|[a-f0-9]{32,}|"
    r"\b(?:\d{1,3}\.){3}\d{1,3}\b|\b(?:[a-z0-9-]+\.)+[a-z]{2,63}\b|"
    r"(access|refresh|private|auth)[_ -]?token|credentials?|token\s*[:= ]\s*\S+|"
    r"(ignore|disregard|forget|override).{0,24}(previous|prior|above|instructions?|directions?)|"
    r"(system|developer)\s+(message|prompt|instructions?)|<script|BEGIN [A-Z ]+>)"
)


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
    seed_policy_version: str = USAGE_SEED_POLICY_VERSION
    reviewed_seed_count: int = 0
    generic_seed_count: int = 0
    redacted_event_count: int = 0
    dropped_event_count: int = 0
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
            "seed_policy_version": self.seed_policy_version,
            "reviewed_seed_count": self.reviewed_seed_count,
            "generic_seed_count": self.generic_seed_count,
            "redacted_event_count": self.redacted_event_count,
            "dropped_event_count": self.dropped_event_count,
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
    seed_policy_version: str,
    rationale: str,
    reviewed_seed_count: int,
    generic_seed_count: int,
    redacted_event_count: int,
    dropped_event_count: int,
) -> str:
    material = json.dumps(
        {
            "proposal_id": proposal_id,
            "base_suite_version": base_suite_version,
            "proposed_suite_version": proposed_suite_version,
            "seed_policy_version": seed_policy_version,
            "rationale": rationale,
            "reviewed_seed_count": reviewed_seed_count,
            "generic_seed_count": generic_seed_count,
            "redacted_event_count": redacted_event_count,
            "dropped_event_count": dropped_event_count,
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
    parts = [
        json.dumps(
            {"task_class": task, "seed": seed, "policy": USAGE_SEED_POLICY_VERSION},
            sort_keys=True,
            separators=(",", ":"),
        )
        for task, seed, _ in _selected_usage_cases(events)
    ]
    return hashlib.sha256("|".join(parts).encode()).hexdigest()[:16]


def _fingerprint_proposal(events: list[dict[str, Any]], suite_fingerprint: str) -> str:
    failed = [
        event
        for event in events
        if str(event.get("outcome") or "").lower() == "failed"
    ]
    audit = {
        "suite_fingerprint": suite_fingerprint,
        "failed_event_count": len(failed),
        "reviewed_seed_count": sum(_reviewed_seed(event) is not None for event in failed),
        "generic_seed_count": sum(_reviewed_seed(event) is None for event in failed),
        "redacted_event_count": sum(
            _reviewed_seed(event) is None
            and bool(event.get("prompt_hint") or event.get("benchmark_seed"))
            for event in failed
        ),
        "policy": USAGE_SEED_POLICY_VERSION,
    }
    material = json.dumps(audit, sort_keys=True, separators=(",", ":"))
    return hashlib.sha256(material.encode()).hexdigest()[:16]


def _reviewed_seed(event: dict[str, Any]) -> str | None:
    if event.get("benchmark_seed_reviewed") is not True:
        return None
    seed = str(event.get("benchmark_seed") or "").strip()
    forbidden_delimiters = {"@", "=", ":", "/", "\\", "`", "<", ">", "{", "}"}
    token_like = re.search(r"\b[a-zA-Z0-9_+=/-]{25,}\b", seed)
    if (
        not seed
        or len(seed) > 240
        or any(character in seed for character in forbidden_delimiters)
        or any(ord(character) < 32 for character in seed)
        or token_like
        or _UNSAFE_SEED.search(seed)
    ):
        return None
    return seed


def _body_state(event: dict[str, Any]) -> str:
    if event.get("has_body") is True:
        return "with-body"
    if event.get("has_body") is False:
        return "title-only"
    return "body-unknown"


def _safe_event_projection(event: dict[str, Any]) -> dict[str, str]:
    task = str(event.get("task_class") or "distill")
    if task not in ("distill", "synthesize", "wrestle", "book_qa"):
        task = "distill"
    reviewed = _reviewed_seed(event)
    return {
        "task_class": task,
        "outcome": str(event.get("outcome") or "").lower(),
        "body_state": _body_state(event),
        "seed": reviewed or "generic",
        "policy": USAGE_SEED_POLICY_VERSION,
    }


def _generic_seed(task_class: TaskClass, event: dict[str, Any]) -> str:
    return (
        f"Evaluate a failed {task_class} workflow using a synthetic "
        f"{_body_state(event)} information asset."
    )


def _usage_case(event: dict[str, Any]) -> tuple[TaskClass, str] | None:
    if str(event.get("outcome") or "").lower() != "failed":
        return None
    projection = _safe_event_projection(event)
    task: TaskClass = projection["task_class"]  # type: ignore[assignment]
    return task, _reviewed_seed(event) or _generic_seed(task, event)


def _selected_usage_cases(
    events: list[dict[str, Any]],
) -> tuple[tuple[TaskClass, str, dict[str, Any]], ...]:
    unique: dict[tuple[TaskClass, str], dict[str, Any]] = {}
    for event in events:
        case = _usage_case(event)
        if case is not None:
            unique.setdefault(case, event)
    selected: list[tuple[TaskClass, str, dict[str, Any]]] = []
    counts: dict[TaskClass, int] = {}
    for (task, seed), event in sorted(unique.items(), key=lambda row: row[0]):
        if counts.get(task, 0) >= MAX_USAGE_ITEMS_PER_TASK:
            continue
        selected.append((task, seed, event))
        counts[task] = counts.get(task, 0) + 1
    return tuple(selected)


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
    suite_fp = _fingerprint_usage(events)
    fp = _fingerprint_proposal(events, suite_fp)
    # Build additive items from failed outcomes with prompt hints
    new_items: list[SuiteItem] = list(base.items)
    added: list[str] = []
    reviewed_seed_count = 0
    generic_seed_count = 0
    redacted_event_count = 0
    dropped_event_count = 0
    failed_events = [
        event
        for event in events
        if str(event.get("outcome") or "").lower() == "failed"
    ]
    for ev in failed_events:
        reviewed = _reviewed_seed(ev)
        if reviewed is not None:
            reviewed_seed_count += 1
        else:
            generic_seed_count += 1
            if ev.get("prompt_hint") or ev.get("benchmark_seed"):
                redacted_event_count += 1
    selected_cases = _selected_usage_cases(events)
    dropped_event_count = len(failed_events) - len(selected_cases)
    for i, (tc, hint, _event) in enumerate(selected_cases):
        item_id = f"usage-{tc}-{suite_fp[:6]}-{i}"
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
    rationale = (
        f"{rationale} · usage seed policy {USAGE_SEED_POLICY_VERSION}: "
        f"reviewed={reviewed_seed_count} · generic={generic_seed_count} · "
        f"redacted={redacted_event_count} · dropped={dropped_event_count}"
    )

    proposed_version = f"{base.suite_version}+usage-{suite_fp[:8]}"
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
            seed_policy_version=USAGE_SEED_POLICY_VERSION,
            rationale=rationale,
            reviewed_seed_count=reviewed_seed_count,
            generic_seed_count=generic_seed_count,
            redacted_event_count=redacted_event_count,
            dropped_event_count=dropped_event_count,
        ),
        reviewed_seed_count=reviewed_seed_count,
        generic_seed_count=generic_seed_count,
        redacted_event_count=redacted_event_count,
        dropped_event_count=dropped_event_count,
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


def migrate_legacy_proposal(
    proposal_id: str,
    *,
    store: BenchStore,
    operator_reviewed: bool,
) -> dict[str, Any]:
    if not operator_reviewed:
        raise ValueError("legacy proposal migration requires explicit operator review")
    row = store.get_proposal(proposal_id)
    if row is None:
        raise KeyError(f"unknown proposal_id: {proposal_id}")
    if row.get("status") != "proposed" or row.get("proposal_digest"):
        raise ProposalStateError("only unsealed proposed rows can be migrated")
    suite = _suite_from_row(row)
    migrated = dict(row)
    migrated["seed_policy_version"] = "legacy-operator-reviewed-v1"
    for field in (
        "reviewed_seed_count",
        "generic_seed_count",
        "redacted_event_count",
        "dropped_event_count",
    ):
        migrated[field] = int(migrated.get(field) or 0)
    migrated["proposal_digest"] = _proposal_digest(
        proposal_id=proposal_id,
        base_suite_version=str(migrated.get("base_suite_version") or ""),
        proposed_suite_version=str(migrated.get("proposed_suite_version") or ""),
        suite=suite,
        seed_policy_version=str(migrated["seed_policy_version"]),
        rationale=str(migrated.get("rationale") or ""),
        reviewed_seed_count=int(migrated["reviewed_seed_count"]),
        generic_seed_count=int(migrated["generic_seed_count"]),
        redacted_event_count=int(migrated["redacted_event_count"]),
        dropped_event_count=int(migrated["dropped_event_count"]),
    )
    store.put_proposal(proposal_id, migrated)
    return migrated


def _suite_from_row(row: dict[str, Any]) -> SuiteDefinition:
    suite_data = row.get("suite") or {}
    items = [
        SuiteItem(
            item_id=str(item["item_id"]),
            task_class=item["task_class"],
            prompt=str(item["prompt"]),
            expected_keywords=tuple(item.get("expected_keywords") or ()),
        )
        for item in suite_data.get("items") or []
    ]
    return SuiteDefinition(
        suite_version=str(suite_data.get("suite_version") or row["proposed_suite_version"]),
        label=str(suite_data.get("label") or "antiek-bench-core"),
        items=tuple(items),
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

    suite = _suite_from_row(row)
    expected_digest = _proposal_digest(
        proposal_id=proposal_id,
        base_suite_version=str(row.get("base_suite_version") or ""),
        proposed_suite_version=str(row.get("proposed_suite_version") or ""),
        suite=suite,
        seed_policy_version=str(row.get("seed_policy_version") or ""),
        rationale=str(row.get("rationale") or ""),
        reviewed_seed_count=int(row.get("reviewed_seed_count") or 0),
        generic_seed_count=int(row.get("generic_seed_count") or 0),
        redacted_event_count=int(row.get("redacted_event_count") or 0),
        dropped_event_count=int(row.get("dropped_event_count") or 0),
    )
    if not row.get("proposal_digest") or not row.get("seed_policy_version"):
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
