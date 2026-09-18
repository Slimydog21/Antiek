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

from hashlib import sha256

from fastapi import Request

SESSION_AUTH_METHOD = "antiek_session_cookie"

# Storage/service identities that cannot name a person. Refused as owners.
FORBIDDEN_OWNERS = frozenset({"__operator__", "shared", "service", "local"})

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

# Namespace marker so a derived owner is never mistaken for a substrate user_id.
_DERIVED_OWNER_PREFIX = "acct_"

# 128 bits of SHA-256. Collision risk is negligible at any plausible user count, and a
# shorter value keeps the column readable.
_DERIVED_OWNER_HEX = 32

_MAX_OWNER_LENGTH = 256
# RFC 5321 maximum reverse-path length; anything longer is malformed, not a person.
_MAX_EMAIL_LENGTH = 320


def derive_owner_from_verified_email(value: object) -> str | None:
    """Stable opaque owner for a session whose e-mail the middleware already verified.

    Shared by every owner predicate so that one person resolves to ONE owner value
    everywhere. If account memory and BYOT dispatch derived this differently, the same
    human would own two disjoint sets of rows and their spend would be attributed to an
    identity their memory could not see — so this lives in one place on purpose.

    Callers are responsible for reaching this only on a path where the address was
    actually verified. This function re-checks shape only; it is not the authorization
    decision and must never be treated as one.
    """
    if not isinstance(value, str):
        return None
    normalized = value.strip().casefold()
    if not normalized or len(normalized) > _MAX_EMAIL_LENGTH:
        return None
    # Shape check, not validation: an address without a single interior "@" cannot have
    # come from the verified-login path, so refusing is the conservative reading.
    local, separator, domain = normalized.partition("@")
    if not separator or not local or not domain or "@" in domain:
        return None
    digest = sha256(normalized.encode("utf-8")).hexdigest()[:_DERIVED_OWNER_HEX]
    return f"{_DERIVED_OWNER_PREFIX}{digest}"


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
