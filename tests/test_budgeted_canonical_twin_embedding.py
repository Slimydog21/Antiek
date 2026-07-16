from __future__ import annotations

# ruff: noqa: F811 - fixture names are intentionally imported for pytest.
import hashlib
import json
from dataclasses import replace
from decimal import Decimal
from pathlib import Path

import pytest
from test_canonical_aggregate_projection import completed_parent  # noqa: F401
from test_canonical_twin_publication import _graph, _ready_parent

from runtime.research_runner.protocol import (
    BillingUnit,
    BoundedUsage,
    CostProjection,
    CostProjectionRequest,
    ProjectionDisposition,
    ProjectionRate,
)
from runtime.research_runner.provider_gateway import (
    PaidFallbackOutcomeUnknown,
    PaidRouteAuthorityIdentity,
    ProviderCapabilities,
    ProviderReconciliation,
    ProviderSuccess,
    ReconciliationStatus,
    ResearchProviderGateway,
)
from substrate.graph.search import search
from substrate.research_spend import ResearchSpendLedger, RunBinding
from substrate.twin_recursion import (
    BudgetedCanonicalTwinEmbedder,
    CanonicalTwinEmbeddingError,
    publish_canonical_twin,
)


def _binding() -> RunBinding:
    return RunBinding("embed-run", "acct", "session-root", "plan-digest", 4)


def _request() -> CostProjectionRequest:
    return CostProjectionRequest(
        "twin.canonical.embed",
        "embed-provider",
        "embed-model",
        "embed",
        (BoundedUsage(BillingUnit.CALL, 1),),
    )


def _project(request: CostProjectionRequest) -> CostProjection:
    return CostProjection(
        request.seam_id,
        request.provider,
        request.model,
        request.operation,
        request.bounded_usage,
        (ProjectionRate(BillingUnit.CALL, Decimal("0.80")),),
        "embed-rate-v1",
        "USD",
        Decimal("0.80"),
        80,
        ProjectionDisposition.HOLD_ELIGIBLE,
    )


def _authorize(request, adapter) -> PaidRouteAuthorityIdentity:
    return PaidRouteAuthorityIdentity(
        "test",
        request.provider,
        adapter.endpoint,
        request.model,
        request.seam_id,
        request.operation,
        "embed-rate-v1",
        "USD",
        (ProjectionRate(BillingUnit.CALL, Decimal("0.80")),),
    )


class EmbeddingAdapter:
    provider = "embed-provider"
    provider_name = "embed-provider"
    model = "embed-model"
    model_name = "embed-model"
    dimension = 3
    endpoint = "https://embed-provider.example/v1"
    capabilities = ProviderCapabilities(True, True, True, frozenset({BillingUnit.CALL}))

    def __init__(self) -> None:
        self.sends: list[str] = []
        self.reconciles: list[str] = []
        self.expected_operation_digest = ""

    def _evidence(self, operation, key: str) -> dict[str, str]:
        vector = (0.25, -0.5, 0.75)
        vector_hash = hashlib.sha256(
            b"".join(__import__("struct").pack(">d", item) for item in vector)
        ).hexdigest()
        return {
            "billing_status": "settled",
            "currency": "USD",
            "operation_digest": self.expected_operation_digest,
            "output_sha256": vector_hash,
            "provider_idempotency_key": key,
            "provider_request_id": "request-1",
            "provider_response_id": "response-1",
            "schema": "antiek.twin-provider-settlement.v1",
            "usage_json": json.dumps({"calls": 1}, separators=(",", ":")),
        }

    def send_once(self, operation, *, provider_idempotency_key, authorized_endpoint):
        assert authorized_endpoint == self.endpoint
        self.sends.append(provider_idempotency_key)
        return ProviderSuccess(
            [0.25, -0.5, 0.75],
            60,
            self._evidence(operation, provider_idempotency_key),
        )

    def reconcile(self, *, provider_idempotency_key, authorized_endpoint):
        self.reconciles.append(provider_idempotency_key)
        raise AssertionError("reconciliation is not expected in this test")


class RecoveringAdapter(EmbeddingAdapter):
    def __init__(self) -> None:
        super().__init__()
        self.fail_after_acceptance = True
        self.return_vector = True

    def send_once(self, operation, *, provider_idempotency_key, authorized_endpoint):
        self.sends.append(provider_idempotency_key)
        if self.fail_after_acceptance:
            self.fail_after_acceptance = False
            raise TimeoutError("response lost after provider acceptance")
        raise AssertionError("gateway must reconcile instead of resending")

    def reconcile(self, *, provider_idempotency_key, authorized_endpoint):
        assert authorized_endpoint == self.endpoint
        self.reconciles.append(provider_idempotency_key)
        return ProviderReconciliation(
            ReconciliationStatus.CHARGED,
            self._evidence(None, provider_idempotency_key),
            actual_cents=60,
            value=[0.25, -0.5, 0.75] if self.return_vector else None,
        )


class SearchEmbedding:
    dimension = 3
    provider_name = "embed-provider"
    model_name = "embed-model"

    def encode(self, text: str) -> list[float]:
        return [0.25, -0.5, 0.75]


