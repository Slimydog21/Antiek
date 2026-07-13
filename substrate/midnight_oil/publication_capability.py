"""Signed, expiring authority for Midnight Oil publication egress.

The capability file is an operator authorization, not a readiness hint.  API
and worker load it independently, verify the same signature and compiled
adapter contract, then pin its content hash into job/consent authority.
"""

from __future__ import annotations

import hashlib
import hmac
import json
from collections.abc import Mapping, Sequence
from pathlib import Path
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field, model_validator

from .publication_sources import ReviewedPublicationManifest

MAX_CAPABILITY_FILE_BYTES = 64_000
MAX_CAPABILITY_LIFETIME_MS = 31 * 24 * 60 * 60 * 1000
ARXIV_ABSTRACT_ADAPTER_CONTRACT_SHA256 = hashlib.sha256(
    b"antiek.acquisition.arxiv.midnight-oil-abstract-adapter.v1"
).hexdigest()
PUBLICATION_RIGHTS_POLICY_SHA256 = hashlib.sha256(
    b"antiek.publication-rights.v1\x00arxiv-abstract:T1:metadata_abstract_research"
).hexdigest()
_CAPABILITY_DOMAIN = b"antiek.midnight-oil.publication-capability.v1\x00"
_SIGNATURE_DOMAIN = b"antiek.midnight-oil.publication-capability-signature.v1\x00"


class PublicationConnectorCapability(BaseModel):
    """One immutable arXiv-abstract connector authorization."""

    model_config = ConfigDict(extra="forbid", strict=True, frozen=True)

    schema_version: Literal[1] = 1
    capability_id: Literal["midnight-oil-arxiv-abstract-v1"]
    connector_id: Literal["acquisition.arxiv.atom"]
    connector_version: Literal["midnight-oil-arxiv-abstract-v1"]
    adapter_contract_sha256: str = Field(pattern=r"^[0-9a-f]{64}$")
    source_kind: Literal["arxiv"]
    acquisition_mode: Literal["arxiv_abstract"]
    extraction_mode: Literal["metadata_abstract"]
    rights_policy_id: Literal["antiek-publication-research-v1"]
    rights_policy_sha256: str = Field(pattern=r"^[0-9a-f]{64}$")
    allowed_rights_tiers: tuple[Literal["T1"], ...] = Field(min_length=1, max_length=1)
    scheme: Literal["https"]
    host: Literal["export.arxiv.org"]
    port: Literal[443]
    path: Literal["/api/query"]
    request_mode: Literal["id_list_single"]
    redirect_policy: Literal["deny"]
    proxy_policy: Literal["deny"]
    dns_policy: Literal["resolve-on-connect-public-only-v1"]
    tls_policy: Literal["system-ca-hostname-tls12-v1"]
    rate_governor_id: Literal["arxiv-host-global-v1"]
    max_response_bytes: int = Field(ge=65_536, le=1_000_000)
    max_excerpt_bytes: int = Field(ge=256, le=32_000)
    timeout_ms: int = Field(ge=1_000, le=60_000)
    issued_at_ms: int = Field(ge=0)
    not_before_ms: int = Field(ge=0)
    expires_at_ms: int = Field(gt=0)
    evidence_ref: str = Field(min_length=1, max_length=2_048)
    key_id: str = Field(pattern=r"^[A-Za-z0-9._-]{1,128}$")
    capability_sha256: str = Field(pattern=r"^[0-9a-f]{64}$")
    signature_sha256: str = Field(pattern=r"^[0-9a-f]{64}$")

    @model_validator(mode="after")
    def _canonical_contract(self) -> PublicationConnectorCapability:
        if self.adapter_contract_sha256 != ARXIV_ABSTRACT_ADAPTER_CONTRACT_SHA256:
            raise ValueError("publication capability adapter contract conflicts")
        if self.rights_policy_sha256 != PUBLICATION_RIGHTS_POLICY_SHA256:
            raise ValueError("publication capability rights policy conflicts")
        if self.allowed_rights_tiers != ("T1",):
            raise ValueError("publication capability rights tiers are not canonical")
        if not self.evidence_ref.startswith(("https://", "urn:")):
            raise ValueError("publication capability evidence must be HTTPS or URN")
        if not self.issued_at_ms <= self.not_before_ms < self.expires_at_ms:
            raise ValueError("publication capability validity interval is invalid")
        if self.expires_at_ms - self.not_before_ms > MAX_CAPABILITY_LIFETIME_MS:
            raise ValueError("publication capability lifetime exceeds the rotation bound")
        if self.capability_sha256 != publication_capability_sha256(self):
            raise ValueError("publication capability hash conflicts")
        return self


def _canonical_material(value: Mapping[str, object]) -> bytes:
    material = dict(value)
    material.pop("capability_sha256", None)
    material.pop("signature_sha256", None)
    return json.dumps(
        material, sort_keys=True, separators=(",", ":"), ensure_ascii=False
    ).encode("utf-8")


def publication_capability_sha256(
    capability: PublicationConnectorCapability | Mapping[str, object],
) -> str:
    raw = (
        capability.model_dump(mode="json")
        if isinstance(capability, PublicationConnectorCapability)
        else capability
    )
    return hashlib.sha256(_CAPABILITY_DOMAIN + _canonical_material(raw)).hexdigest()


def publication_capability_signature(
    capability_sha256: str, *, signing_key: bytes
) -> str:
    if len(signing_key) < 32:
        raise ValueError("publication capability signing key must be at least 256 bits")
    return hmac.digest(
        signing_key, _SIGNATURE_DOMAIN + capability_sha256.encode("ascii"), "sha256"
    ).hex()


