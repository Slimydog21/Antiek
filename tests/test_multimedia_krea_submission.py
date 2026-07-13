from __future__ import annotations

import ast
import copy
import hashlib
import importlib.resources
import json
import socket
import threading
from collections.abc import Generator
from concurrent.futures import ThreadPoolExecutor
from contextlib import contextmanager, suppress
from dataclasses import replace
from datetime import UTC, datetime, timedelta
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from typing import Any

import pytest

from integrations.krea.catalog import (
    CATALOG_DIGEST,
    CATALOG_VERSION,
    OPENAPI_SOURCE_URL,
    OPENAPI_SUBSET_SHA256,
    Imagen3Request,
    RunwayGen45Request,
    extract_reviewed_openapi_paths,
    issue_quote,
    prepare_request,
)
from integrations.krea.client import MAX_RESPONSE_BYTES, KreaClient, KreaClientError
from runtime.db_lock import connect_read, connect_write
from substrate.midnight_oil.budget_ledger import BudgetLedger
from substrate.multimedia.execution_authorization import (
    ExecutionAuthorizationIntegrityError,
    issue_async_execution_authorization,
)
from substrate.multimedia.krea_submit import (
    get_krea_submission_attempt,
    recover_stale_krea_submission,
    submit_krea_job,
)
from substrate.multimedia.provider_execution import (
    ProviderExecutionIntegrityError,
    ProviderExecutionStatus,
    begin_reserved_provider_submission,
)

KEY = b"multimedia-krea-submission-test-key"
ISSUED = datetime(2026, 7, 11, 5, 0, tzinfo=UTC)
NOW = ISSUED + timedelta(minutes=1)
TOKEN = "test-id:secret-never-log-this"
REPO_ROOT = Path(__file__).resolve().parents[1]
AUTHORIZED_KREA_CLIENT_CONSTRUCTORS: frozenset[str] = frozenset(
    {"interfaces/research/api/multimedia_visual_generation_routes.py:82"}
)


class _ServerState:
    def __init__(self, behavior: str) -> None:
        self.behavior = behavior
        self.requests = 0
        self.body = b""
        self.authorization = ""


class _LoopbackKreaClient(KreaClient):
    def __init__(self, api_token: str, origin: str) -> None:
        super().__init__(api_token)
        self._origin = origin


@contextmanager
def _server(behavior: str) -> Generator[tuple[_ServerState, str]]:
    state = _ServerState(behavior)

    class Handler(BaseHTTPRequestHandler):
        def do_POST(self) -> None:  # noqa: N802
            state.requests += 1
            state.authorization = self.headers.get("Authorization", "")
            state.body = self.rfile.read(int(self.headers.get("Content-Length", "0")))
            if behavior == "disconnect":
                self.connection.shutdown(socket.SHUT_RDWR)
                self.connection.close()
                return
            if behavior == "redirect":
                self.send_response(307)
                self.send_header("Location", "http://127.0.0.1:1/private")
                self.end_headers()
                return
            if behavior.startswith("http_"):
                payload = b'{"detail":"secret-never-log-this"}'
                self.send_response(int(behavior.removeprefix("http_")))
            elif behavior == "malformed":
                payload = b'{"secret":"secret-never-log-this"'
                self.send_response(200)
            elif behavior == "oversized":
                payload = b"x" * (MAX_RESPONSE_BYTES + 1)
                self.send_response(200)
            else:
                payload = json.dumps(
                    {
                        "job_id": "3c90c3cc-0d44-4b50-8888-8dd25736052a",
                        "status": "queued",
                    }
                ).encode()
                self.send_response(200)
            self.send_header("Content-Type", "application/json")
            self.send_header("Content-Length", str(len(payload)))
            self.end_headers()
            with suppress(BrokenPipeError):
                self.wfile.write(payload)

        def log_message(self, format: str, *args: Any) -> None:
            return

    httpd = ThreadingHTTPServer(("127.0.0.1", 0), Handler)
    thread = threading.Thread(target=httpd.serve_forever, daemon=True)
    thread.start()
    try:
        yield state, f"http://127.0.0.1:{httpd.server_port}"
    finally:
        httpd.shutdown()
        httpd.server_close()
        thread.join(timeout=2)


