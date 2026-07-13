"""Exact local owner-private Substack reader for Midnight Oil.

This module performs no network acquisition and confers no execution authority.
"""

from __future__ import annotations

import hashlib
import hmac
from collections.abc import Mapping
from dataclasses import dataclass

from substrate.engagement_spine.store import EngagementStore
from substrate.midnight_oil.publication_authority_v2 import (
    ProviderProcessingCapabilityReferenceV2,
    SubstackOwnerPrivateExcerptAuthorityV2,
)
from substrate.midnight_oil.substack_authorization import (
    SubstackExcerptReceipt,
    SubstackUseAuthorizationV2,
    owner_scope_sha256,
    require_active_stored_substack_excerpt,
)
from substrate.midnight_oil.substack_review import (
    ConfirmedSubstackReviewOverlay,
    require_exact_confirmed_substack_review_overlay,
)


@dataclass(frozen=True, slots=True)
class StoredAuthorizedSubstackExcerpt:
    """One exact, currently authorized local excerpt held only in memory."""

    authority: SubstackOwnerPrivateExcerptAuthorityV2
    overlay: ConfirmedSubstackReviewOverlay
    authorization: SubstackUseAuthorizationV2
    receipt: SubstackExcerptReceipt
    exact_bytes: bytes
    source_acquisition_network_egress: bool = False
    confers_execution_authority: bool = False


