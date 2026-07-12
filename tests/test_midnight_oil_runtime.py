from __future__ import annotations

import base64
import hashlib
import json
from collections.abc import Iterator
from concurrent.futures import ThreadPoolExecutor
from dataclasses import replace
from html.parser import HTMLParser
from pathlib import Path
from typing import Any

import pytest
from fastapi import FastAPI, Request
from fastapi.testclient import TestClient

from interfaces.research.api.midnight_oil_routes import register_midnight_oil_routes
from interfaces.research.api.midnight_oil_runtime import (
    build_midnight_oil_api_runtime,
    create_midnight_oil_production_app,
)
from runtime.db_lock import connect_read, connect_write
from substrate.dispatch import (
    DispatchConfig,
    NormalizedUsage,
    OpenAICompatProvider,
    ProviderError,
    RawProviderResponse,
    get_provider,
    register_provider,
    reset_provider_registry,
)
from substrate.graph import ensure_initialized
from substrate.graph.ops import insert_chunk, insert_document
from substrate.midnight_oil.job import create_job, put_job_state
from substrate.midnight_oil.job_store import OperationState, OwnerJob
from substrate.midnight_oil.readiness import build_readiness_receipt
from substrate.midnight_oil.readiness import main as readiness_main
from substrate.midnight_oil.runtime import (
    MidnightOilRuntimeConfig,
    MidnightOilRuntimeConfigError,
    ProviderIdempotencyAttestation,
    provider_endpoint_sha256,
)
from substrate.midnight_oil.worker_cli import build_worker_runtime, run_worker_once


class _Embedding:
    dimension = 2

    def encode(self, text: str) -> list[float]:
        del text
        return [1.0, 0.0]


class _ReadinessJsonParser(HTMLParser):
    def __init__(self) -> None:
        super().__init__()
        self.capture = False
        self.payload = ""

    def handle_starttag(
        self, tag: str, attrs: list[tuple[str, str | None]]
    ) -> None:
        values = dict(attrs)
        self.capture = tag == "script" and values.get("id") == "midnight-oil-readiness"

    def handle_endtag(self, tag: str) -> None:
        if tag == "script":
            self.capture = False

    def handle_data(self, data: str) -> None:
        if self.capture:
            self.payload += data


@pytest.fixture(autouse=True)
def _providers() -> Iterator[None]:
    reset_provider_registry()
    yield
    reset_provider_registry()


def _runtime_files(tmp_path: Path) -> tuple[Path, dict[str, str], Path]:
    dispatch = tmp_path / "dispatch.yaml"
    dispatch.write_text(
        """
tiers:
  synthesis:
    provider: verified-provider
    model: verified-model
    pricing:
      input_per_mtok: 1.0
      output_per_mtok: 2.0
      cached_input_per_mtok: 0.5
tier_defaults:
  synthesis:
    max_tokens: 1000
    context_budget_tokens: 32000
    temperature: 0.1
role_tiers:
  synthesizer: synthesis
""".strip(),
        encoding="utf-8",
    )
    endpoint_hash = provider_endpoint_sha256(
        provider_name="verified-provider",
        base_url="https://provider.example.test",
        chat_completions_path="/v1/chat/completions",
        api_key_env="VERIFIED_PROVIDER_KEY",
    )
    attestation = tmp_path / "provider-attestation.json"
    attestation.write_text(
        json.dumps(
            {
                "schema_version": 1,
                "provider_name": "verified-provider",
                "base_url": "https://provider.example.test",
                "chat_completions_path": "/v1/chat/completions",
                "api_key_env": "VERIFIED_PROVIDER_KEY",
                "endpoint_sha256": endpoint_hash,
                "dispatch_config_sha256": hashlib.sha256(
                    dispatch.read_bytes()
                ).hexdigest(),
                "evidence_ref": "urn:test:verified-idempotency-contract",
                "verified_at": "2026-07-12T12:00:00Z",
            }
        ),
        encoding="utf-8",
    )
    runtime = tmp_path / "runtime.json"
    runtime.write_text(
        json.dumps(
            {
                "state_dir": str(tmp_path / "state"),
                "graph_db_path": str(tmp_path / "graph.duckdb"),
                "engagement_dir": str(tmp_path / "engagement"),
                "dispatch_config_path": str(dispatch),
                "retrieval_kind": "brute_force",
                "embedding_model_name": "test-embedding",
                "consent_active_key_id": "primary",
                "consent_signing_key_env": "MO_PRIMARY_KEY",
                "consent_verification_key_envs": {
                    "primary": "MO_PRIMARY_KEY"
                },
                "provider_attestation_paths": [str(attestation)],
                "worker_lease_ms": 60_000,
                "worker_poll_ms": 1_000,
            }
        ),
        encoding="utf-8",
    )
    environment = {
        "MO_PRIMARY_KEY": base64.urlsafe_b64encode(b"k" * 32).decode().rstrip("="),
        "VERIFIED_PROVIDER_KEY": "test-key-never-serialized",
        "ANTIEK_OPERATOR_TOKEN": "operator-token-never-serialized",
    }
    return runtime, environment, attestation