def _authorization(*, request_id: str, microdollars: int):
    return issue_async_execution_authorization(
        signing_key=KEY,
        request_id=request_id,
        operator_id="alice",
        asset_id="asset-1",
        revision_id="revision-1",
        provider="krea",
        route_policy="balanced",
        model="runway-gen-4.5",
        endpoint_capability="text-to-video",
        catalog_version="2026-07-11",
        catalog_digest=hashlib.sha256(b"catalog").hexdigest(),
        quote_id=f"quote-{request_id}",
        quote_expires_at=ISSUED + timedelta(minutes=10),
        recovery_authority_id="krea-account-audit",
        recovery_verification_key_digest=hashlib.sha256(b"recovery-key").hexdigest(),
        approved_ceiling_microdollars=microdollars,
        request_body_digest=hashlib.sha256(request_id.encode()).hexdigest(),
        issued_at=ISSUED,
        expires_at=ISSUED + timedelta(hours=1),
    )


def _live_authorization(request: Imagen3Request | RunwayGen45Request, request_id: str):
    prepared = prepare_request(request)
    quote = issue_quote(
        signing_key=KEY,
        prepared=prepared,
        ceiling_microdollars=250_000,
        issued_at=ISSUED,
        expires_at=ISSUED + timedelta(minutes=10),
    )
    authorization = issue_async_execution_authorization(
        signing_key=KEY,
        request_id=request_id,
        operator_id="alice",
        asset_id="asset-live",
        revision_id="revision-live",
        provider="krea",
        route_policy="balanced",
        model=prepared.model,
        endpoint_capability=prepared.endpoint_capability,
        catalog_version=prepared.catalog_version,
        catalog_digest=prepared.catalog_digest,
        quote_id=quote.quote_id,
        quote_expires_at=datetime.fromisoformat(quote.expires_at.replace("Z", "+00:00")),
        recovery_authority_id="krea-account-audit",
        recovery_verification_key_digest=hashlib.sha256(b"recovery-key").hexdigest(),
        approved_ceiling_microdollars=250_000,
        request_body_digest=prepared.body_digest,
        issued_at=ISSUED,
        expires_at=ISSUED + timedelta(hours=1),
    )
    return authorization, quote


def _krea_client_constructors(path: Path) -> list[str]:
    source = path.read_text(encoding="utf-8")
    if "KreaClient" not in source:
        return []
    tree = ast.parse(source, filename=str(path))
    client_names = {"KreaClient"}
    for node in ast.walk(tree):
        if not isinstance(node, ast.ImportFrom):
            continue
        for imported in node.names:
            if imported.name == "KreaClient":
                client_names.add(imported.asname or imported.name)
    try:
        display_path = path.relative_to(REPO_ROOT)
    except ValueError:
        display_path = path
    hits: list[str] = []
    for node in ast.walk(tree):
        if not isinstance(node, ast.Call):
            continue
        dotted = _dotted_name(node.func)
        root = dotted.split(".", 1)[0]
        if (
            dotted in client_names
            or dotted.endswith(".KreaClient")
            or dotted.endswith(".KreaClient.for_loopback_test")
            or (root in client_names and dotted.endswith(".for_loopback_test"))
        ):
            hits.append(f"{display_path}:{node.lineno}")
    return hits


def _dotted_name(node: ast.expr) -> str:
    if isinstance(node, ast.Name):
        return node.id
    if isinstance(node, ast.Attribute):
        prefix = _dotted_name(node.value)
        return f"{prefix}.{node.attr}" if prefix else node.attr
    return ""


@pytest.mark.parametrize(
    ("microdollars", "expected_cents"),
    [(1, 1), (9_999, 1), (10_000, 1), (10_001, 2), (250_000, 25)],
)
def test_atomic_begin_conservatively_converts_microdollars(
    tmp_path: Path, microdollars: int, expected_cents: int
) -> None:
    authorization = _authorization(request_id=f"amount-{microdollars}", microdollars=microdollars)
    db_path = str(tmp_path / "execution.duckdb")

    execution, hold = begin_reserved_provider_submission(
        db_path=db_path,
        authorization=authorization,
        signing_key=KEY,
        now=NOW,
    )

    assert execution.authorization_id == authorization.authorization_id
    assert hold.projected_max_cents == expected_cents
    balance = BudgetLedger(db_path).balance(authorization.authorization_id)
    assert balance.ceiling_cents == expected_cents
    assert balance.held_cents == expected_cents
    assert balance.remaining_cents == 0


