"""Read-only, non-conferring mixed publication readiness projection."""

from __future__ import annotations

import hashlib
import json
import re
from collections.abc import Mapping, Sequence
from typing import Annotated, Literal

from pydantic import BaseModel, ConfigDict, Field

from substrate.engagement_spine.store import EngagementStore

from .publication_authority_v2 import (
    ReviewedPublicationAuthorityRowV2,
    arxiv_authority_row_v2,
    build_reviewed_publication_manifest_v2,
    substack_authority_row_v2,
)
from .publication_capability import PublicationCapabilityRegistry
from .publication_sources import ReviewedPublicationSource, build_reviewed_publication_manifest
from .substack_authorization import (
    MAX_SUBSTACK_EXCERPT_BYTES,
    SubstackUseAuthorizationV2,
    inspect_stored_substack_excerpt_binding,
    stored_substack_authorization_state,
)
from .substack_review import ConfirmedSubstackReviewOverlay, list_confirmed_substack_reviews


class _Closed(BaseModel):
    model_config = ConfigDict(extra="forbid", strict=True, frozen=True)


class ArxivReadinessRowV2(_Closed):
    kind: Literal["arxiv"] = "arxiv"
    ref_id: str = Field(pattern=r"^sref_[0-9a-f]{16}$")
    review_state: Literal["reviewed"] = "reviewed"
    binding_state: Literal["bound", "blocked"]
    live_state: Literal["covered", "unavailable"]
    acquisition: Literal["remote_arxiv_abstract"] = "remote_arxiv_abstract"
    network_egress: Literal[True] = True
    rights_tier: Literal["T1"] = "T1"
    capability_sha256: str | None = Field(default=None, pattern=r"^[0-9a-f]{64}$")
    capability_expires_at_ms: int | None = Field(default=None, gt=0)
    execution_ready: Literal[False] = False
    confers_execution_authority: Literal[False] = False
    reason_codes: tuple[str, ...] = Field(max_length=8)


class SubstackReadinessRowV2(_Closed):
    kind: Literal["substack"] = "substack"
    ref_id: str = Field(pattern=r"^sref_[0-9a-f]{16}$")
    review_state: Literal["reviewed"] = "reviewed"
    binding_state: Literal["bound", "blocked"]
    live_state: Literal[
        "active_at_check",
        "selection_required",
        "not_yet_active",
        "expired",
        "horizon_insufficient",
        "revoked",
        "unavailable",
        "reconciliation_required",
    ]
    acquisition: Literal["owner_supplied_local_excerpt"] = "owner_supplied_local_excerpt"
    network_egress: Literal[False] = False
    privacy: Literal["owner_private"] = "owner_private"
    rights_tier: Literal["not_applicable"] = "not_applicable"
    provider_processing_state: Literal["unavailable"] = "unavailable"
    execution_ready: Literal[False] = False
    confers_execution_authority: Literal[False] = False
    reason_codes: tuple[str, ...] = Field(max_length=8)
    available_reviews: tuple[SubstackReviewChoiceV2, ...] = Field(max_length=64)


class SubstackReviewChoiceV2(_Closed):
    overlay_id: str = Field(pattern=r"^csubrev_[0-9a-f]{24}$")
    overlay_sha256: str = Field(pattern=r"^[0-9a-f]{64}$")
    expires_at_ms: int = Field(gt=0)


class UnsupportedReadinessRowV2(_Closed):
    kind: Literal["unsupported"] = "unsupported"
    ref_id: str = Field(min_length=1, max_length=64)
    review_state: Literal["reviewed"] = "reviewed"
    binding_state: Literal["blocked"] = "blocked"
    live_state: Literal["unavailable"] = "unavailable"
    execution_ready: Literal[False] = False
    confers_execution_authority: Literal[False] = False
    reason_codes: tuple[
        Literal[
            "unsupported_source_kind",
            "invalid_source_reference",
            "duplicate_source_reference",
        ],
        ...,
    ] = ("unsupported_source_kind",)


PublicationReadinessRowV2 = Annotated[
    ArxivReadinessRowV2 | SubstackReadinessRowV2 | UnsupportedReadinessRowV2,
    Field(discriminator="kind"),
]


