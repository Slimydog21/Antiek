"""DRW source-policy preflight — consumer of offline readiness probes.

Composes ordered, de-duplicated source packs into a receipt-bearing
preflight response driven by ``probe_source`` (PR #775). Never opens the
network, reserves budget, or launches a run.

``runner_consumes_today`` is taken from the probe (false for arxiv/Substack
until launch is wired). This module does not invent consumption claims.
"""

from __future__ import annotations

import hashlib
import os
from typing import Any

import httpx
from pydantic import BaseModel, Field

from .readiness import SourceName, SourceReadiness, probe_source

SourcePolicy = SourceName


class SourcePreflightEntry(BaseModel):
    source: SourcePolicy
    status: str
    runner_consumes_today: bool
    external_call_would_be_required: bool
    note: str
    adapter_importable: bool
    offline_probe_ok: bool


class SourcePolicyPreflight(BaseModel):
    source_receipt_id: str
    source_policy: list[SourcePolicy]
    gather_mode: str
    entries: list[SourcePreflightEntry]
    notes: list[str] = Field(default_factory=list)


def _dedupe_sources(sources: list[SourcePolicy]) -> list[SourcePolicy]:
    seen: set[str] = set()
    ordered: list[SourcePolicy] = []
    for s in sources:
        if s not in seen:
            seen.add(s)
            ordered.append(s)
    return ordered


def _entry_from_readiness(r: SourceReadiness) -> SourcePreflightEntry:
    return SourcePreflightEntry(
        source=r.source,
        status=r.status,
        runner_consumes_today=r.runner_consumes_today,
        external_call_would_be_required=r.external_call_would_be_required,
        note=r.note,
        adapter_importable=r.adapter_importable,
        offline_probe_ok=r.offline_probe_ok,
    )


def run_source_policy_preflight(
    source_policy: list[SourcePolicy],
    *,
    root_id: str | None = None,
    problem: str | None = None,
    arxiv_client: httpx.Client | None = None,
    arxiv_throttle: Any | None = None,
    substack_client: httpx.Client | None = None,
    gather_mode: str | None = None,
) -> SourcePolicyPreflight:
    """Build a no-spend preflight receipt from real readiness probes.

    Injectable clients/throttle keep tests offline. Production callers omit
    them (import/callable-only probes; no public HTTP from this function).
    """
    if not source_policy:
        raise ValueError("source_policy must be non-empty")

    ordered = _dedupe_sources(list(source_policy))
    mode = (
        gather_mode
        if gather_mode is not None
        else (os.environ.get("ANTIEK_DRW_GATHER", "stub").strip().lower() or "stub")
    )

    entries: list[SourcePreflightEntry] = []
    for source in ordered:
        readiness = probe_source(
            source,
            arxiv_client=arxiv_client if source == "arxiv" else None,
            arxiv_throttle=arxiv_throttle if source == "arxiv" else None,
            substack_client=substack_client if source == "substack" else None,
        )
        entries.append(_entry_from_readiness(readiness))

    basis = "|".join([mode, root_id or "", problem or "", *ordered])
    receipt = "srcpf-" + hashlib.sha256(basis.encode("utf-8")).hexdigest()[:16]

    return SourcePolicyPreflight(
        source_receipt_id=receipt,
        source_policy=ordered,
        gather_mode=mode,
        entries=entries,
        notes=[
            "preflight only: no connector, provider, retrieval, graph write, or budget reservation ran",
            "arxiv/Substack status from offline acquisition readiness probes "
            "(import/callable + optional MockTransport); DRW launch still separate",
            "register interfaces.research.api.source_readiness_routes on create_app when app.py is free",
        ],
    )
