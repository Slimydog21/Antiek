"""Ed25519 signing for .antiek containers (SPR-09 / M5).

The signature is a detached Ed25519 signature over the canonical bytes
of (manifest + content + edges), separated by 0x1F unit separators.
See ``SPEC.md`` §3 ("Signing input") for the normative bytes.

Why detached, not embedded
--------------------------
A detached signature lets the manifest carry the public key without
chicken-and-egg about signing-over-the-key. The signed bytes are
exactly (manifest + content + edges); the signature lives in its own
zip entry (``signature.bin``).

Why canonical bytes, not zip bytes
----------------------------------
Zip envelopes carry timestamps, CRCs, and ordering metadata that don't
belong in the signature scope. The signing bytes are the *content*,
canonicalised. Two writers producing different-byte zips for the same
notebook still produce the same signature.

Key management
--------------
``ensure_keypair(user_id, db_path)`` creates a long-lived Ed25519
keypair on first save and stashes it in a per-user-settings DuckDB
table (substrate-resident; never leaves the device). Subsequent calls
return the same keypair. Key rotation is not implemented in SPR-09 —
see ``SIGNATURE_NOTES.md``.
"""

from __future__ import annotations

import binascii
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    import duckdb

import base64
import json
import os
import sys
from dataclasses import dataclass
from typing import Any

from cryptography.exceptions import InvalidSignature
from cryptography.hazmat.primitives import serialization
from cryptography.hazmat.primitives.asymmetric.ed25519 import (
    Ed25519PrivateKey,
    Ed25519PublicKey,
)

try:
    from runtime.db_lock import connect_write
except ImportError:  # pragma: no cover — direct-script fallback
    _here = os.path.dirname(os.path.abspath(__file__))
    sys.path.insert(0, os.path.dirname(os.path.dirname(_here)))
    from runtime.db_lock import connect_write


# ── Canonicalisation helpers ──

UNIT_SEPARATOR: bytes = b"\x1f"
"""ASCII US (0x1F). Separates canonical sections in the signing input
so a tampered length cannot blur the boundary between manifest, body,
and edges. See SPEC.md §3."""


def canonical_json_bytes(obj: object) -> bytes:
    """Canonical JSON: sorted keys, no insignificant whitespace,
    ensure_ascii=False, trailing LF newline.

    Used for the manifest. Two writers MUST produce identical bytes
    for the same object — that's the precondition for signature
    determinism.
    """
    return (
        json.dumps(obj, sort_keys=True, ensure_ascii=False, separators=(",", ":"))
        + "\n"
    ).encode("utf-8")


def canonical_edges_bytes(edges: list[dict[str, Any]]) -> bytes:
    """Canonical ``edges.jsonl``: one sorted-key JSON per line, lines
    sorted by edge_id, LF newlines, trailing newline.

    Empty when no edges. Empty bytes (``b""``) signal "no edges file";
    we still include the leading 0x1F in the signing input so a future
    addition of edges materially changes the signed bytes.
    """
    if not edges:
        return b""
    rows = sorted(edges, key=lambda e: e["edge_id"])
    lines = [
        json.dumps(r, sort_keys=True, ensure_ascii=False, separators=(",", ":"))
        for r in rows
    ]
    return ("\n".join(lines) + "\n").encode("utf-8")


def build_signing_input(
    *,
    manifest_bytes: bytes,
    content_bytes: bytes,
    edges_bytes: bytes,
    extra_sections: list[bytes] | None = None,
) -> bytes:
    """Concatenate canonical sections with 0x1F separators.

    Notebook variants (SPR-09): three sections (manifest, content,
    edges). ``edges_bytes`` may be ``b""``; the separator is still
    emitted so the absence-of-edges state is part of the signed
    content (otherwise a forger could append an edges file without
    changing the signature).

    Sidecar variant (SPR-10, SPEC.md §11.4): five sections — the
    three above PLUS ``highlights.jsonl`` bytes PLUS ``anchors.jsonl``
    bytes. Callers supply these as ``extra_sections``; each extra
    section is preceded by a 0x1F separator regardless of emptiness,
    so signing-input shape is determined by the **count** of extra
    sections, not the content. The reader keys this off
    ``manifest.content_class`` (``pdf_sidecar`` → 2 extras;
    everything else → 0 extras). Mismatched section count between
    writer and reader → signature verification fails, which is the
    correct failure mode.
    """
    out = (
        manifest_bytes
        + UNIT_SEPARATOR
        + content_bytes
        + UNIT_SEPARATOR
        + edges_bytes
    )
    if extra_sections:
        for section in extra_sections:
            out += UNIT_SEPARATOR + section
    return out


# ── Sign / verify ──


