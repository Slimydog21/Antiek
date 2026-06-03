"""Signing primitives for federated slices.

SCAFFOLD discipline: this module uses HMAC-SHA256 with a shared
secret for the substrate-scaffold phase. Production swaps Ed25519
(via the `cryptography` library) — the `SigningKey` / `VerifyingKey`
interface stays the same; only the internal primitive changes.

The asymmetric *role* discipline is enforced now: SigningKey can
only sign, VerifyingKey can only verify. This means scaffold code
written today won't accidentally treat the symmetric secret as a
public-distributable artefact.
"""

from __future__ import annotations

import hmac
import secrets
from dataclasses import dataclass
from hashlib import sha256


class SignatureError(Exception):
    """Raised when a manifest fails signature verification."""


@dataclass(frozen=True)
class SigningKey:
    """The instance that holds this key can SIGN slices for export.

    In scaffold mode, `_secret` is a 32-byte HMAC secret. Production
    Ed25519 swap will replace this with the private key bytes; the
    .sign(...) method stays the same.

    The fingerprint is a stable identifier for key-rotation tracking;
    operators can pin "partner X's key with fingerprint 9a3f..." in
    docs/federation_partners.md.
    """

    _secret: bytes
    fingerprint: str

    def sign(self, payload: bytes) -> bytes:
        return hmac.new(self._secret, payload, sha256).digest()

    def public(self) -> VerifyingKey:
        """Derive the verifying half. In scaffold mode this shares the
        secret; in production Ed25519 it derives the public key."""
        return VerifyingKey(_verifier=self._secret, fingerprint=self.fingerprint)


@dataclass(frozen=True)
class VerifyingKey:
    """The instance that holds this can VERIFY slices but NOT sign new
    ones. In scaffold mode this is the same bytes as the signing
    secret (symmetric); production Ed25519 will hold only the public
    half."""

    _verifier: bytes
    fingerprint: str

    def verify(self, payload: bytes, signature: bytes) -> bool:
        expected = hmac.new(self._verifier, payload, sha256).digest()
        return hmac.compare_digest(expected, signature)


def generate_keypair(seed: bytes | None = None) -> SigningKey:
    """Generate a fresh signing key. `seed` is honoured for test
    determinism; production callers pass None for randomness."""
    secret = seed if seed is not None else secrets.token_bytes(32)
    if len(secret) < 32:
        secret = (secret + b"\x00" * 32)[:32]
    fp = sha256(secret).hexdigest()[:16]
    return SigningKey(_secret=secret, fingerprint=fp)


@dataclass(frozen=True)
class SignedManifest:
    """A manifest blob with its signature attached."""

    payload: bytes
    signature: bytes
    key_fingerprint: str


def sign_manifest(key: SigningKey, payload: bytes) -> SignedManifest:
    return SignedManifest(
        payload=payload,
        signature=key.sign(payload),
        key_fingerprint=key.fingerprint,
    )


def verify_manifest(
    signed: SignedManifest,
    *,
    expected_key: VerifyingKey,
) -> None:
    """Verify the signature. Raises SignatureError on mismatch.

    Caller is responsible for pinning the expected key — passing the
    wrong key intentionally is how you reject impostor peers.
    """
    if signed.key_fingerprint != expected_key.fingerprint:
        raise SignatureError(
            f"fingerprint mismatch: signed={signed.key_fingerprint!r} "
            f"expected={expected_key.fingerprint!r}",
        )
    if not expected_key.verify(signed.payload, signed.signature):
        raise SignatureError("signature does not verify")