def test_atomic_begin_exact_replay_returns_one_deterministic_hold(tmp_path: Path) -> None:
    authorization = _authorization(request_id="replay", microdollars=250_001)
    db_path = str(tmp_path / "execution.duckdb")

    first = begin_reserved_provider_submission(
        db_path=db_path, authorization=authorization, signing_key=KEY, now=NOW
    )
    replay = begin_reserved_provider_submission(
        db_path=db_path,
        authorization=authorization,
        signing_key=KEY,
        now=NOW + timedelta(minutes=2),
    )

    assert replay == first
    connection = connect_read(db_path)
    try:
        assert connection.execute(
            "SELECT count(*) FROM midnight_oil_call_holds WHERE run_id = ?",
            [authorization.authorization_id],
        ).fetchone() == (1,)
    finally:
        connection.close()


def test_atomic_begin_concurrent_replay_creates_one_execution_and_hold(tmp_path: Path) -> None:
    authorization = _authorization(request_id="race", microdollars=250_000)
    db_path = str(tmp_path / "execution.duckdb")

    def begin():
        return begin_reserved_provider_submission(
            db_path=db_path, authorization=authorization, signing_key=KEY, now=NOW
        )

    with ThreadPoolExecutor(max_workers=8) as pool:
        results = list(pool.map(lambda _: begin(), range(16)))

    assert all(result == results[0] for result in results)
    connection = connect_read(db_path)
    try:
        assert connection.execute(
            "SELECT count(*) FROM multimedia_provider_executions"
        ).fetchone() == (1,)
        assert connection.execute("SELECT count(*) FROM midnight_oil_call_holds").fetchone() == (
            1,
        )
    finally:
        connection.close()


def test_accounting_conflict_rolls_back_execution_and_authorization_claim(tmp_path: Path) -> None:
    authorization = _authorization(request_id="rollback", microdollars=250_000)
    db_path = str(tmp_path / "execution.duckdb")
    ledger = BudgetLedger(db_path)
    ledger.ensure_schema()
    ledger.reserve(authorization.authorization_id, 99, role_budgets={"other": 99})

    with pytest.raises(RuntimeError, match="reservation exists"):
        begin_reserved_provider_submission(
            db_path=db_path, authorization=authorization, signing_key=KEY, now=NOW
        )

    connection = connect_read(db_path)
    try:
        assert connection.execute(
            "SELECT count(*) FROM multimedia_provider_executions"
        ).fetchone() == (0,)
        assert connection.execute(
            "SELECT count(*) FROM multimedia_execution_authorization_claims"
        ).fetchone() == (0,)
    finally:
        connection.close()


def test_intent_mutation_failure_rolls_back_claim_execution_and_hold(tmp_path: Path) -> None:
    authorization = _authorization(request_id="intent-rollback", microdollars=250_000)
    db_path = str(tmp_path / "execution.duckdb")

    def fail_intent(*_: object) -> None:
        raise RuntimeError("intent persistence failed")

    with pytest.raises(RuntimeError, match="intent persistence failed"):
        begin_reserved_provider_submission(
            db_path=db_path,
            authorization=authorization,
            signing_key=KEY,
            now=NOW,
            mutation=fail_intent,
        )
    connection = connect_read(db_path)
    try:
        assert connection.execute(
            "SELECT count(*) FROM multimedia_execution_authorization_claims"
        ).fetchone() == (0,)
        assert connection.execute(
            "SELECT count(*) FROM multimedia_provider_executions"
        ).fetchone() == (0,)
        assert connection.execute(
            "SELECT count(*) FROM information_schema.tables "
            "WHERE table_name = 'midnight_oil_call_holds'"
        ).fetchone() == (0,)
    finally:
        connection.close()


