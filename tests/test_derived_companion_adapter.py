from __future__ import annotations

import hashlib
import json
from dataclasses import dataclass
from pathlib import Path

import pytest

from runtime.research_runner.derived_companion_adapter import (
    CompanionAdapterError,
    CompanionAdapterRegistry,
    CompanionAdapterRoute,
    NormalizedCompanionSuccess,
    ProviderResponseEvidence,
    select_qualified_companion_adapter,
)
from runtime.research_runner.derived_companion_execution import (
    project_derived_companion_execution,
)
from runtime.research_runner.provider_qualification import (
    EvidenceStatus,
    ProviderQualification,
    QualificationEvidence,
    QualificationVerdict,
)


def _candidate(text: str = "A grounded claim.") -> str:
    return json.dumps(
        {
            "claims": [{"citation_ids": ["dchunk_" + "1" * 64], "text": text}],
            "schema_version": "antiek.derived-companion-answer.v1",
        },
        sort_keys=True,
        separators=(",", ":"),
    )


def _qualification(
    route: CompanionAdapterRoute, *, qualified: bool = True, passing: bool = True
) -> ProviderQualification:
    status = EvidenceStatus.PASS if passing else EvidenceStatus.UNPROVEN
    evidence = {
        dimension: QualificationEvidence(status, f"https://example.com/{dimension}", "checked")
        for dimension in (
            "pinned_pricing",
            "durable_idempotency",
            "hidden_retries_disabled",
            "authoritative_reconciliation",
            "stable_provider_evidence",
        )
    }
    return ProviderQualification(
        provider=route.provider,
        model=route.model,
        operation=route.operation,
        checked_at="2026-07-15",
        verdict=(
            QualificationVerdict.QUALIFIED if qualified else QualificationVerdict.REFUSED
        ),
        evidence=evidence,
    )


@dataclass(frozen=True)
class _FakeAdapter:
    route: CompanionAdapterRoute

    def normalize_success(self, response: object) -> NormalizedCompanionSuccess:
        if not isinstance(response, dict) or set(response) != {"candidate", "response_id"}:
            raise ValueError("fake provider response is invalid")
        return NormalizedCompanionSuccess(
            candidate_json=response["candidate"],
            response_evidence=ProviderResponseEvidence(
                provider_response_id=response["response_id"],
                response_body_sha256="2" * 64,
                usage_sha256="3" * 64,
            ),
        )


@dataclass(frozen=True)
class _StringAdapter:
    route: CompanionAdapterRoute

    def normalize_success(self, response: str) -> NormalizedCompanionSuccess:
        return NormalizedCompanionSuccess(
            response, ProviderResponseEvidence("typed-1", "4" * 64, "5" * 64)
        )


def test_registry_is_empty_by_default_and_route_identity_is_closed() -> None:
    assert len(CompanionAdapterRegistry()) == 0
    with pytest.raises(ValueError, match="canonical"):
        CompanionAdapterRoute(" provider", "model")
    with pytest.raises(ValueError, match="operation"):
        CompanionAdapterRoute("provider", "model", "search")


def test_registration_and_qualification_are_independently_insufficient() -> None:
    route = CompanionAdapterRoute("future", "grounded")
    adapter = _FakeAdapter(route)
    with pytest.raises(CompanionAdapterError, match="not fully qualified"):
        select_qualified_companion_adapter(
            route, (), CompanionAdapterRegistry((adapter,)), adapter
        )
    with pytest.raises(CompanionAdapterError, match="not registered"):
        select_qualified_companion_adapter(
            route, (_qualification(route),), CompanionAdapterRegistry(), adapter
        )


@pytest.mark.parametrize(
    ("qualified", "passing"), [(False, True), (False, False), (True, False)]
)
def test_refused_or_incomplete_evidence_cannot_promote_adapter(
    qualified: bool, passing: bool
) -> None:
    route = CompanionAdapterRoute("future", "grounded")
    registry_adapter = _FakeAdapter(route)
    registry = CompanionAdapterRegistry((registry_adapter,))
    with pytest.raises(CompanionAdapterError, match="not fully qualified"):
        select_qualified_companion_adapter(
            route,
            (_qualification(route, qualified=qualified, passing=passing),),
            registry,
            registry_adapter,
        )


@pytest.mark.parametrize(
    "evidence",
    [
        {},
        {
            "unexpected": QualificationEvidence(
                EvidenceStatus.PASS, "https://example.com/unexpected", "checked"
            )
        },
    ],
)
def test_directly_constructed_incomplete_evidence_cannot_pass_dual_gate(
    evidence: dict[str, QualificationEvidence],
) -> None:
    route = CompanionAdapterRoute("future", "grounded")
    qualification = _qualification(route)
    malformed = ProviderQualification(
        provider=qualification.provider,
        model=qualification.model,
        operation=qualification.operation,
        checked_at=qualification.checked_at,
        verdict=QualificationVerdict.QUALIFIED,
        evidence=evidence,
    )
    assert malformed.fully_qualified is False
    adapter = _FakeAdapter(route)
    with pytest.raises(CompanionAdapterError, match="not fully qualified"):
        select_qualified_companion_adapter(
            route, (malformed,), CompanionAdapterRegistry((adapter,)), adapter
        )


