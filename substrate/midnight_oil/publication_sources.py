"""Closed reviewed-publication authority for paid Midnight Oil gathers.

The immutable collective revision is the review boundary.  This module turns
only its canonical arXiv/Substack handles into a signed, bounded manifest and
validates connector results before any provider receives them.  It performs no
ambient network access; production connectors are explicit injections.
"""

from __future__ import annotations

import hashlib
import json
from collections.abc import Callable, Sequence
from typing import Any, Literal, Protocol
from urllib.parse import urlparse

from pydantic import BaseModel, ConfigDict, Field, model_validator

from substrate.engagement_spine.store import EngagementStore

MAX_REVIEWED_SOURCES = 64
MAX_MANIFEST_BYTES = 256_000
MAX_EXCERPT_BYTES = 32_000
SourceKind = Literal["arxiv", "substack"]
AcquisitionMode = Literal["arxiv_abstract", "substack_bounded_excerpt"]
RightsUse = Literal["metadata_abstract_research", "operator_authorized_excerpt"]

_MANIFEST_DOMAIN = b"antiek.midnight-oil.reviewed-publications.v1\x00"


class _Closed(BaseModel):
    model_config = ConfigDict(extra="forbid", strict=True, frozen=True)


class ReviewedPublicationSource(_Closed):
    ref_id: str = Field(pattern=r"^sref_[0-9a-f]{16}$")
    kind: SourceKind
    canonical_url: str = Field(min_length=1, max_length=2_048)
    external_id: str = Field(min_length=1, max_length=1_024)
    acquisition_mode: AcquisitionMode
    rights_use: RightsUse
    max_excerpt_bytes: int = Field(ge=256, le=MAX_EXCERPT_BYTES)

    @model_validator(mode="after")
    def _identity_contract(self) -> ReviewedPublicationSource:
        parsed = urlparse(self.canonical_url)
        if (
            parsed.scheme != "https"
            or parsed.query
            or parsed.fragment
            or parsed.port not in {None, 443}
        ):
            raise ValueError("reviewed publication URL is outside the closed transport contract")
        if self.kind == "arxiv":
            expected_url = f"https://arxiv.org/abs/{self.external_id}"
            expected_ref_id = "sref_" + hashlib.sha256(
                f"arxiv:arxiv:{self.external_id}".encode()
            ).hexdigest()[:16]
            if (
                self.acquisition_mode != "arxiv_abstract"
                or self.rights_use != "metadata_abstract_research"
                or self.canonical_url != expected_url
                or parsed.hostname != "arxiv.org"
                or self.ref_id != expected_ref_id
            ):
                raise ValueError("arXiv reviewed source identity is not canonical")
        else:
            host = (parsed.hostname or "").lower()
            expected_ref_id = "sref_" + hashlib.sha256(
                f"substack:substack:{self.external_id}".encode()
            ).hexdigest()[:16]
            if (
                self.acquisition_mode != "substack_bounded_excerpt"
                or self.rights_use != "operator_authorized_excerpt"
                or not host.endswith(".substack.com")
                or parsed.path.count("/") != 2
                or f"{host}{parsed.path}" != self.external_id
                or self.ref_id != expected_ref_id
            ):
                raise ValueError("Substack reviewed source identity is not canonical")
        return self


class ReviewedPublicationManifest(_Closed):
    schema_version: Literal[1] = 1
    rights_policy_id: Literal["antiek-publication-research-v1"] = (
        "antiek-publication-research-v1"
    )
    connector_capability_id: Literal["reviewed-publications-v1"] = (
        "reviewed-publications-v1"
    )
    sources: tuple[ReviewedPublicationSource, ...] = Field(max_length=MAX_REVIEWED_SOURCES)
    manifest_sha256: str = Field(pattern=r"^[0-9a-f]{64}$")

    @model_validator(mode="after")
    def _canonical(self) -> ReviewedPublicationManifest:
        identities = [(row.kind, row.external_id) for row in self.sources]
        if identities != sorted(identities) or len(set(identities)) != len(identities):
            raise ValueError("reviewed publication sources must be unique and canonical")
        if self.manifest_sha256 != publication_manifest_sha256(self.sources):
            raise ValueError("reviewed publication manifest hash conflicts")
        if len(self.model_dump_json().encode("utf-8")) > MAX_MANIFEST_BYTES:
            raise ValueError("reviewed publication manifest exceeds byte cap")
        return self