def test_runtime_builds_same_durable_api_and_worker_composition(tmp_path: Path) -> None:
    path, environment, _ = _runtime_files(tmp_path)
    api = build_midnight_oil_api_runtime(path, environ=environment)
    worker = build_worker_runtime(path, environ=environment)

    assert type(api.dependencies.owner_jobs) is type(worker.stores.owner_jobs)
    assert api.config == worker.config
    assert api.dependencies.operation_queue is api.stores.operation_queue
    assert api.dependencies.live_plan_resolver is not None
    provider = get_provider("verified-provider")
    assert provider.idempotency_guaranteed is True  # type: ignore[attr-defined]


def test_production_app_does_not_overwrite_attested_provider(tmp_path: Path) -> None:
    path, environment, _ = _runtime_files(tmp_path)
    app = create_midnight_oil_production_app(path, environ=environment)
    assert app.state.midnight_oil_runtime.config.state_dir == tmp_path / "state"
    provider = get_provider("verified-provider")
    assert provider.idempotency_guaranteed is True  # type: ignore[attr-defined]


def test_worker_no_work_is_structured_and_non_spending(tmp_path: Path) -> None:
    path, environment, _ = _runtime_files(tmp_path)
    runtime = build_worker_runtime(path, environ=environment)
    record = run_worker_once(
        runtime,
        worker_id="worker-1",
        embedding_model=_Embedding(),
        clock_ms=lambda: 1_000,
    )
    assert record.result == "no_work"
    assert record.phase == "queue_empty"
    assert "test-key-never-serialized" not in record.to_json()


