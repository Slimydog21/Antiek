# Federation contract

**Status:** Substrate shipped (HMAC scaffold); thread DEFERRED until a
partner Antiek instance expresses negotiation willingness. See
[docs/sprint30_thread_decisions.md §2 Thread 1](../sprint30_thread_decisions.md)
for the gating condition.

This document consolidates Antiek's federation contract — the shape
that lets two Antiek instances exchange knowledge without violating
the single-writer invariant. The contract was implemented as substrate
ahead of an explicit canon document; this file is the canon doc that
catches up to the code, written so a future implementer can reconstruct
the design intent without re-reading every module.

The canonical source of truth is the code: when this document and the
code disagree, the code wins. Updating this document on substrate
changes is the maintainer's responsibility.

---

## Five load-bearing design choices

### 1. PULL-only, never PUSH

The receiver fetches; the sender never pushes. Concretely: there is no
inbound write path from a peer. A peer cannot create an Antiek
investigation, mutate a synthesis, or write to anything in the
receiver's substrate beyond what the receiver's quality gate admits.

**Why this matters:** the single-writer invariant
(`CLAUDE.md` critical invariant §1) survives federation. Sender-side
writes happen in the SENDER's substrate via the sender's normal
write paths; federation only moves *artifacts* between substrates.

**Implemented at:** `substrate/federation/protocol.py:request_slice` /
`serve_slice` / `ingest_slice`.

### 2. Signed manifest, not signed payload

The slice's metadata (manifest) is signed; the payload items are
content-addressed (sha256) and listed by hash in the manifest. The
receiver verifies the manifest signature, then verifies each item's
content matches its listed hash.

**Why this matters:** the manifest is small (sub-kilobyte) and can be
re-verified cheaply on every ingestion attempt. Re-signing the
payload bytes directly would make slice exchange O(payload size)
per verification step.

**Implemented at:** `substrate/federation/slice.py:SliceManifest.canonical_bytes`
+ `substrate/federation/signing.py:sign_manifest`.

### 3. HMAC-SHA256 scaffold, Ed25519-swap-ready

The signing primitive is HMAC-SHA256 with a shared secret today. The
SigningKey / VerifyingKey interface enforces the asymmetric *role*
discipline (a SigningKey can only sign, a VerifyingKey can only
verify), so scaffold code does not accidentally treat the symmetric
secret as a public-distributable artifact. Production swap replaces
the primitive with Ed25519 (via the `cryptography` library); the
interface stays the same.

**Why this matters:** the interface lock means the production swap
is a single-module change. Adding `cryptography` is a new dependency
(CLAUDE.md invariant I-04 — requires an ADR) so the operator
controls the swap timing.

**Implemented at:** `substrate/federation/signing.py` (see the SCAFFOLD
discipline note at top of file).

### 4. Receiver runs the §13.9 quality gate before write

After signature verification, each item is run through the same
quality gate that `promote-public` uses on local notes (master-spec
§13.9). Only PASS items are written into the receiver's DB.

**Why this matters:** a malicious or low-quality partner cannot
degrade the receiver's substrate by sending bad content. The receiver
maintains its own quality bar regardless of partner choices.

**Implemented at:** `substrate/federation/protocol.py:ingest_slice`
(takes a `QualityGateCallable` parameter so receivers can plug their
own gate; the canonical implementation is the §13.9 quality gate).

### 5. Pinned partner keys, explicit rotation

