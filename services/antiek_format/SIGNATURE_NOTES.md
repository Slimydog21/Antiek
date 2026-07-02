# `.antiek` signature scheme — operator notes

Companion to `SPEC.md` §3. This file captures the **key-management**
decisions that aren't in the wire-format spec.

## Algorithm

Ed25519, detached signatures. 32-byte public keys, 64-byte signatures,
32-byte private keys (encoded base64 for storage). Implementation:
`cryptography.hazmat.primitives.asymmetric.ed25519`.

Why Ed25519: small keys, small signatures, deterministic (no nonce
needed), well-tested library, FIPS-186-5 since 2023. Alternatives
considered:

- **ECDSA P-256**: bigger sigs, requires good RNG for nonce, no perf
  win — rejected.
- **RSA-PSS**: 256-byte sigs, slow on hot path, no real benefit — rejected.
- **Symmetric HMAC**: defeats the purpose (any reader could forge) —
  rejected.

## Key storage

Per-user keypair lives in DuckDB at `antiek_user_keypairs` (one row per
`user_id`). The table is created by `ensure_keypair()` on first call;
no separate migration file because the row count is tiny and the table
is creation-on-demand. The private key is base64-encoded **at rest**
and never exported.

The Sprint 22+ multi-user posture (operator-shared substrate) doesn't
change this — each user_id has its own row, and the substrate is the
only entity that can read another user's private key (which would be a
substrate-level privilege check, out of SPR-09's scope).

## Key rotation (open question / SPR-09 stance)

**What happens if a user re-generates their keypair?**

Answer for SPR-09: **the user cannot.** `ensure_keypair()` is
idempotent; it returns the existing row when one exists. There is no
"rotate" verb in the API. This is deliberate because:

1. Rotating a key would invalidate every previously-signed file. We
   don't want a user to accidentally destroy their public-graph
   contributions by clicking "regenerate".
2. The substrate doesn't yet have a public-key registry that maps
   `user_id → list[historical pubkeys]`. Without one, a reader has no
   way to verify an old file against an old key — the pubkey in the
   manifest **is** the verification anchor, but a reader that wants to
   re-check "is this still the user's current key?" needs a registry.
3. Rotation also touches federated-handshake semantics (Sprint 30+).

When rotation lands, the wire-format change required is:

- Each `.antiek` keeps its embedded `creator_pubkey` (no change). The
  signature still verifies against THAT pubkey.
- A separate **revocation list** at the substrate level says "user X's
  key Y has been rotated; do not trust new files signed with Y after
  date Z". The reader cross-references this when surfacing the file's
  age / origin. The wire-format itself stays signed against the pubkey
  in the file.

This is documented here for the post-SPR-09 instance that lands key
rotation — the SPR-09 stance is "old files keep their old signatures;
they are not invalidated".

## What happens on tamper

If `content.tiptap.json` is modified after writing:
1. The signed bytes change.
2. `verify_bytes(...)` returns `False`.
3. The reader returns the notebook (so the operator can read what was
   tampered with) but sets `signature_valid: false` on the result.
4. The UI surfaces a "this file's signature does not verify" warning —
   that wiring is in M6's surface change, marked `signature_valid` in
   the FastAPI response.

Tests in `tests/test_e2e.py::test_tamper` flip a single byte in
`content.tiptap.json` and assert verification fails.

## What's NOT signed

- The zip envelope (timestamps, CRCs, file order). The signature is
  over the **canonical content bytes**, not the zip. This is why the
  zip writer also has to be deterministic (§6 of SPEC.md) — but for a
  different reason (content-hash addressing, not signature integrity).
- Audio block payloads (`blocks/*.audio`). Their integrity is covered
  by SHA-256 hashes inside the **signed** manifest's `blocks_index`.
  A tampered audio file fails the per-block integrity check at read
  time, not the top-level signature.

## What's reserved for SPR-09+

- **Multi-author signatures** (out of scope).
- **Counter-signatures** (a verifier endorses someone else's signed
  artifact) — out of scope; would require a separate `endorsements/`
  zip directory.
- **Key revocation list** — see "Key rotation" above.
- **HSM / TPM-backed key storage** — out of scope; keys are in
  unencrypted DuckDB rows today. The local-only / single-operator
  threat model accepts this; multi-user substrates need a follow-up.
