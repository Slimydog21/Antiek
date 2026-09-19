from pathlib import Path

import pytest

from runtime.research_runner.gather_launch_plan import AuthorizedGatherLaunchPlan
from runtime.research_runner.gather_plan import GatherSource, GatherSourcePlan
from substrate.investigation_tenancy import InvestigationAuthority


def _authority(account: str = "acct", investigation: str = "root") -> InvestigationAuthority:
    return InvestigationAuthority(account, investigation, Path("/tmp/antiek-gather-launch"))


def _sources() -> tuple[GatherSourcePlan, ...]:
    return (
        GatherSourcePlan.reviewed(
            source=GatherSource.EXA,
            max_results=3,
            max_cost_usd="0.005",
            policy_version="exa-v1",
        ),
        GatherSourcePlan.reviewed(
            source=GatherSource.ARXIV,
            max_results=4,
            max_cost_usd="0",
            policy_version="arxiv-v1",
        ),
    )


def test_review_fingerprint_binds_leaf_count_and_total_exposure() -> None:
    plan = AuthorizedGatherLaunchPlan.reviewed(
        _authority(),
        legal_policy_snapshot_sha256="a" * 64,
        leaf_queries=("one", "two", "three"),
        sources=_sources(),
    )
    changed = AuthorizedGatherLaunchPlan.reviewed(
        _authority(),
        legal_policy_snapshot_sha256="a" * 64,
        leaf_queries=("one", "two", "three", "four"),
        sources=_sources(),
    )
    assert plan.per_leaf_max_results == 7
    assert plan.per_leaf_max_cost_micros == 5_000
    assert plan.launch_max_results == 21
    assert plan.launch_max_cost_micros == 15_000
    assert plan.fingerprint != changed.fingerprint


def test_each_leaf_gets_distinct_receipt_namespace() -> None:
    template = AuthorizedGatherLaunchPlan.reviewed(
        _authority(),
        legal_policy_snapshot_sha256="a" * 64,
        leaf_queries=("first", "second"),
        sources=_sources(),
    )
    first = template.materialize_leaf(
        _authority(investigation="leaf-1"), leaf_index=0, query="first"
    )
    second = template.materialize_leaf(
        _authority(investigation="leaf-2"), leaf_index=1, query="second"
    )
    assert first.fingerprint != second.fingerprint
    assert first.sources == second.sources == template.sources
    assert first.aggregate_max_cost_micros == template.per_leaf_max_cost_micros


def test_foreign_or_root_authority_cannot_materialize() -> None:
    template = AuthorizedGatherLaunchPlan.reviewed(
        _authority(),
        legal_policy_snapshot_sha256="a" * 64,
        leaf_queries=("query",),
        sources=_sources(),
    )
    with pytest.raises(ValueError, match="different account"):
        template.materialize_leaf(
            _authority(account="other", investigation="leaf"), leaf_index=0, query="query"
        )
    with pytest.raises(ValueError, match="distinct from the root"):
        template.materialize_leaf(_authority(), leaf_index=0, query="query")


def test_direct_constructor_rejects_forged_totals() -> None:
    valid = AuthorizedGatherLaunchPlan.reviewed(
        _authority(),
        legal_policy_snapshot_sha256="a" * 64,
        leaf_queries=("one", "two"),
        sources=_sources(),
    )
    with pytest.raises(ValueError, match="launch cost exposure"):
        AuthorizedGatherLaunchPlan(
            valid.version,
            valid.account_digest,
            valid.root_investigation_digest,
            valid.legal_policy_snapshot_sha256,
            valid.leaf_count,
            valid.per_leaf_max_results,
            valid.per_leaf_max_cost_micros,
            valid.launch_max_results,
            valid.launch_max_cost_micros + 1,
            valid.leaf_query_sha256,
            valid.sources,
        )


def test_same_count_query_edit_rotates_review_and_materialization_rejects_drift() -> None:
    first = AuthorizedGatherLaunchPlan.reviewed(
        _authority(),
        legal_policy_snapshot_sha256="a" * 64,
        leaf_queries=("one", "two"),
        sources=_sources(),
    )
    changed = AuthorizedGatherLaunchPlan.reviewed(
        _authority(),
        legal_policy_snapshot_sha256="a" * 64,
        leaf_queries=("one", "changed"),
        sources=_sources(),
    )
    assert first.fingerprint != changed.fingerprint
    with pytest.raises(ValueError, match="query differs"):
        first.materialize_leaf(
            _authority(investigation="leaf-2"), leaf_index=1, query="changed"
        )
