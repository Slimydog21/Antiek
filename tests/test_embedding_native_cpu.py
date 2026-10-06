"""Real CPU kernels and optional pretrained weights in disposable Linux children."""

from __future__ import annotations

import ctypes
import hashlib
import json
import math
import os
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

    from processing.embedding.embed import (
        SentenceTransformerEmbedding as ProcessingEmbedding,
    )
    from processing.embedding.embed import embedding_provider_fingerprint
    from substrate.graph.search import SentenceTransformerEmbedding as GraphEmbedding

    torch.set_num_threads(1)
    texts = [
        "Reading a paper and checking its cited evidence.",
        "The notebook stores a question for later review.",
    ]
    baseline = SentenceTransformer("all-MiniLM-L6-v2", device="cpu")
    vectors = baseline.encode(texts)
    assert vectors.shape == (2, 384)
    weights = _weights(baseline)
    revision = baseline[0].auto_model.config._commit_hash
    assert isinstance(revision, str) and revision
    # The baseline may use oneDNN. The new route must work with MDWE retained.
    libc = _enforce_mdwe()
    identities = {}
    for constructor in (GraphEmbedding, ProcessingEmbedding):
        provider = constructor()
        assert provider.dimension == 384
        assert _weights(provider._model) == weights
        assert provider._model[0].auto_model.config._commit_hash == revision
        actual = np.asarray([provider.encode(text) for text in texts])
        np.testing.assert_allclose(actual, vectors, atol=2e-6, rtol=2e-5)
        identities[constructor.__module__] = embedding_provider_fingerprint(provider)
    assert identities == {
        "substrate.graph.search": "embedding-provider-id-v1:substrate.graph.search.SentenceTransformerEmbedding:SentenceTransformerEmbedding-dim-384:384",
        "processing.embedding.embed": "embedding-provider-id-v1:sentence-transformers:all-MiniLM-L6-v2:384",
    }
    assert torch.backends.mkldnn.enabled is False
    assert libc.prctl(66, 0, 0, 0, 0) == 1
    return {
        "control": "pretrained_parity",
        "model": "all-MiniLM-L6-v2",
        "revision": revision,
        "weights_sha256": weights,
        "dimension": 384,
        "identities": identities,
        "mdwe": 1,
        "mkldnn_enabled": False,
        "torch": version("torch"),
        "transformers": version("transformers"),
        "sentence_transformers": version("sentence-transformers"),
    }


def _run_control(control: str, timeout: int, cache: Path) -> dict[str, Any]:
    cache.mkdir(mode=0o700)
    environment = os.environ.copy()
    for name in list(environment):
        if name.endswith(("API_KEY", "TOKEN", "AUTH_SECRET", "PASSWORD")):
            environment.pop(name)
    environment.update({
        "HF_HOME": str(cache), "HF_HUB_CACHE": str(cache / "hub"),
        "HF_HUB_OFFLINE": "0" if control == "pretrained" else "1",
        "TRANSFORMERS_OFFLINE": "0" if control == "pretrained" else "1",
        "PYTHONPATH": str(Path(__file__).resolve().parents[1]),
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
    if len(sys.argv) != 2 or sys.argv[1] not in controls:
        raise SystemExit("Expected one finite control: gelu or pretrained")
    if sys.argv[1] == "pretrained" and (
        os.environ.get("GITHUB_ACTIONS") != "true"
        and os.environ.get("ANTIEK_TEST_PRETRAINED_EMBEDDINGS") != "1"
    ):
        raise SystemExit("Pretrained native control is not enabled")
    print(json.dumps(controls[sys.argv[1]]()))
