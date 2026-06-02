"""Signed-resource-pull federation protocol (Sprint 30+ thread).

Per master-spec §13.9 Phase 3 + the Sprint 30+ federation thread:
two Antiek instances at different organisations can opt-in expose
collective-graph slices to each other. The receiving instance
*fetches* a signed slice (PULL, never push), validates the signing
key, and ingests under its own quality gate (§13.9). Federation
lives at the application-protocol layer; the substrate retains the
single-writer invariant per instance.

Architectural discipline:
- PULL-only — no inbound write paths from peers
- Signing — every slice carries a manifest + signature; receivers
  pin partner public keys; key rotation is explicit
- Quality gate — `ingest_slice` calls the same §13.9 quality gate
  that promote-public uses on local notes
- No cross-instance writes — federation never becomes a backdoor
  for the single-writer invariant; ingestion writes into the
  RECEIVING instance's own DB, never the sending instance's

This module is distinct from `substrate/cross_graph/federation.py`,
which handles per-citation attribution accounting. This module
handles the protocol; that module handles the per-reference
provenance once a slice has been ingested.

Activation gates: Sprint 30+ thread trigger (a partner Antiek instance
willing to negotiate a slice exchange); adversarial review of the
signing + quality-gate path; per-thread go/defer verdict in
docs/sprint30_thread_decisions.md.
"""

from .protocol import (
    FederationPeer,
    FederationRegistry,
    IngestionReport,
    QualityGateCallable,
    QualityGateResult,
    ingest_slice,
    request_slice,
    serve_slice,
)
from .signing import (
    SignatureError,
    SignedManifest,
    SigningKey,
    VerifyingKey,
    generate_keypair,
    sign_manifest,
    verify_manifest,
)
from .slice import (
    FederationSlice,
    NegotiationStatus,
    SliceItem,
    SliceManifest,
    SliceNegotiation,
)

__all__ = [
    "FederationPeer",
    "FederationRegistry",
    "FederationSlice",
    "IngestionReport",
    "NegotiationStatus",
    "QualityGateCallable",
    "QualityGateResult",
    "SignatureError",
    "SignedManifest",
    "SigningKey",
    "SliceItem",
    "SliceManifest",
    "SliceNegotiation",
    "VerifyingKey",
    "generate_keypair",
    "ingest_slice",
    "request_slice",
    "serve_slice",
    "sign_manifest",
    "verify_manifest",
]