def _setup(completed_parent, tmp_path: Path):
    ledger, snapshot, _ = _ready_parent(completed_parent)
    graph = _graph(tmp_path / "embedding-graph.duckdb")
    publication = publish_canonical_twin(graph, ledger, binding_id=snapshot.binding_id)
    spend = ResearchSpendLedger(tmp_path / "embedding-spend.sqlite3")
    gateway = ResearchProviderGateway(
        spend, projector=_project, fallback_route_authorizer=_authorize
    )
    gateway.create_or_reopen_run(_binding(), ceiling_cents=100)
    worker = BudgetedCanonicalTwinEmbedder(
        gateway=gateway, ledger=ledger, journal_path=tmp_path / "embedding-journal.sqlite3"
    )
    return ledger, graph, publication, gateway, worker


def _approved(worker, graph, adapter):
    preview = worker.prepare(
        graph,
        binding=_binding(),
        source_asset_id=_source_asset(graph),
        source_hash=_source_hash(graph),
        projection_request=_request(),
        adapter=adapter,
    )
    adapter.expected_operation_digest = preview.operation_digest
    approval = worker.approve(command_key="approve-embedding", binding=_binding(), preview=preview)
    return preview, approval.approval_id


def _source_hash(graph) -> str:
    metadata = json.loads(
        graph.execute(
            "SELECT metadata FROM documents WHERE document_type='canonical_twin'"
        ).fetchone()[0]
    )
    return metadata["source_hash"]


def _source_asset(graph) -> str:
    metadata = json.loads(
        graph.execute(
            "SELECT metadata FROM documents WHERE document_type='canonical_twin'"
        ).fetchone()[0]
    )
    return metadata["source_asset_id"]


def test_preview_has_no_hold_or_send_and_execution_is_atomic(completed_parent, tmp_path):
    _, graph, publication, gateway, worker = _setup(completed_parent, tmp_path)
    adapter = EmbeddingAdapter()
    try:
        _, approval_id = _approved(worker, graph, adapter)
        assert adapter.sends == []
        assert [event.event_kind for event in gateway.ledger.events("embed-run")] == ["run_created"]
        result = worker.embed(
            graph,
            binding=_binding(),
            source_asset_id=_source_asset(graph),
            source_hash=_source_hash(graph),
            projection_request=_request(),
            adapter=adapter,
            approval_id=approval_id,
        )
        assert result.chunk_id == publication.chunk_id and result.actual_cents == 60
        assert len(adapter.sends) == 1
        assert graph.execute(
            "SELECT embedding FROM chunks WHERE chunk_id=?", [publication.chunk_id]
        ).fetchone()[0] == [0.25, -0.5, 0.75]
        assert graph.execute(
            "SELECT provider,model_name,dimension FROM embeddings_meta WHERE chunk_id=?",
            [publication.chunk_id],
        ).fetchone() == ("embed-provider", "embed-model", 3)
        assert graph.execute("SELECT count(*) FROM nodes").fetchone() == (0,)
        assert graph.execute("SELECT count(*) FROM edges").fetchone() == (0,)
    finally:
        graph.close()


def test_exact_replay_sends_and_charges_once_and_remains_owner_only(completed_parent, tmp_path):
    _, graph, publication, gateway, worker = _setup(completed_parent, tmp_path)
    adapter = EmbeddingAdapter()
    try:
        _, approval_id = _approved(worker, graph, adapter)
        first = worker.embed(
            graph,
            binding=_binding(),
            source_asset_id=_source_asset(graph),
            source_hash=_source_hash(graph),
            projection_request=_request(),
            adapter=adapter,
            approval_id=approval_id,
        )
        replay = worker.embed(
            graph,
            binding=_binding(),
            source_asset_id=_source_asset(graph),
            source_hash=_source_hash(graph),
            projection_request=_request(),
            adapter=adapter,
            approval_id=approval_id,
        )
        assert first.replayed is False and replay.replayed is True
        assert len(adapter.sends) == 1
        assert gateway.ledger.balance("embed-run").authorized_spent_cents == 60
        assert (
            search(graph, "Insight", model=SearchEmbedding(), policy_tag="attribution_eligible")[
                "results"
            ]
            == []
        )
        owner = search(
            graph,
            "Insight",
            model=SearchEmbedding(),
            policy_tag="private_research",
            owner_user_id="acct",
        )
        assert [row["document_id"] for row in owner["results"]] == [publication.document_id]
    finally:
        graph.close()


