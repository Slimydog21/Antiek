from __future__ import annotations

from concurrent.futures import ThreadPoolExecutor
from copy import deepcopy
from threading import Barrier

import pytest

from substrate.antiek_bench import (
    FileBenchStore,
    InMemoryBenchStore,
    ProposalIntegrityError,
    ProposalMigrationRequiredError,
    ProposalStateError,
    StaleSuiteProposalError,
    SuiteRegistry,
    active_suite,
    approve_and_promote,
    default_core_suite,
    propose_suite_delta,
    register_suite,
    settings_approve_suite_proposal_payload,
)


def _registry() -> SuiteRegistry:
    registry = SuiteRegistry()
    register_suite(default_core_suite(), registry=registry, make_active=True)
    return registry


def _proposal(store: InMemoryBenchStore, registry: SuiteRegistry, marker: str):
    return propose_suite_delta(
        [
            {
                "task_class": "distill",
                "outcome": "failed",
                "prompt_hint": f"Distill stale approval case {marker}",
            }
        ],
        store=store,
        registry=registry,
    )


def test_competing_proposal_becomes_stale_without_registry_mutation() -> None:
    store = InMemoryBenchStore()
    registry = _registry()
    first = _proposal(store, registry, "first")
    second = _proposal(store, registry, "second")
    approve_and_promote(first.proposal_id, store=store, registry=registry)
    before_suites = dict(registry.suites)

    with pytest.raises(StaleSuiteProposalError):
        approve_and_promote(second.proposal_id, store=store, registry=registry)

    assert active_suite(registry=registry).suite_version == first.proposed_suite_version
    assert registry.suites == before_suites
    assert store.get_proposal(second.proposal_id)["status"] == "stale"  # type: ignore[index]


def test_concurrent_approvals_have_exactly_one_winner() -> None:
    store = InMemoryBenchStore()
    registry = _registry()
    proposals = (_proposal(store, registry, "left"), _proposal(store, registry, "right"))
    barrier = Barrier(2)

    def approve(proposal_id: str) -> str:
        barrier.wait()
        try:
            return approve_and_promote(
                proposal_id, store=store, registry=registry
            ).suite_version
        except StaleSuiteProposalError:
            return "stale"

    with ThreadPoolExecutor(max_workers=2) as pool:
        outcomes = tuple(pool.map(approve, (proposal.proposal_id for proposal in proposals)))

    assert outcomes.count("stale") == 1
    assert active_suite(registry=registry).suite_version in outcomes
    assert len(registry.suites) == 2


def test_same_proposal_concurrent_replay_does_not_mark_it_stale() -> None:
    store = InMemoryBenchStore()
    registry = _registry()
    proposal = _proposal(store, registry, "same")
    barrier = Barrier(2)

    def approve() -> str:
        barrier.wait()
        return approve_and_promote(
            proposal.proposal_id, store=store, registry=registry
        ).suite_version

    with ThreadPoolExecutor(max_workers=2) as pool:
        outcomes = tuple(pool.map(lambda _: approve(), range(2)))

    assert outcomes == (proposal.proposed_suite_version,) * 2
    assert store.get_proposal(proposal.proposal_id)["status"] == "approved"  # type: ignore[index]


def test_approved_replay_never_rolls_back_a_later_suite() -> None:
    store = InMemoryBenchStore()
    registry = _registry()
    first = _proposal(store, registry, "first")
    approve_and_promote(first.proposal_id, store=store, registry=registry)
    second = _proposal(store, registry, "second")
    approve_and_promote(second.proposal_id, store=store, registry=registry)

    replay = approve_and_promote(first.proposal_id, store=store, registry=registry)

    assert replay.suite_version == second.proposed_suite_version
    assert active_suite(registry=registry).suite_version == second.proposed_suite_version


def test_rejected_proposal_is_terminal() -> None:
    store = InMemoryBenchStore()
    registry = _registry()
    proposal = _proposal(store, registry, "rejected")
    approve_and_promote(proposal.proposal_id, store=store, registry=registry, approve=False)

    with pytest.raises(ProposalStateError, match="terminal"):
        approve_and_promote(proposal.proposal_id, store=store, registry=registry)

    assert active_suite(registry=registry).suite_version == proposal.base_suite_version