class MixedPublicationReadinessPreviewV2(_Closed):
    schema_version: Literal[1] = 1
    projection_kind: Literal["mixed_source_readiness_preview"] = "mixed_source_readiness_preview"
    read_only: Literal[True] = True
    applicability: Literal["mixed_v2", "legacy_v1"]
    collective_unit_id: str = Field(pattern=r"^cunit_[0-9a-f]{24}$")
    collective_preview_sha256: str = Field(pattern=r"^[0-9a-f]{64}$")
    duration_minutes: int = Field(ge=1, le=10_080)
    checked_at_ms: int = Field(ge=0)
    required_until_ms: int = Field(gt=0)
    request_fingerprint_sha256: str = Field(pattern=r"^[0-9a-f]{64}$")
    manifest_schema_version: Literal[2] | None
    manifest_sha256: str | None = Field(default=None, pattern=r"^[0-9a-f]{64}$")
    authority_binding_ready: bool
    live_authority_ready: bool
    legacy_prepare_available: bool
    execution_ready: Literal[False] = False
    consent_enabled: Literal[False] = False
    confers_execution_authority: Literal[False] = False
    live_reverification_required: Literal[True] = True
    reason_codes: tuple[str, ...] = Field(max_length=16)
    sources: tuple[PublicationReadinessRowV2, ...] = Field(max_length=64)
    view_format: Literal["html"] = "html"


