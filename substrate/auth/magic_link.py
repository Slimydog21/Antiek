"""Magic-link token + session-cookie primitives — stdlib HMAC.

Two distinct signed payloads with different TTLs and audiences:

- **Magic-link token** (audience ``"magic-link"``, 15 min TTL): minted
  when the operator submits their email; embedded in the link sent
  via the email provider.
- **Session cookie** (audience ``"session"``, 30 day TTL by default):
  minted at the end of ``GET /auth/callback`` and set as an
  HttpOnly + Secure + SameSite=Lax cookie. The middleware reads
  this on every subsequent request.

Both are signed by ``ANTIEK_AUTH_SECRET``. Rotating the secret
invalidates every outstanding link and session — that is the
intentional kill switch.

We implement signing with stdlib ``hmac`` + ``hashlib`` + ``base64``
+ ``json`` rather than pulling a JWT or itsdangerous dep, per
``pyproject.toml`` "keep this list tight" policy. The payload shape
is intentionally close to JWT's
``base64(header).base64(payload).base64(signature)`` but with our
own audience field so an Antiek token can never be mistaken for a
JWT issued elsewhere and vice versa.
"""

from __future__ import annotations

import base64
import binascii
import hashlib
import hmac
import json
import os
import secrets
import time
from dataclasses import dataclass
from typing import Any

_MAGIC_LINK_AUDIENCE = "antiek-magic-link.v1"
_SESSION_AUDIENCE = "antiek-session.v1"

MAGIC_LINK_TTL_SECONDS = 15 * 60
SESSION_TTL_SECONDS = 30 * 24 * 60 * 60  # 30 days


class InvalidToken(Exception):
    """Generic invalid-token error (signature mismatch, malformed)."""


class TokenExpired(InvalidToken):
    """Token's max_age elapsed."""


class InvalidSessionCookie(InvalidToken):
    """Session cookie was malformed, expired, or wrong-secret."""


@dataclass(frozen=True)
class SessionClaims:
    """What a verified session cookie carries.

    ``user_id`` matches the substrate's ``owner_user_id`` convention
    (``"__operator__"`` for the solo operator; real user IDs once
    Sprint 22 lands). ``email`` is the verified address; the
    middleware enforces the allowlist against this.
    """

    user_id: str
    email: str
    issued_at: int  # unix seconds
    session_id: str | None = None


@dataclass(frozen=True)
class MagicLinkClaims:
    email: str
    nonce: str
    issued_at: int


# ── Internals ────────────────────────────────────────────────────────


def _secret() -> bytes:
    raw = os.environ.get("ANTIEK_AUTH_SECRET", "").strip()
    if not raw:
        raise RuntimeError(
            "ANTIEK_AUTH_SECRET is not set. Generate one with "
            "`python -c 'import secrets; print(secrets.token_urlsafe(48))'` "
            "and place it in /etc/antiek/secrets.env."
        )
    return raw.encode("utf-8")


def _b64url_encode(raw: bytes) -> str:
    return base64.urlsafe_b64encode(raw).rstrip(b"=").decode("ascii")


def _b64url_decode(text: str) -> bytes:
    pad = "=" * (-len(text) % 4)
    return base64.urlsafe_b64decode((text + pad).encode("ascii"))


def _sign(audience: str, payload_bytes: bytes) -> bytes:
    mac = hmac.new(_secret(), digestmod=hashlib.sha256)
    mac.update(audience.encode("utf-8"))
    mac.update(b".")
    mac.update(payload_bytes)
    return mac.digest()


def _encode(audience: str, payload: dict[str, Any]) -> str:
    payload_bytes = json.dumps(
        payload,
        separators=(",", ":"),
        sort_keys=True,
    ).encode("utf-8")
    sig = _sign(audience, payload_bytes)
    return f"{_b64url_encode(payload_bytes)}.{_b64url_encode(sig)}"


