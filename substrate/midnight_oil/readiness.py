"""Zero-spend deployment readiness proof for the Midnight Oil runtime."""

from __future__ import annotations

import argparse
import contextlib
import hashlib
import html
import json
import os
import sys
import time
from collections.abc import Mapping, Sequence
from dataclasses import asdict, dataclass
from pathlib import Path
from typing import Literal

from fastapi.testclient import TestClient

from interfaces.research.api.app import create_app
from interfaces.research.api.midnight_oil_runtime import build_midnight_oil_api_runtime
from runtime.db_lock import connect_write

from .runtime import MidnightOilRuntimeConfigError, ProviderIdempotencyAttestation
from .worker_cli import MidnightOilWorkerRuntime, run_worker_once

ReadinessState = Literal["ready", "not_ready"]


class _UnusedEmbedding:
    """A trap-friendly model; the stopped-before-claim probe never invokes it."""

    dimension = 1

    def encode(self, text: str) -> list[float]:
        del text
        raise RuntimeError("readiness probe attempted retrieval")


@dataclass(frozen=True)
class ReadinessCheck:
    name: str
    passed: bool
    evidence: str


@dataclass(frozen=True)
class MidnightOilReadinessReceipt:
    schema_version: int
    state: ReadinessState
    checked_at_ms: int
    config_sha256: str
    dispatch_config_sha256: str
    attested_providers: tuple[str, ...]
    checks: tuple[ReadinessCheck, ...]
    worker_result: str
    worker_phase: str

    def to_json(self) -> str:
        return json.dumps(asdict(self), sort_keys=True, separators=(",", ":"))

    def to_html(self) -> str:
        rows = "".join(
            "<tr><td>"
            + html.escape(check.name)
            + "</td><td>"
            + ("pass" if check.passed else "fail")
            + "</td><td>"
            + html.escape(check.evidence)
            + "</td></tr>"
            for check in self.checks
        )
        payload = (
            self.to_json()
            .replace("&", "\\u0026")
            .replace("<", "\\u003c")
            .replace(">", "\\u003e")
        )
        return (
            "<!doctype html><html lang=\"en\"><head><meta charset=\"utf-8\">"
            "<title>Midnight Oil readiness</title></head><body><main>"
            f"<h1>Midnight Oil readiness: {html.escape(self.state)}</h1>"
            f"<p>Checked at {self.checked_at_ms} ms · zero-spend probe</p>"
            "<table><thead><tr><th>Check</th><th>Result</th><th>Evidence</th>"
            f"</tr></thead><tbody>{rows}</tbody></table>"
            f"<script type=\"application/json\" id=\"midnight-oil-readiness\">{payload}</script>"
            "</main></body></html>"
        )


def _routes(app: object) -> set[tuple[str, str]]:
    found: set[tuple[str, str]] = set()
    for route in getattr(app, "routes", ()):
        path = getattr(route, "path", None)
        for method in getattr(route, "methods", ()) or ():
            if isinstance(path, str) and isinstance(method, str):
                found.add((method, path))
        found.update(_routes(route))
        original_router = getattr(route, "original_router", None)
        if original_router is not None and original_router is not route:
            found.update(_routes(original_router))
    return found


def _probe_root(path: Path) -> None:
    path.mkdir(parents=True, exist_ok=True)
    marker = path / f".midnight-oil-readiness-{os.getpid()}-{time.time_ns()}"
    try:
        with marker.open("x", encoding="utf-8") as handle:
            handle.write("readiness\n")
            handle.flush()
            os.fsync(handle.fileno())
    finally:
        with contextlib.suppress(FileNotFoundError):
            marker.unlink()


