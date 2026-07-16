from __future__ import annotations

# ruff: noqa: F811 - pytest fixture is intentionally imported.
from pathlib import Path

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient
from test_budgeted_canonical_twin_embedding import (
    EmbeddingAdapter,
    _request,
    _setup,
    _source_asset,
    _source_hash,
)
from test_canonical_aggregate_projection import completed_parent  # noqa: F401

from interfaces.research.api.canonical_twin_embedding_routes import (
    CanonicalTwinEmbeddingRouteRuntime,
    CanonicalTwinEmbeddingRunAuthority,
    canonical_twin_embedding_router,
    get_canonical_twin_embedding_runtime,
    register_canonical_twin_embedding_routes,
)
from substrate.research_spend import RunBinding, RunNotFound
from substrate.twin_recursion import (
    CanonicalEmbeddingRouteRegistry,
    CanonicalEmbeddingRouteUnavailable,
    QualifiedCanonicalEmbeddingRoute,
)


def _body() -> dict[str, object]:
    return {
        "route_id": "server-balanced-v1",
    }


def _app(runtime: CanonicalTwinEmbeddingRouteRuntime, owner: str = "acct") -> FastAPI:
    app = FastAPI()

    @app.middleware("http")
    async def authenticated(request, call_next):  # type: ignore[no-untyped-def]
        request.state.auth_method = "bearer_token"
        request.state.user_id = owner
        return await call_next(request)

    register_canonical_twin_embedding_routes(app, runtime=runtime)
    return app


def _runtime(completed_parent, tmp_path: Path, *, empty: bool = False):
    _, graph, _, _, embedder = _setup(completed_parent, tmp_path)
    db_path = str(
        graph.execute(
            "SELECT path FROM duckdb_databases() WHERE database_name=current_database()"
        ).fetchone()[0]
    )
    source_asset, source_hash = _source_asset(graph), _source_hash(graph)
    graph.close()
    adapter = EmbeddingAdapter()
    routes = (
        ()
        if empty
        else (QualifiedCanonicalEmbeddingRoute("server-balanced-v1", _request(), adapter),)
    )
    runtime = CanonicalTwinEmbeddingRouteRuntime(
        db_path,
        embedder,
        CanonicalEmbeddingRouteRegistry(routes),
        lambda owner, asset, revision, route_id: CanonicalTwinEmbeddingRunAuthority(
            owner,
            asset,
            revision,
            route_id,
            RunBinding(
                "embed-run" if owner == "acct" else f"embed-run-{owner}",
                owner,
                "session-root",
                "plan-digest",
                4,
            ),
            100,
        ),
    )
    return runtime, adapter, source_asset, source_hash


def _url(source_asset: str, action: str) -> str:
    return f"/reader/sources/{source_asset}/canonical-twin/embedding/{action}"


def test_registry_is_exact_immutable_and_empty_by_default() -> None:
    registry = CanonicalEmbeddingRouteRegistry()
    assert registry.available is False
    for route_id in ("missing", " bad", "bad/route"):
        try:
            registry.resolve(route_id)
        except CanonicalEmbeddingRouteUnavailable:
            pass
        else:  # pragma: no cover - assertion branch
            raise AssertionError("unqualified route resolved")


def test_empty_registry_refuses_before_send_and_is_private(completed_parent, tmp_path) -> None:
    runtime, adapter, source_asset, source_hash = _runtime(completed_parent, tmp_path, empty=True)
    response = TestClient(_app(runtime)).post(
        _url(source_asset, "preview"), params={"source_hash": source_hash}, json=_body()
    )
    assert response.status_code == 503
    assert response.headers["cache-control"] == "private, no-store"
    assert adapter.sends == []


def test_authenticated_preview_approve_execute_uses_only_server_route(
    completed_parent, tmp_path
) -> None:
    runtime, adapter, source_asset, source_hash = _runtime(completed_parent, tmp_path)
    client = TestClient(_app(runtime))
    preview = client.post(
        _url(source_asset, "preview"), params={"source_hash": source_hash}, json=_body()
    )
    assert preview.status_code == 200
    assert preview.json()["maximum_chain_exposure_cents"] == 80
    adapter.expected_operation_digest = preview.json()["operation_digest"]
    assert adapter.sends == []
    approval_body = {**_body(), "preview": preview.json()}
    approval = client.post(
        _url(source_asset, "approve"),
        params={"source_hash": source_hash},
        json=approval_body,
    )
    assert approval.status_code == 200 and adapter.sends == []
    execution = client.post(
        _url(source_asset, "execute"),
        params={"source_hash": source_hash},
        json={**_body(), "approval_id": approval.json()["approval_id"]},
    )
    assert execution.status_code == 200
    assert execution.json()["actual_cents"] == 60
    assert len(adapter.sends) == 1
    replay = client.post(
        _url(source_asset, "execute"),
        params={"source_hash": source_hash},
        json={**_body(), "approval_id": approval.json()["approval_id"]},
    )
    assert replay.status_code == 200 and replay.json()["replayed"] is True
    assert len(adapter.sends) == 1
    assert all(
        response.headers["cache-control"] == "private, no-store"
        for response in (preview, approval, execution, replay)
    )


