from __future__ import annotations

import hashlib
import os
from pathlib import Path

# ruff: noqa: F811 - pytest fixture is intentionally imported.
import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient
from test_canonical_aggregate_projection import completed_parent  # noqa: F401
from test_current_canonical_twin_node import _materialized

from interfaces.research.api.current_twin_promotion_routes import (
    CurrentTwinPromotionRouteRuntime,
    current_twin_promotion_router,
    get_current_twin_promotion_runtime,
    register_current_twin_promotion_routes,
)
from substrate.twin_recursion.evidence_promotion import TwinEvidencePromotionLedger
from substrate.twin_recursion.ledger import TwinRecursionLedger
from substrate.twin_recursion.read_routes import (
    CurrentTwinPromotionReadRegistry,
    QualifiedCurrentTwinPromotionRead,
)


def _runtime(completed_parent):
    twins, graph, promotions, candidate, result = _materialized(completed_parent)
    db_path = str(
        graph.execute(
            "SELECT path FROM duckdb_databases() WHERE database_name=current_database()"
        ).fetchone()[0]
    )
    graph.close()
    promotion_key = bytes(promotions._review_key)  # Existing authority fixture key.
    promotions = TwinEvidencePromotionLedger.open_read_only(
        promotions.path, owner_id="acct", review_verify_key=promotion_key
    )
    twins = TwinRecursionLedger.open_read_only(twins.path)
    registry = CurrentTwinPromotionReadRegistry(
        (QualifiedCurrentTwinPromotionRead("acct", db_path, promotions, twins),)
    )
    return CurrentTwinPromotionRouteRuntime(registry), candidate, result, db_path


def _app(runtime, *, owner: str = "acct", method: str = "bearer_token") -> FastAPI:
    app = FastAPI()

    @app.middleware("http")
    async def authenticated(request, call_next):  # type: ignore[no-untyped-def]
        request.state.auth_method = method
        request.state.user_id = owner
        return await call_next(request)

    register_current_twin_promotion_routes(app, runtime=runtime)
    return app


def test_authenticated_owner_reads_exact_current_node_and_citations(completed_parent) -> None:
    runtime, candidate, result, _ = _runtime(completed_parent)
    response = TestClient(_app(runtime)).get(f"/reader/promotions/{candidate.candidate_id}")
    assert response.status_code == 200
    body = response.json()
    assert body["node"]["node_id"] == result.node_id
    assert body["node"]["text"] == candidate.text
    assert [item["citation_kind"] for item in body["citations"]] == [
        "canonical_twin",
        "evidence",
    ]
    assert response.headers["cache-control"] == "private, no-store"
    assert response.headers["x-content-type-options"] == "nosniff"


def test_success_and_not_found_reads_do_not_mutate_authority_stores(completed_parent) -> None:
    runtime, candidate, _, db_path = _runtime(completed_parent)
    route = runtime.registry.resolve("acct")
    promotions, twins = route.open_readers()
    paths = [
        Path(db_path),
        Path(db_path + ".write.lock"),
        Path(promotions.path),
        Path(twins.path),
    ]

    def digests() -> tuple[str, ...]:
        return tuple(hashlib.sha256(path.read_bytes()).hexdigest() for path in paths)

    before = digests()
    client = TestClient(_app(runtime))
    assert client.get(f"/reader/promotions/{candidate.candidate_id}").status_code == 200
    assert client.get("/reader/promotions/absent").status_code == 404
    assert digests() == before


def test_absent_and_foreign_owner_are_uniform_private_not_found(completed_parent) -> None:
    runtime, candidate, _, _ = _runtime(completed_parent)
    absent = TestClient(_app(runtime)).get("/reader/promotions/absent")
    foreign = TestClient(_app(runtime, owner="foreign")).get(
        f"/reader/promotions/{candidate.candidate_id}"
    )
    assert absent.status_code == foreign.status_code == 404
    assert absent.json() == foreign.json() == {"detail": "current twin promotion not found"}
    assert (
        absent.headers["cache-control"] == foreign.headers["cache-control"] == ("private, no-store")
    )


