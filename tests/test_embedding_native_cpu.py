"""Real CPU kernels and optional pretrained weights in disposable Linux children."""

from __future__ import annotations

import ctypes
import hashlib
import json
import math
import os
import stat
import subprocess
import sys
from importlib.metadata import version
from pathlib import Path
from typing import Any

import pytest


def _enforce_mdwe() -> Any:
    libc = ctypes.CDLL(None, use_errno=True)
    assert libc.prctl(65, ctypes.c_ulong(1), 0, 0, 0) == 0, ctypes.get_errno()
    assert libc.prctl(66, 0, 0, 0, 0) == 1
    libc.mmap.restype = ctypes.c_void_p
    libc.mmap.argtypes = [
        ctypes.c_void_p,
        ctypes.c_size_t,
        ctypes.c_int,
        ctypes.c_int,
        ctypes.c_int,
        ctypes.c_long,
    ]
    libc.mprotect.argtypes = [ctypes.c_void_p, ctypes.c_size_t, ctypes.c_int]
    libc.munmap.argtypes = [ctypes.c_void_p, ctypes.c_size_t]
    address = libc.mmap(None, 4096, 3, 0x22, -1, 0)
    assert address not in (None, ctypes.c_void_p(-1).value)
    try:
        assert libc.mprotect(address, 4096, 5) == -1, "writable memory became executable"
    finally:
        assert libc.munmap(address, 4096) == 0
    return libc


def _weights(model: Any) -> str:
    digest = hashlib.sha256()
    for name, tensor in sorted(model.state_dict().items()):
        digest.update(name.encode())
        digest.update(str((tensor.dtype, tuple(tensor.shape))).encode())
        digest.update(tensor.detach().cpu().contiguous().numpy().tobytes())
    return digest.hexdigest()


def _gelu_control() -> dict[str, Any]:
    import torch
    from torch.nn import functional as functional

    from processing.embedding.cpu_inference import configure_cpu_inference

    torch.set_num_threads(1)
    values = torch.linspace(-5, 5, 4096, dtype=torch.float32)
    expected = torch.tensor([0.5 * x * (1 + math.erf(x / math.sqrt(2))) for x in values.tolist()])
    libc = _enforce_mdwe()
    torch.backends.mkldnn.enabled = True
    baseline_error = None
    try:
        functional.gelu(values, approximate="none")
    except RuntimeError as exc:
        baseline_error = str(exc)
    configure_cpu_inference()
    actual = functional.gelu(values, approximate="none")
    torch.testing.assert_close(actual, expected, atol=1e-6, rtol=1e-6)
    assert torch.backends.mkldnn.enabled is False
    assert libc.prctl(66, 0, 0, 0, 0) == 1
    return {
        "control": "native_gelu",
        "mdwe": 1,
        "mkldnn_enabled": False,
        "baseline_runtime_error": baseline_error,
        "max_absolute_error": float((actual - expected).abs().max()),
        "torch": version("torch"),
    }


def _pretrained_control() -> dict[str, Any]:
    import numpy as np
    import torch
    from sentence_transformers import SentenceTransformer

    torch.set_num_threads(1)
    texts = [
        "Reading a paper and checking its cited evidence.",
        "The notebook stores a question for later review.",
    ]
    baseline = SentenceTransformer("all-MiniLM-L6-v2", device="cpu")
    vectors = baseline.encode(texts)
    assert vectors.shape == (2, 384)
    assert np.isfinite(vectors).all()
    weights = _weights(baseline)
    revision = baseline[0].auto_model.config._commit_hash
    assert isinstance(revision, str) and revision
    evidence = {
        "weights_sha256": weights, "revision": revision,
        "texts": texts, "vectors": vectors.tolist(),
    }
    encoded = json.dumps(evidence).encode()
    assert len(encoded) <= 65536
    path = Path(os.environ["HF_HOME"]) / "observed-baseline.json"
    fd = os.open(path, os.O_WRONLY | os.O_CREAT | os.O_EXCL | os.O_NOFOLLOW, 0o600)
    try:
        assert os.write(fd, encoded) == len(encoded)
        os.fsync(fd)
    finally:
        os.close(fd)
    # The new process inherits MDWE before Python/model startup, with no
    # warmed model kernels. Only the private weight cache is reused offline.
    libc = _enforce_mdwe()
    environment = os.environ.copy()
    environment.update({"HF_HUB_OFFLINE": "1", "TRANSFORMERS_OFFLINE": "1"})
    result = subprocess.run(
        [sys.executable, str(Path(__file__).resolve()), "pretrained-cold", str(path), hashlib.sha256(encoded).hexdigest()],
        env=environment, capture_output=True, text=True, timeout=120, check=False,
    )
    assert result.returncode == 0, result.stdout + result.stderr
    cold = json.loads(result.stdout.strip().splitlines()[-1])
    assert cold["weights_sha256"] == weights and cold["revision"] == revision
    assert libc.prctl(66, 0, 0, 0, 0) == 1
    return {
        "control": "pretrained_parity", "model": "all-MiniLM-L6-v2",
        "revision": revision, "weights_sha256": weights, "dimension": 384,
        "cold_child": cold, "mdwe": 1,
        "torch": version("torch"), "transformers": version("transformers"),
        "sentence_transformers": version("sentence-transformers"),
    }


