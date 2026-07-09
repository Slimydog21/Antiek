"""Flatten ``dispatch.call`` trajectory events for the analytics DuckDB plane.

Single reader: :func:`substrate.event_log.events.trajectory`. Workflow
classification mirrors :mod:`substrate.coordination.cost_view` (§10 Engine).
"""

from __future__ import annotations

import os
from collections.abc import Iterable, Iterator, Mapping
from typing import Any

from substrate.coordination.workflow_taxonomy import (
    is_remote_exec_provider,
    workflow_for_role,
)
from substrate.event_log.events import default_events_dir
from substrate.event_log.events import trajectory as _trajectory
from substrate.schemas.events import ActionType


def _investigation_ids(events_dir: str) -> list[str]:
    if not os.path.isdir(events_dir):
        return []
    ids: list[str] = []
    for fn in sorted(os.listdir(events_dir)):
        if fn.endswith(".jsonl"):
            ids.append(fn[: -len(".jsonl")])
        elif fn.endswith(".parquet"):
            ids.append(fn[: -len(".parquet")])
    return sorted(set(ids))


def iter_dispatch_call_rows(
    *,
    events_dir: str | None = None,
    investigation_ids: Iterable[str] | None = None,
) -> Iterator[dict[str, Any]]:
    """Yield one dict per ``dispatch.call`` suitable for Parquet / DuckDB load."""
    resolved = events_dir or default_events_dir()
    dispatch = ActionType.DISPATCH_CALL.value
    ids = list(investigation_ids) if investigation_ids is not None else _investigation_ids(resolved)

    seen: set[str] = set()
    for iid in ids:
        if iid in seen:
            continue
        seen.add(iid)
        for row in _trajectory(iid, events_dir=resolved):
            if row.get("action_type") != dispatch:
                continue
            raw_payload = row.get("payload")
            payload: Mapping[str, Any] = (
                raw_payload if isinstance(raw_payload, dict) else {}
            )

            role = payload.get("target_role") or row.get("role")
            provider = payload.get("provider")
            wf = workflow_for_role(role if isinstance(role, str) else None)

            yield {
                "event_id": row.get("event_id"),
                "investigation_id": row.get("investigation_id") or iid,
                "synthesis_id": row.get("synthesis_id"),
                "phase": row.get("phase"),
                "role": row.get("role"),
                "policy_id": row.get("policy_id"),
                "param_version": row.get("param_version"),
                "emitted_at": row.get("emitted_at"),
                "workflow": wf.value,
                "target_role": payload.get("target_role"),
                "provider": provider,
                "model": payload.get("model"),
                "tier": payload.get("tier"),
                "input_tokens": payload.get("input_tokens"),
                "output_tokens": payload.get("output_tokens"),
                "cost_usd": payload.get("cost_usd"),
                "latency_ms": payload.get("latency_ms"),
                "nd_session_id": payload.get("nd_session_id"),
                "nd_recommended_provider": payload.get("nd_recommended_provider"),
                "nd_recommended_model": payload.get("nd_recommended_model"),
                "nd_tradeoff": payload.get("nd_tradeoff"),
                "nd_decision_latency_ms": payload.get("nd_decision_latency_ms"),
                "nd_bypassed": payload.get("nd_bypassed", False),
                "nd_bypass_reason": payload.get("nd_bypass_reason"),
                "is_remote_exec": is_remote_exec_provider(
                    provider if isinstance(provider, str) else None
                ),
                "context_pack_event_id": payload.get("context_pack_event_id"),
            }