def test_graph_failure_rolls_back_vector_and_metadata(completed_parent, tmp_path):
    ledger, graph, publication, gateway, _ = _setup(completed_parent, tmp_path)
    adapter = EmbeddingAdapter()
    worker = BudgetedCanonicalTwinEmbedder(
        gateway=gateway,
        ledger=ledger,
        journal_path=tmp_path / "embedding-journal.sqlite3",
        failure_injector=lambda point: (
            (_ for _ in ()).throw(RuntimeError("crash")) if point == "after_vector_write" else None
        ),
    )
    try:
        _, approval_id = _approved(worker, graph, adapter)
        with pytest.raises(RuntimeError, match="crash"):
            worker.embed(
                graph,
                binding=_binding(),
                source_asset_id=_source_asset(graph),
                source_hash=_source_hash(graph),
                projection_request=_request(),
                adapter=adapter,
                approval_id=approval_id,
            )
        assert (
            graph.execute(
                "SELECT embedding FROM chunks WHERE chunk_id=?", [publication.chunk_id]
            ).fetchone()[0]
            is None
        )
        assert graph.execute("SELECT count(*) FROM embeddings_meta").fetchone() == (0,)
        recovered = BudgetedCanonicalTwinEmbedder(
            gateway=gateway,
            ledger=ledger,
            journal_path=tmp_path / "embedding-journal.sqlite3",
        ).embed(
            graph,
            binding=_binding(),
            source_asset_id=_source_asset(graph),
            source_hash=_source_hash(graph),
            projection_request=_request(),
            adapter=adapter,
            approval_id=approval_id,
        )
        assert recovered.replayed is False
        assert len(adapter.sends) == 1
        assert gateway.ledger.balance("embed-run").authorized_spent_cents == 60
        assert graph.execute(
            "SELECT count(*) FROM embeddings_meta WHERE chunk_id=?", [publication.chunk_id]
        ).fetchone() == (1,)
    finally:
        graph.close()


def test_substituted_vector_or_publication_is_rejected(completed_parent, tmp_path):
    _, graph, publication, _, worker = _setup(completed_parent, tmp_path)
    adapter = EmbeddingAdapter()
    try:
        _, approval_id = _approved(worker, graph, adapter)
        graph.execute(
            "UPDATE chunks SET text='substituted' WHERE chunk_id=?", [publication.chunk_id]
        )
        with pytest.raises(CanonicalTwinEmbeddingError, match="unavailable"):
            worker.embed(
                graph,
                binding=_binding(),
                source_asset_id=_source_asset(graph),
                source_hash=_source_hash(graph),
                projection_request=_request(),
                adapter=adapter,
                approval_id=approval_id,
            )
        assert adapter.sends == []
    finally:
        graph.close()


def test_unknown_send_reconciles_with_vector_without_resend(completed_parent, tmp_path):
    _, graph, _, gateway, worker = _setup(completed_parent, tmp_path)
    adapter = RecoveringAdapter()
    try:
        _, approval_id = _approved(worker, graph, adapter)
        with pytest.raises(PaidFallbackOutcomeUnknown):
            worker.embed(
                graph,
                binding=_binding(),
                source_asset_id=_source_asset(graph),
                source_hash=_source_hash(graph),
                projection_request=_request(),
                adapter=adapter,
                approval_id=approval_id,
            )
        result = worker.embed(
            graph,
            binding=_binding(),
            source_asset_id=_source_asset(graph),
            source_hash=_source_hash(graph),
            projection_request=_request(),
            adapter=adapter,
            approval_id=approval_id,
        )
        assert result.actual_cents == 60
        assert len(adapter.sends) == 1 and len(adapter.reconciles) == 1
        assert gateway.ledger.balance("embed-run").authorized_spent_cents == 60
    finally:
        graph.close()


def test_charged_reconciliation_without_vector_stays_unknown(completed_parent, tmp_path):
    _, graph, _, gateway, worker = _setup(completed_parent, tmp_path)
    adapter = RecoveringAdapter()
    adapter.return_vector = False
    try:
        _, approval_id = _approved(worker, graph, adapter)
        with pytest.raises(PaidFallbackOutcomeUnknown):
            worker.embed(
                graph,
                binding=_binding(),
                source_asset_id=_source_asset(graph),
                source_hash=_source_hash(graph),
                projection_request=_request(),
                adapter=adapter,
                approval_id=approval_id,
            )
        with pytest.raises(PaidFallbackOutcomeUnknown):
            worker.embed(
                graph,
                binding=_binding(),
                source_asset_id=_source_asset(graph),
                source_hash=_source_hash(graph),
                projection_request=_request(),
                adapter=adapter,
                approval_id=approval_id,
            )
        assert len(adapter.sends) == 1 and len(adapter.reconciles) == 1
        balance = gateway.ledger.balance("embed-run")
        assert balance.authorized_spent_cents == 0 and balance.held_cents == 80
    finally:
        graph.close()


def test_forged_preview_digest_cannot_authorize(completed_parent, tmp_path):
    _, graph, _, _, worker = _setup(completed_parent, tmp_path)
    adapter = EmbeddingAdapter()
    try:
        preview = worker.prepare(
            graph,
            binding=_binding(),
            source_asset_id=_source_asset(graph),
            source_hash=_source_hash(graph),
            projection_request=_request(),
            adapter=adapter,
        )
        with pytest.raises(CanonicalTwinEmbeddingError, match="prepared authority"):
            worker.approve(
                command_key="forged-preview",
                binding=_binding(),
                preview=replace(preview, operation_digest="0" * 64),
            )
        assert adapter.sends == []
    finally:
        graph.close()
