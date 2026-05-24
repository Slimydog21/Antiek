# Federation adapters

**Status:** Empty. Antiek's federation protocol is Antiek-to-Antiek by
design; non-Antiek adapters do not exist and are not on the roadmap
without an explicit operator decision.

This file is a placeholder so a future adapter (if any) has an
established home + format to land into, rather than getting a
parallel doc tree built bespoke.

## What is NOT an adapter

### Hermes bridge

Outside Antiek's substrate. Lives at `~/.hermes/skills/research/`. It
is a *consumer* of Antiek-style substrates, not a federation peer.
Conflating them would create design pressure to make federation
accommodate non-Antiek consumers (which would either bloat the
protocol or weaken its single-writer invariants). See
[CONTRACT.md § "Hermes is NOT an in-Antiek adapter"](CONTRACT.md).

### Per-citation attribution

`substrate/cross_graph/federation.py` handles per-citation
attribution accounting once a slice has been ingested. It is a
downstream of federation, not an adapter to it. The
`substrate/federation/` modules handle the protocol; cross_graph
handles the provenance.

### REST surface

`interfaces/research/api/federation.py` is the HTTP transport for
slice exchange between two Antiek instances over a network — still
Antiek-to-Antiek, just over HTTP rather than a hypothetical
direct-import bridge. Not an adapter to a foreign protocol.

## When an adapter would land

Only if a credible non-Antiek system both:

1. Wants to receive a federated slice from Antiek (the receiver is
   non-Antiek)
2. Cannot run an Antiek-compatible ingest_slice locally

For now, both conditions remain false. The receiver side is the
load-bearing part of federation; an adapter would have to faithfully
reproduce signature verification + the §13.9 quality gate. The
easier path for any consumer is to run an Antiek instance.

## Adapter shape (when written)

Should be a Python module under `substrate/federation/adapters/<name>.py`
exposing:

- A function that translates a `FederationSlice` to the foreign
  protocol's equivalent shape.
- A function that translates the foreign protocol's verifying-key
  format to a `VerifyingKey` Antiek can pin.
- Documented limitations (which fields don't survive translation;
  what quality-gate semantics are degraded).

Plus an entry in this file documenting the adapter, its limitations,
and when the operator decided to write it.

---

## Cross-references

- [CONTRACT.md](CONTRACT.md) — the canonical federation contract.
- `substrate/federation/` — protocol modules.
- `~/specs/antiek-yegge-execute/sprint-11-federation-contract.html` —
  the source spec (note: brainstormed an adapter pattern that
  substrate-fit reality rejected; this file documents the rejection).
