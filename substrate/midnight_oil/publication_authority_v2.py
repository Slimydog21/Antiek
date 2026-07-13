"""Pure mixed-source publication authority for Midnight Oil review.

This module freezes manifest-v2 bytes without making them executable.  ArXiv
rows bind the existing connector-egress capability; Substack rows bind an
owner-private authorization and receipt.  No function performs I/O, creates a
job, or grants provider use.
"""

from __future__ import annotations

import hashlib
import json
from collections.abc import Mapping, Sequence
from typing import Annotated, Literal

from pydantic import BaseModel, ConfigDict, Field, model_validator

from .publication_capability import PublicationConnectorCapability
from .publication_sources import (
    MAX_MANIFEST_BYTES,
    MAX_REVIEWED_SOURCES,
    ReviewedPublicationManifest,
    ReviewedPublicationSource,
)
from .substack_authorization import (
    MAX_SUBSTACK_EXCERPT_BYTES,
    SUBSTACK_PROVIDER_CONSTRAINTS_SHA256,
    SubstackExcerptReceipt,
    SubstackUseAuthorizationV2,
    canonical_substack_post,
)
from .substack_review import ConfirmedSubstackReviewOverlay

_MANIFEST_V2_DOMAIN = b"antiek.midnight-oil.reviewed-publications.v2\x00"


class _Closed(BaseModel):
    model_config = ConfigDict(extra="forbid", strict=True, frozen=True)


class ArxivEgressAuthorityV2(_Closed):
    authority_kind: Literal["arxiv_egress_v1"] = "arxiv_egress_v1"
    capability_id: Literal["midnight-oil-arxiv-abstract-v1"] = "midnight-oil-arxiv-abstract-v1"
    connector_id: Literal["acquisition.arxiv.atom"] = "acquisition.arxiv.atom"
    publication_capability_sha256: str = Field(pattern=r"^[0-9a-f]{64}$")
    max_excerpt_bytes: int = Field(ge=256, le=32_000)
    not_before_ms: int = Field(ge=0)
    expires_at_ms: int = Field(gt=0)
    rights_tier: Literal["T1"] = "T1"
    rights_use: Literal["metadata_abstract_research"] = "metadata_abstract_research"
    capability_verification_state: Literal["content_bound_live_state_unverified"] = (
        "content_bound_live_state_unverified"
    )
    confers_execution_authority: Literal[False] = False

    @model_validator(mode="after")
    def _validity_contract(self) -> ArxivEgressAuthorityV2:
        if self.not_before_ms >= self.expires_at_ms:
            raise ValueError("arXiv egress authority validity conflicts")
        return self


class ProviderProcessingUnavailableV2(_Closed):
    authority_kind: Literal["provider_processing_unavailable_v1"] = (
        "provider_processing_unavailable_v1"
    )
    reason_code: Literal["compatible_provider_capability_missing"] = (
        "compatible_provider_capability_missing"
    )
    confers_execution_authority: Literal[False] = False


class ProviderProcessingCapabilityReferenceV2(_Closed):
    authority_kind: Literal["provider_processing_capability_reference_v1"] = (
        "provider_processing_capability_reference_v1"
    )
    capability_sha256: str = Field(pattern=r"^[0-9a-f]{64}$")
    provider_constraints_sha256: str = Field(
        default=SUBSTACK_PROVIDER_CONSTRAINTS_SHA256, pattern=r"^[0-9a-f]{64}$"
    )
    reference_only: Literal[True] = True
    verification_state: Literal["live_registry_resolution_required"] = (
        "live_registry_resolution_required"
    )
    confers_execution_authority: Literal[False] = False

    @model_validator(mode="after")
    def _policy_contract(self) -> ProviderProcessingCapabilityReferenceV2:
        if self.provider_constraints_sha256 != SUBSTACK_PROVIDER_CONSTRAINTS_SHA256:
            raise ValueError("provider processing capability reference policy conflicts")
        return self