def _decode(
    audience: str,
    token: str,
    *,
    max_age_seconds: int,
    expired_exc: type[InvalidToken],
    invalid_exc: type[InvalidToken],
) -> dict[str, Any]:
    if not token or token.count(".") != 1:
        raise invalid_exc("malformed token")
    payload_b64, sig_b64 = token.split(".", 1)
    try:
        payload_bytes = _b64url_decode(payload_b64)
        provided_sig = _b64url_decode(sig_b64)
    except (ValueError, binascii.Error) as exc:
        raise invalid_exc(f"base64 decode failed: {exc}") from exc
    expected_sig = _sign(audience, payload_bytes)
    if not hmac.compare_digest(provided_sig, expected_sig):
        raise invalid_exc("signature mismatch")
    try:
        payload = json.loads(payload_bytes.decode("utf-8"))
    except (UnicodeDecodeError, json.JSONDecodeError) as exc:
        raise invalid_exc(f"payload decode failed: {exc}") from exc
    if not isinstance(payload, dict):
        raise invalid_exc("payload not an object")
    iat = payload.get("iat")
    if not isinstance(iat, int):
        raise invalid_exc("payload missing iat")
    age = int(time.time()) - iat
    if age > max_age_seconds:
        raise expired_exc(f"token expired ({age}s > {max_age_seconds}s)")
    if age < -60:
        # Clock skew tolerance: future-issued tokens by >1 min are
        # rejected. Without this guard, a misconfigured server clock
        # in the future could grant near-immortal tokens.
        raise invalid_exc("token issued in the future")
    return payload


# ── Magic-link tokens ────────────────────────────────────────────────


def mint_magic_link_token(email: str, *, nonce: str | None = None) -> str:
    """Mint a magic-link token bound to ``email``.

    The token embeds the requested email; verification returns it so
    the callback knows which mailbox the click came from. Allowlist
    enforcement is the caller's job (in ``auth.py``).
    """
    normalized = email.strip().lower()
    return _encode(
        _MAGIC_LINK_AUDIENCE,
        {
            "email": normalized,
            "nonce": nonce or secrets.token_urlsafe(24),
            "iat": int(time.time()),
        },
    )


def verify_magic_link_token(
    token: str,
    *,
    max_age_seconds: int = MAGIC_LINK_TTL_SECONDS,
) -> str:
    """Verify a magic-link token and return the embedded email.

    Raises ``TokenExpired`` if older than ``max_age_seconds``,
    ``InvalidToken`` for any other failure.
    """
    return verify_magic_link_claims(token, max_age_seconds=max_age_seconds).email


def verify_magic_link_claims(
    token: str,
    *,
    max_age_seconds: int = MAGIC_LINK_TTL_SECONDS,
) -> MagicLinkClaims:
    payload = _decode(
        _MAGIC_LINK_AUDIENCE,
        token,
        max_age_seconds=max_age_seconds,
        expired_exc=TokenExpired,
        invalid_exc=InvalidToken,
    )
    email = payload.get("email")
    nonce = payload.get("nonce")
    issued_at = payload.get("iat")
    if (
        not isinstance(email, str)
        or not email
        or not isinstance(nonce, str)
        or len(nonce) < 16
        or not isinstance(issued_at, int)
    ):
        raise InvalidToken("magic-link claims malformed")
    return MagicLinkClaims(email.strip().lower(), nonce, issued_at)


# ── Session cookies ──────────────────────────────────────────────────


def mint_session_cookie(
    *, user_id: str, email: str, session_id: str | None = None
) -> str:
    """Mint a signed session-cookie value.

    Carries ``user_id`` + ``email`` so the middleware can reconstruct
    ``UserClaims`` without a DB lookup. Multi-user Sprint 22 will
    keep this shape and add a per-user scope list.
    """
    return _encode(
        _SESSION_AUDIENCE,
        {
            "user_id": user_id,
            "email": email.strip().lower(),
            "iat": int(time.time()),
            "session_id": session_id,
        },
    )


def verify_session_cookie(
    cookie_value: str,
    *,
    max_age_seconds: int = SESSION_TTL_SECONDS,
) -> SessionClaims:
    """Verify a session cookie and return the embedded claims.

    Raises ``InvalidSessionCookie`` on any failure (expiry, bad
    signature, malformed payload).
    """
    payload = _decode(
        _SESSION_AUDIENCE,
        cookie_value,
        max_age_seconds=max_age_seconds,
        expired_exc=InvalidSessionCookie,
        invalid_exc=InvalidSessionCookie,
    )
    user_id = payload.get("user_id")
    email = payload.get("email")
    iat = payload.get("iat")
    session_id = payload.get("session_id")
    if not isinstance(user_id, str) or not isinstance(email, str) or not isinstance(iat, int):
        raise InvalidSessionCookie("session claims malformed")
    if session_id is not None and not isinstance(session_id, str):
        raise InvalidSessionCookie("session id malformed")
    return SessionClaims(
        user_id=user_id,
        email=email,
        issued_at=iat,
        session_id=session_id,
    )