class AcquiredPublicationExcerpt(_Closed):
    ref_id: str = Field(pattern=r"^sref_[0-9a-f]{16}$")
    kind: SourceKind
    canonical_url: str = Field(min_length=1, max_length=2_048)
    external_id: str = Field(min_length=1, max_length=1_024)
    connector: Literal["acquisition.arxiv", "acquisition.substack"]
    connector_version: str = Field(min_length=1, max_length=128)
    publication_capability_sha256: str = Field(pattern=r"^[0-9a-f]{64}$")
    extraction_mode: Literal["metadata_abstract", "bounded_excerpt"]
    truncation_reason: Literal["not_applicable", "explicit_range", "source_truncated"]
    source_length: int | None = Field(default=None, ge=1, le=100_000_000)
    acquisition_mode: AcquisitionMode
    rights_use: RightsUse
    rights_tier: Literal["T1", "T2", "T3", "not_applicable"]
    truncated: bool
    text: str = Field(min_length=1, max_length=32_000)
    excerpt_sha256: str = Field(pattern=r"^[0-9a-f]{64}$")
    excerpt_bytes: int = Field(ge=1, le=MAX_EXCERPT_BYTES)

    @model_validator(mode="after")
    def _content_contract(self) -> AcquiredPublicationExcerpt:
        encoded = self.text.encode("utf-8")
        if self.excerpt_bytes != len(encoded) or self.excerpt_sha256 != hashlib.sha256(
            encoded
        ).hexdigest():
            raise ValueError("publication excerpt bytes conflict with its receipt")
        if self.kind == "arxiv" and self.connector != "acquisition.arxiv":
            raise ValueError("arXiv excerpt has the wrong connector")
        if self.kind == "substack" and self.connector != "acquisition.substack":
            raise ValueError("Substack excerpt has the wrong connector")
        if self.kind == "arxiv" and (
            self.extraction_mode != "metadata_abstract"
            or self.truncation_reason != "not_applicable"
        ):
            raise ValueError("arXiv excerpt scope is inconsistent")
        if self.kind == "substack" and (
            self.extraction_mode != "bounded_excerpt"
            or self.truncation_reason == "not_applicable"
        ):
            raise ValueError("Substack excerpt scope is unproven")
        return self


class PublicationAcquirer(Protocol):
    def __call__(self, source: ReviewedPublicationSource) -> AcquiredPublicationExcerpt: ...


def build_reviewed_publication_manifest(
    references: Sequence[dict[str, Any]], *, max_excerpt_bytes: int = MAX_EXCERPT_BYTES
) -> ReviewedPublicationManifest:
    """Freeze exact eligible handles from an already-confirmed collective row."""
    if not 256 <= max_excerpt_bytes <= MAX_EXCERPT_BYTES:
        raise ValueError("publication excerpt cap is outside the contract")
    rows: list[ReviewedPublicationSource] = []
    for raw in references:
        if not isinstance(raw, dict):
            raise ValueError("collective source reference requires reconciliation")
        kind = raw.get("kind")
        if kind not in {"arxiv", "substack"}:
            raise ValueError("reviewed collective contains an unsupported publication source")
        if kind == "substack":
            raise ValueError(
                "reviewed Substack acquisition requires an explicit authorization receipt"
            )
        canonical_url = raw.get("canonical_url")
        external_id = raw.get("external_id")
        ref_id = raw.get("ref_id")
        if (
            not isinstance(canonical_url, str)
            or not canonical_url
            or not isinstance(external_id, str)
            or not external_id
            or not isinstance(ref_id, str)
            or not ref_id
        ):
            raise ValueError("reviewed publication identity is incomplete")
        parsed = urlparse(canonical_url)
        if parsed.scheme != "https" or parsed.query or parsed.fragment or parsed.port not in {
            None,
            443,
        }:
            raise ValueError("reviewed publication URL is outside the closed transport contract")
        if kind == "arxiv":
            expected_ref_id = "sref_" + hashlib.sha256(
                f"arxiv:arxiv:{external_id}".encode()
            ).hexdigest()[:16]
            if parsed.hostname != "arxiv.org" or parsed.path != f"/abs/{external_id}":
                raise ValueError("reviewed arXiv identity must be a canonical abs URL")
        else:
            host = (parsed.hostname or "").lower()
            if not host.endswith(".substack.com") or parsed.path.count("/") != 2:
                raise ValueError("reviewed Substack v1 requires a substack.com post URL")
            expected_ref_id = "sref_" + hashlib.sha256(
                f"substack:substack:{external_id}".encode()
            ).hexdigest()[:16]
        if ref_id != expected_ref_id:
            raise ValueError("reviewed publication ref id conflicts with canonical identity")
        rows.append(
            ReviewedPublicationSource(
                ref_id=ref_id,
                kind=kind,
                canonical_url=canonical_url,
                external_id=external_id,
                acquisition_mode=(
                    "arxiv_abstract" if kind == "arxiv" else "substack_bounded_excerpt"
                ),
                rights_use=(
                    "metadata_abstract_research"
                    if kind == "arxiv"
                    else "operator_authorized_excerpt"
                ),
                max_excerpt_bytes=max_excerpt_bytes,
            )
        )
    ordered = tuple(sorted(rows, key=lambda row: (row.kind, row.external_id)))
    if len(ordered) > MAX_REVIEWED_SOURCES:
        raise ValueError("reviewed publication source limit exceeded")
    return ReviewedPublicationManifest(
        sources=ordered,
        manifest_sha256=publication_manifest_sha256(ordered),
    )


