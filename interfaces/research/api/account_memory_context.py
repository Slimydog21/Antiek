"""Owner-private account memory at the thought-partner boundary: read and write-back.

This boundary deliberately accepts only middleware-authenticated request state.
Recall uses ``connect_write`` because the memory store requires the canonical
locked connection even for reads; the context manager is exited before the
rendered string is returned, so no database lock can span provider dispatch.

The write-back half (``record_account_memory_from_turn``) runs after dispatch,
so it never holds the lock across a provider call either, and it is best-effort
in the same posture as the doc-ingest hook in ``acquisition/doc_to_html``: a
failed extraction or write can never fail the turn. It is dark until
``interaction_extractor.INTERACTION_MEMORY_FLAG`` is set.
"""

from __future__ import annotations

import logging
from datetime import UTC, datetime

from fastapi import Request

from runtime.db_lock import WriteLockTimeout, connect_write
from substrate.context_pack.knowledge_reuse import reuse_token_budget
from substrate.graph import default_db_path
from substrate.memory import MemoryItem, format_memory_for_prompt, recall_memory
from substrate.memory.interaction_extractor import (
    extract_memory_candidates,
    interaction_memory_enabled,
    record_interaction_memory,
)

from .account_memory_identity import distinct_signed_owner

_LOG = logging.getLogger(__name__)


def _select_whole_items_within_budget(items: list[MemoryItem]) -> list[MemoryItem]:
    """Keep recall order while fitting valid whole-item JSON in the shared budget.

    The context-pack substrate's established deterministic approximation is
    ``ceil(chars / 4)``. Re-rendering each candidate accounts for the canonical
    JSON envelope and provenance rather than budgeting only raw fact text.
    """
    budget = reuse_token_budget("thought_partner")
    selected: list[MemoryItem] = []
    for item in items:
        candidate = [*selected, item]
        rendered = format_memory_for_prompt(candidate)
        approximate_tokens = max(1, (len(rendered) + 3) // 4)
        if approximate_tokens <= budget:
            selected = candidate
    return selected


def account_memory_context(request: Request, query: str) -> str:
    """Return bounded prompt JSON for one distinct signed-session owner.

    Shared/local operator identity is intentionally ineligible: ``__operator__``
    cannot distinguish owners, and ``unauthenticated_local`` proves no identity.
    Operational unavailability is availability-first and value-free in logs;
    validation and memory-integrity exceptions are not swallowed.
    """
    owner_user_id = distinct_signed_owner(request)
    if owner_user_id is None:
        return ""

    try:
        with connect_write(
            default_db_path(),
            purpose="thought_partner_account_memory_recall",
        ) as con:
            items = recall_memory(con, owner_user_id, query=query, limit=8)
    except (WriteLockTimeout, OSError):
        _LOG.warning("account-memory recall unavailable")
        return ""
    return format_memory_for_prompt(_select_whole_items_within_budget(items))


def record_account_memory_from_turn(
    request: Request, *, prompt: str, investigation_id: str | None = None
) -> None:
    """Distil stable first-person facts from a completed turn into owner memory.

    Same owner rule as recall: only a distinct signed-session owner is eligible,
    so shared or local operator identity writes nothing. Never raises — the
    turn's response is already decided by the time this runs, and a memory
    failure must not turn a 200 into anything else. The log line is value-free
    because the prompt is owner-private.
    """
    if not interaction_memory_enabled():
        return
    try:
        owner_user_id = distinct_signed_owner(request)
        if owner_user_id is None:
            return
        candidates = extract_memory_candidates(
            owner_user_id=owner_user_id,
            prompt=prompt,
            valid_from=datetime.now(UTC).replace(tzinfo=None),
            investigation_id=investigation_id,
        )
        if not candidates:
            return
        with connect_write(
            default_db_path(),
            purpose="thought_partner_account_memory_writeback",
        ) as con:
            record_interaction_memory(con, candidates)
    except Exception:
        _LOG.warning("account-memory write-back skipped")


__all__ = ["account_memory_context", "record_account_memory_from_turn"]
