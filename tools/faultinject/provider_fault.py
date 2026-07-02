"""Provider-fault injector — force a 503 or a timeout at the dispatch seam.

The router (``substrate/dispatch/router.py``) resolves a tier to a provider,
calls ``provider.call(...)``, and on a raised ``ProviderError`` walks the tier's
fallback chain. To test that fallback + failure handling we force the fault at
the *real* seam: the registered provider instance's ``.call`` method (looked up
via ``router.get_provider``) is replaced for the duration of the block with one
that raises the real ``ProviderError`` the router already knows how to handle.

This does NOT touch routing, does NOT register or unregister a provider, and
does NOT add a dispatch provider (§16). It only makes an *already-registered*
provider's call raise — exactly what a 503 or a timeout from that upstream would
do. The original ``.call`` is restored on teardown.

The provider must already be registered (a test registers a stub, or the app's
``register_default_providers`` ran). Looking up an unregistered name raises
``KeyError`` loudly rather than silently no-op'ing — an un-armed fault is worse
than a loud misconfiguration.
"""

from __future__ import annotations

import threading
from collections.abc import Iterator
from contextlib import contextmanager
from typing import Any

from .inject import _CallGate

__all__ = ["provider_fault"]

_VALID_KINDS = ("503", "timeout")

# A provider's .call is patched in place, so only one fault may be armed on a
# given provider at a time — a second concurrent/nested arm on the same provider
# would corrupt the .call restore. Faults on DIFFERENT providers are independent.
_ARM_LOCK = threading.Lock()
_armed_providers: set[str] = set()


@contextmanager
def provider_fault(
    kind: str = "503",
    *,
    provider: str,
    model: str = "<injected>",
    fail_on_call: int | None = None,
) -> Iterator[None]:
    """Arm a ``kind`` fault (``"503"`` or ``"timeout"``) on the registered
    ``provider``'s ``.call``. See :class:`tools.faultinject.inject._CallGate`
    for ``fail_on_call`` semantics."""
    if kind not in _VALID_KINDS:
        raise ValueError(f"kind must be one of {_VALID_KINDS}, got {kind!r}")

    # Lazy imports keep `import tools.faultinject` side-effect-free.
    from substrate.dispatch.base import ProviderError
    from substrate.dispatch.router import get_provider

    prov = get_provider(provider)  # KeyError if not registered — surface loudly
    with _ARM_LOCK:
        if provider in _armed_providers:
            raise RuntimeError(
                f"provider_fault is already armed on provider {provider!r}. "
                "Arm one fault per provider at a time (nested/concurrent arming "
                "on the same provider would corrupt the .call restore)."
            )
        _armed_providers.add(provider)
    gate = _CallGate(fail_on_call)
    original_call = prov.call
    # Whether the instance already shadowed the class method (so we restore
    # correctly rather than leaving an instance attribute behind).
    had_own_call = "call" in vars(prov)

    def _faulted_call(*args: Any, **kwargs: Any):
        if not gate.should_fault():
            return original_call(*args, **kwargs)
        model_arg = kwargs.get("model", model)
        if kind == "503":
            raise ProviderError(
                f"{provider}: HTTP 503 — injected by faultinject",
                provider=provider,
                model=model_arg,
                latency_ms=0,
                retryable=True,
            )
        raise ProviderError(
            f"{provider}: request timeout — injected by faultinject",
            provider=provider,
            model=model_arg,
            latency_ms=0,
            retryable=True,
        )

    prov.call = _faulted_call  # type: ignore[method-assign]
    try:
        yield
    finally:
        if had_own_call:
            prov.call = original_call  # type: ignore[method-assign]
        else:
            # Remove the instance attribute we added, revealing the class method.
            try:
                del prov.call
            except AttributeError:
                prov.call = original_call  # type: ignore[method-assign]
        with _ARM_LOCK:
            _armed_providers.discard(provider)
