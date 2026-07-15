from __future__ import annotations

import json
from dataclasses import replace
from pathlib import Path

import pytest

from runtime.research_runner.cost_projection import CostCatalogEntry, UnitRate
from runtime.research_runner.protocol import BillingUnit
from runtime.research_runner.provider_qualification import (
    EvidenceStatus,
    ProviderQualification,
    QualificationEvidence,
    QualificationVerdict,
    load_provider_qualifications,
    require_paid_catalog_qualifications,
)

ROOT = Path(__file__).parents[1]


def _catalog_entry() -> CostCatalogEntry:
    from datetime import UTC, datetime
    from decimal import Decimal

    return CostCatalogEntry(
        seam_id="test.paid",
        provider="provider-a",
        model="model-a",
        operation="generate",
        rates=(UnitRate(BillingUnit.CALL, Decimal("0.01")),),
        snapshot="test-v1",
        expires_at=datetime.max.replace(tzinfo=UTC),
        durable_idempotency=True,
        authoritative_reconciliation=True,
        hidden_retries_disabled=True,
    )


def _qualification(status: EvidenceStatus = EvidenceStatus.PASS) -> ProviderQualification:
    evidence = {
        dimension: QualificationEvidence(
            status=status,
            source_url="https://provider.example/docs",
            finding="Provider contract proof.",
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
        provider="provider-a",
        model="model-a",
        operation="generate",
        checked_at="2026-07-13",
        verdict=QualificationVerdict.QUALIFIED,
        evidence=evidence,
    )


def test_checked_in_provider_registry_is_closed_and_refuses_all_candidates() -> None:
    qualifications = load_provider_qualifications()
    assert {item.provider for item in qualifications} == {
        "exa",
        "openai",
        "perplexity",
        "tavily",
    }
    assert all(item.verdict is QualificationVerdict.REFUSED for item in qualifications)
    assert all(not item.fully_qualified for item in qualifications)
    assert all(
        set(item.evidence)
        == {
            "pinned_pricing",
            "durable_idempotency",
            "hidden_retries_disabled",
            "authoritative_reconciliation",
            "stable_provider_evidence",
        }
        for item in qualifications
    )


def test_paid_catalog_capability_claim_requires_exact_fully_passing_route() -> None:
    entry = _catalog_entry()
    with pytest.raises(ValueError, match="without fully passing"):
        require_paid_catalog_qualifications((entry,), ())

    qualification = _qualification()
    require_paid_catalog_qualifications((entry,), (qualification,))

    wrong_model = replace(qualification, model="model-b")
    with pytest.raises(ValueError, match="without fully passing"):
        require_paid_catalog_qualifications((entry,), (wrong_model,))


def test_refused_or_non_passing_qualification_cannot_authorize_catalog() -> None:
    entry = _catalog_entry()
    refused = replace(_qualification(), verdict=QualificationVerdict.REFUSED)
    with pytest.raises(ValueError, match="without fully passing"):
        require_paid_catalog_qualifications((entry,), (refused,))

    failed = _qualification(EvidenceStatus.FAIL)
    with pytest.raises(ValueError, match="without fully passing"):
        require_paid_catalog_qualifications((entry,), (failed,))


def test_registry_parser_rejects_qualified_route_with_unproven_dimension(
    tmp_path: Path,
) -> None:
    source = ROOT / "runtime/research_runner/provider_qualification.json"
    payload = json.loads(source.read_text(encoding="utf-8"))
    entry = payload["qualifications"][0]
    entry["verdict"] = "qualified"
    path = tmp_path / "qualification.json"
    path.write_text(json.dumps(payload), encoding="utf-8")

    with pytest.raises(ValueError, match="non-passing evidence"):
        load_provider_qualifications(path)


def test_registry_parser_rejects_non_https_evidence(tmp_path: Path) -> None:
    source = ROOT / "runtime/research_runner/provider_qualification.json"
    payload = json.loads(source.read_text(encoding="utf-8"))
    payload["qualifications"][0]["evidence"]["pinned_pricing"]["source_url"] = (
        "notes/provider-pricing"
    )
    path = tmp_path / "qualification.json"
    path.write_text(json.dumps(payload), encoding="utf-8")

    with pytest.raises(ValueError, match="HTTPS"):
        load_provider_qualifications(path)