def acquire_reviewed_publications(
    manifest: ReviewedPublicationManifest,
    *,
    acquire: PublicationAcquirer,
    publication_capability_sha256: str | None = None,
    expected_connector_version: str | None = None,
) -> tuple[AcquiredPublicationExcerpt, ...]:
    """Acquire exactly the signed manifest; connector identity drift fails closed."""
    return _validate_acquired_results(
        manifest,
        tuple(acquire(source) for source in manifest.sources),
        publication_capability_sha256=publication_capability_sha256,
        expected_connector_version=expected_connector_version,
    )


def _validate_acquired_results(
    manifest: ReviewedPublicationManifest,
    results: Sequence[AcquiredPublicationExcerpt],
    *,
    publication_capability_sha256: str | None = None,
    expected_connector_version: str | None = None,
) -> tuple[AcquiredPublicationExcerpt, ...]:
    if len(results) != len(manifest.sources):
        raise ValueError("publication connector results do not cover the signed manifest")
    out: list[AcquiredPublicationExcerpt] = []
    for source, result in zip(manifest.sources, results, strict=True):
        if (
            result.ref_id != source.ref_id
            or result.kind != source.kind
            or result.canonical_url != source.canonical_url
            or result.external_id != source.external_id
            or result.acquisition_mode != source.acquisition_mode
            or result.rights_use != source.rights_use
            or result.excerpt_bytes > source.max_excerpt_bytes
            or (
                expected_connector_version is not None
                and result.connector_version != expected_connector_version
            )
            or (
                publication_capability_sha256 is not None
                and result.publication_capability_sha256
                != publication_capability_sha256
            )
        ):
            raise ValueError("publication connector result escaped signed source authority")
        if source.kind == "arxiv" and result.truncated:
            raise ValueError("arXiv abstract connector cannot report truncated evidence")
        if source.kind == "substack" and not result.truncated:
            raise ValueError("Substack connector must return an explicitly bounded excerpt")
        if result.rights_tier != "T1":
            raise ValueError("publication rights are insufficient for paid model evidence")
        out.append(result)
    return tuple(out)


def manifest_from_authority(payload: dict[str, Any]) -> ReviewedPublicationManifest | None:
    """Recompute owner-authority JSON/hash; incomplete or changed material is fatal."""
    raw = payload.get("publication_manifest_json")
    digest = payload.get("publication_manifest_sha256")
    if raw is None and digest is None:
        return None
    if type(raw) is not str or type(digest) is not str:
        raise ValueError("publication manifest authority is incomplete")
    manifest = ReviewedPublicationManifest.model_validate_json(raw)
    if manifest.manifest_sha256 != digest:
        raise ValueError("publication manifest authority hash conflicts")
    return manifest


