"""Paid segment/aggregate twin dispatch with crash-safe output binding."""

from __future__ import annotations

import base64
import hashlib
import json
import os
import sqlite3
import time
from collections.abc import Callable, Mapping
from dataclasses import asdict, dataclass, replace
from pathlib import Path
from typing import Generic, TypeVar

from nacl.signing import SigningKey

from runtime.research_runner.protocol import CostProjectionRequest
from runtime.research_runner.provider_gateway import (
    HardCeilingProviderAdapter,
    ProviderReconciliation,
    ProviderSuccess,
    ReconciliationStatus,
    ResearchProviderGateway,
    canonical_digest,
)
from substrate.research_spend import RunBinding, SettledProviderProof
from substrate.twin_note_taker import AssetContent, TwinProposal

from .segmentation import TwinSegmentationManifest, verify_segmentation_manifest
from .segmentation_completion import (
    PAID_COMPLETION_SCHEMA,
    AggregateCompletionReceiptV2,
    SegmentCompletionReceiptV2,
    canonical_json,
    proposal_hash,
    receipt_payload,
    sha256,
    verify_receipt,
)
from .segmentation_completion_ledger import CompletionSnapshot, SegmentationCompletionLedger
from .segmentation_ledger import TwinSegmentationLedger

T = TypeVar("T")
JOURNAL_SCHEMA = "budgeted-twin-worker-journal-v1"


class TwinDispatchIntegrityError(RuntimeError):
    """Worker authority, journal, or paid output is contradictory."""


@dataclass(frozen=True)
class TwinDispatchOperation:
    kind: str
    account_id: str
    asset_id: str
    parent_source_hash: str
    manifest_hash: str
    segment_index: int | None
    start_char: int | None
    end_char: int | None
    content_sha256: str | None
    source_text: str | None
    ordered_segment_bindings_hash: str | None
    segment_proposals: tuple[TwinProposal, ...]


_DDL = {
    "worker_meta": "CREATE TABLE worker_meta (singleton INTEGER PRIMARY KEY CHECK(singleton=1), schema_version TEXT NOT NULL, schema_digest TEXT NOT NULL)",
    "worker_operations": "CREATE TABLE worker_operations (operation_digest TEXT PRIMARY KEY, operation_json TEXT NOT NULL, run_id TEXT NOT NULL, provider TEXT NOT NULL, model TEXT NOT NULL, created_at INTEGER NOT NULL)",
    "worker_proposals": "CREATE TABLE worker_proposals (operation_digest TEXT PRIMARY KEY, proposal_json TEXT NOT NULL, proposal_hash TEXT NOT NULL, provider_idempotency_key TEXT NOT NULL, provider_response_id TEXT NOT NULL, evidence_sha256 TEXT NOT NULL, actual_cents INTEGER NOT NULL, FOREIGN KEY(operation_digest) REFERENCES worker_operations(operation_digest))",
    "worker_receipts": "CREATE TABLE worker_receipts (operation_digest TEXT PRIMARY KEY, receipt_json TEXT NOT NULL, FOREIGN KEY(operation_digest) REFERENCES worker_operations(operation_digest))",
    "worker_settlements": "CREATE TABLE worker_settlements (operation_digest TEXT PRIMARY KEY, run_id TEXT NOT NULL, hold_id TEXT NOT NULL UNIQUE, provider_idempotency_key TEXT NOT NULL, evidence_sha256 TEXT NOT NULL, actual_cents INTEGER NOT NULL, FOREIGN KEY(operation_digest) REFERENCES worker_operations(operation_digest))",
    "worker_operations_no_update": "CREATE TRIGGER worker_operations_no_update BEFORE UPDATE ON worker_operations BEGIN SELECT RAISE(ABORT,'immutable operation'); END",
    "worker_operations_no_delete": "CREATE TRIGGER worker_operations_no_delete BEFORE DELETE ON worker_operations BEGIN SELECT RAISE(ABORT,'immutable operation'); END",
    "worker_proposals_no_update": "CREATE TRIGGER worker_proposals_no_update BEFORE UPDATE ON worker_proposals BEGIN SELECT RAISE(ABORT,'immutable proposal'); END",
    "worker_proposals_no_delete": "CREATE TRIGGER worker_proposals_no_delete BEFORE DELETE ON worker_proposals BEGIN SELECT RAISE(ABORT,'immutable proposal'); END",
    "worker_receipts_no_update": "CREATE TRIGGER worker_receipts_no_update BEFORE UPDATE ON worker_receipts BEGIN SELECT RAISE(ABORT,'immutable receipt'); END",
    "worker_receipts_no_delete": "CREATE TRIGGER worker_receipts_no_delete BEFORE DELETE ON worker_receipts BEGIN SELECT RAISE(ABORT,'immutable receipt'); END",
    "worker_settlements_no_update": "CREATE TRIGGER worker_settlements_no_update BEFORE UPDATE ON worker_settlements BEGIN SELECT RAISE(ABORT,'immutable settlement'); END",
    "worker_settlements_no_delete": "CREATE TRIGGER worker_settlements_no_delete BEFORE DELETE ON worker_settlements BEGIN SELECT RAISE(ABORT,'immutable settlement'); END",
}