def test_stale_evidence_is_private_not_found_and_history_remains(completed_parent) -> None:
    runtime, candidate, result, db_path = _runtime(completed_parent)
    from runtime.db_lock import connect_write

    with connect_write(db_path, purpose="stale_route_test") as graph:
        graph.execute("UPDATE chunks SET text='changed' WHERE chunk_id='evidence-chunk'")
    response = TestClient(_app(runtime)).get(f"/reader/promotions/{candidate.candidate_id}")
    assert response.status_code == 404
    with connect_write(db_path, purpose="history_route_test") as graph:
        assert graph.execute(
            "SELECT count(*) FROM nodes WHERE node_id=?", [result.node_id]
        ).fetchone() == (1,)
        assert graph.execute("SELECT count(*) FROM canonical_twin_node_citations").fetchone() == (
            2,
        )


@pytest.mark.parametrize("method", ["cloudflare_access_email", "cloudflare_access_jwt", ""])
def test_unverified_identity_methods_are_rejected(completed_parent, method: str) -> None:
    runtime, candidate, _, _ = _runtime(completed_parent)
    response = TestClient(_app(runtime, method=method)).get(
        f"/reader/promotions/{candidate.candidate_id}"
    )
    assert response.status_code == 401
    assert response.headers["cache-control"] == "private, no-store"


def test_default_runtime_method_and_namespace_fail_privately(completed_parent) -> None:
    _, candidate, _, _ = _runtime(completed_parent)
    app = FastAPI()

    @app.middleware("http")
    async def authenticated(request, call_next):  # type: ignore[no-untyped-def]
        request.state.auth_method = "bearer_token"
        request.state.user_id = "acct"
        return await call_next(request)

    register_current_twin_promotion_routes(app)
    client = TestClient(app)
    unavailable = client.get(f"/reader/promotions/{candidate.candidate_id}")
    method = client.post(f"/reader/promotions/{candidate.candidate_id}")
    namespace = client.get(f"/reader/promotions/{candidate.candidate_id}/missing")
    namespace_root = client.get("/reader/promotions")
    namespace_root_method = client.post("/reader/promotions")
    assert unavailable.status_code == 503
    assert method.status_code == 405
    assert namespace.status_code == 404
    for response in (unavailable, method, namespace, namespace_root, namespace_root_method):
        assert response.headers["cache-control"] == "private, no-store"


def test_registry_is_exact_immutable_owner_authority(completed_parent) -> None:
    runtime, _, _, _ = _runtime(completed_parent)
    assert runtime.registry.resolve("acct").owner_id == "acct"
    with pytest.raises(ValueError, match="unique"):
        CurrentTwinPromotionReadRegistry(
            (runtime.registry.resolve("acct"), runtime.registry.resolve("acct"))
        )
    with pytest.raises(TypeError, match="exact immutable"):
        CurrentTwinPromotionReadRegistry([])  # type: ignore[arg-type]


def test_registry_rejects_writable_and_replaced_authorities(completed_parent, tmp_path) -> None:
    runtime, _, _, _ = _runtime(completed_parent)
    route = runtime.registry.resolve("acct")
    promotions, twins = route.open_readers()
    writable_twins = TwinRecursionLedger(tmp_path / "writable-twins.sqlite")
    with pytest.raises(ValueError, match="read-only twin"):
        QualifiedCurrentTwinPromotionRead(
            route.owner_id, route.graph_db_path, promotions, writable_twins
        )
    replacement = tmp_path / "replacement.duckdb"
    replacement.write_bytes(Path(route.graph_db_path).read_bytes())
    original = tmp_path / "original.duckdb"
    original.write_bytes(replacement.read_bytes())
    Path(str(original) + ".write.lock").write_bytes(b"lock")
    qualified = QualifiedCurrentTwinPromotionRead(
        route.owner_id, str(original.resolve()), promotions, twins
    )
    original.unlink()
    original.write_bytes(replacement.read_bytes())
    with pytest.raises(Exception, match="authority integrity unavailable"):
        qualified.require_current()


def test_registry_retains_no_live_ledger_handles(completed_parent) -> None:
    runtime, _, _, _ = _runtime(completed_parent)
    route = runtime.registry.resolve("acct")
    assert not hasattr(route, "promotions")
    assert not hasattr(route, "twins")
    first = route.open_readers()
    second = route.open_readers()
    assert first[0] is not second[0]
    assert first[1] is not second[1]


def test_replaced_lock_inode_fails_closed_while_original_is_locked(completed_parent) -> None:
    import fcntl

    runtime, candidate, _, db_path = _runtime(completed_parent)
    lock_path = Path(db_path + ".write.lock")
    held = os.open(lock_path, os.O_WRONLY)
    try:
        fcntl.flock(held, fcntl.LOCK_EX)
        lock_path.unlink()
        lock_path.write_bytes(b"replacement")
        response = TestClient(_app(runtime)).get(f"/reader/promotions/{candidate.candidate_id}")
        assert response.status_code == 503
    finally:
        fcntl.flock(held, fcntl.LOCK_UN)
        os.close(held)