def test_qualification_evidence_cannot_be_mutated_after_construction() -> None:
    qualification = _qualification(CompanionAdapterRoute("future", "grounded"))
    with pytest.raises(TypeError):
        qualification.evidence["pinned_pricing"] = QualificationEvidence(  # type: ignore[index]
            EvidenceStatus.FAIL, "https://example.com/changed", "changed"
        )
    assert qualification.fully_qualified is True


def test_exact_dual_gate_selects_only_the_matching_adapter() -> None:
    route = CompanionAdapterRoute("future", "grounded")
    other = CompanionAdapterRoute("future", "other")
    adapter = _FakeAdapter(route)
    selected = select_qualified_companion_adapter(
        route,
        (_qualification(route), _qualification(other)),
        CompanionAdapterRegistry((adapter, _FakeAdapter(other))),
        adapter,
    )
    assert selected is adapter
    normalized = selected.normalize_success(
        {"candidate": _candidate(), "response_id": "response-1"}
    )
    assert normalized.candidate_json == _candidate()
    expected_material = json.dumps(
        {
            "provider_response_id": "response-1",
            "response_body_sha256": "2" * 64,
            "usage_sha256": "3" * 64,
        },
        sort_keys=True,
        separators=(",", ":"),
    )
    assert normalized.provider_response_digest == hashlib.sha256(
        expected_material.encode()
    ).hexdigest()
    assert len(normalized.provider_response_digest) == 64
    changed = _FakeAdapter(route).normalize_success(
        {"candidate": _candidate(), "response_id": "response-2"}
    )
    assert changed.provider_response_digest != normalized.provider_response_digest


def test_selection_preserves_private_response_type() -> None:
    route = CompanionAdapterRoute("future", "typed")
    adapter = _StringAdapter(route)
    selected: _StringAdapter = select_qualified_companion_adapter(
        route, (_qualification(route),), CompanionAdapterRegistry((adapter,)), adapter
    )
    assert selected.normalize_success(_candidate()).candidate_json == _candidate()


def test_exact_route_mismatch_cannot_borrow_other_route_authority() -> None:
    route = CompanionAdapterRoute("future", "grounded")
    other = CompanionAdapterRoute("future", "other")
    route_adapter = _FakeAdapter(route)
    with pytest.raises(CompanionAdapterError, match="not registered"):
        select_qualified_companion_adapter(
            route,
            (_qualification(route), _qualification(other)),
            CompanionAdapterRegistry((_FakeAdapter(other),)),
            route_adapter,
        )


def test_duplicate_registry_and_qualification_routes_fail_closed() -> None:
    route = CompanionAdapterRoute("future", "grounded")
    adapter = _FakeAdapter(route)
    with pytest.raises(CompanionAdapterError, match="duplicate companion adapter"):
        CompanionAdapterRegistry((adapter, adapter))
    with pytest.raises(CompanionAdapterError, match="duplicate companion route"):
        select_qualified_companion_adapter(
            route,
            (_qualification(route), _qualification(route)),
            CompanionAdapterRegistry((adapter,)),
            adapter,
        )


@pytest.mark.parametrize(
    "candidate",
    [
        '{"claims":[]}',
        '{"claims": [], "schema_version":"antiek.derived-companion-answer.v1"}',
        '{"claims":[{"citation_ids":[],"extra":1,"text":"x"}],'
        '"schema_version":"antiek.derived-companion-answer.v1"}',
    ],
)
def test_normalized_success_refuses_noncanonical_or_invalid_candidates(candidate: str) -> None:
    with pytest.raises(ValueError, match="canonical candidate"):
        NormalizedCompanionSuccess(
            candidate, ProviderResponseEvidence("response-1", "2" * 64, "3" * 64)
        )


def test_response_evidence_refuses_non_sha_or_unbounded_identity() -> None:
    with pytest.raises(ValueError, match="lowercase SHA-256"):
        ProviderResponseEvidence("response-1", "A" * 64, "3" * 64)
    with pytest.raises(ValueError, match="identity"):
        ProviderResponseEvidence("x" * 513, "2" * 64, "3" * 64)


def test_registered_adapter_cannot_promote_public_execution_projection(tmp_path: Path) -> None:
    route = CompanionAdapterRoute("future", "grounded")
    adapter = _FakeAdapter(route)
    assert select_qualified_companion_adapter(
        route, (_qualification(route),), CompanionAdapterRegistry((adapter,)), adapter
    ) is adapter
    evidence = {
        dimension: {
            "status": "pass",
            "source_url": f"https://example.com/{dimension}",
            "finding": "checked",
        }
        for dimension in (
            "pinned_pricing",
            "durable_idempotency",
            "hidden_retries_disabled",
            "authoritative_reconciliation",
            "stable_provider_evidence",
        )
    }
    path = tmp_path / "qualifications.json"
    path.write_text(json.dumps({
        "schema_version": 1,
        "qualifications": [{
            "provider": route.provider, "model": route.model,
            "operation": route.operation, "checked_at": "2026-07-15",
            "verdict": "qualified", "evidence": evidence,
        }],
    }))
    projection = project_derived_companion_execution(
        derived_asset_id="ast_" + "1" * 32,
        revision_id="rev_" + "2" * 32,
        content_sha256="3" * 64,
        generation=1,
        qualification_path=path,
    )
    assert projection["reason"] == "executable_route_not_registered"
    assert projection["available"] is False
    assert projection["reservable"] is False
    assert projection["dispatch_authorized"] is False