def _schema_digest() -> str:
    return sha256(canonical_json(_DDL))


class TwinWorkerJournal:
    def __init__(self, path: str | Path) -> None:
        self.path = str(path)
        with self._connect() as con:
            con.execute("BEGIN IMMEDIATE")
            if con.execute("SELECT 1 FROM sqlite_master WHERE name='worker_meta'").fetchone() is None:
                for statement in _DDL.values():
                    con.execute(statement)
                con.execute("INSERT INTO worker_meta VALUES(1,?,?)", (JOURNAL_SCHEMA, _schema_digest()))
            self._verify(con)

    def _connect(self) -> sqlite3.Connection:
        con = sqlite3.connect(self.path, timeout=30)
        con.row_factory = sqlite3.Row
        con.execute("PRAGMA foreign_keys=ON")
        return con

    def _verify(self, con: sqlite3.Connection) -> None:
        meta = con.execute("SELECT schema_version,schema_digest FROM worker_meta").fetchone()
        if meta is None or tuple(meta) != (JOURNAL_SCHEMA, _schema_digest()):
            raise TwinDispatchIntegrityError("worker journal metadata changed")
        rows = con.execute("SELECT name,sql FROM sqlite_master WHERE name NOT LIKE 'sqlite_%'").fetchall()
        actual = {str(row["name"]): " ".join(str(row["sql"]).split()).lower() for row in rows}
        expected = {name: " ".join(sql.split()).lower() for name, sql in _DDL.items()}
        if actual != expected:
            raise TwinDispatchIntegrityError("worker journal schema changed")

    def stage(
        self, digest: str, operation: TwinDispatchOperation, run_id: str,
        provider: str, model: str,
    ) -> None:
        # source_text is deliberately excluded: the journal stores commitments, never source bytes.
        public = {**asdict(operation), "source_text": None, "source_text_sha256": sha256(operation.source_text or "")}
        value = canonical_json(public)
        with self._connect() as con:
            con.execute("BEGIN IMMEDIATE")
            self._verify(con)
            row = con.execute("SELECT operation_json,run_id,provider,model FROM worker_operations WHERE operation_digest=?", (digest,)).fetchone()
            if row is None:
                con.execute("INSERT INTO worker_operations VALUES(?,?,?,?,?,?)", (digest, value, run_id, provider, model, int(time.time())))
            elif tuple(row) != (value, run_id, provider, model):
                raise TwinDispatchIntegrityError("staged operation substitution")

    def put_proposal(
        self,
        digest: str,
        proposal: TwinProposal,
        actual_cents: int,
        evidence: Mapping[str, str | int | bool | None],
        provider_idempotency_key: str,
    ) -> None:
        proposal_json = canonical_json(asdict(proposal))
        normalized = _provider_evidence(
            evidence,
            operation_digest=digest,
            output_sha256=proposal_hash(proposal),
            provider_idempotency_key=provider_idempotency_key,
        )
        evidence_hash = sha256(
            json.dumps(normalized, sort_keys=True, separators=(",", ":"), ensure_ascii=True)
        )
        values = (
            proposal_json,
            proposal_hash(proposal),
            provider_idempotency_key,
            normalized["provider_response_id"],
            evidence_hash,
            actual_cents,
        )
        with self._connect() as con:
            con.execute("BEGIN IMMEDIATE")
            self._verify(con)
            row = con.execute(
                "SELECT proposal_json,proposal_hash,provider_idempotency_key,"
                "provider_response_id,evidence_sha256,actual_cents "
                "FROM worker_proposals WHERE operation_digest=?", (digest,)
            ).fetchone()
            if row is None:
                con.execute("INSERT INTO worker_proposals VALUES(?,?,?,?,?,?,?)", (digest, *values))
            elif tuple(row) != values:
                raise TwinDispatchIntegrityError("journaled proposal substitution")

    def proposal(self, digest: str) -> TwinProposal | None:
        from substrate.twin_recursion.segmentation_completion_ledger import _proposal_from_json
        with self._connect() as con:
            self._verify(con)
            row = con.execute("SELECT proposal_json,proposal_hash FROM worker_proposals WHERE operation_digest=?", (digest,)).fetchone()
            if row is None:
                return None
            proposal = _proposal_from_json(str(row[0]))
            if str(row[1]) != proposal_hash(proposal):
                raise TwinDispatchIntegrityError("journaled proposal hash changed")
            return proposal

    def proposal_authority(self, digest: str) -> tuple[str, str, str, int] | None:
        with self._connect() as con:
            self._verify(con)
            row = con.execute(
                "SELECT provider_idempotency_key,provider_response_id,"
                "evidence_sha256,actual_cents FROM worker_proposals "
                "WHERE operation_digest=?", (digest,),
            ).fetchone()
            if row is None:
                return None
            return str(row[0]), str(row[1]), str(row[2]), int(row[3])

    def receipt(self, digest: str) -> str | None:
        with self._connect() as con:
            self._verify(con)
            row = con.execute("SELECT receipt_json FROM worker_receipts WHERE operation_digest=?", (digest,)).fetchone()
            return None if row is None else str(row[0])

    def put_receipt(self, digest: str, receipt: object) -> None:
        value = canonical_json(asdict(receipt))
        with self._connect() as con:
            con.execute("BEGIN IMMEDIATE")
            self._verify(con)
            row = con.execute("SELECT receipt_json FROM worker_receipts WHERE operation_digest=?", (digest,)).fetchone()
            if row is None:
                con.execute("INSERT INTO worker_receipts VALUES(?,?)", (digest, value))
            elif str(row[0]) != value:
                raise TwinDispatchIntegrityError("persisted receipt substitution")

    def bind_settlement(self, digest: str, proof: SettledProviderProof) -> None:
        values = (
            proof.run_id, proof.hold_id, proof.provider_idempotency_key,
            proof.settlement_evidence_sha256, proof.actual_cents,
        )
        with self._connect() as con:
            con.execute("BEGIN IMMEDIATE")
            self._verify(con)
            row = con.execute(
                "SELECT run_id,hold_id,provider_idempotency_key,evidence_sha256,"
                "actual_cents FROM worker_settlements WHERE operation_digest=?", (digest,),
            ).fetchone()
            if row is None:
                con.execute("INSERT INTO worker_settlements VALUES(?,?,?,?,?,?)", (digest, *values))
            elif tuple(row) != values:
                raise TwinDispatchIntegrityError("settled hold substitution")