def test_wrong_owner_and_caller_provider_fields_fail_closed(completed_parent, tmp_path) -> None:
    runtime, adapter, source_asset, source_hash = _runtime(completed_parent, tmp_path)
    wrong_owner = TestClient(_app(runtime, owner="other")).post(
        _url(source_asset, "preview"), params={"source_hash": source_hash}, json=_body()
    )
    assert wrong_owner.status_code == 404 and adapter.sends == []
    injected = TestClient(_app(runtime)).post(
        _url(source_asset, "preview"),
        params={"source_hash": source_hash},
        json={**_body(), "provider": "caller", "endpoint": "https://caller.invalid"},
    )
    assert injected.status_code == 422 and adapter.sends == []
    assert injected.headers["cache-control"] == "private, no-store"


def test_caller_spend_authority_fields_are_rejected_before_send(completed_parent, tmp_path) -> None:
    runtime, adapter, source_asset, source_hash = _runtime(completed_parent, tmp_path)
    client = TestClient(_app(runtime))
    changed = client.post(
        _url(source_asset, "preview"),
        params={"source_hash": source_hash},
        json={
            **_body(),
            "ceiling_cents": 9_223_372_036_854_775_807,
            "approval_revision": 999,
            "session_id": "forged",
            "plan_digest": "forged",
        },
    )
    assert changed.status_code == 422 and adapter.sends == []
    assert changed.headers["cache-control"] == "private, no-store"


def test_runtime_failure_is_private_unavailable(completed_parent, tmp_path, monkeypatch) -> None:
    runtime, adapter, source_asset, source_hash = _runtime(completed_parent, tmp_path)

    def fail(*args, **kwargs):  # type: ignore[no-untyped-def]
        raise RuntimeError("internal path must not escape")

    monkeypatch.setattr(runtime.embedder, "prepare", fail)
    response = TestClient(_app(runtime)).post(
        _url(source_asset, "preview"), params={"source_hash": source_hash}, json=_body()
    )
    assert response.status_code == 503 and adapter.sends == []
    assert response.json() == {"detail": "canonical twin embedding unavailable"}
    assert response.headers["cache-control"] == "private, no-store"


def test_resolver_must_attest_exact_request_before_run_creation(completed_parent, tmp_path) -> None:
    runtime, adapter, source_asset, source_hash = _runtime(completed_parent, tmp_path)
    valid = runtime.run_authority_resolver("acct", source_asset, source_hash, _body()["route_id"])
    assert isinstance(valid, CanonicalTwinEmbeddingRunAuthority)
    client = TestClient(_app(runtime))
    for field, value in (
        ("source_asset_id", "foreign-asset"),
        ("source_hash", "foreign-hash"),
        ("route_id", "foreign-route"),
    ):
        rejected = CanonicalTwinEmbeddingRunAuthority(
            valid.owner_id,
            valid.source_asset_id,
            valid.source_hash,
            valid.route_id,
            RunBinding("rejected-run", "acct", "rejected-session", "rejected-plan", 1),
            valid.ceiling_cents,
        )
        object.__setattr__(
            runtime,
            "run_authority_resolver",
            lambda *args, field=field, value=value, rejected=rejected: (
                CanonicalTwinEmbeddingRunAuthority(**{**rejected.__dict__, field: value})
            ),
        )
        response = client.post(
            _url(source_asset, "preview"), params={"source_hash": source_hash}, json=_body()
        )
        assert response.status_code == 503
        assert adapter.sends == []
        with pytest.raises(RunNotFound):
            runtime.embedder.gateway.ledger.balance("rejected-run")