def test_tampered_persisted_suite_fails_before_registry_mutation() -> None:
    store = InMemoryBenchStore()
    registry = _registry()
    proposal = _proposal(store, registry, "tamper")
    row = deepcopy(store.get_proposal(proposal.proposal_id))
    assert row is not None
    row["suite"]["items"][0]["prompt"] = "tampered prompt"
    store.put_proposal(proposal.proposal_id, row)
    before = (active_suite(registry=registry), dict(registry.suites))

    with pytest.raises(ProposalIntegrityError, match="immutable digest"):
        approve_and_promote(proposal.proposal_id, store=store, registry=registry)

    assert (active_suite(registry=registry), registry.suites) == before


def test_legacy_unsealed_proposal_requires_explicit_migration() -> None:
    store = InMemoryBenchStore()
    registry = _registry()
    proposal = _proposal(store, registry, "legacy")
    row = store.get_proposal(proposal.proposal_id)
    assert row is not None
    row.pop("proposal_digest")
    store.put_proposal(proposal.proposal_id, row)

    with pytest.raises(ProposalMigrationRequiredError, match="migration"):
        approve_and_promote(proposal.proposal_id, store=store, registry=registry)

    assert active_suite(registry=registry).suite_version == proposal.base_suite_version


def test_final_store_failure_recovers_from_approving_state() -> None:
    class FailApprovedOnceStore(InMemoryBenchStore):
        failed = False

        def put_proposal(self, proposal_id, proposal):  # type: ignore[no-untyped-def]
            if proposal.get("status") == "approved" and not self.failed:
                self.failed = True
                raise OSError("injected final store failure")
            super().put_proposal(proposal_id, proposal)

    store = FailApprovedOnceStore()
    registry = _registry()
    proposal = _proposal(store, registry, "recover")

    with pytest.raises(OSError, match="injected"):
        approve_and_promote(proposal.proposal_id, store=store, registry=registry)

    assert active_suite(registry=registry).suite_version == proposal.proposed_suite_version
    assert store.get_proposal(proposal.proposal_id)["status"] == "approving"  # type: ignore[index]
    recovered = approve_and_promote(proposal.proposal_id, store=store, registry=registry)
    assert recovered.suite_version == proposal.proposed_suite_version
    assert store.get_proposal(proposal.proposal_id)["status"] == "approved"  # type: ignore[index]


def test_recovery_after_later_promotion_preserves_approved_history() -> None:
    class FailFirstApprovedStore(InMemoryBenchStore):
        failed = False

        def put_proposal(self, proposal_id, proposal):  # type: ignore[no-untyped-def]
            if proposal.get("status") == "approved" and not self.failed:
                self.failed = True
                raise OSError("injected final store failure")
            super().put_proposal(proposal_id, proposal)

    store = FailFirstApprovedStore()
    registry = _registry()
    first = _proposal(store, registry, "first")
    with pytest.raises(OSError):
        approve_and_promote(first.proposal_id, store=store, registry=registry)
    second = _proposal(store, registry, "second")
    approve_and_promote(second.proposal_id, store=store, registry=registry)

    current = approve_and_promote(first.proposal_id, store=store, registry=registry)

    assert current.suite_version == second.proposed_suite_version
    assert store.get_proposal(first.proposal_id)["status"] == "approved"  # type: ignore[index]


def test_file_store_proposal_write_is_atomic_and_leaves_no_temp_file(tmp_path) -> None:  # type: ignore[no-untyped-def]
    store = FileBenchStore(tmp_path)
    store.put_proposal("prop/atomic", {"status": "approving", "value": 1})
    store.put_proposal("prop/atomic", {"status": "approved", "value": 2})

    assert store.get_proposal("prop/atomic") == {"status": "approved", "value": 2}
    assert list((tmp_path / "proposals").iterdir()) == [
        tmp_path / "proposals" / "prop_atomic.json"
    ]


def test_settings_reports_stale_without_promotion() -> None:
    store = InMemoryBenchStore()
    registry = _registry()
    first = _proposal(store, registry, "first")
    second = _proposal(store, registry, "second")
    approve_and_promote(first.proposal_id, store=store, registry=registry)

    payload = settings_approve_suite_proposal_payload(
        second.proposal_id,
        store=store,
        registry=registry,
        approve=True,
        include_html=True,
    )

    assert payload["ok"] is False
    assert payload["status"] == "stale"
    assert payload["promoted"] is False
    assert payload["active_suite_version"] == first.proposed_suite_version
    assert "stale" in payload["html"].lower()