def test_readiness_receipt_proves_zero_spend_composition_without_secrets(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    path, environment, _ = _runtime_files(tmp_path)
    monkeypatch.setattr(
        OpenAICompatProvider,
        "_ensure_client",
        lambda self: (_ for _ in ()).throw(AssertionError("provider network attempted")),
    )

    receipt = build_readiness_receipt(
        path, environ=environment, checked_at_ms=1_234
    )

    assert receipt.state == "ready"
    assert receipt.checked_at_ms == 1_234
    assert receipt.attested_providers == ("verified-provider",)
    assert receipt.worker_result == "no_work"
    assert receipt.worker_phase == "shutdown_before_claim"
    assert all(check.passed for check in receipt.checks)
    serialized = receipt.to_json() + receipt.to_html()
    assert "test-key-never-serialized" not in serialized
    assert "MO_PRIMARY_KEY" not in serialized
    assert "operator-token-never-serialized" not in serialized
    assert str(tmp_path) not in serialized
    assert "<script type=\"application/json\"" in receipt.to_html()
    parser = _ReadinessJsonParser()
    parser.feed(receipt.to_html())
    assert json.loads(parser.payload) == json.loads(receipt.to_json())


def test_readiness_does_not_touch_claimable_work(tmp_path: Path) -> None:
    path, environment, _ = _runtime_files(tmp_path)
    runtime = build_midnight_oil_api_runtime(path, environ=environment)
    runtime.stores.operation_queue.enqueue_once(
        operation_id="operation-readiness-blocked",
        owner_user_id="operator",
        job_id="job-readiness-blocked",
        enqueued_at_ms=1,
        options={
            "max_steps": None,
            "auto_deposit": True,
            "draft_combined": True,
            "force_offline": False,
        },
    )

    receipt = build_readiness_receipt(path, environ=environment, checked_at_ms=2)
    assert receipt.state == "ready"
    assert receipt.worker_phase == "shutdown_before_claim"
    stop_check = next(
        check for check in receipt.checks if check.name == "zero_spend_worker_stop_boundary"
    )
    assert stop_check.passed is True
    assert stop_check.evidence == "stopped_before_claim"

    queued = runtime.stores.operation_queue.get("operation-readiness-blocked")
    assert queued is not None
    assert queued.lease_generation == 0
    assert queued.lease_owner is None


def test_readiness_rejects_open_operator_auth(tmp_path: Path) -> None:
    path, environment, _ = _runtime_files(tmp_path)
    environment.pop("ANTIEK_OPERATOR_TOKEN")

    with pytest.raises(MidnightOilRuntimeConfigError, match="authentication is not enabled"):
        build_readiness_receipt(path, environ=environment, checked_at_ms=2)


def test_readiness_cli_failure_is_sanitized(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
) -> None:
    path, environment, _ = _runtime_files(tmp_path)
    for name, value in environment.items():
        if name != "VERIFIED_PROVIDER_KEY":
            monkeypatch.setenv(name, value)
    monkeypatch.delenv("VERIFIED_PROVIDER_KEY", raising=False)

    assert readiness_main(["--config", str(path)]) == 1

    captured = capsys.readouterr()
    assert captured.out == ""
    payload = json.loads(captured.err)
    assert payload == {
        "error_code": "configuration_not_ready",
        "schema_version": 1,
        "state": "not_ready",
    }
    assert "VERIFIED_PROVIDER_KEY" not in captured.err
    assert str(tmp_path) not in captured.err
    assert "test-key-never-serialized" not in captured.err


def test_attestation_fingerprint_tamper_fails_before_provider_install(
    tmp_path: Path,
) -> None:
    path, environment, attestation = _runtime_files(tmp_path)
    raw = json.loads(attestation.read_text(encoding="utf-8"))
    raw["base_url"] = "https://different.example.test"
    attestation.write_text(json.dumps(raw), encoding="utf-8")
    with pytest.raises(MidnightOilRuntimeConfigError, match="fingerprint conflicts"):
        build_worker_runtime(path, environ=environment)
    with pytest.raises(KeyError):
        get_provider("verified-provider")


def test_dispatch_config_drift_fails_before_provider_install(tmp_path: Path) -> None:
    path, environment, _ = _runtime_files(tmp_path)
    runtime_raw = json.loads(path.read_text(encoding="utf-8"))
    dispatch = Path(runtime_raw["dispatch_config_path"])
    dispatch.write_text(
        dispatch.read_text(encoding="utf-8").replace(
            "model: verified-model", "model: unreviewed-model"
        ),
        encoding="utf-8",
    )
    with pytest.raises(MidnightOilRuntimeConfigError, match="configuration conflicts"):
        build_worker_runtime(path, environ=environment)
    with pytest.raises(KeyError):
        get_provider("verified-provider")


def test_runtime_and_attestation_contracts_reject_unknown_fields(tmp_path: Path) -> None:
    path, _, attestation = _runtime_files(tmp_path)
    runtime_raw = json.loads(path.read_text(encoding="utf-8"))
    runtime_raw["enable_live"] = True
    path.write_text(json.dumps(runtime_raw), encoding="utf-8")
    with pytest.raises(MidnightOilRuntimeConfigError, match="unknown or missing"):
        MidnightOilRuntimeConfig.from_file(path)

    attestation_raw = json.loads(attestation.read_text(encoding="utf-8"))
    attestation_raw["trusted"] = True
    attestation.write_text(json.dumps(attestation_raw), encoding="utf-8")
    with pytest.raises(MidnightOilRuntimeConfigError, match="unknown or missing"):
        ProviderIdempotencyAttestation.from_file(attestation)


def test_missing_secret_reports_configuration_without_naming_secret(tmp_path: Path) -> None:
    path, environment, _ = _runtime_files(tmp_path)
    environment.pop("VERIFIED_PROVIDER_KEY")
    with pytest.raises(MidnightOilRuntimeConfigError) as failure:
        build_worker_runtime(path, environ=environment)
    assert "VERIFIED_PROVIDER_KEY" not in str(failure.value)


@pytest.mark.parametrize(
    "mode",
    [
        "normal",
        "stop_after_paid",
        "config_drift",
        "deposit_crash",
        "projection_crash",
        "provider_timeout",
        "stop_before_claim",
        "stop_before_provider",
        "budget_halt",
        "post_action_crash",
    ],
)
def test_api_to_worker_executes_deposits_projects_and_archives_once(
    tmp_path: Path, mode: str, monkeypatch: pytest.MonkeyPatch
) -> None:
    path, environment, _ = _runtime_files(tmp_path)
    api = build_midnight_oil_api_runtime(path, environ=environment)
    app = FastAPI()

    @app.middleware("http")
    async def _auth(request: Request, call_next):  # type: ignore[no-untyped-def]
        request.state.user_id = "operator-runtime"
        return await call_next(request)

    register_midnight_oil_routes(app, dependencies=api.dependencies)
    client = TestClient(app)
    created = client.post(
        "/midnight-oil/create",
        json={
            "goals": ["Synthesize the seeded evidence."],
            "duration_minutes": 10,
            "model_id": "verified-model",
            "live": True,
        },
    )
    assert created.status_code == 200, created.text
    job_id = created.json()["job_id"]
    consent = client.post(
        f"/midnight-oil/jobs/{job_id}/spend-consent",
        json=(
            {"ceiling_cents": 1, "force_below": True}
            if mode == "budget_halt"
            else {"use_recommended": True}
        ),
    )
    assert consent.status_code == 200, consent.text
    queued = client.post(
        "/midnight-oil/run",
        headers={"X-Midnight-Oil-Spend-Consent": consent.json()["token"]},
        json={"job_id": job_id},
    )
    assert queued.status_code == 200, queued.text

    ensure_initialized(str(api.config.graph_db_path))
    with connect_write(
        str(api.config.graph_db_path), purpose="test/runtime-e2e-seed"
    ) as con:
        insert_document(
            con,
            document_id="runtime-source",
            source_tier=1,
            document_type="paper",
            title="Runtime source",
        )
        insert_chunk(
            con,
            document_id="runtime-source",
            chunk_index=0,
            text="Seeded evidence for the runtime worker.",
            embedding=[1.0, 0.0],
            chunk_id="runtime-chunk",
        )

    class _PaidProvider:
        name = "verified-provider"
        idempotency_guaranteed = True

        def __init__(self) -> None:
            self.keys: list[str] = []

        def call_idempotent(
            self,
            *,
            idempotency_key: str,
            model: str,
            prompt: str,
            max_tokens: int,
            temperature: float,
        ) -> RawProviderResponse:
            del model, prompt, max_tokens, temperature
            self.keys.append(idempotency_key)
            if mode == "provider_timeout":
                raise ProviderError(
                    "secret provider timeout detail",
                    provider=self.name,
                    model="verified-model",
                    latency_ms=1,
                    retryable=True,
                )
            return RawProviderResponse(
                text="Runtime synthesis with durable evidence.",
                raw_usage={"prompt_tokens": 10, "completion_tokens": 5},
                finish_reason="stop",
                latency_ms=1,
                request_id="runtime-request",
            )

        def call(
            self,
            *,
            model: str,
            prompt: str,
            max_tokens: int,
            temperature: float,
        ) -> RawProviderResponse:
            del model, prompt, max_tokens, temperature
            raise AssertionError("live worker must use the idempotent provider method")

        def normalize_usage(self, raw_usage: dict[str, Any]) -> NormalizedUsage:
            return NormalizedUsage(
                input_tokens=int(raw_usage["prompt_tokens"]),
                output_tokens=int(raw_usage["completion_tokens"]),
            )

    paid = _PaidProvider()
    reset_provider_registry()
    register_provider(paid)
    worker = build_worker_runtime(path, environ=environment)
    # build_worker_runtime reinstalls the attested HTTP adapter; replace only
    # after its admission checks so the test proves the same config contract.
    register_provider(paid)

    if mode == "config_drift":
        tier = worker.dispatch_config.tiers["synthesis"]
        worker = replace(
            worker,
            dispatch_config=DispatchConfig(
                role_tiers=worker.dispatch_config.role_tiers,
                tiers={"synthesis": replace(tier, temperature=0.9)},
            ),
        )
        blocked = run_worker_once(
            worker,
            worker_id="runtime-worker-drift",
            embedding_model=_Embedding(),
        )
        assert blocked.result == "blocked_provider"
        assert blocked.deposit_document_id
        assert paid.keys == []
        assert worker.stores.operation_queue.next_claimable(now_ms=10**18) is None
        return
    if mode == "stop_before_claim":
        stopped = run_worker_once(
            worker,
            worker_id="runtime-worker-prestopped",
            embedding_model=_Embedding(),
            stop_requested=lambda: True,
        )
        assert stopped.result == "no_work"
        assert stopped.phase == "shutdown_before_claim"
        assert paid.keys == []
        assert worker.stores.operation_queue.next_claimable(now_ms=10**18) is not None
        return
    if mode == "stop_before_provider":
        checks = 0

        def stop_between_claim_and_provider() -> bool:
            nonlocal checks
            checks += 1
            return checks >= 2

        stopped = run_worker_once(
            worker,
            worker_id="runtime-worker-stop-before-provider",
            embedding_model=_Embedding(),
            stop_requested=stop_between_claim_and_provider,
        )
        assert stopped.result == "lease_pending"
        assert stopped.phase == "shutdown_before_provider"
        assert paid.keys == []
        recovered = run_worker_once(
            worker,
            worker_id="runtime-worker-after-stop",
            embedding_model=_Embedding(),
            clock_ms=lambda: 10**18,
        )
        assert recovered.result == "complete"
        assert len(paid.keys) == 1
        return
    if mode == "provider_timeout":
        reconciled = run_worker_once(
            worker,
            worker_id="runtime-worker-timeout",
            embedding_model=_Embedding(),
        )
        assert reconciled.result == "reconcile_required"
        assert reconciled.deposit_document_id
        assert "secret provider timeout detail" not in reconciled.to_json()
        assert len(paid.keys) == 1
        assert worker.stores.operation_queue.next_claimable(now_ms=10**18) is None
        return
    if mode == "post_action_crash":
        def crash_after_paid_checkpoint() -> None:
            raise RuntimeError("soft crash after paid action")

        worker.stores.operation_queue._after_fenced_action = (  # type: ignore[method-assign]
            crash_after_paid_checkpoint
        )
        recovered = run_worker_once(
            worker,
            worker_id="runtime-worker-post-action-crash",
            embedding_model=_Embedding(),
        )
        assert recovered.result == "recovered"
        assert recovered.graph_deliverable_id
        authority = worker.stores.owner_jobs.get_job(
            owner_user_id="operator-runtime", job_id=job_id
        )
        assert authority is not None
        assert authority.operation_state is OperationState.COMPLETE
        assert len(paid.keys) == 1
        assert worker.stores.operation_queue.next_claimable(now_ms=10**18) is None
        return
    if mode == "budget_halt":
        halted = run_worker_once(
            worker,
            worker_id="runtime-worker-budget",
            embedding_model=_Embedding(),
        )
        assert halted.result == "budget_halted"
        assert halted.phase == "terminal_without_graph_archived"
        assert halted.deposit_document_id
        assert halted.graph_deliverable_id is None
        assert paid.keys == []
        assert worker.stores.operation_queue.next_claimable(now_ms=10**18) is None
        return

    def execute(worker_id: str):  # type: ignore[no-untyped-def]
        return run_worker_once(
            worker,
            worker_id=worker_id,
            embedding_model=_Embedding(),
        )

    if mode in {"deposit_crash", "projection_crash"}:
        import substrate.midnight_oil.worker_cli as worker_module

        attribute = (
            "resume_terminal_deposit"
            if mode == "deposit_crash"
            else "resume_terminal_projection"
        )
        original = getattr(worker_module, attribute)

        def crash(*args: Any, **kwargs: Any) -> Any:
            del args, kwargs
            raise RuntimeError("injected persistence crash")

        monkeypatch.setattr(worker_module, attribute, crash)
        pending = execute("runtime-worker-crashing")
        assert pending.result == (
            "deposit_pending" if mode == "deposit_crash" else "projection_pending"
        )
        assert len(paid.keys) == 1
        monkeypatch.setattr(worker_module, attribute, original)
        result = run_worker_once(
            worker,
            worker_id="runtime-worker-recovery",
            embedding_model=_Embedding(),
            clock_ms=lambda: 10**18,
        )
        assert result.result == "recovered"
    elif mode == "stop_after_paid":
        stopped = run_worker_once(
            worker,
            worker_id="runtime-worker-stopping",
            embedding_model=_Embedding(),
            stop_requested=lambda: bool(paid.keys),
        )
        assert stopped.result == "deposit_pending"
        assert stopped.phase == "shutdown_after_provider"
        assert len(paid.keys) == 1
        result = run_worker_once(
            worker,
            worker_id="runtime-worker-recovery",
            embedding_model=_Embedding(),
            clock_ms=lambda: 10**18,
        )
        assert result.result == "recovered"
    else:
        with ThreadPoolExecutor(max_workers=2) as pool:
            records = list(pool.map(execute, ("runtime-worker-a", "runtime-worker-b")))
        result = next(record for record in records if record.result == "complete")
        assert {record.result for record in records} <= {
            "complete",
            "contended",
            "no_work",
        }
        assert sum(record.result == "complete" for record in records) == 1
    assert result.result in {"complete", "recovered"}
    assert result.deposit_document_id
    assert result.graph_deliverable_id
    assert len(paid.keys) == 1
    assert worker.stores.operation_queue.next_claimable(now_ms=10**18) is None
    second = run_worker_once(
        worker,
        worker_id="runtime-worker",
        embedding_model=_Embedding(),
    )
    assert second.result == "no_work"
    assert len(paid.keys) == 1
    with connect_read(str(api.config.graph_db_path)) as con:
        assert con.execute(
            "SELECT count(*) FROM deliverables WHERE deliverable_id = ?",
            [result.graph_deliverable_id],
        ).fetchone() == (1,)


def test_terminal_failure_without_paid_evidence_deposits_and_archives(
    tmp_path: Path,
) -> None:
    path, environment, _ = _runtime_files(tmp_path)
    runtime = build_worker_runtime(path, environ=environment)
    job = create_job(
        ["A pre-network failure still deserves a visible terminal deposit."],
        10,
        store=runtime.stores.jobs,
        job_id="failed-job",
        asset_id="failed-asset",
    )
    put_job_state(
        replace(job, status="failed"),
        store=runtime.stores.jobs,
    )
    runtime.stores.owner_jobs.put_job(
        OwnerJob(
            owner_user_id="operator-runtime",
            job_id=job.job_id,
            state_version=4,
            approved_ceiling_cents=100,
            consent_receipt_id="receipt",
            consent_config_hash="c" * 64,
            consent_issued_at_ms=1,
            consent_expires_at_ms=100,
            consent_claimed_at_ms=2,
            operation_id="failed-operation",
            operation_state=OperationState.FAILED,
            dispatch_started_at_ms=3,
            dispatched_at_ms=None,
            completed_at_ms=4,
            payload={},
        )
    )
    runtime.stores.operation_queue.enqueue_once(
        operation_id="failed-operation",
        owner_user_id="operator-runtime",
        job_id=job.job_id,
        enqueued_at_ms=1,
        options={
            "max_steps": None,
            "auto_deposit": True,
            "draft_combined": True,
            "force_offline": False,
        },
    )
    runtime.stores.operation_queue.lease(
        operation_id="failed-operation",
        worker_id="dead-worker",
        leased_at_ms=2,
        lease_expires_at_ms=3,
    )
    result = run_worker_once(
        runtime,
        worker_id="recovery-worker",
        embedding_model=_Embedding(),
        clock_ms=lambda: 4,
    )
    assert result.result == "failed"
    assert result.deposit_document_id
    assert result.graph_deliverable_id is None
    assert runtime.stores.operation_queue.next_claimable(now_ms=5) is None


def test_missing_authority_is_quarantined_without_starving_queue(tmp_path: Path) -> None:
    path, environment, _ = _runtime_files(tmp_path)
    runtime = build_worker_runtime(path, environ=environment)
    runtime.stores.operation_queue.enqueue_once(
        operation_id="orphan-operation",
        owner_user_id="missing-owner",
        job_id="missing-job",
        enqueued_at_ms=1,
        options={
            "max_steps": None,
            "auto_deposit": True,
            "draft_combined": True,
            "force_offline": False,
        },
    )
    record = run_worker_once(
        runtime,
        worker_id="quarantine-worker",
        embedding_model=_Embedding(),
        clock_ms=lambda: 2,
    )
    assert record.result == "reconcile_required"
    assert record.phase == "authority_quarantined"
    assert runtime.stores.operation_queue.next_claimable(now_ms=3) is None