def _pretrained_cold_control(path: str, expected_sha256: str) -> dict[str, Any]:
    expected_path = Path(os.environ["HF_HOME"]) / "observed-baseline.json"
    assert Path(path) == expected_path
    fd = os.open(expected_path, os.O_RDONLY | os.O_NOFOLLOW)
    try:
        metadata = os.fstat(fd)
        assert stat.S_ISREG(metadata.st_mode) and metadata.st_size <= 65536
        encoded = os.read(fd, 65537)
        assert hashlib.sha256(encoded).hexdigest() == expected_sha256
        evidence = json.loads(encoded)
    finally:
        os.close(fd)
    libc = _enforce_mdwe()
    import numpy as np
    import torch

    from processing.embedding.embed import (
        SentenceTransformerEmbedding as ProcessingEmbedding,
    )
    from processing.embedding.embed import embedding_provider_fingerprint
    from substrate.graph.search import SentenceTransformerEmbedding as GraphEmbedding

    torch.set_num_threads(1)
    assert os.environ["HF_HUB_OFFLINE"] == "1"
    vectors = np.asarray(evidence["vectors"])
    assert vectors.shape == (2, 384) and np.isfinite(vectors).all()
    identities = {}
    maximum_error = 0.0
    assert GraphEmbedding is ProcessingEmbedding
    for port, constructor in (
        ("substrate.graph.search", GraphEmbedding),
        ("processing.embedding.embed", ProcessingEmbedding),
    ):
        provider = constructor()
        assert provider.dimension == 384
        assert _weights(provider._model) == evidence["weights_sha256"]
        assert provider._model[0].auto_model.config._commit_hash == evidence["revision"]
        actual = np.asarray([provider.encode(text) for text in evidence["texts"]])
        assert np.isfinite(actual).all()
        np.testing.assert_allclose(actual, vectors, atol=2e-6, rtol=2e-5)
        maximum_error = max(maximum_error, float(np.abs(actual - vectors).max()))
        identities[port] = embedding_provider_fingerprint(provider)
    assert identities == {
        "substrate.graph.search": "embedding-provider-id-v1:sentence-transformers:all-MiniLM-L6-v2:384",
        "processing.embedding.embed": "embedding-provider-id-v1:sentence-transformers:all-MiniLM-L6-v2:384",
    }
    corpus = _native_corpus_round_trip(provider, evidence["texts"][0])
    assert torch.backends.mkldnn.enabled is False
    assert libc.prctl(66, 0, 0, 0, 0) == 1
    return {
        "control": "cold_pretrained_parity",
        "model": "all-MiniLM-L6-v2",
        "revision": evidence["revision"],
        "weights_sha256": evidence["weights_sha256"],
        "dimension": 384,
        "identities": identities,
        "corpus_round_trip": corpus,
        "mdwe": 1,
        "mkldnn_enabled": False,
        "max_absolute_error": maximum_error,
        "torch": version("torch"),
        "transformers": version("transformers"),
        "sentence_transformers": version("sentence-transformers"),
    }