def acquire_reviewed_publications_durably(
    manifest: ReviewedPublicationManifest,
    *,
    owner_id: str,
    job_id: str,
    store: EngagementStore,
    acquire: PublicationAcquirer,
    publication_capability_sha256: str = "0" * 64,
    expected_connector_version: str | None = None,
    before_transport: Callable[[], None] | None = None,
) -> tuple[AcquiredPublicationExcerpt, ...]:
    """Persist connector bytes once before any provider; ambiguous claims never refetch."""
    if (
        type(publication_capability_sha256) is not str
        or len(publication_capability_sha256) != 64
        or any(char not in "0123456789abcdef" for char in publication_capability_sha256)
    ):
        raise ValueError("publication acquisition capability hash is invalid")
    logical_id = "psacq_" + hashlib.sha256(
        f"antiek:publication-acquisition:v2\0{owner_id}\0{job_id}\0{manifest.manifest_sha256}"
        f"\0{publication_capability_sha256}".encode()
    ).hexdigest()[:24]
    request_sha = hashlib.sha256(
        b"antiek:publication-acquisition-request:v2\x00"
        + f"{job_id}\0{manifest.manifest_sha256}\0{publication_capability_sha256}".encode()
    ).hexdigest()

    def claim(current: dict[str, Any] | None) -> dict[str, Any]:
        if current is not None:
            if current.get("request_sha256") != request_sha:
                raise ValueError("publication acquisition identity conflicts")
            return current
        return {
            "document_type": "midnight_oil_publication_acquisition",
            "job_id": job_id,
            "publication_manifest_sha256": manifest.manifest_sha256,
            "publication_capability_sha256": publication_capability_sha256,
            "request_sha256": request_sha,
            "state": "claimed",
        }

    row = store.mutate_owned_document(logical_id, owner_id, claim)
    if row.get("state") == "applied":
        results = row.get("results")
        if not isinstance(results, list):
            raise ValueError("publication acquisition checkpoint requires reconciliation")
        parsed = tuple(AcquiredPublicationExcerpt.model_validate(item) for item in results)
        return _validate_acquired_results(
            manifest,
            parsed,
            publication_capability_sha256=publication_capability_sha256,
            expected_connector_version=expected_connector_version,
        )
    if row.get("state") != "claimed" or row.get("claimed_once") is True:
        raise ValueError("publication acquisition claim requires reconciliation")

    # Mark the transport crossing before calling the connector. A process crash
    # after this write is ambiguous and deliberately cannot ambiently refetch.
    def mark_crossing(current: dict[str, Any] | None) -> dict[str, Any]:
        if current is None or current.get("request_sha256") != request_sha:
            raise ValueError("publication acquisition claim disappeared")
        if current.get("state") == "applied":
            return current
        if current.get("state") != "claimed" or current.get("claimed_once") is True:
            raise ValueError("publication acquisition transport was already crossed")
        return {**current, "claimed_once": True}

    if before_transport is not None:
        before_transport()
    store.mutate_owned_document(logical_id, owner_id, mark_crossing)
    results = acquire_reviewed_publications(
        manifest,
        acquire=acquire,
        publication_capability_sha256=publication_capability_sha256,
        expected_connector_version=expected_connector_version,
    )
    result_rows = [item.model_dump(mode="json") for item in results]
    result_sha = hashlib.sha256(
        json.dumps(result_rows, sort_keys=True, separators=(",", ":")).encode()
    ).hexdigest()

    def settle(current: dict[str, Any] | None) -> dict[str, Any]:
        if (
            current is None
            or current.get("request_sha256") != request_sha
            or current.get("claimed_once") is not True
        ):
            raise ValueError("publication acquisition settlement lost authority")
        if current.get("state") == "applied":
            if current.get("result_sha256") != result_sha:
                raise ValueError("publication acquisition result conflicts")
            return current
        return {
            **current,
            "state": "applied",
            "result_sha256": result_sha,
            "results": result_rows,
        }

    settled = store.mutate_owned_document(logical_id, owner_id, settle)
    if settled.get("result_sha256") != result_sha:
        raise ValueError("publication acquisition settlement requires reconciliation")
    return results


def publication_manifest_sha256(sources: Sequence[ReviewedPublicationSource]) -> str:
    material = {
        "schema_version": 1,
        "rights_policy_id": "antiek-publication-research-v1",
        "connector_capability_id": "reviewed-publications-v1",
        "sources": [row.model_dump(mode="json") for row in sources],
    }
    encoded = json.dumps(material, sort_keys=True, separators=(",", ":")).encode()
    return hashlib.sha256(_MANIFEST_DOMAIN + encoded).hexdigest()


def acquired_excerpt(
    source: ReviewedPublicationSource,
    *,
    text: str,
    connector: Literal["acquisition.arxiv", "acquisition.substack"],
    rights_tier: Literal["T1", "T2", "T3", "not_applicable"],
    truncated: bool,
    connector_version: str = "test-injected-v1",
    source_length: int | None = None,
    publication_capability_sha256: str = "0" * 64,
) -> AcquiredPublicationExcerpt:
    encoded = text.encode("utf-8")
    return AcquiredPublicationExcerpt(
        ref_id=source.ref_id,
        kind=source.kind,
        canonical_url=source.canonical_url,
        external_id=source.external_id,
        connector=connector,
        connector_version=connector_version,
        publication_capability_sha256=publication_capability_sha256,
        extraction_mode=(
            "metadata_abstract" if source.kind == "arxiv" else "bounded_excerpt"
        ),
        truncation_reason=(
            "not_applicable"
            if source.kind == "arxiv"
            else "source_truncated"
            if truncated
            else "explicit_range"
        ),
        source_length=source_length,
        acquisition_mode=source.acquisition_mode,
        rights_use=source.rights_use,
        rights_tier=rights_tier,
        truncated=truncated,
        text=text,
        excerpt_sha256=hashlib.sha256(encoded).hexdigest(),
        excerpt_bytes=len(encoded),
    )


__all__ = [
    "AcquiredPublicationExcerpt",
    "PublicationAcquirer",
    "ReviewedPublicationManifest",
    "ReviewedPublicationSource",
    "acquire_reviewed_publications",
    "acquire_reviewed_publications_durably",
    "acquired_excerpt",
    "build_reviewed_publication_manifest",
    "manifest_from_authority",
    "publication_manifest_sha256",
]