@dataclass(frozen=True, slots=True)
class StoredAuthorizedSubstackExcerptReader:
    store: EngagementStore
    verification_keys: Mapping[str, bytes]

    def read(
        self,
        *,
        owner_id: str,
        authority: SubstackOwnerPrivateExcerptAuthorityV2,
        now_ms: int,
        required_until_ms: int,
    ) -> StoredAuthorizedSubstackExcerpt:
        """Reload and cross-bind overlay, V2 authorization, receipt, and exact bytes."""
        try:
            return self._read(
                owner_id=owner_id,
                authority=authority,
                now_ms=now_ms,
                required_until_ms=required_until_ms,
            )
        except (TypeError, ValueError):
            raise ValueError("Substack owner-private excerpt is unavailable") from None

    def _read(
        self,
        *,
        owner_id: str,
        authority: SubstackOwnerPrivateExcerptAuthorityV2,
        now_ms: int,
        required_until_ms: int,
    ) -> StoredAuthorizedSubstackExcerpt:
        authority = SubstackOwnerPrivateExcerptAuthorityV2.model_validate(
            authority.model_dump(mode="python", warnings=False)
        )
        if not isinstance(
            authority.provider_processing_authority,
            ProviderProcessingCapabilityReferenceV2,
        ):
            raise ValueError("Substack private provider capability is unavailable")
        if not hmac.compare_digest(authority.owner_scope_sha256, owner_scope_sha256(owner_id)):
            raise ValueError("Substack owner-private authority is unavailable")

        overlay = self._read_overlay(owner_id=owner_id, authority=authority)
        authorization, receipt = require_active_stored_substack_excerpt(
            self.store,
            owner_id=owner_id,
            authorization_id=authority.authorization_id,
            expected_authorization_sha256=authority.authorization_sha256,
            receipt_id=authority.receipt_id,
            expected_receipt_sha256=authority.receipt_sha256,
            verification_keys=self.verification_keys,
            now_ms=now_ms,
            required_until_ms=required_until_ms,
            collective_unit_id=authority.collective_unit_id,
            collective_preview_sha256=authority.collective_preview_sha256,
            ref_id=authority.ref_id,
        )
        if not isinstance(authorization, SubstackUseAuthorizationV2):
            raise ValueError("Substack owner-private authorization must be V2")
        exact_bytes = receipt.text.encode("utf-8")
        if not self._bindings_match(
            authority=authority,
            overlay=overlay,
            authorization=authorization,
            receipt=receipt,
            exact_bytes=exact_bytes,
        ):
            raise ValueError("Substack owner-private excerpt binding conflicts")

        final_overlay = self._read_overlay(owner_id=owner_id, authority=authority)
        final_authorization, final_receipt = require_active_stored_substack_excerpt(
            self.store,
            owner_id=owner_id,
            authorization_id=authority.authorization_id,
            expected_authorization_sha256=authority.authorization_sha256,
            receipt_id=authority.receipt_id,
            expected_receipt_sha256=authority.receipt_sha256,
            verification_keys=self.verification_keys,
            now_ms=now_ms,
            required_until_ms=required_until_ms,
            collective_unit_id=authority.collective_unit_id,
            collective_preview_sha256=authority.collective_preview_sha256,
            ref_id=authority.ref_id,
        )
        if (
            final_overlay != overlay
            or final_authorization != authorization
            or final_receipt != receipt
            or final_receipt.text.encode("utf-8") != exact_bytes
        ):
            raise ValueError("Substack owner-private excerpt changed during inspection")
        return StoredAuthorizedSubstackExcerpt(
            authority=authority,
            overlay=overlay,
            authorization=authorization,
            receipt=receipt,
            exact_bytes=exact_bytes,
        )

    def _read_overlay(
        self,
        *,
        owner_id: str,
        authority: SubstackOwnerPrivateExcerptAuthorityV2,
    ) -> ConfirmedSubstackReviewOverlay:
        return require_exact_confirmed_substack_review_overlay(
            self.store,
            owner_id=owner_id,
            overlay_id=authority.overlay_id,
            expected_overlay_sha256=authority.overlay_sha256,
            collective_unit_id=authority.collective_unit_id,
            collective_preview_sha256=authority.collective_preview_sha256,
            ref_id=authority.ref_id,
            authorization_id=authority.authorization_id,
            expected_authorization_sha256=authority.authorization_sha256,
            receipt_id=authority.receipt_id,
            expected_receipt_sha256=authority.receipt_sha256,
        )

    @staticmethod
    def _bindings_match(
        *,
        authority: SubstackOwnerPrivateExcerptAuthorityV2,
        overlay: ConfirmedSubstackReviewOverlay,
        authorization: SubstackUseAuthorizationV2,
        receipt: SubstackExcerptReceipt,
        exact_bytes: bytes,
    ) -> bool:
        return all(
            (
                authorization.owner_scope_sha256 == authority.owner_scope_sha256,
                authorization.collective_unit_id == authority.collective_unit_id,
                authorization.collective_preview_sha256
                == authority.collective_preview_sha256,
                authorization.ref_id == authority.ref_id,
                authorization.canonical_url == authority.canonical_url,
                authorization.external_id == authority.external_id,
                overlay.overlay_id == authority.overlay_id,
                overlay.overlay_sha256 == authority.overlay_sha256,
                authorization.authorization_id == authority.authorization_id,
                authorization.authorization_sha256 == authority.authorization_sha256,
                receipt.receipt_id == authority.receipt_id,
                receipt.receipt_sha256 == authority.receipt_sha256,
                authorization.source_representation_sha256
                == authority.source_representation_sha256,
                authorization.source_representation_bytes
                == authority.source_representation_bytes,
                authorization.source_byte_start == authority.source_byte_start,
                authorization.source_byte_end == authority.source_byte_end,
                authorization.excerpt_sha256 == authority.excerpt_sha256,
                authorization.excerpt_bytes == authority.excerpt_bytes,
                authorization.expires_at_ms == authority.expires_at_ms,
                overlay.excerpt_sha256 == authority.excerpt_sha256,
                overlay.excerpt_bytes == authority.excerpt_bytes,
                overlay.source_byte_start == authority.source_byte_start,
                overlay.source_byte_end == authority.source_byte_end,
                overlay.expires_at_ms == authority.expires_at_ms,
                overlay.content_class == authority.content_class,
                overlay.rights_tier == authority.rights_tier,
                overlay.rights_use == authority.rights_use,
                overlay.provider_constraints_sha256
                == authority.provider_constraints_sha256,
                receipt.excerpt_sha256 == hashlib.sha256(exact_bytes).hexdigest(),
                receipt.excerpt_bytes == len(exact_bytes),
            )
        )


__all__ = ["StoredAuthorizedSubstackExcerpt", "StoredAuthorizedSubstackExcerptReader"]
