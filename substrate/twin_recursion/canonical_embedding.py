"""Budget-authorized embedding of one canonical advisory-twin chunk."""

from __future__ import annotations

import hashlib
import json
import math
import sqlite3
import struct
from collections.abc import Callable, Mapping, Sequence
from dataclasses import asdict, dataclass
from pathlib import Path
from typing import Any, Generic, TypeVar

from processing.embedding import embedding_provider_fingerprint
from runtime.db_lock import LockedConnection
from runtime.research_runner.protocol import CostProjectionRequest
from runtime.research_runner.provider_gateway import (
    HardCeilingProviderAdapter,
    PaidFallbackOutcome,
    PaidFallbackPreparation,
    PaidFallbackRoute,
    ProviderReconciliation,
    ProviderSuccess,
    ReconciliationStatus,
    ResearchProviderGateway,
    canonical_digest,
)
from substrate.research_spend import FallbackSpendApproval, RunBinding, SettledProviderProof

from .canonical_reader import CanonicalTwinReader, CanonicalTwinReaderNotFound
from .ledger import TwinRecursionLedger

T = TypeVar("T")
MAX_EMBEDDING_DIMENSION = 65_536
EVIDENCE_SCHEMA = "antiek.twin-provider-settlement.v1"
MAX_EVIDENCE_FIELD_CHARS = 8_192


class CanonicalTwinEmbeddingError(RuntimeError):
    """Embedding authority, evidence, or publication state conflicts."""


@dataclass(frozen=True)
class CanonicalEmbeddingOperation:
    owner_id: str
    source_asset_id: str
    source_hash: str
    binding_id: str
    document_id: str
    chunk_id: str
    chunk_sha256: str
    provider: str
    model: str
    dimension: int


@dataclass(frozen=True)
class CanonicalEmbeddingPreview:
    operation_digest: str
    preparation: PaidFallbackPreparation


@dataclass(frozen=True)
class CanonicalEmbeddingResult:
    document_id: str
    chunk_id: str
    vector_sha256: str
    hold_id: str
    actual_cents: int
    replayed: bool


def _text(value: object, name: str) -> str:
    if type(value) is not str or not value or len(value) > 512:
        raise CanonicalTwinEmbeddingError(f"{name} must be an exact bounded string")
    return value


def _vector(value: object, dimension: int) -> tuple[float, ...]:
    if not 1 <= dimension <= MAX_EMBEDDING_DIMENSION:
        raise CanonicalTwinEmbeddingError("embedding dimension is outside the contract")
    if type(value) not in (list, tuple) or len(value) != dimension:
        raise CanonicalTwinEmbeddingError("provider vector has the wrong dimension")
    result: list[float] = []
    for item in value:
        if isinstance(item, bool) or type(item) not in (int, float):
            raise CanonicalTwinEmbeddingError("provider vector must contain real numbers")
        number = float(item)
        if not math.isfinite(number) or abs(number) > 1_000_000:
            raise CanonicalTwinEmbeddingError("provider vector contains an unsafe value")
        result.append(number)
    return tuple(result)


def _vector_bytes(vector: Sequence[float]) -> bytes:
    return b"".join(struct.pack(">d", item) for item in vector)