def _native_corpus_round_trip(producer: Any, text: str) -> dict[str, Any]:
    from fastapi.testclient import TestClient

    from interfaces.research.api.app import create_app
    from processing.embedding import embedding_provider_fingerprint
    from runtime.db_lock import connect_read, connect_write
    from substrate.auth import mint_session_cookie
    from substrate.graph import insert_chunk, insert_document
    from substrate.graph.schema import init_database_at_path
    from substrate.graph.search import SentenceTransformerEmbedding, search

    path = os.environ["ANTIEK_DUCKDB_PATH"]
    init_database_at_path(path)
    with connect_write(path, purpose="native-canonical-search-control") as con:
        insert_document(
            con, document_id="native-canonical-control", title="Native evidence control",
            source_tier=4, document_type="article", content_class="user_owned",
            owner_user_id="__operator__", raw_text=text,
        )
        insert_chunk(
            con, document_id="native-canonical-control", chunk_index=0,
            text=text, section_path="Page 2", embedding=producer.encode(text),
            embedding_provider=producer,
        )
    con = connect_read(path)
    try:
        before = con.execute("SELECT * FROM embeddings_meta").fetchall()
        vectors = con.execute("SELECT chunk_id, embedding FROM chunks").fetchall()
        query = SentenceTransformerEmbedding()
        result = search(con, text, model=query, policy_tag="private_research")
        assert [r["document_id"] for r in result["results"]] == ["native-canonical-control"]
        assert result["results"][0]["similarity"] == pytest.approx(1.0, abs=1e-4)
        assert embedding_provider_fingerprint(query) == embedding_provider_fingerprint(producer)
    finally:
        con.close()
    app = create_app(
        register_wrestling=False, register_providers=False,
        cors_origins=["https://antiek.ai"],
    )
    with TestClient(app) as client:
        client.cookies.set(
            "ANTIEK_SESSION",
            mint_session_cookie(user_id="__operator__", email=os.environ["ANTIEK_OPERATOR_EMAIL"]),
        )
        assert client.get("/auth/me").status_code == 200
        response = client.get("/corpus/search", params={"q": text}, headers={"Origin": "https://antiek.ai"})
        assert response.status_code == 200, response.text
        body = response.json()
        assert body["count"] == 1 and body["query"] == text
        assert body["hits"][0]["document_id"] == "native-canonical-control"
        assert body["hits"][0]["snippet"] == text
        assert body["hits"][0]["page_index"] == 1
        assert body["hits"][0]["page_resolved"] is True
        assert response.headers["access-control-allow-origin"] == "https://antiek.ai"
    con = connect_read(path)
    try:
        assert con.execute("SELECT * FROM embeddings_meta").fetchall() == before
        assert con.execute("SELECT chunk_id, embedding FROM chunks").fetchall() == vectors
    finally:
        con.close()
    return {
        "stored_fingerprint": embedding_provider_fingerprint(producer),
        "query_fingerprint": embedding_provider_fingerprint(query),
        "direct_hits": 1, "signed_http_status": response.status_code,
        "http_hits": body["count"], "vectors_and_metadata_unchanged": True,
        "live_or_ordinary_account_proof": False,
    }