class _JournalingAdapter(Generic[T]):  # noqa: UP046 - Antiek supports Python 3.11
    def __init__(self, adapter: HardCeilingProviderAdapter[T], journal: TwinWorkerJournal, digest: str, checkpoint: Callable[[str], None]) -> None:
        self._adapter, self._journal, self._digest = adapter, journal, digest
        self._checkpoint = checkpoint
        self.provider, self.model, self.endpoint = adapter.provider, adapter.model, adapter.endpoint
        self.capabilities = adapter.capabilities

    def send_once(self, operation: object, *, provider_idempotency_key: str, authorized_endpoint: str) -> ProviderSuccess[T]:
        success = self._adapter.send_once(operation, provider_idempotency_key=provider_idempotency_key, authorized_endpoint=authorized_endpoint)
        if not isinstance(success.value, TwinProposal):
            raise TwinDispatchIntegrityError("provider returned a malformed twin proposal")
        self._journal.put_proposal(
            self._digest, success.value, success.actual_cents, success.evidence,
            provider_idempotency_key,
        )
        self._checkpoint("after_output_staged")
        return success

    def reconcile(self, *, provider_idempotency_key: str, authorized_endpoint: str) -> ProviderReconciliation[T]:
        result = self._adapter.reconcile(provider_idempotency_key=provider_idempotency_key, authorized_endpoint=authorized_endpoint)
        if result.status is ReconciliationStatus.CHARGED:
            if not isinstance(result.value, TwinProposal) or result.actual_cents is None:
                return ProviderReconciliation(ReconciliationStatus.UNKNOWN, result.evidence)
            self._journal.put_proposal(
                self._digest, result.value, result.actual_cents, result.evidence,
                provider_idempotency_key,
            )
            self._checkpoint("after_output_staged")
        return result