def preview_mixed_publication_readiness(
    *,
    collective_unit_id: str,
    collective_preview_sha256: str,
    references: Sequence[object],
    owner_id: str,
    store: EngagementStore,
    publication_capabilities: PublicationCapabilityRegistry,
    substack_verification_keys: Mapping[str, bytes],
    selected_overlays: Mapping[str, tuple[str, str]],
    duration_minutes: int,
    checked_at_ms: int,
    required_until_ms: int,
    request_fingerprint_sha256: str,
) -> MixedPublicationReadinessPreviewV2:
    """Observe binding/live state without writes, transport, or authority creation."""
    has_declared_substack = any(
        isinstance(raw, dict) and raw.get("kind") == "substack" for raw in references
    )
    overlays = (
        list_confirmed_substack_reviews(
            store,
            owner_id=owner_id,
            collective_unit_id=collective_unit_id,
            collective_preview_sha256=collective_preview_sha256,
        )
        if has_declared_substack
        else ()
    )
    overlays_by_ref: dict[str, list[ConfirmedSubstackReviewOverlay]] = {}
    for overlay in overlays:
        overlays_by_ref.setdefault(overlay.ref_id, []).append(overlay)

    projection_rows: list[PublicationReadinessRowV2] = []
    authority_rows: list[ReviewedPublicationAuthorityRowV2] = []
    known_ref_ids: set[str] = set()
    has_substack = False
    binding_ready = True
    live_ready = True
    substack_ref_ids: set[str] = set()

    for raw in references:
        if not isinstance(raw, dict):
            binding_ready = False
            digest = hashlib.sha256(
                json.dumps(raw, sort_keys=True, default=str).encode()
            ).hexdigest()[:16]
            projection_rows.append(
                UnsupportedReadinessRowV2(
                    ref_id=f"invalid-{digest}", reason_codes=("invalid_source_reference",)
                )
            )
            continue
        ref_id = raw.get("ref_id")
        kind = raw.get("kind")
        if not isinstance(ref_id, str) or re.fullmatch(r"sref_[0-9a-f]{16}", ref_id) is None:
            binding_ready = False
            digest = hashlib.sha256(
                json.dumps(raw, sort_keys=True, default=str).encode()
            ).hexdigest()[:16]
            projection_rows.append(
                UnsupportedReadinessRowV2(
                    ref_id=f"invalid-{digest}", reason_codes=("invalid_source_reference",)
                )
            )
            continue
        safe_ref_id = ref_id
        if safe_ref_id in known_ref_ids:
            binding_ready = False
            projection_rows.append(
                UnsupportedReadinessRowV2(
                    ref_id=safe_ref_id, reason_codes=("duplicate_source_reference",)
                )
            )
            continue
        known_ref_ids.add(safe_ref_id)

        if kind == "arxiv":
            try:
                manifest_v1 = build_reviewed_publication_manifest([raw])
                source = manifest_v1.sources[0]
            except ValueError:
                binding_ready = False
                projection_rows.append(
                    UnsupportedReadinessRowV2(
                        ref_id=safe_ref_id, reason_codes=("invalid_source_reference",)
                    )
                )
                continue
            try:
                capability = publication_capabilities.select(
                    manifest_v1,
                    now_ms=checked_at_ms,
                    required_until_ms=required_until_ms,
                )
                if capability is None:
                    raise ValueError("capability unavailable")
                authority_rows.append(arxiv_authority_row_v2(source, capability=capability))
                projection_rows.append(
                    ArxivReadinessRowV2(
                        ref_id=source.ref_id,
                        binding_state="bound",
                        live_state="covered",
                        capability_sha256=capability.capability_sha256,
                        capability_expires_at_ms=capability.expires_at_ms,
                        reason_codes=(),
                    )
                )
            except ValueError:
                binding_ready = False
                projection_rows.append(
                    ArxivReadinessRowV2(
                        ref_id=safe_ref_id,
                        binding_state="blocked",
                        live_state="unavailable",
                        reason_codes=("arxiv_capability_unavailable_for_horizon",),
                    )
                )
            continue

        if kind == "substack":
            has_substack = True
            try:
                source = ReviewedPublicationSource(
                    ref_id=safe_ref_id,
                    kind="substack",
                    canonical_url=str(raw.get("canonical_url") or ""),
                    external_id=str(raw.get("external_id") or ""),
                    acquisition_mode="substack_bounded_excerpt",
                    rights_use="operator_authorized_excerpt",
                    max_excerpt_bytes=MAX_SUBSTACK_EXCERPT_BYTES,
                )
            except ValueError:
                binding_ready = False
                live_ready = False
                projection_rows.append(
                    UnsupportedReadinessRowV2(
                        ref_id=safe_ref_id, reason_codes=("invalid_source_reference",)
                    )
                )
                continue
            substack_ref_ids.add(safe_ref_id)
            selection = selected_overlays.get(safe_ref_id)
            candidates = overlays_by_ref.get(safe_ref_id, [])
            choices = tuple(
                SubstackReviewChoiceV2(
                    overlay_id=item.overlay_id,
                    overlay_sha256=item.overlay_sha256,
                    expires_at_ms=item.expires_at_ms,
                )
                for item in candidates
            )
            if selection is None:
                binding_ready = False
                live_ready = False
                projection_rows.append(
                    SubstackReadinessRowV2(
                        ref_id=safe_ref_id,
                        binding_state="blocked",
                        live_state="selection_required",
                        reason_codes=("substack_review_selection_required",),
                        available_reviews=choices,
                    )
                )
                continue
            selected_overlay = next(
                (
                    item
                    for item in candidates
                    if item.overlay_id == selection[0] and item.overlay_sha256 == selection[1]
                ),
                None,
            )
            if selected_overlay is None:
                binding_ready = False
                live_ready = False
                projection_rows.append(
                    SubstackReadinessRowV2(
                        ref_id=safe_ref_id,
                        binding_state="blocked",
                        live_state="unavailable",
                        reason_codes=("substack_authority_unavailable",),
                        available_reviews=choices,
                    )
                )
                continue
            try:
                authorization, receipt = inspect_stored_substack_excerpt_binding(
                    store,
                    owner_id=owner_id,
                    authorization_id=selected_overlay.authorization_id,
                    expected_authorization_sha256=selected_overlay.authorization_sha256,
                    receipt_id=selected_overlay.receipt_id,
                    expected_receipt_sha256=selected_overlay.receipt_sha256,
                    verification_keys=substack_verification_keys,
                    now_ms=checked_at_ms,
                    collective_unit_id=collective_unit_id,
                    collective_preview_sha256=collective_preview_sha256,
                    ref_id=safe_ref_id,
                )
                if not isinstance(authorization, SubstackUseAuthorizationV2):
                    raise ValueError("authorization version unavailable")
                authority_rows.append(
                    substack_authority_row_v2(
                        source=source,
                        authorization=authorization,
                        receipt=receipt,
                        overlay=selected_overlay,
                    )
                )
            except ValueError:
                binding_ready = False
                live_ready = False
                projection_rows.append(
                    SubstackReadinessRowV2(
                        ref_id=safe_ref_id,
                        binding_state="blocked",
                        live_state="reconciliation_required",
                        reason_codes=("substack_authority_reconciliation_required",),
                        available_reviews=choices,
                    )
                )
                continue
            state = stored_substack_authorization_state(
                store,
                owner_id=owner_id,
                authorization_id=selected_overlay.authorization_id,
                expected_authorization_sha256=selected_overlay.authorization_sha256,
                verification_keys=substack_verification_keys,
                now_ms=checked_at_ms,
            )
            if state != "active":
                live_ready = False
                if state not in {"expired", "revoked", "not_yet_active"}:
                    binding_ready = False
                live_state = (
                    state
                    if state in {"expired", "revoked", "unavailable"}
                    else (
                        "not_yet_active" if state == "not_yet_active" else "reconciliation_required"
                    )
                )
                projection_rows.append(
                    SubstackReadinessRowV2(
                        ref_id=safe_ref_id,
                        binding_state="bound" if state in {"expired", "revoked", "not_yet_active"} else "blocked",
                        live_state=live_state,
                        reason_codes=(f"substack_authorization_{live_state}",),
                        available_reviews=choices,
                    )
                )
                continue
            if selected_overlay.expires_at_ms <= required_until_ms:
                live_ready = False
                projection_rows.append(
                    SubstackReadinessRowV2(
                        ref_id=safe_ref_id,
                        binding_state="bound",
                        live_state="horizon_insufficient",
                        reason_codes=("substack_authorization_horizon_insufficient",),
                        available_reviews=choices,
                    )
                )
                continue
            projection_rows.append(
                SubstackReadinessRowV2(
                    ref_id=safe_ref_id,
                    binding_state="bound",
                    live_state="active_at_check",
                    reason_codes=(
                        "compatible_provider_capability_missing",
                        "private_output_gate_missing",
                        "manifest_v2_not_executable",
                    ),
                    available_reviews=choices,
                )
            )
            continue

        binding_ready = False
        projection_rows.append(UnsupportedReadinessRowV2(ref_id=safe_ref_id))

    extra_selections = set(selected_overlays) - substack_ref_ids
    if extra_selections:
        raise ValueError("readiness overlay selection is outside the collective")

    manifest_sha256: str | None = None
    manifest_schema_version: Literal[2] | None = None
    if has_substack and binding_ready and len(authority_rows) == len(references):
        manifest_v2 = build_reviewed_publication_manifest_v2(
            collective_unit_id=collective_unit_id,
            collective_preview_sha256=collective_preview_sha256,
            sources=authority_rows,
        )
        manifest_sha256 = manifest_v2.manifest_sha256
        manifest_schema_version = 2

    reasons = (
        ("manifest_v2_not_executable", "private_output_gate_missing")
        if has_substack
        else ("readiness_preview_does_not_confer_execution",)
    )
    return MixedPublicationReadinessPreviewV2(
        applicability="mixed_v2" if has_substack else "legacy_v1",
        collective_unit_id=collective_unit_id,
        collective_preview_sha256=collective_preview_sha256,
        duration_minutes=duration_minutes,
        checked_at_ms=checked_at_ms,
        required_until_ms=required_until_ms,
        request_fingerprint_sha256=request_fingerprint_sha256,
        manifest_schema_version=manifest_schema_version,
        manifest_sha256=manifest_sha256,
        authority_binding_ready=(binding_ready and manifest_sha256 is not None),
        live_authority_ready=(binding_ready and live_ready),
        legacy_prepare_available=(not has_substack and binding_ready and live_ready),
        reason_codes=reasons,
        sources=tuple(projection_rows),
    )


__all__ = [
    "ArxivReadinessRowV2",
    "MixedPublicationReadinessPreviewV2",
    "PublicationReadinessRowV2",
    "SubstackReadinessRowV2",
    "SubstackReviewChoiceV2",
    "UnsupportedReadinessRowV2",
    "preview_mixed_publication_readiness",
]
