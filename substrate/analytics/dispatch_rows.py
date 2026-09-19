"""Flatten ``dispatch.call`` trajectory events for the analytics DuckDB plane.

Single reader: :func:`substrate.event_log.events.trajectory`. Workflow
classification mirrors :mod:`substrate.coordination.cost_view` (§10 Engine).
"""

from __future__ import annotations

from collections.abc import Iterable, Iterator, Mapping
from typing import Any

from substrate.coordination.workflow_taxonomy import (
    is_remote_exec_provider,
    workflow_for_role,
)
from substrate.event_log import trajectory_authorized
from substrate.investigation_streams import (
    list_authorized_investigation_ids,
    list_operator_investigation_authorities,
)
from substrate.investigation_tenancy import InvestigationAuthority
from substrate.schemas.events import ActionType


def iter_dispatch_call_rows(
    *,
    authority: InvestigationAuthority,
    investigation_ids: Iterable[str] | None = None,
    global_scope: bool = False,
) -> Iterator[dict[str, Any]]:
    """Yield one dict per ``dispatch.call`` suitable for Parquet / DuckDB load."""
    dispatch = ActionType.DISPATCH_CALL.value
    stream_authorities = (
        list_operator_investigation_authorities(authority)
        if global_scope
        else [
            InvestigationAuthority(authority.account_id, iid, authority.root)
            for iid in list_authorized_investigation_ids(
                authority.account_id,
                root=authority.root,
            )
        ]
    )
    selected_ids = set(investigation_ids) if investigation_ids is not None else None
    stream_authorities = [
        item
        for item in stream_authorities
        if selected_ids is None or item.investigation_id in selected_ids
    ]

    seen: set[tuple[str, str]] = set()
    for stream_authority in stream_authorities:
        stream_identity = (
            stream_authority.account_id,
            stream_authority.investigation_id,
        )
        if stream_identity in seen:
            continue
        seen.add(stream_identity)
        iid = stream_authority.investigation_id
        for row in trajectory_authorized(stream_authority):
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
                "finish_reason": payload.get("finish_reason"),
                "is_remote_exec": is_remote_exec_provider(
                    provider if isinstance(provider, str) else None
                ),
                "context_pack_event_id": payload.get("context_pack_event_id"),
            }