def _provider_evidence(
    evidence: Mapping[str, str | int | bool | None],
    *,
    operation_digest: str,
    output_sha256: str,
    provider_idempotency_key: str,
) -> dict[str, str]:
    required = {
        "billing_status", "currency", "operation_digest", "output_sha256",
        "provider_idempotency_key", "provider_request_id", "provider_response_id",
        "schema", "usage_json",
    }
    if set(evidence) != required or any(type(evidence[key]) is not str for key in required):
        raise TwinDispatchIntegrityError("provider evidence is not a typed twin settlement")
    normalized = {key: str(evidence[key]) for key in required}
    if (
        normalized["schema"] != "antiek.twin-provider-settlement.v1"
        or normalized["billing_status"] != "settled"
        or normalized["currency"] != "USD"
        or normalized["operation_digest"] != operation_digest
        or normalized["output_sha256"] != output_sha256
        or normalized["provider_idempotency_key"] != provider_idempotency_key
        or not normalized["provider_request_id"]
        or not normalized["provider_response_id"]
    ):
        raise TwinDispatchIntegrityError("provider evidence conflicts with exact output")
    try:
        usage = json.loads(normalized["usage_json"])
    except json.JSONDecodeError as exc:
        raise TwinDispatchIntegrityError("provider usage evidence is invalid") from exc
    if type(usage) is not dict or not usage:
        raise TwinDispatchIntegrityError("provider usage evidence is empty")
    return normalized