def _run_control(control: str, timeout: int, cache: Path) -> dict[str, Any]:
    cache.mkdir(mode=0o700)
    environment = os.environ.copy()
    canonical = environment.get("ANTIEK_CANONICAL_REAL_DUCKDB") or os.path.realpath(
        os.path.expanduser("~/.antiek/research_graph.duckdb")
    )
    pretrained_admitted = environment.get("ANTIEK_TEST_PRETRAINED_EMBEDDINGS")
    for name in list(environment):
        if name.startswith("ANTIEK_") or name.endswith(("API_KEY", "TOKEN", "SECRET", "PASSWORD")):
            environment.pop(name)
    if pretrained_admitted == "1":
        environment["ANTIEK_TEST_PRETRAINED_EMBEDDINGS"] = pretrained_admitted
    private = cache / "antiek"
    private.mkdir(mode=0o700)
    for name, relative in {
        "ANTIEK_HOME": "home", "ANTIEK_DUCKDB_PATH": "graph.duckdb",
        "ANTIEK_STATE_DIR": "state", "ANTIEK_RESEARCH_EVENTS_DIR": "events",
        "ANTIEK_ACCOUNT_STORE": "accounts.json", "ANTIEK_PASSKEY_STORE": "passkeys.json",
        "ANTIEK_USER_MODELS_PATH": "models.json", "ANTIEK_BYOK_ARTIFACT": "credentials.enc",
        "ANTIEK_BYOK_KEY_FILE": "master.key", "ANTIEK_ARXIV_THROTTLE_PATH": "arxiv.json",
        "ANTIEK_ARXIV_GOVERNOR_LOCK_PATH": "arxiv.lock", "ANTIEK_BAN_EVENT_LOG_PATH": "bans.jsonl",
    }.items():
        environment[name] = str(private / relative)
    environment.update({
        "ANTIEK_CANONICAL_REAL_DUCKDB": canonical,
        "ANTIEK_ENFORCE_TEST_STORE_ISOLATION": "1",
        "ANTIEK_OPERATOR_EMAIL": "native-canonical@example.invalid",
        "ANTIEK_AUTH_SECRET": "synthetic-native-canonical-control-secret",
        "ANTIEK_PUBLIC_SIGNUP_ENABLED": "0",
        "HF_HOME": str(cache), "HF_HUB_CACHE": str(cache / "hub"),
        "HF_HUB_OFFLINE": "0" if control == "pretrained" else "1",
        "TRANSFORMERS_OFFLINE": "0" if control == "pretrained" else "1",
        "PYTHONPATH": str(Path(__file__).resolve().parents[1]),
        "HF_TOKEN_PATH": str(cache / "unused-token"), "HF_HUB_DISABLE_IMPLICIT_TOKEN": "1",
        "XDG_CACHE_HOME": str(cache / "xdg"), "TORCH_HOME": str(cache / "torch"),
        "OMP_NUM_THREADS": "1", "MKL_NUM_THREADS": "1", "OPENBLAS_NUM_THREADS": "1",
    })
    result = subprocess.run(
        [sys.executable, str(Path(__file__).resolve()), control],
        capture_output=True,
        text=True,
        timeout=timeout,
        check=False,
        env=environment,
    )
    assert result.returncode == 0, result.stdout + result.stderr
    payload: dict[str, Any] = json.loads(result.stdout.strip().splitlines()[-1])
    print(json.dumps(payload, sort_keys=True))
    return payload


@pytest.mark.skipif(sys.platform != "linux", reason="Linux PR_SET_MDWE control")
def test_native_gelu_retains_formula_under_enforced_mdwe(tmp_path: Path) -> None:
    assert _run_control("gelu", 60, tmp_path / "gelu-cache")["mdwe"] == 1


@pytest.mark.skipif(
    sys.platform != "linux" or (
        os.environ.get("GITHUB_ACTIONS") != "true"
        and os.environ.get("ANTIEK_TEST_PRETRAINED_EMBEDDINGS") != "1"
    ),
    reason="Pretrained download runs in normal CI or an explicitly admitted native control",
)
def test_real_pretrained_weights_vectors_dimensions_and_fingerprints_match(tmp_path: Path) -> None:
    assert _run_control("pretrained", 300, tmp_path / "pretrained-cache")["dimension"] == 384


if __name__ == "__main__":
    controls = {"gelu": _gelu_control, "pretrained": _pretrained_control}
    cold = len(sys.argv) == 4 and sys.argv[1] == "pretrained-cold"
    if not cold and (len(sys.argv) != 2 or sys.argv[1] not in controls):
        raise SystemExit("Expected one finite control: gelu or pretrained")
    if sys.argv[1] in {"pretrained", "pretrained-cold"} and (
        os.environ.get("GITHUB_ACTIONS") != "true"
        and os.environ.get("ANTIEK_TEST_PRETRAINED_EMBEDDINGS") != "1"
    ):
        raise SystemExit("Pretrained native control is not enabled")
    print(json.dumps(_pretrained_cold_control(sys.argv[2], sys.argv[3]) if cold else controls[sys.argv[1]]()))
