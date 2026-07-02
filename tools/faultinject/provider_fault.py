"""Dispatch provider-call fault injector."""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Literal

from substrate.dispatch import router
from substrate.dispatch.base import ProviderError

ProviderFaultKind = Literal["503", "timeout"]


@dataclass
class ProviderFaultInjector:
    """Patch one registered provider's ``.call`` method, leaving routing intact."""

    provider: str
    kind: ProviderFaultKind
    fail_on_call: int = 1
    name: str = "provider_fault"
    calls: int = 0
    _provider_obj: Any = field(default=None, init=False, repr=False)
    _original_call: Any = field(default=None, init=False, repr=False)
    _armed: bool = field(default=False, init=False, repr=False)

    def __post_init__(self) -> None:
        if self.kind not in ("503", "timeout"):
            raise ValueError("kind must be '503' or 'timeout'")
        if self.fail_on_call < 1:
            raise ValueError("fail_on_call must be >= 1")

    def install(self) -> None:
        if self._armed:
            return
        provider_obj = router.get_provider(self.provider)
        self.calls = 0
        self._provider_obj = provider_obj
        self._original_call = provider_obj.call
        original_call = self._original_call
        injector = self

        def guarded_call(*args: Any, **kwargs: Any) -> Any:
            injector.calls += 1
            if injector.calls == injector.fail_on_call:
                model = str(kwargs.get("model") or "<unknown>")
                if injector.kind == "503":
                    raise ProviderError(
                        f"{injector.provider}: HTTP 503 - injected provider fault",
                        provider=injector.provider,
                        model=model,
                        latency_ms=0,
                        retryable=True,
                        request_id="faultinject-503",
                    )
                raise ProviderError(
                    f"{injector.provider}: request timeout - injected provider fault",
                    provider=injector.provider,
                    model=model,
                    latency_ms=0,
                    retryable=True,
                    request_id="faultinject-timeout",
                )
            return original_call(*args, **kwargs)

        provider_obj.call = guarded_call
        self._armed = True

    def uninstall(self) -> None:
        if not self._armed:
            return
        self._provider_obj.call = self._original_call
        self._provider_obj = None
        self._original_call = None
        self._armed = False


def provider_fault(
    *,
    provider: str,
    kind: ProviderFaultKind,
    fail_on_call: int = 1,
) -> ProviderFaultInjector:
    return ProviderFaultInjector(
        provider=provider,
        kind=kind,
        fail_on_call=fail_on_call,
    )