class BudgetedTwinDispatchWorker:
    def __init__(self, *, gateway: ResearchProviderGateway, registry: TwinSegmentationLedger, completions: SegmentationCompletionLedger, journal_path: str | Path, signing_seed: bytes, expires_in_seconds: int = 3600, failure_injector: Callable[[str], None] | None = None) -> None:
        if type(signing_seed) is not bytes or len(signing_seed) != 32:
            raise ValueError("signing seed must be exactly 32 private bytes")
        self.gateway, self.registry, self.completions = gateway, registry, completions
        self.journal, self.key = TwinWorkerJournal(journal_path), SigningKey(signing_seed)
        configured = os.environ.get("ANTIEK_TWIN_AUTHORITY_VERIFY_KEY", "")
        encoded_verify = base64.b64encode(bytes(self.key.verify_key)).decode("ascii")
        if configured != encoded_verify:
            raise ValueError("signing key is not the active twin completion authority")
        if not 1 <= expires_in_seconds <= 86_400:
            raise ValueError("receipt lifetime must be between 1 second and 1 day")
        self.expires_in_seconds = expires_in_seconds
        self._failure_injector = failure_injector

    def _checkpoint(self, name: str) -> None:
        if self._failure_injector is not None:
            self._failure_injector(name)

    def dispatch_segment(self, *, binding: RunBinding, manifest: TwinSegmentationManifest, asset: AssetContent, segment_index: int, projection_request: CostProjectionRequest, adapter: HardCeilingProviderAdapter[T]) -> CompletionSnapshot:
        verify_segmentation_manifest(manifest, account_id=binding.owner_id, asset=asset)
        registered = self.registry.get(manifest.account_id, manifest.asset_id, manifest.parent_source_hash)
        if registered.manifest_hash != manifest.manifest_hash or not 0 <= segment_index < len(manifest.segments):
            raise TwinDispatchIntegrityError("current segment authority differs")
        segment = manifest.segments[segment_index]
        operation = TwinDispatchOperation("segment", manifest.account_id, manifest.asset_id, manifest.parent_source_hash, manifest.manifest_hash, segment_index, segment.start_char, segment.end_char, segment.content_sha256, asset.content_text[segment.start_char:segment.end_char], None, ())
        existing = self.completions.paid_segment_completion(
            manifest, segment_index, asset=asset, registry=self.registry
        )
        if existing is not None:
            self._validate_existing(
                binding, operation, projection_request, adapter, *existing
            )
            return self.completions.get(
                manifest.account_id, manifest.asset_id, manifest.parent_source_hash,
                asset=asset, registry=self.registry,
            )
        return self._dispatch(binding, manifest, asset, projection_request, adapter, operation)

    def dispatch_aggregate(self, *, binding: RunBinding, manifest: TwinSegmentationManifest, asset: AssetContent, projection_request: CostProjectionRequest, adapter: HardCeilingProviderAdapter[T]) -> CompletionSnapshot:
        verify_segmentation_manifest(manifest, account_id=binding.owner_id, asset=asset)
        ordered_hash, proposals = self.completions.aggregate_inputs(manifest)
        operation = TwinDispatchOperation("aggregate", manifest.account_id, manifest.asset_id, manifest.parent_source_hash, manifest.manifest_hash, None, None, None, None, None, ordered_hash, proposals)
        existing = self.completions.paid_aggregate_completion(
            manifest, asset=asset, registry=self.registry
        )
        if existing is not None:
            self._validate_existing(
                binding, operation, projection_request, adapter, *existing
            )
            return self.completions.get(
                manifest.account_id, manifest.asset_id, manifest.parent_source_hash,
                asset=asset, registry=self.registry,
            )
        return self._dispatch(binding, manifest, asset, projection_request, adapter, operation)

    def _dispatch(self, binding: RunBinding, manifest: TwinSegmentationManifest, asset: AssetContent, request: CostProjectionRequest, adapter: HardCeilingProviderAdapter[T], operation: TwinDispatchOperation) -> CompletionSnapshot:
        self._validate_route(request, adapter, operation.kind)
        digest = canonical_digest(operation)
        self.journal.stage(digest, operation, binding.run_id, adapter.provider, adapter.model)
        wrapped = _JournalingAdapter(adapter, self.journal, digest, self._checkpoint)
        result = self.gateway.dispatch_paid(binding, logical_operation_id=f"twin:{operation.kind}:{digest}", projection_request=request, operation=operation, adapter=wrapped)
        proposal = self.journal.proposal(digest)
        if proposal is None:
            raise TwinDispatchIntegrityError("settled operation has no durable proposal")
        proof = self.gateway.ledger.settled_provider_proof(
            result.hold.hold_id,
            expected_run_id=binding.run_id,
            expected_operation_digest=digest,
            expected_provider_idempotency_key=result.hold.intent.provider_idempotency_key,
        )
        if (proof.owner_id, proof.provider, proof.model, proof.operation_digest) != (binding.owner_id, adapter.provider, adapter.model, digest):
            raise TwinDispatchIntegrityError("settled provider proof conflicts with operation")
        if self.journal.proposal_authority(digest) != (
            proof.provider_idempotency_key,
            proof.provider_response_id,
            proof.settlement_evidence_sha256,
            proof.actual_cents,
        ):
            raise TwinDispatchIntegrityError("journaled output conflicts with settled proof")
        self.journal.bind_settlement(digest, proof)
        self._checkpoint("after_settlement_bound")
        persisted = self.journal.receipt(digest)
        if persisted is None:
            receipt = self._receipt(operation, proposal, proof)
            verify_receipt(receipt)
            self.journal.put_receipt(digest, receipt)
            self._checkpoint("after_receipt_persisted")
        else:
            receipt_type = SegmentCompletionReceiptV2 if operation.kind == "segment" else AggregateCompletionReceiptV2
            try:
                receipt = receipt_type(**json.loads(persisted))
            except (TypeError, ValueError, json.JSONDecodeError) as exc:
                raise TwinDispatchIntegrityError("persisted worker receipt is malformed") from exc
            if canonical_json(asdict(receipt)) != persisted:
                raise TwinDispatchIntegrityError("persisted worker receipt is not canonical")
            # The receipt is not authoritative until completion apply. It must
            # still be current and signed by this worker's active authority.
            verify_receipt(receipt)
            self._assert_receipt(receipt, operation, proposal, proof)
        if operation.kind == "segment":
            assert operation.segment_index is not None
            return self.completions.apply_segment(manifest, asset=asset, segment_index=operation.segment_index, proposal=proposal, receipt=receipt, registry=self.registry)
        return self.completions.apply_aggregate(manifest, asset=asset, proposal=proposal, receipt=receipt, registry=self.registry)

    @staticmethod
    def _validate_route(
        request: CostProjectionRequest,
        adapter: HardCeilingProviderAdapter[object],
        kind: str,
    ) -> None:
        if (request.provider, request.model) != (adapter.provider, adapter.model):
            raise TwinDispatchIntegrityError("projection route differs from adapter")
        if (
            request.seam_id != f"twin.{kind}.generate"
            or request.operation != "generate_twin_proposal"
        ):
            raise TwinDispatchIntegrityError("projection is not the pinned twin operation")

    def _validate_existing(
        self,
        binding: RunBinding,
        operation: TwinDispatchOperation,
        request: CostProjectionRequest,
        adapter: HardCeilingProviderAdapter[T],
        proposal: TwinProposal,
        receipt: SegmentCompletionReceiptV2 | AggregateCompletionReceiptV2,
    ) -> None:
        self._validate_route(request, adapter, operation.kind)
        if receipt.spend_run_id != binding.run_id:
            raise TwinDispatchIntegrityError("paid completion belongs to another spend run")
        hold = self.gateway.ledger.hold(receipt.paid_hold_id)
        proof = self.gateway.ledger.settled_provider_proof(
            receipt.paid_hold_id,
            expected_run_id=binding.run_id,
            expected_operation_digest=canonical_digest(operation),
            expected_provider_idempotency_key=hold.intent.provider_idempotency_key,
        )
        if (proof.owner_id, proof.provider, proof.model) != (
            binding.owner_id, adapter.provider, adapter.model,
        ):
            raise TwinDispatchIntegrityError("paid completion proof differs from replay")
        self._assert_receipt(receipt, operation, proposal, proof)

    def _assert_receipt(
        self,
        receipt: SegmentCompletionReceiptV2 | AggregateCompletionReceiptV2,
        operation: TwinDispatchOperation,
        proposal: TwinProposal,
        proof: SettledProviderProof,
    ) -> None:
        verify = bytes(self.key.verify_key)
        expected_key_id = "key_" + hashlib.sha256(verify).hexdigest()
        expected_receipt_id = "receipt_" + canonical_digest(
            {
                "operation": operation,
                "hold": proof.hold_id,
                "proposal": proposal_hash(proposal),
                "settlement": proof.settlement_evidence_sha256,
                "key": hashlib.sha256(verify).hexdigest(),
            }
        )
        if (
            receipt.receipt_id,
            receipt.account_id,
            receipt.manifest_hash,
            receipt.parent_source_hash,
            receipt.model_id,
            receipt.budget_authority_id,
            receipt.spend_run_id,
            receipt.paid_hold_id,
            receipt.proposal_hash,
            receipt.provider,
            receipt.provider_response_id,
            receipt.provider_idempotency_key_sha256,
            receipt.actual_cents,
            receipt.currency,
            receipt.settlement_evidence_sha256,
            receipt.settlement_intent_sha256,
            receipt.settled_at,
            receipt.ceiling_breached,
            receipt.operation_digest,
            receipt.authority_key_id,
            receipt.authority_verify_key,
        ) != (
            expected_receipt_id,
            operation.account_id,
            operation.manifest_hash,
            operation.parent_source_hash,
            proof.model,
            proof.hold_id,
            proof.run_id,
            proof.hold_id,
            proposal_hash(proposal),
            proof.provider,
            proof.provider_response_id,
            sha256(proof.provider_idempotency_key),
            proof.actual_cents,
            proof.currency,
            proof.settlement_evidence_sha256,
            proof.settlement_intent_sha256,
            proof.settled_at,
            proof.ceiling_breached,
            proof.operation_digest,
            expected_key_id,
            base64.b64encode(verify).decode("ascii"),
        ):
            raise TwinDispatchIntegrityError("persisted receipt conflicts with settled proof")

    def _receipt(self, operation: TwinDispatchOperation, proposal: TwinProposal, proof: SettledProviderProof) -> SegmentCompletionReceiptV2 | AggregateCompletionReceiptV2:
        verify = bytes(self.key.verify_key)
        if proof.output_sha256 != proposal_hash(proposal):
            raise TwinDispatchIntegrityError("settled proof is bound to another output")
        common = dict(schema=PAID_COMPLETION_SCHEMA, receipt_id="receipt_" + canonical_digest({"operation": operation, "hold": proof.hold_id, "proposal": proposal_hash(proposal), "settlement": proof.settlement_evidence_sha256, "key": hashlib.sha256(verify).hexdigest()}), account_id=operation.account_id, manifest_hash=operation.manifest_hash, parent_source_hash=operation.parent_source_hash, model_id=proof.model, budget_authority_id=proof.hold_id, spend_run_id=proof.run_id, paid_hold_id=proof.hold_id, proposal_hash=proposal_hash(proposal), provider=proof.provider, provider_response_id=proof.provider_response_id, provider_idempotency_key_sha256=sha256(proof.provider_idempotency_key), actual_cents=proof.actual_cents, currency=proof.currency, settlement_evidence_sha256=proof.settlement_evidence_sha256, settlement_intent_sha256=proof.settlement_intent_sha256, settled_at=proof.settled_at, ceiling_breached=proof.ceiling_breached, operation_digest=proof.operation_digest, authority_key_id="key_" + hashlib.sha256(verify).hexdigest(), authority_verify_key=base64.b64encode(verify).decode(), expires_at_unix=int(time.time()) + self.expires_in_seconds, signature="")
        if operation.kind == "segment":
            assert operation.segment_index is not None
            assert operation.start_char is not None and operation.end_char is not None
            assert operation.content_sha256 is not None
            receipt = SegmentCompletionReceiptV2(**common, segment_index=operation.segment_index, start_char=operation.start_char, end_char=operation.end_char, content_sha256=operation.content_sha256)
        else:
            assert operation.ordered_segment_bindings_hash is not None
            receipt = AggregateCompletionReceiptV2(**common, ordered_segment_bindings_hash=operation.ordered_segment_bindings_hash)
        return replace(receipt, signature=base64.b64encode(self.key.sign(receipt_payload(receipt)).signature).decode())


__all__ = ["BudgetedTwinDispatchWorker", "TwinDispatchIntegrityError", "TwinDispatchOperation", "TwinWorkerJournal"]
