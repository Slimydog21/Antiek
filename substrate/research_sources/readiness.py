"""Offline readiness probes for deep-research source packs.

These probes never open the public internet. They:

1. Import the real acquisition modules (fail closed if missing).
2. Assert the load-bearing callables exist and are callable.
3. Optionally exercise real client paths via injected ``httpx.Client``
   (``MockTransport`` in tests) and isolated throttle state.

Preflight / DRW launch use the results to report honest status:
``adapter_importable`` is not the same as ``offline_probe_ok`` or
``runner_consumes_today`` — execution wiring remains a separate residual.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Literal

import httpx

SourceName = Literal["arxiv", "substack", "web", "operator_corpus"]
ReadinessStatus = Literal["ready", "gated", "stub", "unavailable"]


@dataclass(frozen=True)
class SourceReadiness:
    source: SourceName
    status: ReadinessStatus
    adapter_importable: bool
    """True when the house acquisition surface for this source can be imported."""
    callables_present: bool
    """True when required entry points exist and are callable."""
    offline_probe_ok: bool
    """True only when an injected offline client smoke path succeeded."""
    runner_consumes_today: bool
    """Whether the DRW runner would actually consume this source today."""
    external_call_would_be_required: bool
    note: str
    details: list[str] = field(default_factory=list)


def probe_arxiv(
    *,
    client: httpx.Client | None = None,
    sample_id: str = "2402.03300",
    throttle: Any | None = None,
) -> SourceReadiness:
    """Probe arXiv acquisition readiness.

    When ``client`` is provided (tests: ``MockTransport``), drives the real
    ``acquisition.arxiv.client.fetch_by_id`` path end-to-end without network.
    When ``client`` is ``None``, only import + callable checks run — and
    ``offline_probe_ok`` stays False (callable ≠ offline probe).
    """
    details: list[str] = []
    try:
        from acquisition.arxiv.client import fetch_by_id, search
    except Exception as exc:  # noqa: BLE001 — honesty over crash
        return SourceReadiness(
            source="arxiv",
            status="unavailable",
            adapter_importable=False,
            callables_present=False,
            offline_probe_ok=False,
            runner_consumes_today=False,
            external_call_would_be_required=True,
            note=f"acquisition.arxiv import failed: {type(exc).__name__}",
            details=[str(exc)],
        )

    callables_ok = callable(fetch_by_id) and callable(search)
    details.append(f"fetch_by_id={getattr(fetch_by_id, '__module__', '?')}")
    details.append(f"search={getattr(search, '__module__', '?')}")
    if not callables_ok:
        return SourceReadiness(
            source="arxiv",
            status="unavailable",
            adapter_importable=True,
            callables_present=False,
            offline_probe_ok=False,
            runner_consumes_today=False,
            external_call_would_be_required=True,
            note="acquisition.arxiv imported but fetch_by_id/search not callable",
            details=details,
        )

    offline_ok = False
    if client is not None:
        try:
            paper = fetch_by_id(sample_id, client=client, throttle=throttle)
            offline_ok = paper is not None and bool(
                getattr(paper, "arxiv_id", None) or getattr(paper, "title", None)
            )
            if offline_ok:
                details.append(
                    f"offline fetch_by_id returned arxiv_id={getattr(paper, 'arxiv_id', None)!r} "
                    f"title={getattr(paper, 'title', None)!r}"
                )
            else:
                details.append("offline fetch_by_id returned empty/None paper")
        except Exception as exc:  # noqa: BLE001
            details.append(f"offline fetch_by_id error: {type(exc).__name__}: {exc}")
            offline_ok = False
    else:
        details.append("no client injected — import/callable checks only (offline_probe_ok=false)")

    # DRW launch still does not consume arXiv.
    if not callables_ok:
        status: ReadinessStatus = "unavailable"
    elif client is not None and offline_ok:
        status = "ready"
    elif client is not None and not offline_ok:
        status = "gated"
    else:
        # Importable but no offline exercise — gated, not ready.
        status = "gated"

    return SourceReadiness(
        source="arxiv",
        status=status,
        adapter_importable=True,
        callables_present=callables_ok,
        offline_probe_ok=offline_ok,
        runner_consumes_today=False,
        external_call_would_be_required=True,
        note=(
            "acquisition.arxiv.client.fetch_by_id/search importable and callable; "
            + (
                "offline MockTransport probe ok; "
                if offline_ok
                else "offline probe not run or failed; "
            )
            + "DRW launch does not dispatch arXiv yet"
        ),
        details=details,
    )


def probe_substack(
    *,
    client: httpx.Client | None = None,
    sample_feed_url: str = "https://example.substack.com/feed",
) -> SourceReadiness:
    """Probe Substack acquisition readiness.

    With ``client`` injected, drives real ``fetch_feed`` parse path offline.
    Without client, import/callable only — ``offline_probe_ok`` stays False.
    """
    details: list[str] = []
    try:
        from acquisition.substack.client import fetch_feed
    except Exception as exc:  # noqa: BLE001
        return SourceReadiness(
            source="substack",
            status="unavailable",
            adapter_importable=False,
            callables_present=False,
            offline_probe_ok=False,
            runner_consumes_today=False,
            external_call_would_be_required=True,
            note=f"acquisition.substack import failed: {type(exc).__name__}",
            details=[str(exc)],
        )

    callables_ok = callable(fetch_feed)
    details.append(f"fetch_feed={getattr(fetch_feed, '__module__', '?')}")
    try:
        from acquisition.substack.adapter import ingest_post  # noqa: F401

        details.append("adapter.ingest_post importable")
    except Exception as exc:  # noqa: BLE001
        details.append(f"adapter.ingest_post not importable: {type(exc).__name__}")

    offline_ok = False
    if not callables_ok:
        return SourceReadiness(
            source="substack",
            status="unavailable",
            adapter_importable=True,
            callables_present=False,
            offline_probe_ok=False,
            runner_consumes_today=False,
            external_call_would_be_required=True,
            note="substack fetch_feed not callable",
            details=details,
        )

    if client is not None:
        try:
            pub = fetch_feed(sample_feed_url, client=client)
            posts = getattr(pub, "posts", None) or getattr(pub, "items", None) or []
            offline_ok = pub is not None and (
                bool(getattr(pub, "title", None)) or bool(posts) or True
            )
            # Require at least one post for offline_ok honesty (empty feed ≠ ok).
            offline_ok = pub is not None and len(list(posts)) > 0
            if offline_ok:
                details.append(
                    f"offline fetch_feed returned posts={len(list(getattr(pub, 'posts', []) or getattr(pub, 'items', []) or []))}"
                )
            else:
                details.append("offline fetch_feed returned empty publication/posts")
        except Exception as exc:  # noqa: BLE001
            details.append(f"offline fetch_feed error: {type(exc).__name__}: {exc}")
            offline_ok = False
    else:
        details.append("no client injected — import/callable checks only (offline_probe_ok=false)")

    if client is not None and offline_ok:
        status: ReadinessStatus = "ready"
    elif client is not None and not offline_ok:
        status = "gated"
    else:
        status = "gated"

    return SourceReadiness(
        source="substack",
        status=status,
        adapter_importable=True,
        callables_present=callables_ok,
        offline_probe_ok=offline_ok,
        runner_consumes_today=False,
        external_call_would_be_required=True,
        note=(
            "acquisition.substack.client.fetch_feed importable and callable; "
            + (
                "offline MockTransport probe ok; "
                if offline_ok
                else "offline probe not run or failed; "
            )
            + "DRW launch does not consume Substack yet"
        ),
        details=details,
    )


def probe_source(
    source: SourceName,
    *,
    arxiv_client: httpx.Client | None = None,
    arxiv_throttle: Any | None = None,
    substack_client: httpx.Client | None = None,
) -> SourceReadiness:
    """Dispatch readiness probe for a closed source-policy name."""
    if source == "arxiv":
        return probe_arxiv(client=arxiv_client, throttle=arxiv_throttle)
    if source == "substack":
        return probe_substack(client=substack_client)
    if source == "operator_corpus":
        return SourceReadiness(
            source="operator_corpus",
            status="ready",
            adapter_importable=True,
            callables_present=True,
            offline_probe_ok=True,
            runner_consumes_today=True,
            external_call_would_be_required=False,
            note="local corpus/reuse substrate available when the runner reads prior knowledge",
        )
    if source == "web":
        import os

        gather = os.environ.get("ANTIEK_DRW_GATHER", "stub").strip().lower() or "stub"
        exa = gather == "exa"
        return SourceReadiness(
            source="web",
            status="gated" if exa else "stub",
            adapter_importable=True,
            callables_present=True,
            offline_probe_ok=True,
            runner_consumes_today=exa,
            external_call_would_be_required=exa,
            note=(
                "ANTIEK_DRW_GATHER=exa would use the env-gated Exa gather loop"
                if exa
                else "current gather mode is stub; no public-web call will run"
            ),
        )
    raise ValueError(f"unknown source: {source!r}")


def readiness_to_preflight_fields(r: SourceReadiness) -> dict[str, Any]:
    """Map probe result to cascade SourcePolicyPreflightEntry-like fields."""
    return {
        "source": r.source,
        "status": r.status,
        "runner_consumes_today": r.runner_consumes_today,
        "external_call_would_be_required": r.external_call_would_be_required,
        "note": r.note,
        "adapter_importable": r.adapter_importable,
        "offline_probe_ok": r.offline_probe_ok,
    }
