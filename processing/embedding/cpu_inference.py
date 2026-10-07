"""CPU embedding inference under the service's executable-memory restriction."""

from __future__ import annotations

from typing import Protocol, cast


class EmbeddingInferenceUnavailable(RuntimeError):
    """The configured model failed to produce a vector. No fallback was used."""


class _MKLDNNBackend(Protocol):
    enabled: bool


def configure_cpu_inference() -> None:
    """Select native PyTorch CPU kernels for the lifetime of this process.

    oneDNN can allocate executable memory for GELU. The service prohibits
    that allocation. Disabling MKLDNN keeps PyTorch's existing GELU formula
    and weights, and avoids per-request flag restoration across threads.
    """
    import torch

    cast(_MKLDNNBackend, torch.backends.mkldnn).enabled = False
