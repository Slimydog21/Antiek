"""Resolve the calling account from an MCP request's ``auth_context``.

ONE person must map to ONE owner value everywhere in Antiek. If the MCP
surface derived an owner differently from the HTTP surface, the same human
would own two disjoint sets of rows and would search a personal graph their
own uploads had never landed in. So this module owns no derivation of its
own: it reuses ``interfaces.research.api.account_memory_identity`` — the
predicate ``account_memory_context``, ``account_memory_routes`` and
``doc_ingest_routes`` already share — and only adapts its input from a
FastAPI ``Request`` to the JSON-RPC ``auth_context`` dict.

What that buys, concretely, is the refusal list. ``FORBIDDEN_OWNERS`` names
the storage and service identities that cannot name a person; every
production login still mints the single-operator storage sentinel among them,
so admitting it would hand any authenticated caller the same shared pile of
rows. That is precisely the defect SPR-11 Task 2 removes from
``search_personal``, and re-deriving the list here would let the two surfaces
drift apart the first time one of them is edited.

Resolution, in order:

  1. ``user_id`` that is a genuine per-account id (not in ``FORBIDDEN_OWNERS``)
     — used as-is. This is the Sprint 22+ multi-user path.
  2. ``user_id`` equal to the single-operator storage sentinel — fall back to
     the same verified-e-mail derivation the HTTP paths use, so the MCP tool
     and the browser resolve the operator to the identical ``acct_`` owner.
  3. Anything else — ``None``. The caller must fail closed.

There is no fourth branch. No default account, no sentinel, no "first owner
in the table": a tool that cannot name its caller returns an error.

Branch 2 reaches ``derive_owner_from_verified_email`` with an address this
module did not verify, which on the HTTP path the auth middleware had already
checked. That is not a hole here, because it widens nothing: a peer that can
write ``user_email`` on the MCP pipe can equally write the derived ``acct_``
value straight into ``user_id`` and reach the same rows. The pipe is the trust
boundary on the stdio transport (see ``server.extract_auth_context``), and a
transport that one day carries a verified bearer token will be the thing that
makes this an authorization decision. What branch 2 buys today is that the
operator's MCP client and the operator's browser resolve to the SAME owner, so
the tool searches the graph his uploads actually landed in.
"""

from __future__ import annotations

from interfaces.research.api.account_memory_identity import (
    FORBIDDEN_OWNERS,
    OPERATOR_STORAGE_SENTINEL,
    derive_owner_from_verified_email,
)

# Matches ``account_memory_identity._MAX_OWNER_LENGTH``. Duplicated as a bound
# check rather than imported because it is a private name there; the value is
# a sanity ceiling, not a contract, and a mismatch cannot widen the boundary —
# both ends refuse anything longer.
_MAX_OWNER_LENGTH = 256


def resolve_owner_from_auth_context(auth_context: object) -> str | None:
    """Return the caller's owner id, or ``None`` when no person is named.

    ``None`` is the fail-closed answer and the caller must treat it as one. It
    is returned for a missing context, a context that is not a dict, a missing
    or non-string ``user_id``, a shared storage identity with no verified
    address to fall back to, and an over-long value.
    """
    if not isinstance(auth_context, dict):
        return None

    raw = auth_context.get("user_id")
    if not isinstance(raw, str):
        return None
    owner = raw.strip()
    if not owner or len(owner) > _MAX_OWNER_LENGTH:
        return None

    folded = owner.casefold()
    if folded not in FORBIDDEN_OWNERS:
        return owner
    if folded != OPERATOR_STORAGE_SENTINEL:
        # A genuinely shared or machine context ("shared", "service",
        # "local"). No fallback — mirrors ``distinct_signed_owner`` exactly.
        return None

    return derive_owner_from_verified_email(auth_context.get("user_email"))


__all__ = ["resolve_owner_from_auth_context"]
