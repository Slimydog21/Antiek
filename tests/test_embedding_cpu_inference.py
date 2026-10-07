from __future__ import annotations

import asyncio
import sys
import threading
from collections.abc import Iterator
from concurrent.futures import ThreadPoolExecutor
from contextlib import suppress
from importlib import import_module
from types import ModuleType, SimpleNamespace
from typing import Any

import httpx
import pytest
from fastapi.testclient import TestClient

from interfaces.research.api.app import create_app
from processing.embedding.cpu_inference import EmbeddingInferenceUnavailable
from substrate.auth import mint_session_cookie


class _BrokenModel:
    max_seq_length = 256
    tokenizer = None

    def get_sentence_embedding_dimension(self) -> int:
        return 384

    def encode(self, _texts: list[str]) -> list[list[float]]:
        raise RuntimeError("could not create a primitive: synthetic-private-model-path")


@pytest.fixture
def unavailable_model(monkeypatch: pytest.MonkeyPatch) -> list[tuple[str, object]]:
    calls: list[tuple[str, object]] = []

    def construct(name: str, *, device: object = None) -> _BrokenModel:
        calls.append((name, device))
        return _BrokenModel()

    dependency = ModuleType("sentence_transformers")
    monkeypatch.setattr(dependency, "SentenceTransformer", construct, raising=False)
    monkeypatch.setitem(sys.modules, "sentence_transformers", dependency)
    monkeypatch.setitem(
        sys.modules,
        "torch",
        SimpleNamespace(backends=SimpleNamespace(mkldnn=SimpleNamespace(enabled=True))),
    )
    return calls


@pytest.fixture
def client(monkeypatch: pytest.MonkeyPatch) -> Iterator[TestClient]:
    monkeypatch.delenv("ANTIEK_OPERATOR_TOKEN", raising=False)
    monkeypatch.delenv("ANTIEK_AUTH_MODE", raising=False)
    monkeypatch.setenv("ANTIEK_OPERATOR_EMAIL", "cpu-inference@example.invalid")
    monkeypatch.setenv("ANTIEK_AUTH_SECRET", "synthetic-cpu-inference-signing-secret")
    monkeypatch.setenv("ANTIEK_PUBLIC_SIGNUP_ENABLED", "0")
    app = create_app(
        register_wrestling=False,
        register_providers=False,
        cors_origins=["https://antiek.ai"],
    )
    with TestClient(app, raise_server_exceptions=False) as client:
        client.cookies.set(
            "ANTIEK_SESSION",
            mint_session_cookie(user_id="__operator__", email="cpu-inference@example.invalid"),
        )
        assert client.get("/auth/me").status_code == 200
        yield client


@pytest.mark.parametrize("origin", ["https://antiek.ai", "https://unallowed.invalid", None])
def test_corpus_encode_failure_is_an_opaque_non_success_with_cors(
    client: TestClient,
    unavailable_model: list[tuple[str, object]],
    origin: str | None,
) -> None:
    headers = {} if origin is None else {"Origin": origin}
    response = client.get("/corpus/search?q=synthetic-inference-control", headers=headers)
    assert response.status_code == 503
    assert response.json() == {"detail": "embedding_unavailable"}
    assert "synthetic-private-model-path" not in response.text
    assert "hits" not in response.json()
    assert len(unavailable_model) == 1
    if origin == "https://antiek.ai":
        assert response.headers["access-control-allow-origin"] == origin
    else:
        assert "access-control-allow-origin" not in response.headers


def test_unauthenticated_search_does_not_construct_a_model(
    client: TestClient,
    unavailable_model: list[tuple[str, object]],
) -> None:
    client.cookies.clear()
    response = client.get("/corpus/search?q=unadmitted-inference-control")
    assert response.status_code == 401
    assert unavailable_model == []


@pytest.mark.parametrize("failure", [RuntimeError, OSError, ValueError])
def test_initialization_failure_does_not_expose_native_details(
    client: TestClient,
    unavailable_model: list[tuple[str, object]],
    monkeypatch: pytest.MonkeyPatch,
    failure: type[Exception],
) -> None:
    def refuse(_name: str, *, device: str) -> None:
        assert device == "cpu"
        raise failure("synthetic-private-model-path")

    monkeypatch.setattr(sys.modules["sentence_transformers"], "SentenceTransformer", refuse)
    response = client.get(
        "/corpus/search?q=initialization-control", headers={"Origin": "https://antiek.ai"}
    )
    assert response.status_code == 503
    assert response.json() == {"detail": "embedding_unavailable"}
    assert response.headers["access-control-allow-origin"] == "https://antiek.ai"