def signed_publication_capability(
    material: Mapping[str, object], *, key_id: str, signing_key: bytes
) -> PublicationConnectorCapability:
    """Operator/test helper that closes, hashes, and signs one capability."""
    raw = {**material, "key_id": key_id}
    digest = publication_capability_sha256(raw)
    return PublicationConnectorCapability.model_validate(
        {
            **raw,
            "capability_sha256": digest,
            "signature_sha256": publication_capability_signature(
                digest, signing_key=signing_key
            ),
        }
    )


def _reject_duplicate_keys(pairs: list[tuple[str, object]]) -> dict[str, object]:
    out: dict[str, object] = {}
    for key, value in pairs:
        if key in out:
            raise ValueError("publication capability contains duplicate JSON keys")
        out[key] = value
    return out


def load_publication_capability(
    path: str | Path, *, verification_keys: Mapping[str, bytes]
) -> PublicationConnectorCapability:
    source = Path(path)
    try:
        if not source.is_absolute() or not source.is_file():
            raise ValueError("publication capability path must be an existing absolute file")
        if source.stat().st_size > MAX_CAPABILITY_FILE_BYTES:
            raise ValueError("publication capability file exceeds the size limit")
        raw = json.loads(source.read_text(encoding="utf-8"), object_pairs_hook=_reject_duplicate_keys)
    except ValueError:
        raise
    except (OSError, json.JSONDecodeError) as exc:
        raise ValueError("publication capability file is unreadable") from exc
    if isinstance(raw, dict) and isinstance(raw.get("allowed_rights_tiers"), list):
        raw = {**raw, "allowed_rights_tiers": tuple(raw["allowed_rights_tiers"])}
    capability = PublicationConnectorCapability.model_validate(raw)
    key = verification_keys.get(capability.key_id)
    if key is None:
        raise ValueError("publication capability signing key is unknown")
    expected = publication_capability_signature(
        capability.capability_sha256, signing_key=key
    )
    if not hmac.compare_digest(capability.signature_sha256, expected):
        raise ValueError("publication capability signature is invalid")
    return capability


class PublicationCapabilityRegistry:
    """Closed exact-hash registry shared in shape, not ambient process state."""

    def __init__(self, capabilities: Sequence[PublicationConnectorCapability] = ()) -> None:
        by_hash = {item.capability_sha256: item for item in capabilities}
        if len(by_hash) != len(capabilities):
            raise ValueError("publication capability hashes must be unique")
        self._by_hash = by_hash

    @classmethod
    def from_paths(
        cls,
        paths: Sequence[Path],
        *,
        verification_keys: Mapping[str, bytes],
    ) -> PublicationCapabilityRegistry:
        if len(paths) > 8:
            raise ValueError("publication capability registry exceeds its bound")
        return cls(
            [
                load_publication_capability(path, verification_keys=verification_keys)
                for path in paths
            ]
        )

    @property
    def hashes(self) -> tuple[str, ...]:
        return tuple(sorted(self._by_hash))

    def get(self, capability_sha256: str) -> PublicationConnectorCapability | None:
        return self._by_hash.get(capability_sha256)

    def select(
        self,
        manifest: ReviewedPublicationManifest,
        *,
        now_ms: int,
        required_until_ms: int,
    ) -> PublicationConnectorCapability | None:
        matching = [
            item
            for item in self._by_hash.values()
            if publication_capability_covers(
                item,
                manifest,
                now_ms=now_ms,
                required_until_ms=required_until_ms,
            )
        ]
        if not matching:
            return None
        return max(matching, key=lambda item: (item.expires_at_ms, item.capability_sha256))


def publication_capability_covers(
    capability: PublicationConnectorCapability,
    manifest: ReviewedPublicationManifest,
    *,
    now_ms: int,
    required_until_ms: int,
) -> bool:
    if type(now_ms) is not int or type(required_until_ms) is not int:
        return False
    if not capability.not_before_ms <= now_ms < capability.expires_at_ms:
        return False
    if required_until_ms >= capability.expires_at_ms or required_until_ms < now_ms:
        return False
    if manifest.rights_policy_id != capability.rights_policy_id:
        return False
    return bool(manifest.sources) and all(
        source.kind == capability.source_kind
        and source.acquisition_mode == capability.acquisition_mode
        and source.rights_use == "metadata_abstract_research"
        and source.max_excerpt_bytes <= capability.max_excerpt_bytes
        for source in manifest.sources
    )


def require_pinned_publication_capability(
    registry: PublicationCapabilityRegistry,
    *,
    capability_sha256: str,
    manifest: ReviewedPublicationManifest,
    now_ms: int,
    required_until_ms: int,
) -> PublicationConnectorCapability:
    capability = registry.get(capability_sha256)
    if capability is None or not publication_capability_covers(
        capability,
        manifest,
        now_ms=now_ms,
        required_until_ms=required_until_ms,
    ):
        raise ValueError("pinned publication capability is unavailable or outside authority")
    return capability


__all__ = [
    "ARXIV_ABSTRACT_ADAPTER_CONTRACT_SHA256",
    "PUBLICATION_RIGHTS_POLICY_SHA256",
    "PublicationCapabilityRegistry",
    "PublicationConnectorCapability",
    "load_publication_capability",
    "publication_capability_covers",
    "publication_capability_sha256",
    "publication_capability_signature",
    "require_pinned_publication_capability",
    "signed_publication_capability",
]
