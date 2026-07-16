from __future__ import annotations

import base64
import hashlib
import json
import sqlite3
from concurrent.futures import ThreadPoolExecutor
from decimal import Decimal
from pathlib import Path

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
    ProviderOutcomeUnknown,
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
from substrate.twin_recursion.budgeted_dispatch_worker import (
    BudgetedTwinDispatchWorker,
    TwinDispatchIntegrityError,
)
from substrate.twin_recursion.segmentation import build_segmentation_manifest
from substrate.twin_recursion.segmentation_completion import (
    SegmentationCompletionError,
    SegmentCompletionReceiptV2,
    canonical_json,
    proposal_hash,
    receipt_payload,
)
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


def _request(kind: str = "segment") -> CostProjectionRequest:
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
        rate_snapshot="qualified-test-rate-v1",
        currency="USD",
        maximum_cost_usd=Decimal("0.50"),
        reservation_cents=50,
        disposition=ProjectionDisposition.HOLD_ELIGIBLE,
    )


def _fail_once(target: str):
    failed = False

    def inject(checkpoint: str) -> None:
        nonlocal failed
        if checkpoint == target and not failed:
            failed = True
            raise RuntimeError(f"injected crash at {target}")

    return inject


class _Adapter:
    provider = "qualified-provider"
    model = "qualified-model"
    endpoint = "https://qualified.invalid/v1"
    capabilities = ProviderCapabilities(
        True, True, True, frozenset({BillingUnit.CALL})
    )

    def __init__(self, proposal: TwinProposal, *, corrupt_evidence: bool = False) -> None:
        self.proposal = proposal
        self.corrupt_evidence = corrupt_evidence
        self.send_count = 0
        self.last_operation: object | None = None

    def _evidence(self, operation: object, key: str) -> dict[str, str]:
        digest = canonical_digest(operation)
        return {
            "billing_status": "settled",
            "currency": "USD",
            "operation_digest": "0" * 64 if self.corrupt_evidence else digest,
            "output_sha256": proposal_hash(self.proposal),
            "provider_idempotency_key": key,
            "provider_request_id": "request-1",
            "provider_response_id": "response-1",
            "schema": "antiek.twin-provider-settlement.v1",
            "usage_json": json.dumps({"calls": 1}, sort_keys=True, separators=(",", ":")),
        }

    def send_once(
        self, operation: object, *, provider_idempotency_key: str, authorized_endpoint: str
    ) -> ProviderSuccess[TwinProposal]:
        assert authorized_endpoint == self.endpoint
        self.send_count += 1
        self.last_operation = operation
        return ProviderSuccess(
            self.proposal, 40, self._evidence(operation, provider_idempotency_key)
        )

    def reconcile(
        self, *, provider_idempotency_key: str, authorized_endpoint: str
    ) -> ProviderReconciliation[TwinProposal]:
        assert self.last_operation is not None
        return ProviderReconciliation(
            ReconciliationStatus.CHARGED,
            self._evidence(self.last_operation, provider_idempotency_key),
            actual_cents=40,
            value=self.proposal,
        )


class _AmbiguousAdapter(_Adapter):
    def send_once(
        self, operation: object, *, provider_idempotency_key: str, authorized_endpoint: str
    ) -> ProviderSuccess[TwinProposal]:
        self.send_count += 1
        self.last_operation = operation
        raise TimeoutError("provider outcome is ambiguous")


