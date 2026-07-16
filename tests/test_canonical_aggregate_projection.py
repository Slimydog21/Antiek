from __future__ import annotations

import base64
import hashlib
import json
import sqlite3
from concurrent.futures import ThreadPoolExecutor
from decimal import Decimal

import pytest
from nacl.signing import SigningKey

from runtime.research_runner.protocol import (
    BillingUnit,
    BoundedUsage,
    CostProjection,
    CostProjectionRequest,
    ProjectionDisposition,
    ProjectionRate,
)
from runtime.research_runner.provider_gateway import (
    ProviderCapabilities,
    ProviderReconciliation,
    ProviderSuccess,
    ReconciliationStatus,
    ResearchProviderGateway,
    canonical_digest,
)
from substrate.research_spend import ResearchSpendLedger, RunBinding
from substrate.twin_note_taker import (
    AUTHORITY_VERIFY_KEY_ENV,
    AssetContent,
    ProposedInsight,
    ProposedQuestion,
    TwinProposal,
)
from substrate.twin_recursion.budgeted_dispatch_worker import BudgetedTwinDispatchWorker
from substrate.twin_recursion.ledger import (
    TRIGGERS,
    SourceRevision,
    TwinIntegrityError,
    TwinRecursionLedger,
)
from substrate.twin_recursion.segmentation import build_segmentation_manifest
from substrate.twin_recursion.segmentation_completion import proposal_hash
from substrate.twin_recursion.segmentation_completion_ledger import (
    SegmentationCompletionLedger,
)
from substrate.twin_recursion.segmentation_ledger import TwinSegmentationLedger


def _proposal(label: str) -> TwinProposal:
    return TwinProposal(
        (ProposedInsight(f"Insight {label}", ""),),
        (ProposedQuestion(f"Question {label}?"),),
        f"Synthesis {label}",
    )


def _request(kind: str) -> CostProjectionRequest:
    return CostProjectionRequest(
        seam_id=f"twin.{kind}.generate",
        provider="qualified-provider",
        model="qualified-model",
        operation="generate_twin_proposal",
        bounded_usage=(BoundedUsage(BillingUnit.CALL, 1),),
    )


def _project(request: CostProjectionRequest) -> CostProjection:
    return CostProjection(
        seam_id=request.seam_id,
        provider=request.provider,
        model=request.model,
        operation=request.operation,
        bounded_usage=request.bounded_usage,
        rates=(ProjectionRate(BillingUnit.CALL, Decimal("0.50")),),
        rate_snapshot="cycle109-test-rate-v1",
        currency="USD",
        maximum_cost_usd=Decimal("0.50"),
        reservation_cents=50,
        disposition=ProjectionDisposition.HOLD_ELIGIBLE,
    )


class _Adapter:
    provider = "qualified-provider"
    model = "qualified-model"
    endpoint = "https://qualified.invalid/v1"
    capabilities = ProviderCapabilities(True, True, True, frozenset({BillingUnit.CALL}))

    def __init__(self, proposal: TwinProposal) -> None:
        self.proposal = proposal
        self.send_count = 0

    def _evidence(self, operation: object, key: str) -> dict[str, str]:
        return {
            "billing_status": "settled",
            "currency": "USD",
            "operation_digest": canonical_digest(operation),
            "output_sha256": proposal_hash(self.proposal),
            "provider_idempotency_key": key,
            "provider_request_id": "request-1",
            "provider_response_id": "response-1",
            "schema": "antiek.twin-provider-settlement.v1",
            "usage_json": json.dumps({"calls": 1}, separators=(",", ":")),
        }

    def send_once(
        self,
        operation: object,
        *,
        provider_idempotency_key: str,
        authorized_endpoint: str,
    ) -> ProviderSuccess[TwinProposal]:
        assert authorized_endpoint == self.endpoint
        self.send_count += 1
        return ProviderSuccess(
            self.proposal,
            40,
            self._evidence(operation, provider_idempotency_key),
        )

    def reconcile(
        self,
        *,
        provider_idempotency_key: str,
        authorized_endpoint: str,
    ) -> ProviderReconciliation[TwinProposal]:
        return ProviderReconciliation(ReconciliationStatus.NOT_CHARGED, {})


@pytest.fixture
def completed_parent(tmp_path, monkeypatch: pytest.MonkeyPatch):
    signing = SigningKey.generate()
    monkeypatch.setenv(
        AUTHORITY_VERIFY_KEY_ENV,
        base64.b64encode(bytes(signing.verify_key)).decode("ascii"),
    )
    asset = AssetContent(
        "oversized",
        "Oversized canonical source",
        "Canonical source line with information.\n" * 8_000,
        source_event_ids=("evt-source",),
    )
    manifest = build_segmentation_manifest(account_id="acct", asset=asset)
    registry = TwinSegmentationLedger(tmp_path / "segments.sqlite3")
    registry.register(manifest, account_id="acct", asset=asset)
    completions = SegmentationCompletionLedger(tmp_path / "completions.sqlite3")
    completions.register_manifest(manifest, asset=asset, registry=registry)
    spend = ResearchSpendLedger(tmp_path / "spend.sqlite3")
    gateway = ResearchProviderGateway(spend, projector=_project)
    binding = RunBinding("run", "acct", "session", "plan", 1)
    gateway.create_or_reopen_run(binding, ceiling_cents=500)
    worker = BudgetedTwinDispatchWorker(
        gateway=gateway,
        registry=registry,
        completions=completions,
        journal_path=tmp_path / "worker.sqlite3",
        signing_seed=bytes(signing),
    )
    adapters: list[_Adapter] = []
    for index in range(len(manifest.segments)):
        adapter = _Adapter(_proposal(f"segment-{index}"))
        adapters.append(adapter)
        worker.dispatch_segment(
            binding=binding,
            manifest=manifest,
            asset=asset,
            segment_index=index,
            projection_request=_request("segment"),
            adapter=adapter,
        )
    aggregate_adapter = _Adapter(_proposal("parent"))
    adapters.append(aggregate_adapter)
    worker.dispatch_aggregate(
        binding=binding,
        manifest=manifest,
        asset=asset,
        projection_request=_request("aggregate"),
        adapter=aggregate_adapter,
    )
    return asset, manifest, registry, completions, spend, binding, adapters, tmp_path