ProviderProcessingAuthorityV2 = Annotated[
    ProviderProcessingUnavailableV2 | ProviderProcessingCapabilityReferenceV2,
    Field(discriminator="authority_kind"),
]


class SubstackOwnerPrivateExcerptAuthorityV2(_Closed):
    authority_kind: Literal["substack_owner_private_excerpt_v2"] = (
        "substack_owner_private_excerpt_v2"
    )
    owner_scope_sha256: str = Field(pattern=r"^[0-9a-f]{64}$")
    collective_unit_id: str = Field(pattern=r"^cunit_[0-9a-f]{24}$")
    collective_preview_sha256: str = Field(pattern=r"^[0-9a-f]{64}$")
    ref_id: str = Field(pattern=r"^sref_[0-9a-f]{16}$")
    canonical_url: str = Field(min_length=1, max_length=2_048)
    external_id: str = Field(min_length=1, max_length=1_024)
    overlay_id: str = Field(pattern=r"^csubrev_[0-9a-f]{24}$")
    overlay_sha256: str = Field(pattern=r"^[0-9a-f]{64}$")
    authorization_id: str = Field(pattern=r"^sua_[0-9a-f]{24}$")
    authorization_sha256: str = Field(pattern=r"^[0-9a-f]{64}$")
    receipt_id: str = Field(pattern=r"^suer_[0-9a-f]{24}$")
    receipt_sha256: str = Field(pattern=r"^[0-9a-f]{64}$")
    representation_evidence: Literal["owner_attestation_unverified"] = (
        "owner_attestation_unverified"
    )
    source_representation_sha256: str = Field(pattern=r"^[0-9a-f]{64}$")
    source_representation_bytes: int = Field(ge=1, le=100_000_000)
    source_byte_start: int = Field(ge=0)
    source_byte_end: int = Field(gt=0)
    excerpt_sha256: str = Field(pattern=r"^[0-9a-f]{64}$")
    excerpt_bytes: int = Field(ge=1, le=MAX_SUBSTACK_EXCERPT_BYTES)
    expires_at_ms: int = Field(gt=0)
    content_class: Literal["personal_reading"] = "personal_reading"
    rights_tier: Literal["not_applicable"] = "not_applicable"
    rights_use: Literal["operator_authorized_excerpt"] = "operator_authorized_excerpt"
    provider_constraints_sha256: str = Field(pattern=r"^[0-9a-f]{64}$")
    provider_processing_authority: ProviderProcessingAuthorityV2
    authorization_verification_state: Literal["content_bound_live_state_unverified"] = (
        "content_bound_live_state_unverified"
    )
    confers_execution_authority: Literal[False] = False

    @model_validator(mode="after")
    def _range_contract(self) -> SubstackOwnerPrivateExcerptAuthorityV2:
        canonical_substack_post(self.canonical_url, self.external_id)
        expected_ref_id = (
            "sref_"
            + hashlib.sha256(f"substack:substack:{self.external_id}".encode()).hexdigest()[:16]
        )
        if (
            self.ref_id != expected_ref_id
            or self.provider_constraints_sha256 != SUBSTACK_PROVIDER_CONSTRAINTS_SHA256
            or self.source_byte_end > self.source_representation_bytes
            or self.source_byte_end - self.source_byte_start != self.excerpt_bytes
            or (
                self.source_byte_start == 0
                and self.source_byte_end == self.source_representation_bytes
            )
        ):
            raise ValueError("Substack authority range conflicts")
        return self


PublicationAuthorityV2 = Annotated[
    ArxivEgressAuthorityV2 | SubstackOwnerPrivateExcerptAuthorityV2,
    Field(discriminator="authority_kind"),
]


