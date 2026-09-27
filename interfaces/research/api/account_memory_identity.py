"""Single owner-identity predicate for private account-memory boundaries.

WHAT THIS ANSWERS
─────────────────
"Which distinct human is this request?" — deliberately a different question from
"which row-ownership key does the substrate write?". The substrate answers the second
with ``owner_user_id='__operator__'`` for the whole Sprint 17-21 single-operator range
(see ``substrate.multi_user.auth.operator_claims``), and that is correct: it is a
storage identity shared by every operator-authenticated path.

It is NOT a person. Private account memory keyed on it would be readable by anything
that authenticates as the operator, which is why the shared sentinels below are refused.

THE GAP THAT MADE THIS REAL
───────────────────────────
Every production login mints ``user_id="__operator__"`` (``auth.py`` magic-link callback,
code exchange, passkey assertion, and dev-login all do). So this predicate returned
``None`` for every signed-in session, and its three consumers —
``account_memory_context``, ``account_memory_routes`` and ``doc_ingest_routes`` — were
unreachable in production. The document-ingest route in particular answered a plain
``401 signed owner identity required`` to the operator on his own deployment, which made
"ingest any asset and view it as HTML" impossible while looking like an auth bug.

The fix is not to admit ``__operator__``: the privacy boundary it protects is real. It is
to notice that a distinct human IS provable here by other means. A session-cookie request
has already had its e-mail verified and checked against the operator allowlist by the
auth middleware, and that e-mail is carried on ``request.state.user_email``. One person,
one stable owner — and when genuine per-user ids arrive (Sprint 22+), they are used
directly and this fallback simply stops being reached.

WHY A DERIVED OPAQUE ID RATHER THAN THE E-MAIL ITSELF
────────────────────────────────────────────────────
The owner value is written into rows and can surface in diagnostics. A hash keeps the
address out of storage and logs while preserving the only two properties that matter:
it is stable across logins (a pure function of the normalized address) and distinct
between people. It is not a security control — anyone able to see the rows could
confirm a guessed address — it is PII hygiene, and it is described as exactly that.
"""

from __future__ import annotations

from fastapi import Request

from substrate.constants import FORBIDDEN_OWNERS
from substrate.owner_identity import (
    derive_owner_from_verified_email as derive_owner_from_verified_email,
)

SESSION_AUTH_METHOD = "antiek_session_cookie"

# The one sentinel the authentication paths actually mint (magic-link callback, code
# exchange, passkey assertion, dev-login — all of ``auth.py``). A request carrying it has
# been through e-mail or passkey proof AND the operator allowlist, so a verified address
# is present and names the person. The e-mail fallback is scoped to exactly this value.
#
# "shared", "service" and "local" stay hard-refused with no fallback. No auth path mints
# them, so their appearance means a genuinely shared or machine context, and admitting
# them on a matching address would widen a privacy boundary to buy nothing. Narrow beats
# clever here: this fixes the case that actually occurs and changes no other.
OPERATOR_STORAGE_SENTINEL = "__operator__"

_MAX_OWNER_LENGTH = 256


def distinct_signed_owner(request: Request) -> str | None:
    """Return the normalized distinct owner, or ``None`` when proof is unsafe."""
    state = getattr(request, "state", None)
    if getattr(state, "auth_method", None) != SESSION_AUTH_METHOD:
        return None

    value = getattr(state, "user_id", None)
    if not isinstance(value, str):
        return None
    owner = value.strip()
    if not owner or len(owner) > _MAX_OWNER_LENGTH:
        return None

    folded = owner.casefold()
    if folded not in FORBIDDEN_OWNERS:
        # A genuine per-user id. Used as-is; the fallback below is not reached, so
        # Sprint 22+ multi-user sessions are unaffected by any of this.
        return owner

    if folded != OPERATOR_STORAGE_SENTINEL:
        # "shared" / "service" / "local": no fallback, no owner.
        return None

    # The single-operator storage sentinel. Fall back to the verified session e-mail,
    # which does name one person. Returns None when there is none, so this still fails
    # closed rather than inventing an owner.
    return derive_owner_from_verified_email(getattr(state, "user_email", None))


__all__ = [
    "FORBIDDEN_OWNERS",
    "SESSION_AUTH_METHOD",
    "OPERATOR_STORAGE_SENTINEL",
    "derive_owner_from_verified_email",
    "distinct_signed_owner",
]
