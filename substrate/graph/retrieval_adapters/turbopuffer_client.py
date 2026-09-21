"""Lazy official-SDK boundary for the Turbopuffer shadow benchmark."""

from __future__ import annotations

from collections.abc import Iterable
from typing import Any, Protocol, cast


class ShadowNamespace(Protocol):
    def write(self, **kwargs: Any) -> Any: ...
    def query(self, **kwargs: Any) -> Any: ...
    def multi_query(self, **kwargs: Any) -> Any: ...

    def metadata(self, **kwargs: Any) -> Any: ...


def make_namespace(*, api_key: str, region: str, namespace: str) -> ShadowNamespace:
    try:
        import turbopuffer
    except ImportError as exc:
        raise RuntimeError("install the turbopuffer_shadow extra") from exc
    client = turbopuffer.Turbopuffer(api_key=api_key, region=region, timeout=30.0,
                                     max_retries=2)
    return cast(ShadowNamespace, client.namespace(namespace))


def response_rows(response: Any) -> Iterable[Any]:
    results = getattr(response, "results", None)
    if not results:
        return ()
    return getattr(results[0], "rows", ()) or ()