Receivers pin partner public-key fingerprints (e.g., "Partner X's
fingerprint is 9a3f..."). Key rotation is an explicit operator action:
a partner announces new key + fingerprint via an out-of-band channel,
the receiver updates the pin, the next slice signed with the old key
is rejected.

**Why this matters:** silent key rotation = potential MITM. Forcing
explicit rotation surfaces the change at audit time.

**Implemented at:** `substrate/federation/protocol.py:FederationRegistry`
+ `substrate/cross_graph/federation_config_store.py`.

---

## The three-step protocol

```
   Receiver A                              Sender B
       |                                       |
       | --- request_slice(manifest_spec) ---> |
       |                                       | builds items + manifest
       |                                       | signs manifest
       | <----- FederationSlice (signed) ----- |
       |                                       |
       | verify manifest signature             |
       | verify each item content_hash         |
       | for item in items:                    |
       |   quality_gate(item)                  |
       |   if PASS: write to receiver's DB     |
       |                                       |
       | IngestionReport (pass/fail counts)    |
```

Function signatures (from `substrate/federation/protocol.py`):

```python
def request_slice(peer, manifest_spec) -> FederationSlice
def serve_slice(items, signing_key, manifest_args) -> FederationSlice
def ingest_slice(slice, verifying_key, quality_gate) -> IngestionReport
```

Pre-flight: `SliceNegotiation` lets receiver and sender agree on
manifest_spec before the signed slice flows. Negotiation lives at
the application-protocol layer (above the substrate signing
primitives).

---

## Why no message envelope / idempotency-key / conflict-resolution clause

The brainstorming chamber for this sprint
(`~/specs/antiek-yegge-sharpen/sprint-09-federation-contract.html`)
proposed a generic message envelope with idempotency keys and a
syntheses-conflict-resolution policy. **Antiek's PULL-only design
sidesteps all three:**

- **Message envelope** — slice exchange is HTTP-style request/response,
  not a streaming message bus. The "envelope" is the
  `FederationSlice` dataclass; no separate transport envelope.
- **Idempotency keys** — manifests are content-addressed (item_hashes
  + slice_id). Re-ingesting the same slice is naturally idempotent at
  the receiver via the manifest's slice_id check.
- **Conflict resolution** — there are no conflicts to resolve because
  there are no concurrent writes. The receiver writes its own
  substrate; the sender writes its own substrate; federated artifacts
  are read-only on both sides except where the receiver's quality
  gate explicitly admits them.

This is the substrate-fit answer: the contract Antiek's federation
actually has, not the contract a naive cross-instance system would
need.

---

## Hermes is NOT an in-Antiek adapter

The brainstorming chamber referenced the Hermes bridge as the
"reference adapter" for federation. **The Hermes bridge lives in a
separate repo (`~/.hermes/skills/research/`), not in Antiek's
substrate.** It is a different system entirely: Hermes is a research
agent that calls Antiek-style substrates as a *consumer*; federation
is Antiek-to-Antiek slice exchange between *peers*. Conflating them
would create design pressure to make federation accommodate
non-Antiek consumers, which would either bloat the protocol or weaken
its single-writer invariants.

See [ADAPTERS.md](ADAPTERS.md) for the (currently empty) adapter list.

---

## Test coverage

Six test files exercise the federation surface today:

- `tests/test_federation.py`
- `tests/test_federation_config.py`
- `tests/test_federation_event_emit.py`
- `tests/test_federation_inbound.py`
- `tests/test_federation_outbound.py`
- `tests/test_federation_wired_hooks.py`
- `tests/test_api_federation.py`

Plus visual regression baselines at
`apps/reading/.lostpixel/baseline/trust-federation--default__*.png`.

---

## Reversal conditions

| Choice | When to reconsider |
|---|---|
| PULL-only | Partner relationships shift to "push artifacts when generated" semantics (e.g., real-time collaboration). Would require a new write-side invariant. |
| Signed manifest, not payload | Slice payloads stop being amenable to content addressing (e.g., dynamic content). |
| HMAC scaffold → Ed25519 swap | First real partner exchange — add `cryptography` dep via ADR, swap signing primitive, update fingerprint scheme. |
| Quality gate at ingestion | A class of valuable federated content can't pass the local quality gate; consider per-source policies. |
| Pinned partner keys | Key-management infrastructure exists (e.g., a federation key directory). Until then, manual pinning beats silent rotation. |

---

## Cross-references

- `CLAUDE.md` § "Critical invariants — DO NOT VIOLATE" #1 (single-writer)
- `docs/master-product-spec.md` §13.9 (quality gate)
- `docs/sprint30_thread_decisions.md` §2 Thread 1 (Federation GO/DEFER verdict)
- `~/.claude/projects/-Users-slimydog/memory/project_antiek_phase3_substrate.md`
  (memory: federation + advertiser onboarding + intent targeting landed
  in commit e59c4e2)
- Spec: `~/specs/antiek-yegge-execute/sprint-11-federation-contract.html`