@pytest.mark.parametrize("stage", ["initialization", "inference"])
def test_blocked_cpu_work_does_not_block_concurrent_authenticated_http(
    client: TestClient,
    unavailable_model: list[tuple[str, object]],
    monkeypatch: pytest.MonkeyPatch,
    stage: str,
) -> None:
    entered = threading.Event()
    release = threading.Event()

    def hold() -> None:
        entered.set()
        assert release.wait(10), "control did not release the CPU worker"

    class HeldModel(_BrokenModel):
        def encode(self, texts: list[str]) -> list[list[float]]:
            if stage == "inference":
                hold()
            return super().encode(texts)

    def construct(_name: str, *, device: str) -> HeldModel:
        assert device == "cpu"
        if stage == "initialization":
            hold()
        return HeldModel()

    monkeypatch.setattr(sys.modules["sentence_transformers"], "SentenceTransformer", construct)
    with ThreadPoolExecutor(max_workers=2) as executor:
        query = executor.submit(client.get, "/corpus/search?q=concurrency-control")
        try:
            assert entered.wait(5), "HTTP query did not reach the CPU worker"
            identity = executor.submit(client.get, "/auth/me").result(timeout=3)
            assert identity.status_code == 200
            assert not query.done(), "CPU control must still be held"
        finally:
            release.set()
        assert query.result(timeout=5).status_code == 503


def test_cancelled_http_request_leaves_connection_cleanup_with_the_cpu_worker(
    client: TestClient,
    unavailable_model: list[tuple[str, object]],
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    from runtime import db_lock

    entered = threading.Event()
    release = threading.Event()
    closed = threading.Event()
    owner_threads: dict[str, int] = {}
    original_connect = db_lock.connect_read

    class HeldModel(_BrokenModel):
        def encode(self, texts: list[str]) -> list[list[float]]:
            owner_threads["encode"] = threading.get_ident()
            entered.set()
            assert release.wait(10)
            return super().encode(texts)

    class TrackedConnection:
        def __init__(self, connection: Any) -> None:
            self.connection = connection

        def __getattr__(self, name: str) -> Any:
            return getattr(self.connection, name)

        def close(self) -> None:
            owner_threads["close"] = threading.get_ident()
            try:
                self.connection.close()
            finally:
                closed.set()

    def construct(_name: str, *, device: str) -> HeldModel:
        assert device == "cpu"
        owner_threads["construct"] = threading.get_ident()
        return HeldModel()

    def connect(*args: Any, **kwargs: Any) -> Any:
        connection = original_connect(*args, **kwargs)
        if threading.get_ident() == owner_threads.get("construct"):
            owner_threads["connect"] = threading.get_ident()
            return TrackedConnection(connection)
        return connection

    monkeypatch.setattr(sys.modules["sentence_transformers"], "SentenceTransformer", construct)
    monkeypatch.setattr(db_lock, "connect_read", connect)

    async def control() -> None:
        async with httpx.AsyncClient(
            transport=httpx.ASGITransport(app=client.app),
            base_url="http://testserver",
            cookies=client.cookies,
        ) as http:
            query = asyncio.create_task(http.get("/corpus/search?q=cancellation-control"))
            try:
                assert await asyncio.to_thread(entered.wait, 5)
                query.cancel()
                await asyncio.sleep(0.05)
                assert not closed.is_set(), "cancellation closed a connection still in use"
            finally:
                release.set()
                with suppress(asyncio.CancelledError):
                    await asyncio.wait_for(query, timeout=5)
            assert await asyncio.to_thread(closed.wait, 5)

    asyncio.run(control())
    assert len(set(owner_threads.values())) == 1
    assert set(owner_threads) == {"construct", "connect", "encode", "close"}


@pytest.mark.parametrize("module", ["substrate.graph.search", "processing.embedding.embed"])
def test_both_embedding_constructors_select_cpu_and_leave_mkldnn_disabled(
    monkeypatch: pytest.MonkeyPatch,
    unavailable_model: list[tuple[str, object]],
    module: str,
) -> None:
    backend = SimpleNamespace(enabled=True)
    monkeypatch.setitem(
        sys.modules, "torch", SimpleNamespace(backends=SimpleNamespace(mkldnn=backend))
    )
    provider = import_module(module).SentenceTransformerEmbedding("all-MiniLM-L6-v2")
    assert unavailable_model == [("all-MiniLM-L6-v2", "cpu")]
    assert backend.enabled is False
    assert provider.dimension == 384
    with pytest.raises(EmbeddingInferenceUnavailable, match="embedding inference failed") as failure:
        provider.encode("synthetic-inference-control")
    assert isinstance(failure.value.__cause__, RuntimeError)
    assert backend.enabled is False