def test_approval_uses_single_resolved_authority(completed_parent, tmp_path) -> None:
    runtime, adapter, source_asset, source_hash = _runtime(completed_parent, tmp_path)
    original = runtime.run_authority_resolver
    client = TestClient(_app(runtime))
    preview = client.post(
        _url(source_asset, "preview"), params={"source_hash": source_hash}, json=_body()
    )
    assert preview.status_code == 200
    calls = 0

    def changing(*args):  # type: ignore[no-untyped-def]
        nonlocal calls
        calls += 1
        authority = original(*args)
        if calls > 1:
            return CanonicalTwinEmbeddingRunAuthority(
                authority.owner_id,
                authority.source_asset_id,
                authority.source_hash,
                authority.route_id,
                RunBinding("changed-run", "acct", "changed-session", "changed-plan", 5),
                99,
            )
        return authority

    object.__setattr__(runtime, "run_authority_resolver", changing)
    approval = client.post(
        _url(source_asset, "approve"),
        params={"source_hash": source_hash},
        json={**_body(), "preview": preview.json()},
    )
    assert approval.status_code == 200
    assert calls == 1 and adapter.sends == []
    with pytest.raises(RunNotFound):
        runtime.embedder.gateway.ledger.balance("changed-run")


def test_namespace_is_private_when_unconfigured_or_unauthenticated() -> None:
    unconfigured = FastAPI()
    register_canonical_twin_embedding_routes(unconfigured)
    missing = TestClient(unconfigured).post(
        _url("asset", "preview"), params={"source_hash": "hash"}, json=_body()
    )
    assert missing.status_code == 401
    assert missing.headers["cache-control"] == "private, no-store"

    unavailable = FastAPI()

    @unavailable.middleware("http")
    async def authenticated(request, call_next):  # type: ignore[no-untyped-def]
        request.state.auth_method = "bearer_token"
        request.state.user_id = "acct"
        return await call_next(request)

    register_canonical_twin_embedding_routes(unavailable)
    response = TestClient(unavailable).post(
        _url("asset", "preview"), params={"source_hash": "hash"}, json=_body()
    )
    assert response.status_code == 503
    assert response.headers["cache-control"] == "private, no-store"


def test_unverified_cloudflare_identity_cannot_authorize_spend(completed_parent, tmp_path) -> None:
    runtime, adapter, source_asset, source_hash = _runtime(completed_parent, tmp_path)
    app = FastAPI()

    @app.middleware("http")
    async def spoofed_cloudflare_identity(request, call_next):  # type: ignore[no-untyped-def]
        request.state.auth_method = "cloudflare_access_email"
        request.state.user_id = "acct"
        return await call_next(request)

    register_canonical_twin_embedding_routes(app, runtime=runtime)
    response = TestClient(app).post(
        _url(source_asset, "preview"), params={"source_hash": source_hash}, json=_body()
    )
    assert response.status_code == 401 and adapter.sends == []
    assert response.headers["cache-control"] == "private, no-store"


def test_production_factory_mounts_embedding_namespace(monkeypatch) -> None:
    import importlib

    app_module = importlib.import_module("interfaces.research.api.app")

    monkeypatch.delenv("ANTIEK_TWIN_LEDGER_PATH", raising=False)
    monkeypatch.setenv("ANTIEK_OPERATOR_TOKEN", "cycle113-test-token")
    app = app_module.create_app()
    paths = {route.path for route in app.routes}
    assert _url("{source_asset_id}", "preview") in paths
    assert _url("{source_asset_id}", "approve") in paths
    assert _url("{source_asset_id}", "execute") in paths
    client = TestClient(app)
    unauthenticated = client.post(
        _url("asset", "preview"), params={"source_hash": "hash"}, json=_body()
    )
    assert unauthenticated.status_code == 401
    assert unauthenticated.headers["cache-control"] == "private, no-store"
    unavailable = client.post(
        _url("asset", "preview"),
        params={"source_hash": "hash"},
        json=_body(),
        headers={"Authorization": "Bearer cycle113-test-token"},
    )
    assert unavailable.status_code == 503
    assert unavailable.headers["cache-control"] == "private, no-store"


def test_router_dependency_defaults_to_unavailable() -> None:
    app = FastAPI()
    app.include_router(canonical_twin_embedding_router)
    app.dependency_overrides[get_canonical_twin_embedding_runtime] = (
        get_canonical_twin_embedding_runtime
    )
    response = TestClient(app).post(
        _url("asset", "preview"), params={"source_hash": "hash"}, json=_body()
    )
    assert response.status_code == 401
