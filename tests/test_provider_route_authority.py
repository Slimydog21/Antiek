from __future__ import annotations

from dataclasses import replace
from datetime import UTC, datetime, timedelta
from decimal import Decimal

import pytest

from runtime.research_runner.cost_projection import CostCatalogEntry, UnitRate
from runtime.research_runner.protocol import BillingUnit
from runtime.research_runner.provider_gateway import ProviderCapabilities
from runtime.research_runner.provider_qualification import (
    EvidenceStatus,
    ProviderQualification,
    QualificationEvidence,
    QualificationVerdict,
)
from runtime.research_runner.provider_route_authority import (
    ProviderRouteAuthorityResolver,
    ProviderRouteIdentity,
    RouteAuthorityCatalogEntry,
    RouteExecutionStatus,
    canonical_provider_endpoint,
)


class FakeHardCeilingAdapter:
    provider = "user-route"
    model = "model-a"

    def __init__(self, capabilities: ProviderCapabilities | None = None) -> None:
        self.capabilities = capabilities or ProviderCapabilities(True, True, True)

    def send_once(self, operation: object, *, provider_idempotency_key: str):
        raise AssertionError("authority resolution must not send")

    def reconcile(self, *, provider_idempotency_key: str):
        raise AssertionError("authority resolution must not reconcile")


def _identity(endpoint: str = "https://provider.example/v1") -> ProviderRouteIdentity:
    return ProviderRouteIdentity(
        "openai_compat", "model-a", endpoint, "user.prompt.generate", "generate"
    )


def _cost(*, expires_at: datetime | None = None) -> CostCatalogEntry:
    return CostCatalogEntry(
        seam_id="user.prompt.generate",
        provider="provider-family",
        model="model-a",
        operation="generate",
        rates=(
            UnitRate(BillingUnit.INPUT_TOKEN, Decimal("0.000001")),
            UnitRate(BillingUnit.OUTPUT_TOKEN, Decimal("0.000004")),
        ),
        snapshot="provider-family-2026-07-16",
        expires_at=expires_at or datetime.now(UTC) + timedelta(days=30),
        durable_idempotency=True,
        authoritative_reconciliation=True,
        hidden_retries_disabled=True,
    )


def _qualification(
    overrides: dict[str, EvidenceStatus] | None = None,
) -> ProviderQualification:
    overrides = overrides or {}
    evidence = {
        dimension: QualificationEvidence(
            status=overrides.get(dimension, EvidenceStatus.PASS),
            source_url="https://provider.example/contract",
            finding="Exact provider contract evidence.",
        )
        for dimension in (
            "pinned_pricing",
            "durable_idempotency",
            "hidden_retries_disabled",
            "authoritative_reconciliation",
            "stable_provider_evidence",
        )
    }
    return ProviderQualification(
        provider="provider-family",
        model="model-a",
        operation="generate",
        checked_at="2026-07-16",
        verdict=QualificationVerdict.QUALIFIED,
        evidence=evidence,
    )


def _entry(
    identity: ProviderRouteIdentity | None = None,
    cost: CostCatalogEntry | None = None,
    qualification: ProviderQualification | None = None,
    *,
    qualified_provider_kind: str | None = None,
    qualified_endpoint: str | None = None,
) -> RouteAuthorityCatalogEntry:
    identity = identity or _identity()
    return RouteAuthorityCatalogEntry(
        identity,
        cost or _cost(),
        qualification or _qualification(),
        qualified_provider_kind or identity.provider_kind,
        qualified_endpoint or identity.endpoint,
    )


def _resolver(
    *,
    identity: ProviderRouteIdentity | None = None,
    cost: CostCatalogEntry | None = None,
    qualification: ProviderQualification | None = None,
    adapter: FakeHardCeilingAdapter | None = None,
):
    identity = identity or _identity()
    adapter = adapter or FakeHardCeilingAdapter()
    live: dict[str, object] = {adapter.provider: adapter}
    resolver = ProviderRouteAuthorityResolver(
        (_entry(identity, cost, qualification),),
        adapter_lookup=live.get,
    )
    resolver.register_adapter(identity, adapter.provider, adapter)
    return resolver, adapter, live


def test_exact_server_authorities_make_route_executable_without_dispatch() -> None:
    resolver, adapter, _ = _resolver()
    result = resolver.resolve(_identity(), provider_id=adapter.provider)
    assert result.pricing_status == "known"
    assert result.rate_snapshot == "provider-family-2026-07-16"
    assert result.hard_ceiling_eligible is True
    assert result.execution_status is RouteExecutionStatus.EXECUTABLE


def test_missing_endpoint_or_stale_price_remains_unknown() -> None:
    resolver, adapter, _ = _resolver()
    mismatch = resolver.resolve(
        _identity("https://other.example/v1"), provider_id=adapter.provider
    )
    assert mismatch.execution_status is RouteExecutionStatus.BLOCKED_UNKNOWN_PRICING
    assert mismatch.pricing_status == "unknown"

    expired, adapter, _ = _resolver(
        cost=_cost(expires_at=datetime.now(UTC) - timedelta(seconds=1))
    )
    stale = expired.resolve(_identity(), provider_id=adapter.provider)
    assert stale.execution_status is RouteExecutionStatus.BLOCKED_UNKNOWN_PRICING