@pytest.mark.parametrize(
    "mutation",
    [
        "DELETE FROM midnight_oil_role_budgets",
        "DELETE FROM midnight_oil_spend_ledger WHERE event = 'hold'",
        "UPDATE midnight_oil_role_budgets SET held_cents = 0",
    ],
)
def test_exact_replay_rejects_incomplete_or_tampered_accounting(
    tmp_path: Path, mutation: str
) -> None:
    authorization = _authorization(request_id=hashlib.sha256(mutation.encode()).hexdigest(), microdollars=250_000)
    db_path = str(tmp_path / "execution.duckdb")
    begin_reserved_provider_submission(
        db_path=db_path, authorization=authorization, signing_key=KEY, now=NOW
    )
    connection = connect_write(db_path)
    try:
        connection.execute(mutation)
    finally:
        connection.close()

    with pytest.raises(RuntimeError, match="role budget|audit ledger"):
        begin_reserved_provider_submission(
            db_path=db_path,
            authorization=authorization,
            signing_key=KEY,
            now=NOW + timedelta(minutes=2),
        )


def test_pinned_catalog_produces_exact_snake_case_provider_bytes() -> None:
    image = prepare_request(Imagen3Request(prompt="Aircraft factory", width=2048, height=1024))
    video = prepare_request(
        RunwayGen45Request(
            prompt="Aircraft factory",
            duration=8,
            aspect_ratio="1584:672",
            seed=7,
        )
    )
    assert CATALOG_VERSION == "2026-07-11.ac30291d"
    assert image.catalog_digest == video.catalog_digest == CATALOG_DIGEST
    assert json.loads(image.body) == {
        "height": 1024,
        "prompt": "Aircraft factory",
        "seed": 1337,
        "width": 2048,
    }
    assert json.loads(video.body) == {
        "aspect_ratio": "1584:672",
        "duration": 8,
        "prompt": "Aircraft factory",
        "seed": 7,
    }
    with pytest.raises(ValueError, match="duration"):
        prepare_request(RunwayGen45Request(prompt="Aircraft", duration=11))
    with pytest.raises(ValueError, match="aspect_ratio"):
        prepare_request(RunwayGen45Request(prompt="Aircraft", aspect_ratio="16:9"))
    with pytest.raises(ValueError, match="width"):
        prepare_request(Imagen3Request(prompt="Aircraft", width=256))


def test_reviewed_openapi_subset_is_packaged_and_digest_pinned() -> None:
    resource = importlib.resources.files("integrations.krea").joinpath("openapi_subset.json")
    value = json.loads(resource.read_text(encoding="utf-8"))
    canonical = json.dumps(value, sort_keys=True, separators=(",", ":")).encode()
    assert hashlib.sha256(canonical).hexdigest() == OPENAPI_SUBSET_SHA256
    assert value["source_url"] == OPENAPI_SOURCE_URL
    image = value["paths"]["/generate/image/google/imagen-3"]["request_schema"]
    runway = value["paths"]["/generate/video/runway/gen-4.5"]["request_schema"]
    assert image["properties"]["width"]["maximum"] == 8192
    assert "seed" in image["properties"]
    assert "aspect_ratio" in runway["properties"]
    assert "aspectRatio" not in runway["properties"]


def test_openapi_drift_extractor_matches_reviewed_subset_and_detects_change() -> None:
    resource = importlib.resources.files("integrations.krea").joinpath("openapi_subset.json")
    reviewed = json.loads(resource.read_text(encoding="utf-8"))["paths"]
    expected = copy.deepcopy(reviewed)
    document: dict[str, object] = {"paths": {}}
    paths = document["paths"]
    assert isinstance(paths, dict)
    for endpoint, contract in reviewed.items():
        paths[endpoint] = {
            "post": {
                "requestBody": {
                    "content": {"application/json": {"schema": contract["request_schema"]}}
                },
                "responses": {
                    "200": {
                        "content": {
                            "application/json": {
                                "schema": {
                                    "properties": {
                                        "job_id": {"format": contract["response"]["job_id"]},
                                        "status": {"enum": contract["response"]["status"]},
                                    }
                                }
                            }
                        }
                    }
                },
            }
        }
    assert extract_reviewed_openapi_paths(document) == expected
    paths["/generate/image/google/imagen-3"]["post"]["requestBody"]["content"][
        "application/json"
    ]["schema"]["properties"]["width"]["maximum"] = 2048
    assert extract_reviewed_openapi_paths(document) != expected