def _sha(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def _evidence(
    value: Mapping[str, str | int | bool | None],
    *,
    operation_digest: str,
    provider_idempotency_key: str,
    vector_sha256: str,
) -> dict[str, str]:
    keys = {
        "billing_status",
        "currency",
        "operation_digest",
        "output_sha256",
        "provider_idempotency_key",
        "provider_request_id",
        "provider_response_id",
        "schema",
        "usage_json",
    }
    if set(value) != keys or any(type(value[key]) is not str for key in keys):
        raise CanonicalTwinEmbeddingError("provider evidence is not an exact typed settlement")
    result = {key: str(value[key]) for key in keys}
    if any(len(item) > MAX_EVIDENCE_FIELD_CHARS for item in result.values()):
        raise CanonicalTwinEmbeddingError("provider evidence exceeds the bounded journal contract")
    if (
        result["schema"] != EVIDENCE_SCHEMA
        or result["billing_status"] != "settled"
        or result["currency"] != "USD"
        or result["operation_digest"] != operation_digest
        or result["output_sha256"] != vector_sha256
        or result["provider_idempotency_key"] != provider_idempotency_key
        or not result["provider_request_id"]
        or not result["provider_response_id"]
    ):
        raise CanonicalTwinEmbeddingError("provider evidence conflicts with the vector")
    try:
        usage = json.loads(result["usage_json"])
    except json.JSONDecodeError as exc:
        raise CanonicalTwinEmbeddingError("provider usage evidence is invalid") from exc
    if type(usage) is not dict or not usage:
        raise CanonicalTwinEmbeddingError("provider usage evidence is empty")
    return result


class CanonicalEmbeddingJournal:
    """Append-once output and settlement bindings used for crash recovery."""

    def __init__(self, path: str | Path) -> None:
        self.path = Path(path)
        self.path.parent.mkdir(parents=True, exist_ok=True)
        with self._connect() as con:
            con.execute("""CREATE TABLE IF NOT EXISTS embedding_outputs (
                operation_digest TEXT PRIMARY KEY, operation_json TEXT NOT NULL,
                vector_json TEXT NOT NULL, vector_sha256 TEXT NOT NULL,
                evidence_json TEXT NOT NULL, provider_idempotency_key TEXT NOT NULL,
                hold_id TEXT, settlement_sha256 TEXT, actual_cents INTEGER)""")
            con.execute("""CREATE TABLE IF NOT EXISTS embedding_previews (
                chain_id TEXT PRIMARY KEY, run_id TEXT NOT NULL, owner_id TEXT NOT NULL,
                operation_digest TEXT NOT NULL, preparation_json TEXT NOT NULL)""")

    def _connect(self) -> sqlite3.Connection:
        con = sqlite3.connect(self.path, timeout=30, isolation_level=None)
        con.execute("PRAGMA journal_mode=WAL")
        return con

    def stage(
        self,
        operation: CanonicalEmbeddingOperation,
        vector: tuple[float, ...],
        evidence: Mapping[str, str],
        provider_idempotency_key: str,
    ) -> None:
        digest = canonical_digest(operation)
        values = (
            digest,
            json.dumps(operation.__dict__, sort_keys=True, separators=(",", ":")),
            json.dumps(vector, separators=(",", ":")),
            _sha(_vector_bytes(vector)),
            json.dumps(evidence, sort_keys=True, separators=(",", ":")),
            provider_idempotency_key,
        )
        with self._connect() as con:
            con.execute("BEGIN IMMEDIATE")
            row = con.execute(
                "SELECT operation_digest,operation_json,vector_json,vector_sha256,"
                "evidence_json,provider_idempotency_key FROM embedding_outputs "
                "WHERE operation_digest=?",
                (digest,),
            ).fetchone()
            if row is None:
                con.execute(
                    "INSERT INTO embedding_outputs VALUES (?,?,?,?,?,?,NULL,NULL,NULL)", values
                )
            elif tuple(row) != values:
                raise CanonicalTwinEmbeddingError("journaled provider output was substituted")
            con.execute("COMMIT")

    def stage_preview(self, binding: RunBinding, preview: CanonicalEmbeddingPreview) -> None:
        values = (
            preview.preparation.chain_id,
            binding.run_id,
            binding.owner_id,
            preview.operation_digest,
            json.dumps(asdict(preview.preparation), sort_keys=True, separators=(",", ":")),
        )
        with self._connect() as con:
            con.execute("BEGIN IMMEDIATE")
            row = con.execute(
                "SELECT chain_id,run_id,owner_id,operation_digest,preparation_json "
                "FROM embedding_previews WHERE chain_id=?",
                (preview.preparation.chain_id,),
            ).fetchone()
            if row is None:
                con.execute("INSERT INTO embedding_previews VALUES (?,?,?,?,?)", values)
            elif tuple(row) != values:
                raise CanonicalTwinEmbeddingError("embedding preview authority was substituted")
            con.execute("COMMIT")

    def require_preview(self, binding: RunBinding, preview: CanonicalEmbeddingPreview) -> None:
        expected = (
            preview.preparation.chain_id,
            binding.run_id,
            binding.owner_id,
            preview.operation_digest,
            json.dumps(asdict(preview.preparation), sort_keys=True, separators=(",", ":")),
        )
        with self._connect() as con:
            row = con.execute(
                "SELECT chain_id,run_id,owner_id,operation_digest,preparation_json "
                "FROM embedding_previews WHERE chain_id=?",
                (preview.preparation.chain_id,),
            ).fetchone()
        if row is None or tuple(row) != expected:
            raise CanonicalTwinEmbeddingError("embedding preview is not the prepared authority")

    def output(
        self, operation: CanonicalEmbeddingOperation
    ) -> tuple[tuple[float, ...], str, dict[str, str], str]:
        digest = canonical_digest(operation)
        with self._connect() as con:
            row = con.execute(
                "SELECT operation_json,vector_json,vector_sha256,evidence_json,"
                "provider_idempotency_key FROM embedding_outputs WHERE operation_digest=?",
                (digest,),
            ).fetchone()
        if row is None:
            raise CanonicalTwinEmbeddingError("settled operation has no durable vector")
        expected_operation = json.dumps(operation.__dict__, sort_keys=True, separators=(",", ":"))
        try:
            vector = _vector(json.loads(row[1]), operation.dimension)
            evidence = json.loads(row[3])
        except (TypeError, ValueError, json.JSONDecodeError) as exc:
            raise CanonicalTwinEmbeddingError("journaled output is malformed") from exc
        if (
            row[0] != expected_operation
            or row[2] != _sha(_vector_bytes(vector))
            or type(evidence) is not dict
        ):
            raise CanonicalTwinEmbeddingError("journaled output integrity failed")
        evidence_operation_digest = evidence.get("operation_digest")
        if type(evidence_operation_digest) is not str or not evidence_operation_digest:
            raise CanonicalTwinEmbeddingError("journaled provider operation is absent")
        checked = _evidence(
            evidence,
            operation_digest=evidence_operation_digest,
            provider_idempotency_key=row[4],
            vector_sha256=row[2],
        )
        return vector, row[2], checked, row[4]

    def bind(self, operation: CanonicalEmbeddingOperation, proof: SettledProviderProof) -> None:
        vector, vector_sha, _, key = self.output(operation)
        del vector
        digest = canonical_digest(operation)
        evidence_operation_digest = self.output(operation)[2]["operation_digest"]
        if (
            proof.operation_digest != evidence_operation_digest
            or proof.output_sha256 != vector_sha
            or proof.provider_idempotency_key != key
            or proof.provider != operation.provider
            or proof.model != operation.model
            or proof.owner_id != operation.owner_id
        ):
            raise CanonicalTwinEmbeddingError("settlement proof conflicts with journaled output")
        with self._connect() as con:
            con.execute("BEGIN IMMEDIATE")
            row = con.execute(
                "SELECT hold_id,settlement_sha256,actual_cents FROM embedding_outputs "
                "WHERE operation_digest=?",
                (digest,),
            ).fetchone()
            values = (proof.hold_id, proof.settlement_evidence_sha256, proof.actual_cents)
            if row == (None, None, None):
                con.execute(
                    "UPDATE embedding_outputs SET hold_id=?,settlement_sha256=?,actual_cents=? "
                    "WHERE operation_digest=?",
                    (*values, digest),
                )
            elif tuple(row) != values:
                raise CanonicalTwinEmbeddingError("journal settlement was substituted")
            con.execute("COMMIT")


class _JournalingAdapter(Generic[T]):  # noqa: UP046 - Antiek supports Python 3.11
    def __init__(
        self,
        adapter: HardCeilingProviderAdapter[T],
        journal: CanonicalEmbeddingJournal,
        operation: CanonicalEmbeddingOperation,
        gateway_operation_digest: str,
    ) -> None:
        self._adapter, self._journal, self._operation = adapter, journal, operation
        self.provider, self.model, self.endpoint = adapter.provider, adapter.model, adapter.endpoint
        self.capabilities = adapter.capabilities
        self._gateway_operation_digest = gateway_operation_digest

    def _stage(self, success: ProviderSuccess[Any], key: str) -> ProviderSuccess[Any]:
        vector = _vector(success.value, self._operation.dimension)
        evidence = _evidence(
            success.evidence,
            operation_digest=self._gateway_operation_digest,
            provider_idempotency_key=key,
            vector_sha256=_sha(_vector_bytes(vector)),
        )
        self._journal.stage(self._operation, vector, evidence, key)
        return ProviderSuccess(vector, success.actual_cents, evidence)

    def send_once(
        self, operation: object, *, provider_idempotency_key: str, authorized_endpoint: str
    ) -> ProviderSuccess[Any]:
        return self._stage(
            self._adapter.send_once(
                operation,
                provider_idempotency_key=provider_idempotency_key,
                authorized_endpoint=authorized_endpoint,
            ),
            provider_idempotency_key,
        )

    def reconcile(
        self, *, provider_idempotency_key: str, authorized_endpoint: str
    ) -> ProviderReconciliation[Any]:
        result = self._adapter.reconcile(
            provider_idempotency_key=provider_idempotency_key,
            authorized_endpoint=authorized_endpoint,
        )
        if result.status is not ReconciliationStatus.CHARGED:
            if result.value is not None:
                return ProviderReconciliation(
                    ReconciliationStatus.UNKNOWN,
                    {"embedding_recovery": "nonterminal_output_rejected"},
                )
            return result
        if result.value is None:
            # A billed response without recoverable bytes must not become a
            # terminal settlement: replay could never apply or verify it.
            return ProviderReconciliation(
                ReconciliationStatus.UNKNOWN,
                {"embedding_recovery": "charged_output_unavailable"},
            )
        if (
            isinstance(result.actual_cents, bool)
            or not isinstance(result.actual_cents, int)
            or result.actual_cents < 0
        ):
            return result
        staged = self._stage(
            ProviderSuccess(result.value, result.actual_cents, result.evidence),
            provider_idempotency_key,
        )
        return ProviderReconciliation(
            result.status, staged.evidence, result.actual_cents, staged.value
        )


class BudgetedCanonicalTwinEmbedder:
    def __init__(
        self,
        *,
        gateway: ResearchProviderGateway,
        ledger: TwinRecursionLedger,
        journal_path: str | Path,
        failure_injector: Callable[[str], None] | None = None,
    ) -> None:
        if type(ledger) is not TwinRecursionLedger:
            raise TypeError("embedder requires the exact canonical twin ledger")
        self.gateway, self.ledger = gateway, ledger
        self.journal = CanonicalEmbeddingJournal(journal_path)
        self.failure_injector = failure_injector

    def _gateway_digest(
        self,
        binding: RunBinding,
        logical_operation_id: str,
        operation: CanonicalEmbeddingOperation,
        route: PaidFallbackRoute[Any],
    ) -> str:
        # Fallback holds bind the complete approved route plan, not merely the
        # inner operation. Keep that distinction in one gateway-derived value.
        plan = self.gateway._fallback_plan(  # noqa: SLF001
            binding,
            logical_operation_id=logical_operation_id,
            operation=operation,
            routes=(route,),
        )
        return plan.manifest.operation_digest

    def _operation(
        self,
        con: LockedConnection,
        *,
        owner_id: str,
        source_asset_id: str,
        source_hash: str,
        adapter: HardCeilingProviderAdapter[Any],
    ) -> CanonicalEmbeddingOperation:
        if type(con) is not LockedConnection:
            raise TypeError("embedding requires the exact locked graph connection")
        owner_id, source_asset_id, source_hash = (
            _text(owner_id, "owner_id"),
            _text(source_asset_id, "source_asset_id"),
            _text(source_hash, "source_hash"),
        )
        dimension = getattr(adapter, "dimension", None)
        if (
            isinstance(dimension, bool)
            or not isinstance(dimension, int)
            or not 1 <= dimension <= MAX_EMBEDDING_DIMENSION
        ):
            raise CanonicalTwinEmbeddingError("adapter dimension is outside the contract")
        try:
            view = CanonicalTwinReader(con, self.ledger).read_by_source(
                owner_id=owner_id, source_asset_id=source_asset_id, source_hash=source_hash
            )
        except CanonicalTwinReaderNotFound as exc:
            raise CanonicalTwinEmbeddingError("canonical publication is unavailable") from exc
        # Resolve the publication-owned chunk id from exact v2 document metadata.
        metadata = json.loads(
            con.execute(
                "SELECT metadata FROM documents WHERE document_id=?", [view.document_id]
            ).fetchone()[0]
        )
        chunk_id = metadata["chunk_id"]
        row = con.execute(
            "SELECT text,embedding FROM chunks WHERE chunk_id=?", [chunk_id]
        ).fetchone()
        if row is None:
            raise CanonicalTwinEmbeddingError("canonical publication chunk is absent")
        return CanonicalEmbeddingOperation(
            owner_id,
            source_asset_id,
            source_hash,
            metadata["binding_id"],
            view.document_id,
            chunk_id,
            hashlib.sha256(row[0].encode()).hexdigest(),
            adapter.provider,
            adapter.model,
            dimension,
        )

    def prepare(
        self,
        con: LockedConnection,
        *,
        binding: RunBinding,
        source_asset_id: str,
        source_hash: str,
        projection_request: CostProjectionRequest,
        adapter: HardCeilingProviderAdapter[T],
    ) -> CanonicalEmbeddingPreview:
        operation = self._operation(
            con,
            owner_id=binding.owner_id,
            source_asset_id=source_asset_id,
            source_hash=source_hash,
            adapter=adapter,
        )
        existing = con.execute(
            "SELECT embedding FROM chunks WHERE chunk_id=?", [operation.chunk_id]
        ).fetchone()
        meta = con.execute(
            "SELECT 1 FROM embeddings_meta WHERE chunk_id=?", [operation.chunk_id]
        ).fetchone()
        if existing is None or existing[0] is not None or meta is not None:
            raise CanonicalTwinEmbeddingError("canonical chunk is already embedded")
        if (projection_request.provider, projection_request.model) != (
            adapter.provider,
            adapter.model,
        ):
            raise CanonicalTwinEmbeddingError("projection route differs from adapter")
        route = PaidFallbackRoute(projection_request, adapter)
        logical_id = f"canonical-twin-embedding:{canonical_digest(operation)}"
        preparation = self.gateway.prepare_paid_fallbacks(
            binding,
            logical_operation_id=logical_id,
            operation=operation,
            routes=(route,),
        )
        preview = CanonicalEmbeddingPreview(
            self._gateway_digest(binding, logical_id, operation, route), preparation
        )
        self.journal.stage_preview(binding, preview)
        return preview

    def approve(
        self, *, command_key: str, binding: RunBinding, preview: CanonicalEmbeddingPreview
    ) -> FallbackSpendApproval:
        self.journal.require_preview(binding, preview)
        return self.gateway.approve_paid_fallbacks(command_key, binding, preview.preparation)

    def embed(
        self,
        con: LockedConnection,
        *,
        binding: RunBinding,
        source_asset_id: str,
        source_hash: str,
        projection_request: CostProjectionRequest,
        adapter: HardCeilingProviderAdapter[T],
        approval_id: str,
    ) -> CanonicalEmbeddingResult:
        operation = self._operation(
            con,
            owner_id=binding.owner_id,
            source_asset_id=source_asset_id,
            source_hash=source_hash,
            adapter=adapter,
        )
        digest = canonical_digest(operation)
        logical_id = f"canonical-twin-embedding:{digest}"
        original_route = PaidFallbackRoute(projection_request, adapter)
        gateway_digest = self._gateway_digest(binding, logical_id, operation, original_route)
        route = PaidFallbackRoute(
            projection_request,
            _JournalingAdapter(adapter, self.journal, operation, gateway_digest),
        )
        outcome = self.gateway.dispatch_paid_fallbacks(
            binding,
            logical_operation_id=logical_id,
            operation=operation,
            routes=(route,),
            approval_id=approval_id,
        )
        if outcome.outcome is not PaidFallbackOutcome.SETTLED or len(outcome.attempts) != 1:
            raise CanonicalTwinEmbeddingError("embedding provider did not settle")
        hold = outcome.attempts[0].hold
        proof = self.gateway.ledger.settled_provider_proof(
            hold.hold_id,
            expected_run_id=binding.run_id,
            expected_operation_digest=hold.intent.operation_digest,
            expected_provider_idempotency_key=hold.intent.provider_idempotency_key,
        )
        self.journal.bind(operation, proof)
        if self.failure_injector:
            self.failure_injector("after_settlement_bound")
        vector, vector_sha, _, _ = self.journal.output(operation)
        replayed = self._apply(con, operation, vector, vector_sha, adapter)
        return CanonicalEmbeddingResult(
            operation.document_id,
            operation.chunk_id,
            vector_sha,
            proof.hold_id,
            proof.actual_cents,
            replayed,
        )

    def _apply(
        self,
        con: LockedConnection,
        operation: CanonicalEmbeddingOperation,
        vector: tuple[float, ...],
        vector_sha: str,
        adapter: HardCeilingProviderAdapter[Any],
    ) -> bool:
        fingerprint = embedding_provider_fingerprint(adapter)
        con.execute("BEGIN TRANSACTION")
        try:
            current = self._operation(
                con,
                owner_id=operation.owner_id,
                source_asset_id=operation.source_asset_id,
                source_hash=operation.source_hash,
                adapter=adapter,
            )
            if current != operation:
                raise CanonicalTwinEmbeddingError("canonical publication changed before apply")
            row = con.execute(
                "SELECT embedding FROM chunks WHERE chunk_id=?", [operation.chunk_id]
            ).fetchone()
            meta = con.execute(
                "SELECT provider,model_name,dimension,fingerprint FROM embeddings_meta WHERE chunk_id=?",
                [operation.chunk_id],
            ).fetchone()
            if row[0] is None and meta is None:
                con.execute(
                    "UPDATE chunks SET embedding=? WHERE chunk_id=?",
                    [list(vector), operation.chunk_id],
                )
                if self.failure_injector:
                    self.failure_injector("after_vector_write")
                con.execute(
                    "INSERT INTO embeddings_meta(chunk_id,provider,model_name,dimension,fingerprint) VALUES (?,?,?,?,?)",
                    [
                        operation.chunk_id,
                        operation.provider,
                        operation.model,
                        operation.dimension,
                        fingerprint,
                    ],
                )
                replayed = False
            else:
                stored = _vector(row[0], operation.dimension) if row[0] is not None else ()
                expected_meta = (
                    operation.provider,
                    operation.model,
                    operation.dimension,
                    fingerprint,
                )
                if _sha(_vector_bytes(stored)) != vector_sha or tuple(meta or ()) != expected_meta:
                    raise CanonicalTwinEmbeddingError("persisted embedding was substituted")
                replayed = True
            con.execute("COMMIT")
            return replayed
        except Exception:
            con.execute("ROLLBACK")
            raise


__all__ = [
    "BudgetedCanonicalTwinEmbedder",
    "CanonicalEmbeddingJournal",
    "CanonicalEmbeddingOperation",
    "CanonicalEmbeddingPreview",
    "CanonicalEmbeddingResult",
    "CanonicalTwinEmbeddingError",
]
