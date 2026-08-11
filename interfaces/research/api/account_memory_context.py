"""Owner-private account-memory context for provider prompts.

This boundary deliberately accepts only middleware-authenticated request state.
Recall uses ``connect_write`` because the memory store requires the canonical
locked connection even for reads; the context manager is exited before the
rendered string is returned, so no database lock can span provider dispatch.
"""

from __future__ import annotations

import logging

from fastapi import Request

from runtime.db_lock import WriteLockTimeout, connect_write
from substrate.context_pack.knowledge_reuse import reuse_token_budget
from substrate.graph import default_db_path
from substrate.memory import MemoryItem, format_memory_for_prompt, recall_memory

_LOG = logging.getLogger(__name__)
_SESSION_AUTH_METHOD = "antiek_session_cookie"
_SHARED_OWNER_ID = "__operator__"


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
    state = getattr(request, "state", None)
    auth_method = getattr(state, "auth_method", None)
    owner_user_id = getattr(state, "user_id", None)
    if auth_method != _SESSION_AUTH_METHOD:
        return ""
    if not isinstance(owner_user_id, str):
        return ""
    owner_user_id = owner_user_id.strip()
    if not owner_user_id or owner_user_id == _SHARED_OWNER_ID:
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


__all__ = ["account_memory_context"]
