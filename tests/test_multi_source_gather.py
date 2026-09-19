from collections import OrderedDict
from dataclasses import dataclass, field
from pathlib import Path

import pytest

from runtime.research_runner.authorized_gather import (
    GatherAuthorityDenied,
    GatherNotDispatched,
    GatherProviderResult,
)
from runtime.research_runner.authorized_gather_sql import (
    DuckDBAuthorizedGatherAuthority,
    ensure_authorized_gather_schema,
)
from runtime.research_runner.gather_plan import AuthorizedGatherPlan, GatherSource, GatherSourcePlan
from runtime.research_runner.multi_source_gather import (
    GatherSourceStatus,
    execute_authorized_gather_plan,
)
from substrate.investigation_tenancy import InvestigationAuthority


def _authority(root: Path) -> InvestigationAuthority:
    return InvestigationAuthority("acct-1", "inv-multi", root)


def _plan(authority: InvestigationAuthority) -> AuthorizedGatherPlan:
    return AuthorizedGatherPlan.reviewed(
        authority,
        legal_policy_snapshot_sha256="b" * 64,
        aggregate_max_results=4,
        aggregate_max_cost_usd="0.04",
        sources=(
            GatherSourcePlan.reviewed(
                source=GatherSource.EXA,
                max_results=1,
                max_cost_usd="0.02",
                policy_version="exa-v1",
            ),
            GatherSourcePlan.reviewed(
                source=GatherSource.PARALLEL,
                max_results=1,
                max_cost_usd="0.02",
                policy_version="parallel-v1",
            ),
            GatherSourcePlan.reviewed(
                source=GatherSource.ARXIV,
                max_results=1,
                max_cost_usd="0",
                policy_version="arxiv-v1",
            ),
            GatherSourcePlan.reviewed(
                source=GatherSource.SUBSTACK,
                max_results=1,
                max_cost_usd="0",
                policy_version="substack-v1",
            ),
        ),
    )


@dataclass
class Provider:
    source: GatherSource
    result: GatherProviderResult
    error: Exception | None = None
    calls: list[str] = field(default_factory=list)

    def execute(self, **kwargs: object) -> GatherProviderResult:
        self.calls.append(str(kwargs["idempotency_key"]))
        if self.error is not None:
            raise self.error
        return self.result


def _providers() -> OrderedDict[GatherSource, Provider]:
    return OrderedDict(
        (
            (GatherSource.EXA, Provider(GatherSource.EXA, GatherProviderResult(("doc-exa",), 10_000))),
            (
                GatherSource.PARALLEL,
                Provider(GatherSource.PARALLEL, GatherProviderResult(("doc-parallel",), 10_000)),
            ),
            (GatherSource.ARXIV, Provider(GatherSource.ARXIV, GatherProviderResult(("doc-arxiv",), 0))),
            (
                GatherSource.SUBSTACK,
                Provider(GatherSource.SUBSTACK, GatherProviderResult(("doc-substack",), 0)),
            ),
        )
    )


@pytest.fixture
def context(tmp_path: Path):
    db_path = str(tmp_path / "multi.duckdb")
    ensure_authorized_gather_schema(db_path)
    authority = _authority(tmp_path)
    return db_path, authority, _plan(authority)


def _execute(context, providers, *, minimum=1, validator=lambda authority, snapshot: None):
    db_path, authority, plan = context
    store = DuckDBAuthorizedGatherAuthority(db_path, authority)
    return execute_authorized_gather_plan(
        plan=plan,
        expected_plan_fingerprint=plan.fingerprint,
        authority=authority,
        query="AI hardware fault tolerance",
        providers=providers,
        validate_policy_snapshot=validator,
        budget=store,
        receipts=store,
        minimum_evidence_documents=minimum,
    )


def test_mixed_sources_execute_in_canonical_order_and_complete(context) -> None:
    providers = _providers()
    report = _execute(context, providers, minimum=4)
    assert tuple(item.source for item in report.source_receipts) == tuple(GatherSource)
    assert report.document_ids == ("doc-exa", "doc-parallel", "doc-arxiv", "doc-substack")
    assert report.evidence_complete is True
    assert report.partial is False
    assert report.unknown_outcome is False


def test_provider_set_mismatch_fails_before_any_claim_or_dispatch(context) -> None:
    providers = _providers()
    providers.pop(GatherSource.SUBSTACK)
    with pytest.raises(GatherAuthorityDenied, match="set/order"):
        _execute(context, providers)
    assert all(not provider.calls for provider in providers.values())


def test_proven_not_dispatched_source_can_yield_partial_evidence_complete(context) -> None:
    providers = _providers()
    providers[GatherSource.EXA].error = GatherNotDispatched("client construction failed")
    report = _execute(context, providers, minimum=3)
    assert report.source_receipts[0].status is GatherSourceStatus.FAILED
    assert report.evidence_complete is True
    assert report.partial is True
    assert len(report.document_ids) == 3


def test_ambiguous_outcome_stops_later_sources_and_replay_never_dispatches(context) -> None:
    providers = _providers()
    providers[GatherSource.PARALLEL].error = TimeoutError("unknown")
    first = _execute(context, providers)
    assert [item.status for item in first.source_receipts] == [
        GatherSourceStatus.SUCCEEDED,
        GatherSourceStatus.UNKNOWN,
        GatherSourceStatus.SKIPPED,
        GatherSourceStatus.SKIPPED,
    ]
    assert first.evidence_complete is False
    assert first.unknown_outcome is True

    replay = _providers()
    second = _execute(context, replay)
    assert second.unknown_outcome is True
    assert replay[GatherSource.EXA].calls == []
    assert replay[GatherSource.PARALLEL].calls == []
    assert replay[GatherSource.ARXIV].calls == []


def test_policy_drift_before_first_source_produces_zero_provider_calls(context) -> None:
    providers = _providers()
    report = _execute(
        context,
        providers,
        validator=lambda authority, snapshot: (_ for _ in ()).throw(
            GatherAuthorityDenied("policy drift")
        ),
    )
    assert report.evidence_complete is False
    assert report.source_receipts[0].status is GatherSourceStatus.FAILED
    assert all(not provider.calls for provider in providers.values())


def test_zero_documents_never_rounds_up_to_evidence_complete(context) -> None:
    providers = _providers()
    for provider in providers.values():
        provider.result = GatherProviderResult((), provider.result.actual_cost_micros)
    report = _execute(context, providers)
    assert report.document_ids == ()
    assert report.evidence_complete is False
    assert report.partial is False