@dataclass(frozen=True)
class Keypair:
    """Ed25519 keypair bound to one substrate user."""

    user_id: str
    private_key: Ed25519PrivateKey
    public_key: Ed25519PublicKey

    @property
    def public_key_b64(self) -> str:
        """Base64-encoded 32-byte public key. This is what lands in
        ``manifest.creator_pubkey``."""
        raw = self.public_key.public_bytes(
            encoding=serialization.Encoding.Raw,
            format=serialization.PublicFormat.Raw,
        )
        return base64.b64encode(raw).decode("ascii")

    @property
    def private_key_b64(self) -> str:
        raw = self.private_key.private_bytes(
            encoding=serialization.Encoding.Raw,
            format=serialization.PrivateFormat.Raw,
            encryption_algorithm=serialization.NoEncryption(),
        )
        return base64.b64encode(raw).decode("ascii")


def sign_bytes(keypair: Keypair, signing_input: bytes) -> bytes:
    """Return a 64-byte detached Ed25519 signature."""
    return keypair.private_key.sign(signing_input)


def verify_bytes(
    *,
    creator_pubkey_b64: str,
    signing_input: bytes,
    signature: bytes,
) -> bool:
    """Verify a detached signature. Returns False on any failure (bad
    base64, wrong length, mismatch) — callers translate that to
    ``signature_valid: false`` on the loaded notebook.
    """
    try:
        raw = base64.b64decode(creator_pubkey_b64, validate=True)
    except (ValueError, binascii.Error):
        return False
    if len(raw) != 32:
        return False
    try:
        pub = Ed25519PublicKey.from_public_bytes(raw)
    except Exception:
        return False
    try:
        pub.verify(signature, signing_input)
        return True
    except InvalidSignature:
        return False
    except Exception:
        # Defensive: cryptography can raise other types for malformed
        # input. Treat any verify error as "signature invalid".
        return False


# ── Keypair persistence ──


_KEYPAIR_SCHEMA_SQL = """
CREATE TABLE IF NOT EXISTS antiek_user_keypairs (
    user_id           TEXT PRIMARY KEY,
    private_key_b64   TEXT NOT NULL,
    public_key_b64    TEXT NOT NULL,
    created_at        TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP
);
"""


def _connect_for_read(db_path: str) -> duckdb.DuckDBPyConnection:
    import duckdb
    return duckdb.connect(db_path)


def ensure_keypair(user_id: str, *, db_path: str) -> Keypair:
    """Return the user's keypair, creating one on first call.

    The private key is stored in the substrate's DuckDB under
    ``antiek_user_keypairs``. It NEVER leaves substrate-resident
    storage. The public key is the same value that gets stamped into
    every ``.antiek`` the user writes.
    """
    if not user_id:
        raise ValueError("ensure_keypair: user_id must be non-empty")

    # Fast path: read.
    parent = os.path.dirname(db_path)
    if parent:
        os.makedirs(parent, exist_ok=True)
    if os.path.exists(db_path):
        existing = _load_keypair(user_id, db_path=db_path)
        if existing is not None:
            return existing

    # Slow path: create.
    sk = Ed25519PrivateKey.generate()
    pk = sk.public_key()
    kp = Keypair(user_id=user_id, private_key=sk, public_key=pk)

    con = connect_write(db_path, purpose="antiek_keypair_create")
    try:
        con.execute(_KEYPAIR_SCHEMA_SQL)
        # Race: another writer may have created the row between our
        # earlier _load_keypair and now. Re-check inside the lock.
        row = con.execute(
            "SELECT private_key_b64, public_key_b64 "
            "FROM antiek_user_keypairs WHERE user_id = ?",
            [user_id],
        ).fetchone()
        if row is not None:
            return _keypair_from_b64(user_id, row[0], row[1])
        con.execute(
            "INSERT INTO antiek_user_keypairs "
            "(user_id, private_key_b64, public_key_b64) VALUES (?, ?, ?)",
            [user_id, kp.private_key_b64, kp.public_key_b64],
        )
    finally:
        con.close()
    return kp


def _load_keypair(user_id: str, *, db_path: str) -> Keypair | None:
    con = _connect_for_read(db_path)
    try:
        # If the table doesn't exist yet, treat as "no keypair yet".
        tables = con.execute(
            "SELECT table_name FROM information_schema.tables "
            "WHERE table_name = 'antiek_user_keypairs'"
        ).fetchone()
        if tables is None:
            return None
        row = con.execute(
            "SELECT private_key_b64, public_key_b64 "
            "FROM antiek_user_keypairs WHERE user_id = ?",
            [user_id],
        ).fetchone()
    finally:
        con.close()
    if row is None:
        return None
    return _keypair_from_b64(user_id, row[0], row[1])


def _keypair_from_b64(
    user_id: str, private_key_b64: str, public_key_b64: str
) -> Keypair:
    raw_sk = base64.b64decode(private_key_b64)
    raw_pk = base64.b64decode(public_key_b64)
    sk = Ed25519PrivateKey.from_private_bytes(raw_sk)
    pk = Ed25519PublicKey.from_public_bytes(raw_pk)
    return Keypair(user_id=user_id, private_key=sk, public_key=pk)


__all__ = [
    "Keypair",
    "UNIT_SEPARATOR",
    "build_signing_input",
    "canonical_edges_bytes",
    "canonical_json_bytes",
    "ensure_keypair",
    "sign_bytes",
    "verify_bytes",
]
