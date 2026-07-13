from __future__ import annotations

import base64
import hashlib
import json
import sqlite3
import time
from collections.abc import Callable, Iterator
from concurrent.futures import ThreadPoolExecutor
from dataclasses import replace
from html.parser import HTMLParser
from multiprocessing import get_context
from pathlib import Path
from typing import Any

import pytest
from cryptography.hazmat.primitives import serialization
from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PrivateKey
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
from substrate.midnight_oil.private_provider_composition import (
    PRIVATE_PROVIDER_CAPABILITY_KEYRING_ENVS_ENV,
    PRIVATE_PROVIDER_CAPABILITY_PATHS_ENV,
    PRIVATE_PROVIDER_EXPECTED_COMPOSITION_SHA256_ENV,
    PRIVATE_PROVIDER_EXPECTED_CURRENT_PATH_ENV,
    PRIVATE_PROVIDER_EXPECTED_CURRENT_SHA256_ENV,
    PRIVATE_PROVIDER_REVOCATION_KEYRING_ENVS_ENV,
    PRIVATE_PROVIDER_TRUSTED_FLOOR_PATH_ENV,
    PRIVATE_PROVIDER_TRUSTED_FLOOR_SHA256_ENV,
    private_provider_composition_sha256,
    signed_private_provider_revocation_head,
)
from substrate.midnight_oil.private_provider_policy import (
    OWNER_PRIVATE_OUTPUT_SINK_POLICY_SHA256,
    signed_private_provider_capability,
    signed_private_provider_revocation_snapshot,
)
from substrate.midnight_oil.publication_capability import (
    ARXIV_ABSTRACT_ADAPTER_CONTRACT_SHA256,
    PUBLICATION_RIGHTS_POLICY_SHA256,
    signed_publication_capability,
)
from substrate.midnight_oil.readiness import build_readiness_receipt
from substrate.midnight_oil.readiness import main as readiness_main
from substrate.midnight_oil.runtime import (
    MidnightOilRuntimeConfig,
    MidnightOilRuntimeConfigError,
    ProviderIdempotencyAttestation,
    provider_endpoint_sha256,
)
from substrate.midnight_oil.substack_authorization import (
    SUBSTACK_PROVIDER_CONSTRAINTS_SHA256,
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

    def handle_starttag(self, tag: str, attrs: list[tuple[str, str | None]]) -> None:
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


def _runtime_files(
    tmp_path: Path, *, swarm: bool = False, publication_capability: bool = False
) -> tuple[Path, dict[str, str], Path]:
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
""".strip()
        + ("\n  planner: synthesis\n  gatherer: synthesis\n  verifier: synthesis" if swarm else ""),
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
                "dispatch_config_sha256": hashlib.sha256(dispatch.read_bytes()).hexdigest(),
                "evidence_ref": "urn:test:verified-idempotency-contract",
                "verified_at": "2026-07-12T12:00:00Z",
            }
        ),
        encoding="utf-8",
    )
    publication_paths: list[str] = []
    if publication_capability:
        for index, expires_at_ms in enumerate((4_000_000, 5_000_000), start=1):
            capability = signed_publication_capability(
                {
                    "schema_version": 1,
                    "capability_id": "midnight-oil-arxiv-abstract-v1",
                    "connector_id": "acquisition.arxiv.atom",
                    "connector_version": "midnight-oil-arxiv-abstract-v1",
                    "adapter_contract_sha256": ARXIV_ABSTRACT_ADAPTER_CONTRACT_SHA256,
                    "source_kind": "arxiv",
                    "acquisition_mode": "arxiv_abstract",
                    "extraction_mode": "metadata_abstract",
                    "rights_policy_id": "antiek-publication-research-v1",
                    "rights_policy_sha256": PUBLICATION_RIGHTS_POLICY_SHA256,
                    "allowed_rights_tiers": ("T1",),
                    "scheme": "https",
                    "host": "export.arxiv.org",
                    "port": 443,
                    "path": "/api/query",
                    "request_mode": "id_list_single",
                    "redirect_policy": "deny",
                    "proxy_policy": "deny",
                    "dns_policy": "resolve-on-connect-public-only-v1",
                    "tls_policy": "system-ca-hostname-tls12-v1",
                    "rate_governor_id": "arxiv-host-global-v1",
                    "max_response_bytes": 256_000,
                    "max_excerpt_bytes": 32_000,
                    "timeout_ms": 15_000,
                    "issued_at_ms": 0,
                    "not_before_ms": 0,
                    "expires_at_ms": expires_at_ms,
                    "evidence_ref": f"urn:test:runtime-publication-capability:{index}",
                },
                key_id="primary",
                signing_key=b"k" * 32,
            )
            capability_path = tmp_path / f"publication-capability-{index}.json"
            capability_path.write_text(capability.model_dump_json(), encoding="utf-8")
            publication_paths.append(str(capability_path))
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
                "consent_verification_key_envs": {"primary": "MO_PRIMARY_KEY"},
                "provider_attestation_paths": [str(attestation)],
                "publication_capability_paths": publication_paths,
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


def _install_private_provider_fixture(
    tmp_path: Path, environment: dict[str, str]
) -> None:
    capability_private = bytes(range(32))
    revocation_private = bytes(range(32, 64))

    def public(private: bytes) -> bytes:
        return Ed25519PrivateKey.from_private_bytes(private).public_key().public_bytes(
            encoding=serialization.Encoding.Raw,
            format=serialization.PublicFormat.Raw,
        )

    now_ms = time.time_ns() // 1_000_000
    capability = signed_private_provider_capability(
        {
            "schema_version": 1,
            "purpose": "midnight_oil_owner_private_substack_research",
            "provider_id": "private-provider",
            "model_id": "private-model",
            "route_key": "private-provider/private-model",
            "api_mode": "responses_no_store",
            "processing_region": "us",
            "endpoint_origin_sha256": "1" * 64,
            "account_project_scope_sha256": "2" * 64,
            "adapter_contract_sha256": "3" * 64,
            "dispatch_config_sha256": "4" * 64,
            "allowed_router_roles": ("gatherer", "synthesizer", "verifier"),
            "max_private_input_bytes": 8_192,
            "max_output_bytes": 1_000_000,
            "provider_constraints_sha256": SUBSTACK_PROVIDER_CONSTRAINTS_SHA256,
            "evidence_ref": "urn:test:runtime-private-provider",
            "evidence_sha256": "5" * 64,
            "evidence_observed_at_ms": now_ms,
            "output_policy_sha256": OWNER_PRIVATE_OUTPUT_SINK_POLICY_SHA256,
            "revocation_epoch": 0,
            "issued_at_ms": now_ms,
            "not_before_ms": now_ms,
            "expires_at_ms": now_ms + 600_000,
        },
        key_id="private-capability-issuer",
        signing_key=capability_private,
    )
    snapshot = signed_private_provider_revocation_snapshot(
        epoch=0,
        issued_at_ms=now_ms,
        key_id="private-revocation-issuer",
        signing_key=revocation_private,
    )
    floor = signed_private_provider_revocation_head(
        snapshot=snapshot,
        previous_head_sha256="0" * 64,
        key_id="private-revocation-issuer",
        signing_key=revocation_private,
    )
    capability_path = tmp_path / "private-provider-capability.json"
    floor_path = tmp_path / "private-provider-floor.json"
    capability_path.write_text(capability.model_dump_json(), encoding="utf-8")
    floor_path.write_text(floor.model_dump_json(), encoding="utf-8")
    environment.update(
        {
            PRIVATE_PROVIDER_CAPABILITY_KEYRING_ENVS_ENV: json.dumps(
                {"private-capability-issuer": "PRIVATE_CAPABILITY_PUBLIC_KEY"}
            ),
            PRIVATE_PROVIDER_REVOCATION_KEYRING_ENVS_ENV: json.dumps(
                {"private-revocation-issuer": "PRIVATE_REVOCATION_PUBLIC_KEY"}
            ),
            PRIVATE_PROVIDER_CAPABILITY_PATHS_ENV: json.dumps([str(capability_path)]),
            PRIVATE_PROVIDER_TRUSTED_FLOOR_PATH_ENV: str(floor_path),
            PRIVATE_PROVIDER_TRUSTED_FLOOR_SHA256_ENV: floor.head_sha256,
            PRIVATE_PROVIDER_EXPECTED_CURRENT_PATH_ENV: str(floor_path),
            PRIVATE_PROVIDER_EXPECTED_CURRENT_SHA256_ENV: floor.head_sha256,
            "PRIVATE_CAPABILITY_PUBLIC_KEY": base64.urlsafe_b64encode(
                public(capability_private)
            )
            .decode()
            .rstrip("="),
            "PRIVATE_REVOCATION_PUBLIC_KEY": base64.urlsafe_b64encode(
                public(revocation_private)
            )
            .decode()
            .rstrip("="),
        }
    )
    environment[PRIVATE_PROVIDER_EXPECTED_COMPOSITION_SHA256_ENV] = (
        private_provider_composition_sha256(
            capabilities=(capability,),
            capability_keys={"private-capability-issuer": public(capability_private)},
            revocation_keys={"private-revocation-issuer": public(revocation_private)},
            floor=floor,
            current=floor,
            state_path=tmp_path / "state" / "private-provider-revocations.sqlite3",
        )
    )


def _runtime_composition_process(
    kind: str, config_path: str, environment: dict[str, str], results: Any
) -> None:
    reset_provider_registry()
    if kind == "api":
        composition = build_midnight_oil_api_runtime(
            config_path, environ=environment
        ).private_provider_composition
    else:
        composition = build_worker_runtime(
            config_path, environ=environment
        ).private_provider_composition
    results.put(None if composition is None else composition.composition_sha256)


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


def test_runtime_loads_identical_signed_publication_capability_in_api_and_worker(
    tmp_path: Path,
) -> None:
    path, environment, _ = _runtime_files(tmp_path, publication_capability=True)
    api = build_midnight_oil_api_runtime(path, environ=environment)
    worker = build_worker_runtime(path, environ=environment)
    assert api.dependencies.publication_capabilities.hashes
    assert len(api.dependencies.publication_capabilities.hashes) == 2
    assert (
        api.dependencies.publication_capabilities.hashes
        == worker.publication_capabilities.hashes
        == tuple(sorted(worker.publication_acquirers))
    )


def test_runtime_composes_identical_inert_private_provider_reference(
    tmp_path: Path,
) -> None:
    path, environment, _ = _runtime_files(tmp_path)
    _install_private_provider_fixture(tmp_path, environment)
    api = build_midnight_oil_api_runtime(path, environ=environment)
    worker = build_worker_runtime(path, environ=environment)
    api_private = api.private_provider_composition
    worker_private = worker.private_provider_composition
    assert api_private is not None and worker_private is not None
    assert api_private.composition_sha256 == worker_private.composition_sha256
    assert api_private.capability_hashes == worker_private.capability_hashes
    assert api_private.current_head.head_sha256 == worker_private.current_head.head_sha256
    assert api_private.confers_execution_authority is False
    assert not hasattr(api.dependencies, "private_provider_composition")
    assert worker.publication_acquirers == {}


def test_api_and_worker_processes_converge_on_exact_pinned_composition(
    tmp_path: Path,
) -> None:
    path, environment, _ = _runtime_files(tmp_path)
    _install_private_provider_fixture(tmp_path, environment)
    expected = environment[PRIVATE_PROVIDER_EXPECTED_COMPOSITION_SHA256_ENV]
    context = get_context("spawn")
    results = context.Queue()
    processes = tuple(
        context.Process(
            target=_runtime_composition_process,
            args=(kind, str(path), environment, results),
        )
        for kind in ("api", "worker")
    )
    for process in processes:
        process.start()
    for process in processes:
        process.join(timeout=30)
        assert process.exitcode == 0
    assert {results.get(timeout=2), results.get(timeout=2)} == {expected}


def test_runtime_private_provider_composition_is_optional_and_partial_is_fatal(
    tmp_path: Path,
) -> None:
    path, environment, _ = _runtime_files(tmp_path)
    assert build_midnight_oil_api_runtime(
        path, environ=environment
    ).private_provider_composition is None
    reset_provider_registry()
    _install_private_provider_fixture(tmp_path, environment)
    environment.pop(PRIVATE_PROVIDER_TRUSTED_FLOOR_SHA256_ENV)
    with pytest.raises(MidnightOilRuntimeConfigError, match="composition is invalid"):
        build_worker_runtime(path, environ=environment)
    with pytest.raises(KeyError):
        get_provider("verified-provider")


def test_runtime_private_provider_keys_cannot_reuse_consent_or_substack(
    tmp_path: Path,
) -> None:
    path, environment, _ = _runtime_files(tmp_path)
    _install_private_provider_fixture(tmp_path, environment)
    environment[PRIVATE_PROVIDER_CAPABILITY_KEYRING_ENVS_ENV] = json.dumps(
        {"private-capability-issuer": "MO_PRIMARY_KEY"}
    )
    with pytest.raises(MidnightOilRuntimeConfigError, match="composition is invalid"):
        build_midnight_oil_api_runtime(path, environ=environment)

    environment[PRIVATE_PROVIDER_CAPABILITY_KEYRING_ENVS_ENV] = json.dumps(
        {"private-capability-issuer": "VERIFIED_PROVIDER_KEY"}
    )
    with pytest.raises(MidnightOilRuntimeConfigError, match="composition is invalid"):
        build_midnight_oil_api_runtime(path, environ=environment)
    with pytest.raises(MidnightOilRuntimeConfigError, match="composition is invalid"):
        build_worker_runtime(path, environ=environment)

    provider_material_path = tmp_path / "provider-material"
    provider_material_path.mkdir()
    path, environment, _ = _runtime_files(provider_material_path)
    _install_private_provider_fixture(provider_material_path, environment)
    environment["VERIFIED_PROVIDER_KEY"] = environment[
        "PRIVATE_CAPABILITY_PUBLIC_KEY"
    ]
    with pytest.raises(MidnightOilRuntimeConfigError, match="composition is invalid"):
        build_midnight_oil_api_runtime(path, environ=environment)
    with pytest.raises(MidnightOilRuntimeConfigError, match="composition is invalid"):
        build_worker_runtime(path, environ=environment)

    substack_path = tmp_path / "substack"
    substack_path.mkdir()
    path, environment, _ = _runtime_files(substack_path)
    _install_private_provider_fixture(substack_path, environment)
    environment.update(
        {
            "ANTIEK_SUBSTACK_AUTH_ACTIVE_KEY_ID": "substack-key",
            "ANTIEK_SUBSTACK_AUTH_SIGNING_KEY_ENV": "PRIVATE_CAPABILITY_PUBLIC_KEY",
            "ANTIEK_SUBSTACK_AUTH_VERIFICATION_KEY_ENVS_JSON": json.dumps(
                {"substack-key": "PRIVATE_CAPABILITY_PUBLIC_KEY"}
            ),
        }
    )
    with pytest.raises(MidnightOilRuntimeConfigError, match="composition is invalid"):
        create_midnight_oil_production_app(path, environ=environment)
    with pytest.raises(MidnightOilRuntimeConfigError, match="composition is invalid"):
        build_worker_runtime(path, environ=environment)


def test_private_provider_runtime_repr_redacts_capability_evidence(tmp_path: Path) -> None:
    path, environment, _ = _runtime_files(tmp_path)
    _install_private_provider_fixture(tmp_path, environment)
    api = build_midnight_oil_api_runtime(path, environ=environment)
    worker = build_worker_runtime(path, environ=environment)
    evidence = "urn:test:runtime-private-provider"
    assert evidence not in repr(api.private_provider_composition)
    assert evidence not in repr(worker.private_provider_composition)
    assert evidence not in repr(api)
    assert evidence not in repr(worker)


def test_private_provider_store_failure_is_generic_and_context_suppressed(
    tmp_path: Path,
) -> None:
    path, environment, _ = _runtime_files(tmp_path)
    _install_private_provider_fixture(tmp_path, environment)
    assert build_midnight_oil_api_runtime(path, environ=environment) is not None
    database = tmp_path / "state" / "private-provider-revocations.sqlite3"
    connection = sqlite3.connect(database)
    connection.execute(
        "UPDATE private_provider_revocation_heads SET document_json = ?",
        [json.dumps({"evidence_ref": "urn:private:must-not-leak"})],
    )
    connection.commit()
    connection.close()
    with pytest.raises(
        MidnightOilRuntimeConfigError, match="Private provider composition is invalid"
    ) as captured:
        build_worker_runtime(path, environ=environment)
    assert captured.value.__suppress_context__ is True
    assert "must-not-leak" not in str(captured.value)


def test_production_app_does_not_overwrite_attested_provider(tmp_path: Path) -> None:
    path, environment, _ = _runtime_files(tmp_path)
    app = create_midnight_oil_production_app(path, environ=environment)
    assert app.state.midnight_oil_runtime.config.state_dir == tmp_path / "state"


def test_production_app_mounts_only_a_distinct_substack_authorization_keyring(
    tmp_path: Path,
) -> None:
    path, environment, _ = _runtime_files(tmp_path)
    environment.update(
        {
            "ANTIEK_SUBSTACK_AUTH_ACTIVE_KEY_ID": "substack-2026-07",
            "ANTIEK_SUBSTACK_AUTH_SIGNING_KEY_ENV": "SUBSTACK_PRIVATE_KEY",
            "ANTIEK_SUBSTACK_AUTH_VERIFICATION_KEY_ENVS_JSON": json.dumps(
                {"substack-2026-07": "SUBSTACK_PRIVATE_KEY"}
            ),
            "SUBSTACK_PRIVATE_KEY": base64.urlsafe_b64encode(b"s" * 32).decode().rstrip("="),
        }
    )
    app = create_midnight_oil_production_app(path, environ=environment)
    dependencies = app.state.substack_authorization_dependencies
    assert dependencies.engagement_store is app.state.midnight_oil_runtime.stores.engagement_store
    assert dependencies.active_key_id == "substack-2026-07"

    environment["ANTIEK_SUBSTACK_AUTH_SIGNING_KEY_ENV"] = "MO_PRIMARY_KEY"
    environment["ANTIEK_SUBSTACK_AUTH_VERIFICATION_KEY_ENVS_JSON"] = json.dumps(
        {"substack-2026-07": "MO_PRIMARY_KEY"}
    )
    with pytest.raises(MidnightOilRuntimeConfigError, match="composition is invalid"):
        create_midnight_oil_production_app(path, environ=environment)

    environment["ANTIEK_SUBSTACK_AUTH_SIGNING_KEY_ENV"] = "SUBSTACK_KEY_ALIAS"
    environment["ANTIEK_SUBSTACK_AUTH_VERIFICATION_KEY_ENVS_JSON"] = json.dumps(
        {"substack-2026-07": "SUBSTACK_KEY_ALIAS"}
    )
    environment["SUBSTACK_KEY_ALIAS"] = environment["MO_PRIMARY_KEY"]
    with pytest.raises(MidnightOilRuntimeConfigError, match="composition is invalid"):
        create_midnight_oil_production_app(path, environ=environment)
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


def test_production_api_to_worker_executes_signed_four_role_swarm(
    tmp_path: Path,
) -> None:
    path, environment, _ = _runtime_files(tmp_path, swarm=True)
    api = build_midnight_oil_api_runtime(path, environ=environment)
    app = FastAPI()

    @app.middleware("http")
    async def _auth(request: Request, call_next):  # type: ignore[no-untyped-def]
        request.state.user_id = "swarm-owner"
        return await call_next(request)

    register_midnight_oil_routes(app, dependencies=api.dependencies)
    client = TestClient(app)
    created = client.post(
        "/midnight-oil/create",
        json={
            "goals": ["Test the signed causal chain."],
            "duration_minutes": 10,
            "model_id": "verified-model",
            "fanout_depth": 1,
            "live": True,
        },
    )
    assert created.status_code == 200, created.text
    job_id = created.json()["job_id"]
    consent = client.post(
        f"/midnight-oil/jobs/{job_id}/spend-consent",
        json={"ceiling_cents": 100_000},
    )
    assert consent.status_code == 200, consent.text
    queued = client.post(
        "/midnight-oil/run",
        headers={"X-Midnight-Oil-Spend-Consent": consent.json()["token"]},
        json={"job_id": job_id},
    )
    assert queued.status_code == 200, queued.text

    ensure_initialized(str(api.config.graph_db_path))
    with connect_write(str(api.config.graph_db_path), purpose="test/swarm-runtime-seed") as con:
        insert_document(
            con,
            document_id="swarm-doc",
            source_tier=1,
            document_type="paper",
            title="Swarm source",
        )
        insert_chunk(
            con,
            document_id="swarm-doc",
            chunk_index=0,
            text="The primary source supports the bounded proposition.",
            embedding=[1.0, 0.0],
            chunk_id="swarm-chunk",
        )

    claim = "The primary source supports the bounded proposition."
    proposition_digest = hashlib.sha256(f"q-1\x00{claim}".encode()).hexdigest()
    proposition_id = f"prop-{proposition_digest[:16]}"

    class _SwarmProvider:
        name = "verified-provider"
        idempotency_guaranteed = True

        def __init__(self) -> None:
            self.roles: list[str] = []

        def call_idempotent(
            self,
            *,
            idempotency_key: str,
            model: str,
            prompt: str,
            max_tokens: int,
            temperature: float,
        ) -> RawProviderResponse:
            del idempotency_key, model, max_tokens, temperature
            role = prompt.split("\n", 1)[0].removeprefix("ROLE=")
            self.roles.append(role)
            encoded = prompt.split("UNTRUSTED_JSON_BASE64=", 1)[1]
            payload = json.loads(base64.b64decode(encoded))
            if role == "planner":
                output = {
                    "role": "planner",
                    "schema_version": 1,
                    "research_frame": "Test the bounded proposition.",
                    "questions": [
                        {
                            "question_id": "q-1",
                            "question": "What does the primary source support?",
                            "inclusion_criteria": ["Primary evidence"],
                            "exclusion_criteria": [],
                            "expected_evidence_types": ["Quoted source"],
                            "falsifiers": ["Contradictory primary evidence"],
                        }
                    ],
                }
            elif role == "gatherer":
                source = payload["source_receipts"][0]
                output = {
                    "role": "gatherer",
                    "schema_version": 1,
                    "question_id": "q-1",
                    "evidence": [
                        {
                            "evidence_id": "ev-0123456789abcdef",
                            "source_receipt_id": source["source_receipt_id"],
                            "document_id": source["document_id"],
                            "chunk_id": source["chunk_id"],
                            "excerpt_sha256": source["excerpt_sha256"],
                            "claim": claim,
                            "relevance": "Direct evidence.",
                            "limitations": ["Single source"],
                        }
                    ],
                    "search_limitations": ["Operator corpus only"],
                }
            elif role == "verifier":
                output = {
                    "role": "verifier",
                    "schema_version": 1,
                    "findings": [
                        {
                            "finding_id": "vf-0123456789abcdef",
                            "proposition_id": proposition_id,
                            "question_id": "q-1",
                            "claim": claim,
                            "status": "supported",
                            "evidence_ids": ["ev-0123456789abcdef"],
                            "rationale": "The canonical excerpt supports it.",
                            "missing_evidence": [],
                        }
                    ],
                    "evidence_dispositions": [
                        {
                            "evidence_id": "ev-0123456789abcdef",
                            "question_id": "q-1",
                            "disposition": "considered_support",
                            "rationale": "Accepted primary evidence.",
                        }
                    ],
                }
            else:
                output = {
                    "role": "synthesizer",
                    "schema_version": 1,
                    "claims": [
                        {
                            "claim_id": "cl-0123456789abcdef",
                            "proposition_id": proposition_id,
                            "text": claim,
                            "finding_id": "vf-0123456789abcdef",
                            "evidence_ids": ["ev-0123456789abcdef"],
                            "confidence": "low",
                        }
                    ],
                    "summary_claim_ids": ["cl-0123456789abcdef"],
                    "addressed_contradictions": [],
                    "addressed_gaps": [],
                    "limitations": ["Single source"],
                    "open_questions": [],
                }
            return RawProviderResponse(
                text=json.dumps(output),
                raw_usage={"prompt_tokens": 10, "completion_tokens": 5},
                finish_reason="stop",
                latency_ms=1,
                request_id=f"swarm-{role}",
            )

        def call(self, **kwargs: object) -> RawProviderResponse:
            raise AssertionError("swarm worker must use idempotent transport")

        def normalize_usage(self, raw_usage: dict[str, Any]) -> NormalizedUsage:
            return NormalizedUsage(
                input_tokens=int(raw_usage["prompt_tokens"]),
                output_tokens=int(raw_usage["completion_tokens"]),
            )

    provider = _SwarmProvider()
    worker = build_worker_runtime(path, environ=environment)
    register_provider(provider)
    base_ms = api.dependencies.clock_ms() + 1_000

    def clock_at(value: int) -> Callable[[], int]:
        return lambda: value

    stop_checks = 0

    def stop_after_first_stage() -> bool:
        nonlocal stop_checks
        stop_checks += 1
        return stop_checks >= 3

    first = run_worker_once(
        worker,
        worker_id="swarm-worker",
        embedding_model=_Embedding(),
        clock_ms=clock_at(base_ms),
        stop_requested=stop_after_first_stage,
    )
    records = [
        first,
        *[
            run_worker_once(
                worker,
                worker_id="swarm-worker",
                embedding_model=_Embedding(),
                clock_ms=clock_at(base_ms + index * 120_000),
            )
            for index in range(1, 4)
        ],
    ]
    result = records[-1]
    assert [record.result for record in records] == [
        "lease_pending",
        "lease_pending",
        "lease_pending",
        "complete",
    ]
    assert records[0].phase == "shutdown_after_swarm_stage"
    assert result.result == "complete"
    assert provider.roles == ["planner", "gatherer", "verifier", "synthesizer"]
    authority = worker.stores.owner_jobs.get_job(owner_user_id="swarm-owner", job_id=job_id)
    assert authority is not None
    assert authority.consent_stage_plan_hash == worker.stores.jobs.get_stage_plan(job_id).plan_hash


def test_readiness_receipt_proves_zero_spend_composition_without_secrets(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    path, environment, _ = _runtime_files(tmp_path)
    monkeypatch.setattr(
        OpenAICompatProvider,
        "_ensure_client",
        lambda self: (_ for _ in ()).throw(AssertionError("provider network attempted")),
    )

    receipt = build_readiness_receipt(path, environ=environment, checked_at_ms=1_234)

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
    assert '<script type="application/json"' in receipt.to_html()
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
        request.state.user_id = request.headers.get("X-Test-Owner", "operator-runtime")
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
    initial_status = client.get(f"/midnight-oil/jobs/{job_id}/status")
    assert initial_status.status_code == 200
    assert initial_status.headers["cache-control"] == "no-store"
    assert initial_status.json()["state"] == "consent_required"
    foreign = client.get(
        f"/midnight-oil/jobs/{job_id}/status",
        headers={"X-Test-Owner": "foreign-operator"},
    )
    assert foreign.status_code == 404
    consent = client.post(
        f"/midnight-oil/jobs/{job_id}/spend-consent",
        json=(
            {"ceiling_cents": 1, "force_below": True}
            if mode == "budget_halt"
            else {"use_recommended": True}
        ),
    )
    assert consent.status_code == 200, consent.text
    consent_status = client.get(f"/midnight-oil/jobs/{job_id}/status")
    assert consent_status.status_code == 200
    assert consent_status.json()["state"] == "consent_issued"
    queued = client.post(
        "/midnight-oil/run",
        headers={"X-Midnight-Oil-Spend-Consent": consent.json()["token"]},
        json={"job_id": job_id},
    )
    assert queued.status_code == 200, queued.text
    queued_status = client.get(f"/midnight-oil/jobs/{job_id}/status")
    assert queued_status.status_code == 200
    assert queued_status.json()["state"] == "queued"

    ensure_initialized(str(api.config.graph_db_path))
    with connect_write(str(api.config.graph_db_path), purpose="test/runtime-e2e-seed") as con:
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
        status = client.get(f"/midnight-oil/jobs/{job_id}/status")
        assert status.status_code == 200, status.text
        assert status.json()["state"] == "blocked_provider"
        assert status.json()["terminal_outcome"] == "blocked_provider"
        assert status.json()["cost_state"] == "not_reserved"
        assert status.json()["confirmed_spent_cents"] == 0
        assert status.json()["reserved_cents"] == 0
        artifact = client.get(status.json()["deposit_href"])
        assert artifact.status_code == 200
        assert artifact.headers["content-type"].startswith("text/html")
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
        leased_status = client.get(f"/midnight-oil/jobs/{job_id}/status")
        assert leased_status.status_code == 200
        assert leased_status.json()["state"] == "leased"
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
        status = client.get(f"/midnight-oil/jobs/{job_id}/status")
        assert status.status_code == 200, status.text
        assert status.json()["state"] == "reconcile_required"
        assert status.json()["terminal_outcome"] == "failed_reconcile"
        assert status.json()["confirmed_spent_cents"] == 0
        assert status.json()["reserved_cents"] > 0
        assert status.json()["unknown_outcome"] is True
        assert status.json()["cost_state"] == "unknown_outcome"
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
        status = client.get(f"/midnight-oil/jobs/{job_id}/status")
        assert status.status_code == 200, status.text
        assert status.json()["state"] == "budget_halted"
        assert status.json()["terminal_outcome"] == "budget_halted"
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
            "resume_terminal_deposit" if mode == "deposit_crash" else "resume_terminal_projection"
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
        pending_status = client.get(f"/midnight-oil/jobs/{job_id}/status")
        assert pending_status.status_code == 200
        assert pending_status.json()["state"] == pending.result
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
    status = client.get(f"/midnight-oil/jobs/{job_id}/status")
    assert status.status_code == 200, status.text
    lifecycle = status.json()
    assert lifecycle["state"] == "complete"
    assert lifecycle["terminal_outcome"] == "complete"
    assert lifecycle["deposit_document_id"] == result.deposit_document_id
    assert lifecycle["graph_deliverable_id"] == result.graph_deliverable_id
    assert lifecycle["graph_deep_links"]
    assert lifecycle["confirmed_spent_cents"] > 0
    assert lifecycle["reserved_cents"] == 0
    assert lifecycle["unknown_outcome"] is False
    assert lifecycle["cost_state"] == "settled"
    assert "token" not in json.dumps(lifecycle).lower()
    artifact = client.get(lifecycle["deposit_href"])
    assert artifact.status_code == 200
    assert "<html" in artifact.text.lower()
    foreign_artifact = client.get(
        lifecycle["deposit_href"], headers={"X-Test-Owner": "foreign-operator"}
    )
    assert foreign_artifact.status_code == 404
    stored_artifact = worker.stores.engagement_store.get_document(lifecycle["deposit_document_id"])
    assert stored_artifact is not None
    worker.stores.engagement_store.put_document(
        lifecycle["deposit_document_id"],
        {**stored_artifact, "html": "<html><body>tampered</body></html>"},
    )
    tampered_artifact = client.get(lifecycle["deposit_href"])
    assert tampered_artifact.status_code == 409
    assert worker.stores.operation_queue.next_claimable(now_ms=10**18) is None
    second = run_worker_once(
        worker,
        worker_id="runtime-worker",
        embedding_model=_Embedding(),
    )
    assert second.result == "no_work"
    assert len(paid.keys) == 1
    with connect_read(str(api.config.graph_db_path)) as read_con:
        assert read_con.execute(
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