def test_paid_aggregate_becomes_one_canonical_non_recursive_twin(completed_parent) -> None:
    asset, manifest, registry, completions, spend, binding, adapters, tmp_path = completed_parent
    ledger = TwinRecursionLedger(tmp_path / "twins.sqlite3")
    revision = SourceRevision("acct", asset)
    spent_before = spend.balance(binding.run_id).authorized_spent_cents

    first = ledger.apply_paid_aggregate(
        revision, manifest=manifest, completions=completions, registry=registry
    )
    replay = ledger.apply_paid_aggregate(
        revision, manifest=manifest, completions=completions, registry=registry
    )

    assert first == replay
    assert first.state == "ready" and first.body is not None
    assert "Insight parent" in " ".join(first.body.agent_notes)
    assert spend.balance(binding.run_id).authorized_spent_cents == spent_before
    assert sum(adapter.send_count for adapter in adapters) == len(adapters)
    assert ledger.render_twin_html(first.binding_id).startswith("<!doctype html>")
    ledger.verify_integrity()
    child = ledger.register_materialized_twin(first.binding_id)
    assert child.state == "ready" and not child.twinnable


def test_projection_crash_leaves_pending_then_exact_replay_recovers(
    completed_parent,
) -> None:
    asset, manifest, registry, completions, _, _, _, tmp_path = completed_parent
    path = tmp_path / "crash-twins.sqlite3"

    def crash() -> None:
        raise RuntimeError("projection crash")

    revision = SourceRevision("acct", asset)
    crashing = TwinRecursionLedger(path, before_commit=crash)
    with pytest.raises(RuntimeError, match="projection crash"):
        crashing.apply_paid_aggregate(
            revision, manifest=manifest, completions=completions, registry=registry
        )
    assert (
        TwinRecursionLedger(path).get("acct", asset.asset_id, revision.source_hash).state
        == "pending_authorization"
    )

    recovered = TwinRecursionLedger(path).apply_paid_aggregate(
        revision, manifest=manifest, completions=completions, registry=registry
    )
    assert recovered.state == "ready"
    TwinRecursionLedger(path).verify_integrity()


def test_concurrent_projection_converges_on_one_binding_and_event(completed_parent) -> None:
    asset, manifest, registry, completions, _, _, _, tmp_path = completed_parent
    path = tmp_path / "concurrent-twins.sqlite3"
    revision = SourceRevision("acct", asset)
    ledger = TwinRecursionLedger(path)

    def project(_unused: int):
        return ledger.apply_paid_aggregate(
            revision, manifest=manifest, completions=completions, registry=registry
        )

    with ThreadPoolExecutor(max_workers=2) as pool:
        first, second = pool.map(project, range(2))
    assert first == second
    with sqlite3.connect(path) as con:
        assert con.execute("SELECT count(*) FROM twin_bindings").fetchone()[0] == 1
        assert (
            con.execute(
                "SELECT count(*) FROM twin_events WHERE event_type='completion_bound'"
            ).fetchone()[0]
            == 1
        )


def test_offline_manifest_substitution_is_detected_even_with_rehashed_row(
    completed_parent,
) -> None:
    asset, manifest, registry, completions, _, _, _, tmp_path = completed_parent
    path = tmp_path / "corrupt-twins.sqlite3"
    ledger = TwinRecursionLedger(path)
    ledger.apply_paid_aggregate(
        SourceRevision("acct", asset),
        manifest=manifest,
        completions=completions,
        registry=registry,
    )
    with sqlite3.connect(path) as con:
        con.execute("DROP TRIGGER twin_binding_immutable")
        raw = con.execute("SELECT completion_json FROM twin_bindings").fetchone()[0]
        value = json.loads(raw)
        value["manifest"]["body_chars"] += 1
        changed = json.dumps(value, sort_keys=True, separators=(",", ":"))
        con.execute(
            "UPDATE twin_bindings SET completion_json=?,completion_digest=?",
            (changed, hashlib.sha256(changed.encode()).hexdigest()),
        )
        con.execute(TRIGGERS["twin_binding_immutable"])

    with pytest.raises(TwinIntegrityError, match="provenance|source authority"):
        ledger.verify_integrity()


def test_oversized_source_cannot_bypass_aggregate_authority(completed_parent) -> None:
    asset, _, _, _, _, _, _, tmp_path = completed_parent
    with pytest.raises(ValueError, match="aggregate projection authority"):
        TwinRecursionLedger(tmp_path / "refused.sqlite3").register_source(
            SourceRevision("acct", asset)
        )


def test_duck_typed_completion_exporter_cannot_create_ready_binding(
    completed_parent,
) -> None:
    asset, manifest, registry, completions, _, _, _, tmp_path = completed_parent

    class ForgedExporter:
        paid_aggregate_export = completions.paid_aggregate_export

    ledger = TwinRecursionLedger(tmp_path / "forged-export.sqlite3")
    with pytest.raises(TypeError, match="exact canonical completion ledger"):
        ledger.apply_paid_aggregate(
            SourceRevision("acct", asset),
            manifest=manifest,
            completions=ForgedExporter(),  # type: ignore[arg-type]
            registry=registry,
        )