class ReviewedPublicationAuthorityRowV2(_Closed):
    source: ReviewedPublicationSource
    authority: PublicationAuthorityV2

    @model_validator(mode="after")
    def _kind_contract(self) -> ReviewedPublicationAuthorityRowV2:
        if self.source.kind == "arxiv":
            if not isinstance(self.authority, ArxivEgressAuthorityV2):
                raise ValueError("arXiv source requires arXiv egress authority")
            if (
                self.source.acquisition_mode != "arxiv_abstract"
                or self.source.max_excerpt_bytes > self.authority.max_excerpt_bytes
            ):
                raise ValueError("arXiv source authority mode conflicts")
        else:
            authority = self.authority
            if not isinstance(authority, SubstackOwnerPrivateExcerptAuthorityV2):
                raise ValueError("Substack source requires owner-private authority")
            if (
                self.source.acquisition_mode != "substack_bounded_excerpt"
                or self.source.max_excerpt_bytes > MAX_SUBSTACK_EXCERPT_BYTES
                or authority.excerpt_bytes > self.source.max_excerpt_bytes
                or authority.ref_id != self.source.ref_id
                or authority.canonical_url != self.source.canonical_url
                or authority.external_id != self.source.external_id
            ):
                raise ValueError("Substack source authority scope conflicts")
        return self


class ReviewedPublicationManifestV2(_Closed):
    schema_version: Literal[2] = 2
    purpose: Literal["authority_binding_only"] = "authority_binding_only"
    confers_execution_authority: Literal[False] = False
    authority_policy_id: Literal["antiek-reviewed-publication-authority-v2"] = (
        "antiek-reviewed-publication-authority-v2"
    )
    collective_unit_id: str = Field(pattern=r"^cunit_[0-9a-f]{24}$")
    collective_preview_sha256: str = Field(pattern=r"^[0-9a-f]{64}$")
    sources: tuple[ReviewedPublicationAuthorityRowV2, ...] = Field(
        min_length=1, max_length=MAX_REVIEWED_SOURCES
    )
    manifest_sha256: str = Field(pattern=r"^[0-9a-f]{64}$")

    @model_validator(mode="after")
    def _canonical(self) -> ReviewedPublicationManifestV2:
        identities = [
            (row.source.kind, row.source.external_id, row.source.ref_id) for row in self.sources
        ]
        ref_ids = [row.source.ref_id for row in self.sources]
        if (
            identities != sorted(identities)
            or len(set(identities)) != len(identities)
            or len(set(ref_ids)) != len(ref_ids)
        ):
            raise ValueError("reviewed publication v2 sources must be unique and canonical")
        if not any(
            isinstance(row.authority, SubstackOwnerPrivateExcerptAuthorityV2)
            for row in self.sources
        ):
            raise ValueError("manifest v2 requires owner-private Substack authority")
        for row in self.sources:
            if isinstance(row.authority, SubstackOwnerPrivateExcerptAuthorityV2) and (
                row.authority.collective_unit_id != self.collective_unit_id
                or row.authority.collective_preview_sha256 != self.collective_preview_sha256
            ):
                raise ValueError("Substack authority collective binding conflicts")
        if self.manifest_sha256 != publication_manifest_v2_sha256(
            collective_unit_id=self.collective_unit_id,
            collective_preview_sha256=self.collective_preview_sha256,
            sources=self.sources,
        ):
            raise ValueError("reviewed publication v2 manifest hash conflicts")
        if len(self.model_dump_json().encode("utf-8")) > MAX_MANIFEST_BYTES:
            raise ValueError("reviewed publication v2 manifest exceeds byte cap")
        return self


ReviewedPublicationManifestAny = ReviewedPublicationManifest | ReviewedPublicationManifestV2


def _canonical(value: Mapping[str, object]) -> bytes:
    return json.dumps(value, sort_keys=True, separators=(",", ":"), ensure_ascii=False).encode()