@pytest.fixture
def setup(tmp_path, monkeypatch: pytest.MonkeyPatch):
    signing = SigningKey.generate()
    monkeypatch.setenv(
        AUTHORITY_VERIFY_KEY_ENV,
        base64.b64encode(bytes(signing.verify_key)).decode("ascii"),
    )
    asset = AssetContent(
        "asset", "Oversized source", "source line\n" * 20_000,
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
    return worker, binding, manifest, asset, completions, registry, spend


def test_segment_reserves_settles_signs_and_replays_without_spend(setup) -> None:
    worker, binding, manifest, asset, _, _, spend = setup
    adapter = _Adapter(_proposal("segment"))

    first = worker.dispatch_segment(
        binding=binding,
        manifest=manifest,
        asset=asset,
        segment_index=0,
        projection_request=_request(),
        adapter=adapter,
    )
    replay = worker.dispatch_segment(
        binding=binding,
        manifest=manifest,
        asset=asset,
        segment_index=0,
        projection_request=_request(),
        adapter=adapter,
    )

    assert first == replay
    assert adapter.send_count == 1
    assert first.completed_segments == 1
    balance = spend.balance(binding.run_id)
    assert balance.authorized_spent_cents == 40
    assert balance.held_cents == 0
    with sqlite3.connect(worker.journal.path) as con:
        row = con.execute(
            "SELECT s.run_id,s.hold_id,s.provider_idempotency_key,r.receipt_json "
            "FROM worker_settlements s JOIN worker_receipts r USING(operation_digest)"
        ).fetchone()
    receipt = json.loads(row[3])
    assert row[0] == binding.run_id
    assert receipt["paid_hold_id"] == receipt["budget_authority_id"] == row[1]
    assert receipt["provider_idempotency_key_sha256"]


def test_provider_evidence_must_bind_exact_operation_before_settlement(setup) -> None:
    worker, binding, manifest, asset, _, _, spend = setup
    adapter = _Adapter(_proposal("bad"), corrupt_evidence=True)

    with pytest.raises(ProviderOutcomeUnknown):
        worker.dispatch_segment(
            binding=binding,
            manifest=manifest,
            asset=asset,
            segment_index=0,
            projection_request=_request(),
            adapter=adapter,
        )

    recovery = spend.recovery_work(binding.run_id)
    assert recovery and recovery[0].state == "unknown"


def test_aggregate_requires_and_binds_every_ordered_segment(setup) -> None:
    worker, binding, manifest, asset, completions, registry, _ = setup
    with pytest.raises(SegmentationCompletionError, match="all ordered segment completions"):
        worker.dispatch_aggregate(
            binding=binding,
            manifest=manifest,
            asset=asset,
            projection_request=_request("aggregate"),
            adapter=_Adapter(_proposal("aggregate")),
        )

    for index in range(len(manifest.segments)):
        worker.dispatch_segment(
            binding=binding,
            manifest=manifest,
            asset=asset,
            segment_index=index,
            projection_request=_request(),
            adapter=_Adapter(_proposal(str(index))),
        )
    result = worker.dispatch_aggregate(
        binding=binding,
        manifest=manifest,
        asset=asset,
        projection_request=_request("aggregate"),
        adapter=_Adapter(_proposal("aggregate")),
    )

    assert result.parent_ready
    assert completions.get(
        manifest.account_id,
        manifest.asset_id,
        manifest.parent_source_hash,
        asset=asset,
        registry=registry,
    ).parent_ready


def test_ambiguous_send_recovers_exact_output_without_resend(setup) -> None:
    worker, binding, manifest, asset, _, _, _ = setup
    adapter = _AmbiguousAdapter(_proposal("recovered"))

    with pytest.raises(ProviderOutcomeUnknown):
        worker.dispatch_segment(
            binding=binding, manifest=manifest, asset=asset, segment_index=0,
            projection_request=_request(), adapter=adapter,
        )
    recovered = worker.dispatch_segment(
        binding=binding, manifest=manifest, asset=asset, segment_index=0,
        projection_request=_request(), adapter=adapter,
    )

    assert recovered.completed_segments == 1
    assert adapter.send_count == 1


def test_concurrent_exact_dispatch_converges_on_one_send(setup) -> None:
    worker, binding, manifest, asset, completions, _, spend = setup
    adapter = _Adapter(_proposal("concurrent"))

    def dispatch() -> int:
        return worker.dispatch_segment(
            binding=binding, manifest=manifest, asset=asset, segment_index=0,
            projection_request=_request(), adapter=adapter,
        ).completed_segments

    with ThreadPoolExecutor(max_workers=2) as pool:
        assert list(pool.map(lambda _: dispatch(), range(2))) == [1, 1]
    assert adapter.send_count == 1
    assert spend.balance(binding.run_id).authorized_spent_cents == 40
    with sqlite3.connect(spend._db_path) as con:
        assert con.execute("SELECT COUNT(*) FROM research_spend_holds").fetchone()[0] == 1
        assert con.execute(
            "SELECT COUNT(*) FROM research_spend_events WHERE event_kind='hold_settled'"
        ).fetchone()[0] == 1
    with sqlite3.connect(worker.journal.path) as con:
        assert con.execute("SELECT COUNT(*) FROM worker_proposals").fetchone()[0] == 1
        assert con.execute("SELECT COUNT(*) FROM worker_settlements").fetchone()[0] == 1
        assert con.execute("SELECT COUNT(*) FROM worker_receipts").fetchone()[0] == 1
    with sqlite3.connect(completions.path) as con:
        assert con.execute(
            "SELECT COUNT(*) FROM segment_completion_bindings"
        ).fetchone()[0] == 1


def test_crash_after_output_staging_reconciles_without_resend(setup) -> None:
    worker, binding, manifest, asset, _, _, spend = setup
    adapter = _Adapter(_proposal("staged"))
    worker._failure_injector = _fail_once("after_output_staged")

    with pytest.raises(ProviderOutcomeUnknown):
        worker.dispatch_segment(
            binding=binding, manifest=manifest, asset=asset, segment_index=0,
            projection_request=_request(), adapter=adapter,
        )
    recovered = worker.dispatch_segment(
        binding=binding, manifest=manifest, asset=asset, segment_index=0,
        projection_request=_request(), adapter=adapter,
    )

    assert recovered.completed_segments == 1
    assert adapter.send_count == 1
    assert spend.balance(binding.run_id).authorized_spent_cents == 40


@pytest.mark.parametrize("checkpoint", ["after_settlement_bound", "after_receipt_persisted"])
def test_crash_after_settlement_recovers_without_new_spend(setup, checkpoint: str) -> None:
    worker, binding, manifest, asset, _, _, spend = setup
    adapter = _Adapter(_proposal(checkpoint))
    worker._failure_injector = _fail_once(checkpoint)

    with pytest.raises(RuntimeError, match=f"injected crash at {checkpoint}"):
        worker.dispatch_segment(
            binding=binding, manifest=manifest, asset=asset, segment_index=0,
            projection_request=_request(), adapter=adapter,
        )
    recovered = worker.dispatch_segment(
        binding=binding, manifest=manifest, asset=asset, segment_index=0,
        projection_request=_request(), adapter=adapter,
    )

    assert recovered.completed_segments == 1
    assert adapter.send_count == 1
    assert spend.balance(binding.run_id).authorized_spent_cents == 40


def test_wrong_signing_key_refuses_before_receipt_journal(setup) -> None:
    worker, _, _, _, completions, registry, _ = setup
    wrong_path = Path(worker.journal.path).with_name("wrong-key-worker.sqlite3")
    with pytest.raises(ValueError, match="active twin completion authority"):
        BudgetedTwinDispatchWorker(
            gateway=worker.gateway,
            registry=registry,
            completions=completions,
            journal_path=wrong_path,
            signing_seed=bytes(SigningKey.generate()),
        )
    with sqlite3.connect(wrong_path) as con:
        assert con.execute("SELECT COUNT(*) FROM worker_receipts").fetchone()[0] == 0


def test_completion_read_rejects_forged_persisted_signature(setup) -> None:
    worker, binding, manifest, asset, completions, registry, _ = setup
    worker.dispatch_segment(
        binding=binding, manifest=manifest, asset=asset, segment_index=0,
        projection_request=_request(), adapter=_Adapter(_proposal("signed")),
    )
    with sqlite3.connect(completions.path) as con:
        triggers = con.execute(
            "SELECT name,sql FROM sqlite_master WHERE type='trigger' "
            "AND tbl_name='segment_completion_bindings'"
        ).fetchall()
        for name, _ in triggers:
            con.execute(f'DROP TRIGGER "{name}"')
        raw = con.execute(
            "SELECT receipt_json FROM segment_completion_bindings"
        ).fetchone()[0]
        receipt = json.loads(raw)
        receipt["signature"] = base64.b64encode(b"x" * 64).decode("ascii")
        con.execute(
            "UPDATE segment_completion_bindings SET receipt_json=?",
            (json.dumps(receipt, sort_keys=True, separators=(",", ":")),),
        )
        for _, sql in triggers:
            con.execute(sql)

    with pytest.raises(SegmentationCompletionError, match="signature"):
        completions.get(
            manifest.account_id, manifest.asset_id, manifest.parent_source_hash,
            asset=asset, registry=registry,
        )


def test_journal_recomputes_proposal_hash_after_offline_mutation(setup) -> None:
    worker, binding, manifest, asset, _, _, _ = setup
    worker.dispatch_segment(
        binding=binding, manifest=manifest, asset=asset, segment_index=0,
        projection_request=_request(), adapter=_Adapter(_proposal("journal")),
    )
    with sqlite3.connect(worker.journal.path) as con:
        digest = con.execute(
            "SELECT operation_digest FROM worker_proposals"
        ).fetchone()[0]
        triggers = con.execute(
            "SELECT name,sql FROM sqlite_master WHERE type='trigger' "
            "AND tbl_name='worker_proposals'"
        ).fetchall()
        for name, _ in triggers:
            con.execute(f'DROP TRIGGER "{name}"')
        con.execute(
            "UPDATE worker_proposals SET proposal_hash=? WHERE operation_digest=?",
            ("0" * 64, digest),
        )
        for _, sql in triggers:
            con.execute(sql)

    with pytest.raises(TwinDispatchIntegrityError, match="proposal hash"):
        worker.journal.proposal(digest)


def test_recovery_rejects_receipt_signed_by_untrusted_embedded_key(setup) -> None:
    worker, binding, manifest, asset, _, _, _ = setup
    adapter = _Adapter(_proposal("forged-journal"))
    worker._failure_injector = _fail_once("after_receipt_persisted")
    with pytest.raises(RuntimeError, match="after_receipt_persisted"):
        worker.dispatch_segment(
            binding=binding, manifest=manifest, asset=asset, segment_index=0,
            projection_request=_request(), adapter=adapter,
        )

    wrong = SigningKey.generate()
    with sqlite3.connect(worker.journal.path) as con:
        triggers = con.execute(
            "SELECT name,sql FROM sqlite_master WHERE type='trigger' "
            "AND tbl_name='worker_receipts'"
        ).fetchall()
        for name, _ in triggers:
            con.execute(f'DROP TRIGGER "{name}"')
        digest, raw = con.execute(
            "SELECT operation_digest,receipt_json FROM worker_receipts"
        ).fetchone()
        values = json.loads(raw)
        embedded = bytes(wrong.verify_key)
        values["authority_verify_key"] = base64.b64encode(embedded).decode("ascii")
        values["authority_key_id"] = "key_" + hashlib.sha256(embedded).hexdigest()
        unsigned = SegmentCompletionReceiptV2(**{**values, "signature": ""})
        values["signature"] = base64.b64encode(
            wrong.sign(receipt_payload(unsigned)).signature
        ).decode("ascii")
        con.execute(
            "UPDATE worker_receipts SET receipt_json=? WHERE operation_digest=?",
            (canonical_json(values), digest),
        )
        for _, sql in triggers:
            con.execute(sql)

    with pytest.raises(SegmentationCompletionError, match="not configured"):
        worker.dispatch_segment(
            binding=binding, manifest=manifest, asset=asset, segment_index=0,
            projection_request=_request(), adapter=adapter,
        )
