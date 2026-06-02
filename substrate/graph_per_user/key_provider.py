"""Per-graph key provider — Protocol + two implementations.

Per master-spec §13.6: encryption at rest with per-graph keys via KMS
is a Stage 1+ requirement. Substrate-side this module owns the
abstraction; production wires AWS KMS / GCP Cloud KMS / Vault.
"""

from __future__ import annotations

import secrets
import threading
from dataclasses import dataclass, field
from typing import Protocol


class KeyProviderError(Exception):
    """Raised on key-provider lookup / generate / rewrap failures."""


@dataclass(frozen=True)
class KeyMaterial:
    """Wrapped key material for one graph.

    `wrapped_data_key` is the data-encryption key wrapped by the
    user's master key. The data-encryption key is what DuckDB
    consumes at file-create time; the master key never leaves KMS.
    """

    graph_id: str
    key_id: str  # KMS key alias / ARN
    wrapped_data_key: bytes
    algorithm: str = "AES_256_GCM"


class KeyProvider(Protocol):
    """The substrate operations the per-user storage needs."""

    def generate_data_key(self, *, graph_id: str) -> KeyMaterial: ...
    def lookup(self, *, graph_id: str) -> KeyMaterial | None: ...
    def rotate(self, *, graph_id: str) -> KeyMaterial: ...
    def revoke(self, *, graph_id: str) -> None: ...


@dataclass
class InMemoryKeyProvider:
    """Process-local key store. For tests + the Stage-0 transition
    window before KMS is wired."""

    keys: dict[str, KeyMaterial] = field(default_factory=dict)
    _lock: threading.Lock = field(default_factory=threading.Lock)

    def generate_data_key(self, *, graph_id: str) -> KeyMaterial:
        with self._lock:
            if graph_id in self.keys:
                raise KeyProviderError(
                    f"graph_id {graph_id!r} already has a key; "
                    f"use rotate() to replace it",
                )
            material = KeyMaterial(
                graph_id=graph_id,
                key_id=f"alias/antiek-graph-{graph_id}",
                wrapped_data_key=secrets.token_bytes(48),
            )
            self.keys[graph_id] = material
            return material

    def lookup(self, *, graph_id: str) -> KeyMaterial | None:
        with self._lock:
            return self.keys.get(graph_id)

    def rotate(self, *, graph_id: str) -> KeyMaterial:
        with self._lock:
            if graph_id not in self.keys:
                raise KeyProviderError(
                    f"cannot rotate unknown graph_id {graph_id!r}",
                )
            existing = self.keys[graph_id]
            material = KeyMaterial(
                graph_id=graph_id,
                key_id=existing.key_id,
                wrapped_data_key=secrets.token_bytes(48),
            )
            self.keys[graph_id] = material
            return material

    def revoke(self, *, graph_id: str) -> None:
        with self._lock:
            self.keys.pop(graph_id, None)


@dataclass
class KMSStubKeyProvider:
    """Production-shaped provider — calls into a KMS client (AWS KMS,
    GCP Cloud KMS, HashiCorp Vault) when wired. The client is
    injected at construction time; this class shapes the substrate
    contract so production wiring is a Drop-in.

    Tests can pass a fake client with `generate_data_key`,
    `describe_key`, and `disable_key` methods.
    """

    client: object  # actual KMS client; substrate doesn't import any SDK
    key_alias_prefix: str = "alias/antiek-graph"
    _lock: threading.Lock = field(default_factory=threading.Lock)

    def _alias_for(self, graph_id: str) -> str:
        return f"{self.key_alias_prefix}-{graph_id}"

    def generate_data_key(self, *, graph_id: str) -> KeyMaterial:
        alias = self._alias_for(graph_id)
        try:
            resp = self.client.generate_data_key(
                KeyId=alias,
                KeySpec="AES_256",
            )  # type: ignore[attr-defined]
        except Exception as e:
            raise KeyProviderError(
                f"KMS generate_data_key failed for {alias!r}: {e}",
            ) from e
        wrapped = resp.get("CiphertextBlob") if isinstance(resp, dict) else None
        if not isinstance(wrapped, (bytes, bytearray)):
            raise KeyProviderError(
                f"KMS response missing CiphertextBlob for {alias!r}",
            )
        return KeyMaterial(
            graph_id=graph_id,
            key_id=alias,
            wrapped_data_key=bytes(wrapped),
        )

    def lookup(self, *, graph_id: str) -> KeyMaterial | None:
        # KMS doesn't store wrapped data keys; the substrate's
        # catalog (substrate/ducklake/catalog.py) does. This stub
        # always returns None; production wires the catalog lookup.
        return None

    def rotate(self, *, graph_id: str) -> KeyMaterial:
        return self.generate_data_key(graph_id=graph_id)

    def revoke(self, *, graph_id: str) -> None:
        alias = self._alias_for(graph_id)
        try:
            self.client.disable_key(KeyId=alias)  # type: ignore[attr-defined]
        except Exception as e:
            raise KeyProviderError(
                f"KMS disable_key failed for {alias!r}: {e}",
            ) from e
