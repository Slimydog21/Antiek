"""Pure owner-key derivation shared by signed human account surfaces."""

from __future__ import annotations

from hashlib import sha256

# Namespace marker so a derived owner is never mistaken for a substrate user_id.
_DERIVED_OWNER_PREFIX = "acct_"

# 128 bits of SHA-256. Collision risk is negligible at any plausible user count, and a
# shorter value keeps the column readable.
_DERIVED_OWNER_HEX = 32

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
