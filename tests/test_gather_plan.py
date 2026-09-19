from decimal import Decimal
from pathlib import Path

import pytest

from runtime.research_runner.gather_plan import (
    AuthorizedGatherPlan,
    GatherSource,
    GatherSourcePlan,
)
from substrate.investigation_tenancy import InvestigationAuthority


def _authority(investigation_id: str = "inv-1") -> InvestigationAuthority:
    return InvestigationAuthority("acct-1", investigation_id, Path("/tmp/antiek-test"))


def _source(source: GatherSource, *, cost: str = "0", results: int = 3) -> GatherSourcePlan:
    return GatherSourcePlan.reviewed(
        source=source,
        max_results=results,
        max_cost_usd=cost,
        policy_version=f"{source.value}-policy-v1",
    )


def _plan(**overrides: object) -> AuthorizedGatherPlan:
    values = {
        "legal_policy_snapshot_sha256": "a" * 64,
        "aggregate_max_results": 9,
        "aggregate_max_cost_usd": Decimal("0.05"),
        "sources": (
            _source(GatherSource.EXA, cost="0.03"),
            _source(GatherSource.ARXIV),
            _source(GatherSource.SUBSTACK),
        ),
    }
    values.update(overrides)
    return AuthorizedGatherPlan.reviewed(_authority(), **values)  # type: ignore[arg-type]


def test_fingerprint_is_stable_and_contains_no_raw_account_identifier() -> None:
    first = _plan()
    second = _plan()

    assert first.fingerprint == second.fingerprint
    assert len(first.fingerprint) == 64
    assert "acct-1" not in str(first.canonical_dict())
    assert first.canonical_dict()["sources"] == [
        source.canonical_dict() for source in first.sources
    ]


def test_authority_and_policy_drift_change_the_fingerprint() -> None:
    baseline = _plan()
    other_authority = AuthorizedGatherPlan.reviewed(
        _authority("inv-2"),
        legal_policy_snapshot_sha256="a" * 64,
        aggregate_max_results=3,
        aggregate_max_cost_usd="0.03",
        sources=(_source(GatherSource.EXA, cost="0.03"),),
    )
    other_policy = _plan(legal_policy_snapshot_sha256="b" * 64)

    assert len({baseline.fingerprint, other_authority.fingerprint, other_policy.fingerprint}) == 3


@pytest.mark.parametrize(
    ("overrides", "message"),
    [
        ({"sources": ()}, "at least one"),
        (
            {"sources": (_source(GatherSource.EXA), _source(GatherSource.EXA))},
            "unique",
        ),
        (
            {"sources": (_source(GatherSource.SUBSTACK), _source(GatherSource.ARXIV))},
            "canonical order",
        ),
        (
            {"aggregate_max_results": 2, "sources": (_source(GatherSource.ARXIV),)},
            "result caps",
        ),
        ({"aggregate_max_results": 1.5}, "must be an integer"),
        (
            {
                "aggregate_max_cost_usd": "0.01",
                "sources": (_source(GatherSource.EXA, cost="0.02"),),
            },
            "cost caps",
        ),
    ],
)
def test_invalid_or_underfunded_plans_fail_closed(overrides: dict[str, object], message: str) -> None:
    with pytest.raises(ValueError, match=message):
        _plan(**overrides)


def test_source_plan_rejects_float_and_excess_precision() -> None:
    with pytest.raises(ValueError, match="decimal amount"):
        _source(GatherSource.EXA, cost=0.1)  # type: ignore[arg-type]
    with pytest.raises(ValueError, match="six decimal"):
        _source(GatherSource.EXA, cost="0.0000001")
    with pytest.raises(ValueError, match="must be an integer"):
        _source(GatherSource.ARXIV, results=1.5)  # type: ignore[arg-type]


def test_direct_dataclass_construction_cannot_bypass_reviewed_validation() -> None:
    with pytest.raises(ValueError, match="max_results must be an integer"):
        GatherSourcePlan(GatherSource.EXA, 1.5, 0, "v1")  # type: ignore[arg-type]
    valid = _plan()
    with pytest.raises(ValueError, match="aggregate_max_cost_micros"):
        AuthorizedGatherPlan(
            valid.version,
            valid.account_digest,
            valid.investigation_digest,
            valid.legal_policy_snapshot_sha256,
            valid.aggregate_max_results,
            1.5,  # type: ignore[arg-type]
            valid.sources,
        )
    with pytest.raises(ValueError, match="unsupported gather plan version"):
        AuthorizedGatherPlan(
            True,  # type: ignore[arg-type]
            valid.account_digest,
            valid.investigation_digest,
            valid.legal_policy_snapshot_sha256,
            valid.aggregate_max_results,
            valid.aggregate_max_cost_micros,
            valid.sources,
        )


def test_source_configuration_is_fingerprinted_and_validated() -> None:
    first = GatherSourcePlan.reviewed(
        source=GatherSource.SUBSTACK,
        max_results=1,
        max_cost_usd="0",
        policy_version="rss-v1",
        source_configuration_sha256="a" * 64,
    )
    second = GatherSourcePlan.reviewed(
        source=GatherSource.SUBSTACK,
        max_results=1,
        max_cost_usd="0",
        policy_version="rss-v1",
        source_configuration_sha256="b" * 64,
    )
    kwargs = {
        "legal_policy_snapshot_sha256": "c" * 64,
        "aggregate_max_results": 1,
        "aggregate_max_cost_usd": "0",
    }
    assert AuthorizedGatherPlan.reviewed(_authority(), sources=(first,), **kwargs).fingerprint != (
        AuthorizedGatherPlan.reviewed(_authority(), sources=(second,), **kwargs).fingerprint
    )
    with pytest.raises(ValueError, match="source_configuration_sha256"):
        GatherSourcePlan(GatherSource.SUBSTACK, 1, 0, "rss-v1", "invalid")