def test_no_shipped_module_constructs_live_krea_client() -> None:
    offenders: list[str] = []
    for path in REPO_ROOT.rglob("*.py"):
        relative = path.relative_to(REPO_ROOT)
        if "tests" in relative.parts or path.name.startswith("test_"):
            continue
        for hit in _krea_client_constructors(path):
            if hit not in AUTHORIZED_KREA_CLIENT_CONSTRUCTORS:
                offenders.append(hit)
    assert offenders == [], (
        "A shipped module constructed KreaClient without an explicit reviewed allowlist entry: "
        + ", ".join(offenders)
    )


def test_krea_client_constructor_guard_detects_bare_and_qualified_calls(tmp_path: Path) -> None:
    bare = tmp_path / "bare.py"
    qualified = tmp_path / "qualified.py"
    bare.write_text("client = KreaClient(token)\n", encoding="utf-8")
    qualified.write_text(
        "client = edge.KreaClient(token)\ntest = edge.KreaClient.for_loopback_test(token, origin)\n",
        encoding="utf-8",
    )
    assert _krea_client_constructors(bare)
    assert len(_krea_client_constructors(qualified)) == 2


def test_catalog_or_body_drift_fails_before_claim_or_packet(tmp_path: Path) -> None:
    approved_request = RunwayGen45Request(prompt="Aircraft history", duration=5)
    changed_request = RunwayGen45Request(prompt="Aircraft history", duration=6)
    authorization, quote = _live_authorization(approved_request, "drift")
    db_path = str(tmp_path / "execution.duckdb")
    with (
        _server("success") as (state, origin),
        pytest.raises(ExecutionAuthorizationIntegrityError, match="Krea quote integrity"),
    ):
        submit_krea_job(
            db_path=db_path,
            authorization=authorization,
            signing_key=KEY,
            now=NOW,
            request=changed_request,
            quote=quote,
            client=_LoopbackKreaClient(TOKEN, origin),
        )
    assert state.requests == 0
    assert not Path(db_path).exists()


def test_tampered_quote_fails_before_claim_or_packet(tmp_path: Path) -> None:
    request = Imagen3Request(prompt="Aircraft quote integrity")
    authorization, quote = _live_authorization(request, "quote-tamper")
    db_path = str(tmp_path / "execution.duckdb")
    with (
        _server("success") as (state, origin),
        pytest.raises(ExecutionAuthorizationIntegrityError, match="Krea quote integrity"),
    ):
        submit_krea_job(
            db_path=db_path,
            authorization=authorization,
            signing_key=KEY,
            now=NOW,
            request=request,
            quote=replace(quote, ceiling_microdollars=1),
            client=_LoopbackKreaClient(TOKEN, origin),
        )
    assert state.requests == 0
    assert not Path(db_path).exists()


def test_success_posts_once_binds_uuid_and_replay_never_posts(tmp_path: Path) -> None:
    request = RunwayGen45Request(prompt="Aircraft history", duration=5)
    authorization, quote = _live_authorization(request, "success")
    db_path = str(tmp_path / "execution.duckdb")
    prepared = prepare_request(request)
    with _server("success") as (state, origin):
        client = _LoopbackKreaClient(TOKEN, origin)
        first = submit_krea_job(
            db_path=db_path,
            authorization=authorization,
            signing_key=KEY,
            now=NOW,
            request=request,
            quote=quote,
            client=client,
        )
        replay = submit_krea_job(
            db_path=db_path,
            authorization=authorization,
            signing_key=KEY,
            now=NOW + timedelta(minutes=2),
            request=request,
            quote=quote,
            client=client,
        )
    assert first == replay
    assert first.status is ProviderExecutionStatus.SUBMITTED
    assert first.provider_job_id == "3c90c3cc-0d44-4b50-8888-8dd25736052a"
    assert state.requests == 1
    assert state.body == prepared.body
    assert state.authorization == f"Bearer {TOKEN}"
    balance = BudgetLedger(db_path).balance(authorization.authorization_id)
    assert balance.held_cents == 25
    assert balance.spent_cents == 0
    attempt = get_krea_submission_attempt(
        db_path=db_path, execution_id=first.execution_id, signing_key=KEY
    )
    assert attempt.outcome == "job_bound"
    assert attempt.provider_status == "queued"
    assert attempt.http_status == 200
    assert attempt.failure_kind is None