def publication_manifest_v2_sha256(
    *,
    collective_unit_id: str,
    collective_preview_sha256: str,
    sources: Sequence[ReviewedPublicationAuthorityRowV2],
) -> str:
    material: dict[str, object] = {
        "schema_version": 2,
        "purpose": "authority_binding_only",
        "confers_execution_authority": False,
        "authority_policy_id": "antiek-reviewed-publication-authority-v2",
        "collective_unit_id": collective_unit_id,
        "collective_preview_sha256": collective_preview_sha256,
        "sources": [row.model_dump(mode="json") for row in sources],
    }
    return hashlib.sha256(_MANIFEST_V2_DOMAIN + _canonical(material)).hexdigest()


def build_reviewed_publication_manifest_v2(
    *,
    collective_unit_id: str,
    collective_preview_sha256: str,
    sources: Sequence[ReviewedPublicationAuthorityRowV2],
) -> ReviewedPublicationManifestV2:
    ordered = tuple(
        sorted(
            sources, key=lambda row: (row.source.kind, row.source.external_id, row.source.ref_id)
        )
    )
    if len(ordered) > MAX_REVIEWED_SOURCES:
        raise ValueError("reviewed publication v2 source limit exceeded")
    return ReviewedPublicationManifestV2(
        collective_unit_id=collective_unit_id,
        collective_preview_sha256=collective_preview_sha256,
        sources=ordered,
        manifest_sha256=publication_manifest_v2_sha256(
            collective_unit_id=collective_unit_id,
            collective_preview_sha256=collective_preview_sha256,
            sources=ordered,
        ),
    )


def arxiv_authority_row_v2(
    source: ReviewedPublicationSource, *, capability: PublicationConnectorCapability
) -> ReviewedPublicationAuthorityRowV2:
    if (
        source.kind != "arxiv"
        or source.acquisition_mode != capability.acquisition_mode
        or source.rights_use != "metadata_abstract_research"
        or source.max_excerpt_bytes > capability.max_excerpt_bytes
    ):
        raise ValueError("arXiv source escapes connector capability")
    return ReviewedPublicationAuthorityRowV2(
        source=source,
        authority=ArxivEgressAuthorityV2(
            publication_capability_sha256=capability.capability_sha256,
            max_excerpt_bytes=capability.max_excerpt_bytes,
            not_before_ms=capability.not_before_ms,
            expires_at_ms=capability.expires_at_ms,
        ),
    )