def build_readiness_receipt(
    config_path: str | Path,
    *,
    environ: Mapping[str, str] | None = None,
    checked_at_ms: int | None = None,
) -> MidnightOilReadinessReceipt:
    """Validate exact composition and execute one stopped worker iteration.

    Construction installs attested provider adapters but never calls them. The
    production queue is inspected read-only. The worker receives an unconditional
    stop signal and therefore proves only its pre-claim boundary, even when real
    work is queued.
    """

    environment = os.environ if environ is None else environ
    if not any(
        environment.get(name, "").strip()
        for name in (
            "ANTIEK_OPERATOR_TOKEN",
            "ANTIEK_OPERATOR_EMAIL",
            "ANTIEK_OPERATOR_SERVICE_TOKEN_CLIENT_ID",
        )
    ):
        raise MidnightOilRuntimeConfigError("operator authentication is not enabled")
    source = Path(config_path)
    runtime = build_midnight_oil_api_runtime(source, environ=environment)
    config = runtime.config
    attestations = tuple(
        ProviderIdempotencyAttestation.from_file(path)
        for path in config.provider_attestation_paths
    )
    dispatch_hash = hashlib.sha256(config.dispatch_config_path.read_bytes()).hexdigest()
    checks: list[ReadinessCheck] = []

    for name, root in (
        ("state_root_writable", config.state_dir),
        ("engagement_root_writable", config.engagement_dir),
        ("graph_root_writable", config.graph_db_path.parent),
    ):
        _probe_root(root)
        checks.append(ReadinessCheck(name=name, passed=True, evidence="write_fsync_delete"))

    with connect_write(
        str(config.graph_db_path), purpose="midnight-oil-readiness", log_on_close=False
    ) as graph:
        graph.execute("SELECT 1").fetchone()
    checks.append(
        ReadinessCheck(
            name="graph_database_openable",
            passed=True,
            evidence="duckdb_open_select_close",
        )
    )

    default_app = create_app(
        register_providers=False,
        enable_midnight_oil=False,
        operator_auth_environ=environment,
    )
    production_app = create_app(
        register_providers=False,
        enable_midnight_oil=True,
        midnight_oil_dependencies=runtime.dependencies,
        operator_auth_environ=environment,
    )
    default_routes = _routes(default_app)
    production_routes = _routes(production_app)
    spend_route = ("POST", "/midnight-oil/run")
    route_posture = spend_route not in default_routes and spend_route in production_routes
    checks.append(
        ReadinessCheck(
            name="fail_closed_route_posture",
            passed=route_posture,
            evidence="default_absent_production_present" if route_posture else "route_posture_conflict",
        )
    )
    if not route_posture:
        raise MidnightOilRuntimeConfigError("Midnight Oil route posture conflicts")
    unauthorized = TestClient(production_app).post(
        "/midnight-oil/run", json={"job_id": "readiness-auth-probe"}
    )
    auth_posture = unauthorized.status_code == 401
    checks.append(
        ReadinessCheck(
            name="unauthenticated_spend_route_denied",
            passed=auth_posture,
            evidence="http_401_before_handler" if auth_posture else "auth_boundary_open",
        )
    )
    if not auth_posture:
        raise MidnightOilRuntimeConfigError("operator authentication boundary is open")

    worker_runtime = MidnightOilWorkerRuntime(
        config=config,
        stores=runtime.stores,
        dispatch_config=runtime.dispatch_config,
    )
    probe_now = checked_at_ms if checked_at_ms is not None else time.time_ns() // 1_000_000
    runtime.stores.operation_queue.next_claimable(now_ms=probe_now)
    checks.append(
        ReadinessCheck(
            name="operation_queue_readable",
            passed=True,
            evidence="read_only_claimability_probe",
        )
    )
    result = run_worker_once(
        worker_runtime,
        worker_id="readiness-probe",
        embedding_model=_UnusedEmbedding(),
        clock_ms=lambda: probe_now,
        stop_requested=lambda: True,
    )
    stopped_before_claim = (
        result.result == "no_work" and result.phase == "shutdown_before_claim"
    )
    checks.append(
        ReadinessCheck(
            name="zero_spend_worker_stop_boundary",
            passed=stopped_before_claim,
            evidence=(
                "stopped_before_claim"
                if stopped_before_claim
                else "worker_probe_conflict"
            ),
        )
    )
    if not stopped_before_claim:
        raise MidnightOilRuntimeConfigError("readiness worker probe crossed the claim boundary")
    checks.append(
        ReadinessCheck(
            name="attested_dispatch_binding",
            passed=True,
            evidence=f"{len(attestations)}_provider_attestation(s)",
        )
    )
    now = checked_at_ms if checked_at_ms is not None else time.time_ns() // 1_000_000
    return MidnightOilReadinessReceipt(
        schema_version=1,
        state="ready",
        checked_at_ms=now,
        config_sha256=hashlib.sha256(source.read_bytes()).hexdigest(),
        dispatch_config_sha256=dispatch_hash,
        attested_providers=tuple(sorted(item.provider_name for item in attestations)),
        checks=tuple(checks),
        worker_result=result.result,
        worker_phase=result.phase,
    )


def _parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Prove Midnight Oil readiness without spend")
    parser.add_argument("--config", required=True, help="absolute closed runtime JSON path")
    parser.add_argument("--format", choices=("json", "html"), default="json")
    return parser


def main(argv: Sequence[str] | None = None) -> int:
    args = _parser().parse_args(list(argv) if argv is not None else None)
    try:
        receipt = build_readiness_receipt(args.config)
    except Exception as exc:
        error_code = (
            "configuration_not_ready"
            if isinstance(exc, (MidnightOilRuntimeConfigError, OSError, ValueError))
            else "readiness_probe_failed"
        )
        sys.stderr.write(
            json.dumps(
                {"schema_version": 1, "state": "not_ready", "error_code": error_code},
                sort_keys=True,
                separators=(",", ":"),
            )
            + "\n"
        )
        return 1
    sys.stdout.write((receipt.to_html() if args.format == "html" else receipt.to_json()) + "\n")
    return 0


__all__ = [
    "MidnightOilReadinessReceipt",
    "ReadinessCheck",
    "build_readiness_receipt",
    "main",
]