@pytest.mark.parametrize(
    ("behavior", "failure_kind", "http_status"),
    [
        ("disconnect", "transport_ambiguous", None),
        ("redirect", "redirect_refused", 307),
        ("http_400", "request_rejected", 400),
        ("http_401", "authentication_rejected", 401),
        ("http_402", "balance_insufficient", 402),
        ("http_429", "rate_limited", 429),
        ("http_500", "provider_unavailable", 500),
        ("malformed", "malformed_json", None),
        ("oversized", "response_too_large", None),
    ],
)
def test_ambiguous_response_posts_once_charges_ceiling_and_never_retries(
    tmp_path: Path, behavior: str, failure_kind: str, http_status: int | None
) -> None:
    request = Imagen3Request(prompt=f"Aircraft {behavior}")
    authorization, quote = _live_authorization(request, f"ambiguous-{behavior}")
    db_path = str(tmp_path / "execution.duckdb")
    with _server(behavior) as (state, origin):
        client = _LoopbackKreaClient(TOKEN, origin)
        unknown = submit_krea_job(
            db_path=db_path,
            authorization=authorization,
            signing_key=KEY,
            now=NOW,
            request=request,
            quote=quote,
            client=client,
        )
        replay = submit_krea_job(
            db_path=db_path,
            authorization=authorization,
            signing_key=KEY,
            now=NOW + timedelta(minutes=2),
            request=request,
            quote=quote,
            client=client,
        )
    assert unknown == replay
    assert unknown.status is ProviderExecutionStatus.OUTCOME_UNKNOWN
    assert state.requests == 1
    balance = BudgetLedger(db_path).balance(authorization.authorization_id)
    assert balance.spent_cents == balance.ceiling_cents == 25
    assert balance.held_cents == 0
    attempt = get_krea_submission_attempt(
        db_path=db_path, execution_id=unknown.execution_id, signing_key=KEY
    )
    assert attempt.outcome == "outcome_unknown"
    assert attempt.provider_status is None
    assert attempt.failure_kind == failure_kind
    assert attempt.http_status == http_status


def test_client_never_exposes_secrets() -> None:
    with _server("malformed") as (_, origin):
        client = _LoopbackKreaClient(TOKEN, origin)
        with pytest.raises(KreaClientError) as caught:
            client.submit(
                endpoint="/generate/image/google/imagen-3",
                body=b'{"prompt":"aircraft"}',
            )
    rendered = repr(caught.value) + str(caught.value)
    assert TOKEN not in rendered
    assert "secret-never-log-this" not in rendered
    assert caught.value.__cause__ is None


def test_stale_send_marker_recovery_charges_without_another_post(tmp_path: Path) -> None:
    request = RunwayGen45Request(prompt="Aircraft crash recovery")
    authorization, quote = _live_authorization(request, "crash-recovery")
    db_path = str(tmp_path / "execution.duckdb")

    class ProcessCrashClient:
        def submit(self, **_: object) -> None:
            raise SystemExit("simulated process death")

    with pytest.raises(SystemExit, match="process death"):
        submit_krea_job(
            db_path=db_path,
            authorization=authorization,
            signing_key=KEY,
            now=NOW,
            request=request,
            quote=quote,
            client=ProcessCrashClient(),  # type: ignore[arg-type]
        )
    execution_id = "mmexec_" + hashlib.sha256(
        f"{authorization.authorization_id}:{authorization.request_body_digest}".encode()
    ).hexdigest()
    with pytest.raises(ProviderExecutionIntegrityError, match="not stale"):
        recover_stale_krea_submission(
            db_path=db_path,
            execution_id=execution_id,
            signing_key=KEY,
            now=NOW + timedelta(minutes=1),
        )
    unknown = recover_stale_krea_submission(
        db_path=db_path,
        execution_id=execution_id,
        signing_key=KEY,
        now=NOW + timedelta(minutes=6),
    )
    assert unknown.status is ProviderExecutionStatus.OUTCOME_UNKNOWN
    assert BudgetLedger(db_path).balance(authorization.authorization_id).spent_cents == 25