def substack_authority_row_v2(
    *,
    source: ReviewedPublicationSource,
    authorization: SubstackUseAuthorizationV2,
    receipt: SubstackExcerptReceipt,
    overlay: ConfirmedSubstackReviewOverlay,
) -> ReviewedPublicationAuthorityRowV2:
    """Cross-bind validated owner-private artifacts without serializing excerpt text."""
    common = (
        source.ref_id,
        source.canonical_url,
        source.external_id,
    )
    if (
        source.kind != "substack"
        or common
        != (
            authorization.ref_id,
            authorization.canonical_url,
            authorization.external_id,
        )
        or common != (receipt.ref_id, receipt.canonical_url, receipt.external_id)
    ):
        raise ValueError("Substack authority source identity conflicts")
    if (
        overlay.collective_unit_id != authorization.collective_unit_id
        or overlay.collective_preview_sha256 != authorization.collective_preview_sha256
        or overlay.ref_id != authorization.ref_id
        or overlay.authorization_id != authorization.authorization_id
        or overlay.authorization_sha256 != authorization.authorization_sha256
        or overlay.receipt_id != receipt.receipt_id
        or overlay.receipt_sha256 != receipt.receipt_sha256
        or receipt.authorization_id != authorization.authorization_id
        or receipt.authorization_sha256 != authorization.authorization_sha256
        or receipt.owner_scope_sha256 != authorization.owner_scope_sha256
        or receipt.collective_unit_id != authorization.collective_unit_id
        or receipt.collective_preview_sha256 != authorization.collective_preview_sha256
        or receipt.excerpt_sha256 != authorization.excerpt_sha256
        or receipt.excerpt_bytes != authorization.excerpt_bytes
        or receipt.source_representation_sha256 != authorization.source_representation_sha256
        or receipt.source_representation_bytes != authorization.source_representation_bytes
        or receipt.source_byte_start != authorization.source_byte_start
        or receipt.source_byte_end != authorization.source_byte_end
        or receipt.injected_at_ms != authorization.not_before_ms
        or overlay.excerpt_sha256 != receipt.excerpt_sha256
        or overlay.excerpt_bytes != receipt.excerpt_bytes
        or overlay.source_byte_start != receipt.source_byte_start
        or overlay.source_byte_end != receipt.source_byte_end
        or overlay.expires_at_ms != authorization.expires_at_ms
        or overlay.provider_constraints_sha256 != authorization.provider_constraints_sha256
    ):
        raise ValueError("Substack authority artifact binding conflicts")
    return ReviewedPublicationAuthorityRowV2(
        source=source,
        authority=SubstackOwnerPrivateExcerptAuthorityV2(
            owner_scope_sha256=authorization.owner_scope_sha256,
            collective_unit_id=authorization.collective_unit_id,
            collective_preview_sha256=authorization.collective_preview_sha256,
            ref_id=authorization.ref_id,
            canonical_url=authorization.canonical_url,
            external_id=authorization.external_id,
            overlay_id=overlay.overlay_id,
            overlay_sha256=overlay.overlay_sha256,
            authorization_id=authorization.authorization_id,
            authorization_sha256=authorization.authorization_sha256,
            receipt_id=receipt.receipt_id,
            receipt_sha256=receipt.receipt_sha256,
            source_representation_sha256=receipt.source_representation_sha256,
            source_representation_bytes=receipt.source_representation_bytes,
            source_byte_start=receipt.source_byte_start,
            source_byte_end=receipt.source_byte_end,
            excerpt_sha256=receipt.excerpt_sha256,
            excerpt_bytes=receipt.excerpt_bytes,
            expires_at_ms=authorization.expires_at_ms,
            provider_constraints_sha256=authorization.provider_constraints_sha256,
            provider_processing_authority=ProviderProcessingUnavailableV2(),
        ),
    )


def _reject_duplicate_keys(pairs: list[tuple[str, object]]) -> dict[str, object]:
    out: dict[str, object] = {}
    for key, value in pairs:
        if key in out:
            raise ValueError("publication manifest contains duplicate JSON keys")
        out[key] = value
    return out


def parse_reviewed_publication_manifest_json(raw: str) -> ReviewedPublicationManifestAny:
    """Strictly dispatch manifest versions without downgrade inference."""
    if type(raw) is not str or not raw or len(raw.encode("utf-8")) > MAX_MANIFEST_BYTES:
        raise ValueError("publication manifest JSON is invalid")
    try:
        payload = json.loads(raw, object_pairs_hook=_reject_duplicate_keys)
    except (json.JSONDecodeError, UnicodeError) as exc:
        raise ValueError("publication manifest JSON is invalid") from exc
    if type(payload) is not dict:
        raise ValueError("publication manifest JSON is invalid")
    version = payload.get("schema_version")
    if type(version) is not int:
        raise ValueError("publication manifest schema version is invalid")
    sources = payload.get("sources")
    if type(sources) is list:
        payload = {**payload, "sources": tuple(sources)}
    if version == 1:
        return ReviewedPublicationManifest.model_validate(payload)
    if version == 2:
        return ReviewedPublicationManifestV2.model_validate(payload)
    raise ValueError("publication manifest schema version is unsupported")


__all__ = [
    "ArxivEgressAuthorityV2",
    "ProviderProcessingCapabilityReferenceV2",
    "ProviderProcessingUnavailableV2",
    "ReviewedPublicationAuthorityRowV2",
    "ReviewedPublicationManifestAny",
    "ReviewedPublicationManifestV2",
    "SubstackOwnerPrivateExcerptAuthorityV2",
    "arxiv_authority_row_v2",
    "build_reviewed_publication_manifest_v2",
    "parse_reviewed_publication_manifest_json",
    "publication_manifest_v2_sha256",
    "substack_authority_row_v2",
]