def test_graph_replacement_during_open_fails_closed(
    completed_parent, monkeypatch, tmp_path
) -> None:
    import runtime.db_lock as db_lock

    runtime, candidate, _, db_path = _runtime(completed_parent)
    original_connect = db_lock.duckdb.connect
    replacement = tmp_path / "replacement.duckdb"
    replacement.write_bytes(Path(db_path).read_bytes())
    replaced = False

    def replacing_connect(path, *args, **kwargs):  # type: ignore[no-untyped-def]
        nonlocal replaced
        if kwargs.get("read_only") is True and not replaced:
            replaced = True
            os.replace(replacement, db_path)
        return original_connect(path, *args, **kwargs)

    monkeypatch.setattr(db_lock.duckdb, "connect", replacing_connect)
    response = TestClient(_app(runtime)).get(f"/reader/promotions/{candidate.candidate_id}")
    assert response.status_code == 503


def test_post_open_identity_error_closes_duckdb(monkeypatch, tmp_path) -> None:
    import runtime.db_lock as db_lock

    graph = tmp_path / "graph.duckdb"
    lock = Path(str(graph) + ".write.lock")
    graph.write_bytes(b"graph")
    lock.write_bytes(b"lock")
    graph_stat = graph.stat()
    lock_stat = lock.stat()

    class FakeConnection:
        closed = False

        def close(self) -> None:
            self.closed = True

    fake = FakeConnection()
    monkeypatch.setattr(db_lock.duckdb, "connect", lambda *args, **kwargs: fake)
    original_stat = db_lock.os.stat
    graph_stats = 0

    def failing_stat(path, *args, **kwargs):  # type: ignore[no-untyped-def]
        nonlocal graph_stats
        if str(path) == str(graph):
            graph_stats += 1
            if graph_stats == 1:
                raise OSError("post-open graph stat failed")
        return original_stat(path, *args, **kwargs)

    monkeypatch.setattr(db_lock.os, "stat", failing_stat)
    with pytest.raises(OSError, match="post-open"):
        db_lock.connect_authority_read(
            str(graph),
            expected_db_identity=(graph_stat.st_dev, graph_stat.st_ino),
            expected_lock_identity=(lock_stat.st_dev, lock_stat.st_ino),
        )
    assert fake.closed is True


def test_authority_read_connection_is_never_write_authority(completed_parent) -> None:
    from runtime.db_lock import (
        connect_authority_read,
        is_active_authority_read_connection,
        is_active_write_connection,
    )

    runtime, _, _, _ = _runtime(completed_parent)
    route = runtime.registry.resolve("acct")
    with connect_authority_read(
        route.graph_db_path,
        expected_db_identity=route.graph_identity,
        expected_lock_identity=route.lock_identity,
    ) as graph:
        assert is_active_authority_read_connection(graph) is True
        assert is_active_write_connection(graph) is False


def test_router_dependency_defaults_to_unavailable() -> None:
    app = FastAPI()
    app.include_router(current_twin_promotion_router)
    app.dependency_overrides[get_current_twin_promotion_runtime] = (
        get_current_twin_promotion_runtime
    )
    response = TestClient(app).get("/reader/promotions/candidate")
    assert response.status_code == 401


def test_production_factory_mounts_private_unavailable_namespace(monkeypatch) -> None:
    import importlib

    app_module = importlib.import_module("interfaces.research.api.app")
    monkeypatch.delenv("ANTIEK_TWIN_LEDGER_PATH", raising=False)
    monkeypatch.setenv("ANTIEK_OPERATOR_TOKEN", "cycle118-test-token")
    app = app_module.create_app()
    assert "/reader/promotions/{candidate_id}" in {route.path for route in app.routes}
    client = TestClient(app)
    unauthenticated = client.get("/reader/promotions/candidate")
    unavailable = client.get(
        "/reader/promotions/candidate",
        headers={"Authorization": "Bearer cycle118-test-token"},
    )
    assert unauthenticated.status_code == 401
    assert unavailable.status_code == 503
    assert unauthenticated.headers["cache-control"] == "private, no-store"
    assert unavailable.headers["cache-control"] == "private, no-store"
