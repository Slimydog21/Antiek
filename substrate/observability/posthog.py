"""Env-gated PostHog server capture — sole production import site for ``posthog``.

Bridge property ``antiek_event_id`` must match substrate jsonl ``event_id`` when both
are emitted for the same fact (see ``docs/duckdb_plane.md`` §7).

Enable:
  ANTIEK_POSTHOG_ENABLED=1
  POSTHOG_PROJECT_API_KEY=phc_…   (or POSTHOG_API_KEY)
  POSTHOG_HOST=https://eu.i.posthog.com  (optional; ingest host)

Install: ``uv sync --extra observability`` (optional dependency group).
"""

from __future__ import annotations

import os
import uuid
from typing import Any

_client: Any | None = None
_init_attempted = False


def _truthy(name: str) -> bool:
    return os.environ.get(name, "").strip().lower() in ("1", "true", "yes", "on")


def _api_key() -> str | None:
    for name in ("POSTHOG_PROJECT_API_KEY", "POSTHOG_API_KEY", "POSTHOG_PROJECT_TOKEN"):
        val = os.environ.get(name, "").strip()
        if val:
            return val
    return None


def is_enabled() -> bool:
    return _truthy("ANTIEK_POSTHOG_ENABLED") and _api_key() is not None


def _host() -> str:
    return (
        os.environ.get("POSTHOG_HOST")
        or os.environ.get("POSTHOG_INGEST_HOST")
        or "https://eu.i.posthog.com"
    ).rstrip("/")


def _client_or_none() -> Any | None:
    global _client, _init_attempted
    if not is_enabled():
        return None
    if _init_attempted:
        return _client
    _init_attempted = True
    try:
        import posthog  # tier-allow: sole shim; integrations.toml prod_call_sites
    except ImportError:
        return None
    posthog.api_key = _api_key()
    posthog.host = _host()
    _client = posthog
    return _client


def capture_distinct() -> str:
    """Stable-ish server distinct_id when no user context is available."""
    return os.environ.get("ANTIEK_POSTHOG_DISTINCT_ID", "antiek-api")


def capture(
    event: str,
    *,
    distinct_id: str | None = None,
    properties: dict[str, Any] | None = None,
    antiek_event_id: str | None = None,
) -> str | None:
    """Capture a product event. Returns ``antiek_event_id`` used (generated if omitted)."""
    ph = _client_or_none()
    if ph is None:
        return None
    eid = antiek_event_id or str(uuid.uuid4())
    props = dict(properties or {})
    props.setdefault("antiek_event_id", eid)
    props.setdefault("antiek_param_plane", "posthog_shim")
    did = distinct_id or capture_distinct()
    ph.capture(did, event, props)
    return eid


def shutdown() -> None:
    """Flush queued events (CLI / test teardown)."""
    ph = _client_or_none()
    if ph is None:
        return
    flush = getattr(ph, "flush", None)
    if callable(flush):
        flush()
    shutdown_fn = getattr(ph, "shutdown", None)
    if callable(shutdown_fn):
        shutdown_fn()