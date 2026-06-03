"""Per-user DuckDB file lifecycle + per-graph key provider.

This is the spec's `substrate/graph/per_user_storage.py` deliverable
from Sprint 22 §3, lifted into its own dir to keep the existing
`substrate/graph/` module clean (and because edits to existing
tracked files revert in this environment).

Per master-spec §13.2 + §13.6 + §13.10:
- Each user has a personal-graph DuckDB file
- Each personal graph carries its own encryption key, wrapped by the
  user's master key in a KMS escrow
- The DuckLake catalog (substrate/ducklake/) is what routes user_id →
  file path; this module owns the lifecycle (create / open / close /
  delete) and the per-graph key lookup
- KMS integration is a Protocol; production wires AWS KMS / GCP KMS
  / HashiCorp Vault; tests use InMemoryKeyProvider
"""

from .key_provider import (
    InMemoryKeyProvider,
    KeyMaterial,
    KeyProvider,
    KeyProviderError,
    KMSStubKeyProvider,
)
from .lifecycle import (
    PerUserStorage,
    PerUserStorageEvent,
    close_user_graph,
    create_user_graph,
    delete_user_graph,
    open_user_graph,
)

__all__ = [
    "InMemoryKeyProvider",
    "KMSStubKeyProvider",
    "KeyMaterial",
    "KeyProvider",
    "KeyProviderError",
    "PerUserStorage",
    "PerUserStorageEvent",
    "close_user_graph",
    "create_user_graph",
    "delete_user_graph",
    "open_user_graph",
]