@pytest.mark.parametrize(
    ("dimension", "status"),
    [
        ("durable_idempotency", RouteExecutionStatus.BLOCKED_IDEMPOTENCY_UNPROVEN),
        (
            "authoritative_reconciliation",
            RouteExecutionStatus.BLOCKED_RECONCILIATION_UNPROVEN,
        ),
        ("hidden_retries_disabled", RouteExecutionStatus.BLOCKED_HIDDEN_RETRIES),
    ],
)
def test_each_gateway_capability_fails_with_typed_status(
    dimension: str, status: RouteExecutionStatus
) -> None:
    qualification = _qualification({dimension: EvidenceStatus.UNPROVEN})
    qualification = replace(qualification, verdict=QualificationVerdict.REFUSED)
    resolver, adapter, _ = _resolver(qualification=qualification)
    assert resolver.resolve(_identity(), provider_id=adapter.provider).execution_status is status


def test_catalog_capability_claim_must_also_pass_for_execution() -> None:
    resolver, adapter, _ = _resolver(cost=replace(_cost(), durable_idempotency=False))
    result = resolver.resolve(_identity(), provider_id=adapter.provider)
    assert result.execution_status is RouteExecutionStatus.BLOCKED_IDEMPOTENCY_UNPROVEN


def test_partial_qualification_cannot_mint_execution_authority() -> None:
    identity = _identity()
    qualification = _qualification()
    partial = ProviderQualification(
        provider=qualification.provider,
        model=qualification.model,
        operation=qualification.operation,
        checked_at=qualification.checked_at,
        verdict=qualification.verdict,
        evidence={
            key: value
            for key, value in qualification.evidence.items()
            if key not in {"pinned_pricing", "stable_provider_evidence"}
        },
    )
    adapter = FakeHardCeilingAdapter()
    resolver = ProviderRouteAuthorityResolver(
        (_entry(identity, qualification=partial),),
        adapter_lookup=lambda _provider_id: adapter,
    )
    resolver.register_adapter(identity, adapter.provider, adapter)

    authority = resolver.resolve(identity, provider_id=adapter.provider)

    assert authority.execution_status is RouteExecutionStatus.BLOCKED_QUALIFICATION
    assert not authority.hard_ceiling_eligible


def test_missing_replaced_or_wrong_route_adapter_fails_closed() -> None:
    identity = _identity()
    entry = _entry(identity)
    no_adapter = ProviderRouteAuthorityResolver((entry,))
    result = no_adapter.resolve(identity, provider_id="user-route")
    assert result.execution_status is RouteExecutionStatus.BLOCKED_NO_ADAPTER

    resolver, adapter, live = _resolver()
    live[adapter.provider] = FakeHardCeilingAdapter()
    replaced = resolver.resolve(identity, provider_id=adapter.provider)
    assert replaced.execution_status is RouteExecutionStatus.BLOCKED_ADAPTER_MISMATCH
    wrong_id = resolver.resolve(identity, provider_id="user-other")
    assert wrong_id.execution_status is RouteExecutionStatus.BLOCKED_ADAPTER_MISMATCH

    live[adapter.provider] = adapter
    adapter.model = "retargeted-model"
    mutated = resolver.resolve(identity, provider_id=adapter.provider)
    assert mutated.execution_status is RouteExecutionStatus.BLOCKED_ADAPTER_MISMATCH


def test_http_endpoint_can_be_selected_but_never_catalogued_for_paid_execution() -> None:
    identity = _identity("http://localhost:8080/v1/")
    assert identity.endpoint == "http://localhost:8080/v1"
    with pytest.raises(ValueError, match="HTTPS"):
        _entry(identity)


def test_endpoint_canonicalization_is_exact_and_credential_free() -> None:
    assert canonical_provider_endpoint("HTTPS://Provider.Example:443/v1/") == (
        "https://provider.example/v1"
    )
    with pytest.raises(ValueError, match="credential-free"):
        canonical_provider_endpoint("https://user:secret@provider.example/v1")
    assert canonical_provider_endpoint("https://[::1]:443/v1/") == "https://[::1]/v1"
    assert canonical_provider_endpoint("https://[::1]:8443/v1/") == (
        "https://[::1]:8443/v1"
    )


def test_duplicate_billing_units_cannot_enter_route_authority() -> None:
    duplicate = replace(
        _cost(),
        rates=(
            UnitRate(BillingUnit.CALL, Decimal("0.01")),
            UnitRate(BillingUnit.CALL, Decimal("0.02")),
        ),
    )
    with pytest.raises(ValueError, match="repeats a billing unit"):
        _entry(cost=duplicate)


def test_price_for_another_dispatch_seam_cannot_be_borrowed() -> None:
    with pytest.raises(ValueError, match="differs from exact identity"):
        _entry(cost=replace(_cost(), seam_id="other.workload"))


def test_qualification_authority_is_bound_to_exact_provider_route() -> None:
    with pytest.raises(ValueError, match="provider kind"):
        _entry(qualified_provider_kind="anthropic")
    with pytest.raises(ValueError, match="provider endpoint"):
        _entry(qualified_endpoint="https://other.example/v1")

    canonical_equivalent = _entry(
        qualified_endpoint="HTTPS://Provider.Example:443/v1/"
    )
    assert canonical_equivalent.identity.endpoint == "https://provider.example/v1"


@pytest.mark.parametrize("snapshot", ["", "   "])
def test_empty_pricing_snapshot_never_mints_execution_authority(snapshot: str) -> None:
    resolver, adapter, _ = _resolver(cost=replace(_cost(), snapshot=snapshot))
    authority = resolver.resolve(_identity(), provider_id=adapter.provider)

    assert authority.execution_status is RouteExecutionStatus.BLOCKED_UNKNOWN_PRICING
    assert authority.pricing_status == "unknown"
    assert not authority.hard_ceiling_eligible
