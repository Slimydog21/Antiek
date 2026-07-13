from __future__ import annotations

import hashlib
import json

import pytest
from pydantic import ValidationError

from substrate.engagement_spine.store import InMemoryEngagementStore
from substrate.midnight_oil.publication_authority_v2 import (
    ArxivEgressAuthorityV2,
    ProviderProcessingCapabilityReferenceV2,
    ProviderProcessingUnavailableV2,
    ReviewedPublicationAuthorityRowV2,
    ReviewedPublicationManifestV2,
    SubstackOwnerPrivateExcerptAuthorityV2,
    arxiv_authority_row_v2,
    build_reviewed_publication_manifest_v2,
    parse_reviewed_publication_manifest_json,
    substack_authority_row_v2,
)
from substrate.midnight_oil.publication_capability import (
    ARXIV_ABSTRACT_ADAPTER_CONTRACT_SHA256,
    PUBLICATION_RIGHTS_POLICY_SHA256,
    signed_publication_capability,
)
from substrate.midnight_oil.publication_sources import (
    ReviewedPublicationManifest,
    ReviewedPublicationSource,
)
from substrate.midnight_oil.substack_authorization import (
    SUBSTACK_PROVIDER_CONSTRAINTS_SHA256,
    SubstackUseAuthorizationV2,
    require_active_stored_substack_excerpt,
)
from substrate.midnight_oil.substack_review import (
    claim_substack_excerpt_review,
    confirm_substack_excerpt_review,
)

UNIT_ID = "cunit_" + "1" * 24
PREVIEW_SHA = "2" * 64
_KEY = b"v2-manifest-purpose-key-00000000"


def _capability():
    return signed_publication_capability(
        {
            "schema_version": 1,
            "capability_id": "midnight-oil-arxiv-abstract-v1",
            "connector_id": "acquisition.arxiv.atom",
            "connector_version": "midnight-oil-arxiv-abstract-v1",
            "adapter_contract_sha256": ARXIV_ABSTRACT_ADAPTER_CONTRACT_SHA256,
            "source_kind": "arxiv",
            "acquisition_mode": "arxiv_abstract",
            "extraction_mode": "metadata_abstract",
            "rights_policy_id": "antiek-publication-research-v1",
            "rights_policy_sha256": PUBLICATION_RIGHTS_POLICY_SHA256,
            "allowed_rights_tiers": ("T1",),
            "scheme": "https",
            "host": "export.arxiv.org",
            "port": 443,
            "path": "/api/query",
            "request_mode": "id_list_single",
            "redirect_policy": "deny",
            "proxy_policy": "deny",
            "dns_policy": "resolve-on-connect-public-only-v1",
            "tls_policy": "system-ca-hostname-tls12-v1",
            "rate_governor_id": "arxiv-host-global-v1",
            "max_response_bytes": 256_000,
            "max_excerpt_bytes": 32_000,
            "timeout_ms": 15_000,
            "issued_at_ms": 0,
            "not_before_ms": 1_000,
            "expires_at_ms": 5_000_000,
            "evidence_ref": "urn:test:manifest-v2-arxiv-egress",
        },
        key_id="publication-key",
        signing_key=_KEY,
    )


def _arxiv_source() -> ReviewedPublicationSource:
    return ReviewedPublicationSource(
        ref_id="sref_c01474352cabeb52",
        kind="arxiv",
        canonical_url="https://arxiv.org/abs/1706.03762",
        external_id="1706.03762",
        acquisition_mode="arxiv_abstract",
        rights_use="metadata_abstract_research",
        max_excerpt_bytes=32_000,
    )


def _substack_source() -> ReviewedPublicationSource:
    external_id = "example.substack.com/p/research-note"
    return ReviewedPublicationSource(
        ref_id="sref_"
        + hashlib.sha256(f"substack:substack:{external_id}".encode()).hexdigest()[:16],
        kind="substack",
        canonical_url=f"https://{external_id}",
        external_id=external_id,
        acquisition_mode="substack_bounded_excerpt",
        rights_use="operator_authorized_excerpt",
        max_excerpt_bytes=8_192,
    )


def _substack_authority() -> SubstackOwnerPrivateExcerptAuthorityV2:
    source = _substack_source()
    return SubstackOwnerPrivateExcerptAuthorityV2(
        owner_scope_sha256="3" * 64,
        collective_unit_id=UNIT_ID,
        collective_preview_sha256=PREVIEW_SHA,
        ref_id=source.ref_id,
        canonical_url=source.canonical_url,
        external_id=source.external_id,
        overlay_id="csubrev_" + "4" * 24,
        overlay_sha256="5" * 64,
        authorization_id="sua_" + "6" * 24,
        authorization_sha256="7" * 64,
        receipt_id="suer_" + "8" * 24,
        receipt_sha256="9" * 64,
        source_representation_sha256="a" * 64,
        source_representation_bytes=100,
        source_byte_start=10,
        source_byte_end=20,
        excerpt_sha256="b" * 64,
        excerpt_bytes=10,
        expires_at_ms=2_000_000,
        provider_constraints_sha256=SUBSTACK_PROVIDER_CONSTRAINTS_SHA256,
        provider_processing_authority=ProviderProcessingUnavailableV2(),
    )


def _mixed_manifest() -> ReviewedPublicationManifestV2:
    rows = (
        ReviewedPublicationAuthorityRowV2(
            source=_substack_source(), authority=_substack_authority()
        ),
        arxiv_authority_row_v2(_arxiv_source(), capability=_capability()),
    )
    return build_reviewed_publication_manifest_v2(
        collective_unit_id=UNIT_ID,
        collective_preview_sha256=PREVIEW_SHA,
        sources=rows,
    )


def test_v1_manifest_golden_vector_and_parser_remain_exact() -> None:
    raw = (
        '{"schema_version":1,"rights_policy_id":"antiek-publication-research-v1",'
        '"connector_capability_id":"reviewed-publications-v1","sources":['
        '{"ref_id":"sref_c01474352cabeb52","kind":"arxiv",'
        '"canonical_url":"https://arxiv.org/abs/1706.03762",'
        '"external_id":"1706.03762","acquisition_mode":"arxiv_abstract",'
        '"rights_use":"metadata_abstract_research","max_excerpt_bytes":32000}],'
        '"manifest_sha256":"7a4424e25fa257935dd0a3b123108f368bec33ff4c374c9aeaa32b068ea33d98"}'
    )
    parsed = parse_reviewed_publication_manifest_json(raw)
    assert type(parsed) is ReviewedPublicationManifest
    assert parsed.model_dump_json() == raw
    assert parsed.manifest_sha256 == (
        "7a4424e25fa257935dd0a3b123108f368bec33ff4c374c9aeaa32b068ea33d98"
    )


def test_mixed_manifest_is_canonical_content_addressed_and_private() -> None:
    manifest = _mixed_manifest()
    assert manifest.manifest_sha256 == (
        "7bdd55ea1365c31b629ea4907ea9c9f7fb4385fb6d9237ccf27833a64bc65df1"
    )
    assert [row.source.kind for row in manifest.sources] == ["arxiv", "substack"]
    assert manifest == build_reviewed_publication_manifest_v2(
        collective_unit_id=UNIT_ID,
        collective_preview_sha256=PREVIEW_SHA,
        sources=tuple(reversed(manifest.sources)),
    )
    raw = manifest.model_dump_json()
    assert parse_reviewed_publication_manifest_json(raw) == manifest
    assert "personal_reading" in raw
    assert '"rights_tier":"not_applicable"' in raw
    assert '"confers_execution_authority":false' in raw
    assert '"purpose":"authority_binding_only"' in raw
    assert "compatible_provider_capability_missing" in raw
    assert "signature_sha256" not in raw
    assert "selection_text" not in raw
    assert '"text"' not in raw


def test_authority_kind_cannot_be_swapped_or_inferred() -> None:
    with pytest.raises(ValidationError, match="owner-private"):
        ReviewedPublicationAuthorityRowV2(
            source=_substack_source(),
            authority=ArxivEgressAuthorityV2(
                publication_capability_sha256="d" * 64,
                max_excerpt_bytes=32_000,
                not_before_ms=1_000,
                expires_at_ms=2_000,
            ),
        )
    payload = _mixed_manifest().model_dump(mode="json")
    payload["sources"][1]["authority"]["authority_kind"] = "unknown"
    payload["sources"] = tuple(payload["sources"])
    with pytest.raises(ValidationError, match="union_tag_invalid"):
        ReviewedPublicationManifestV2.model_validate(payload)


def test_substack_cannot_claim_t1_or_whole_source_range() -> None:
    payload = _substack_authority().model_dump(mode="json")
    payload["rights_tier"] = "T1"
    with pytest.raises(ValidationError):
        SubstackOwnerPrivateExcerptAuthorityV2.model_validate(payload)


def test_substack_authority_is_intrinsically_source_and_policy_bound() -> None:
    authority = _substack_authority()
    other_external_id = "other.substack.com/p/other-note"
    other = ReviewedPublicationSource(
        ref_id="sref_"
        + hashlib.sha256(f"substack:substack:{other_external_id}".encode()).hexdigest()[:16],
        kind="substack",
        canonical_url=f"https://{other_external_id}",
        external_id=other_external_id,
        acquisition_mode="substack_bounded_excerpt",
        rights_use="operator_authorized_excerpt",
        max_excerpt_bytes=8_192,
    )
    with pytest.raises(ValidationError, match="scope conflicts"):
        ReviewedPublicationAuthorityRowV2(source=other, authority=authority)
    payload = authority.model_dump(mode="json")
    payload["provider_constraints_sha256"] = "0" * 64
    with pytest.raises(ValidationError, match="range conflicts"):
        SubstackOwnerPrivateExcerptAuthorityV2.model_validate(payload)
    payload = authority.model_dump(mode="json")
    payload["canonical_url"] = "https://evil@example.substack.com/p/research-note"
    with pytest.raises((ValidationError, ValueError)):
        SubstackOwnerPrivateExcerptAuthorityV2.model_validate(payload)


def test_v2_requires_substack_and_never_confers_execution_by_itself() -> None:
    arxiv = arxiv_authority_row_v2(_arxiv_source(), capability=_capability())
    with pytest.raises(ValidationError, match="requires owner-private Substack"):
        build_reviewed_publication_manifest_v2(
            collective_unit_id=UNIT_ID,
            collective_preview_sha256=PREVIEW_SHA,
            sources=(arxiv,),
        )
    payload = _mixed_manifest().model_dump(mode="json")
    payload["confers_execution_authority"] = True
    payload["sources"] = tuple(payload["sources"])
    with pytest.raises(ValidationError):
        ReviewedPublicationManifestV2.model_validate(payload)


def test_detached_authorities_and_provider_reference_never_confer_execution() -> None:
    provider_reference = ProviderProcessingCapabilityReferenceV2(capability_sha256="6" * 64)
    assert provider_reference.reference_only is True
    assert provider_reference.confers_execution_authority is False
    assert provider_reference.verification_state == "live_registry_resolution_required"
    assert _substack_authority().confers_execution_authority is False
    assert (
        arxiv_authority_row_v2(
            _arxiv_source(), capability=_capability()
        ).authority.confers_execution_authority
        is False
    )

    capable = SubstackOwnerPrivateExcerptAuthorityV2.model_validate(
        {
            **_substack_authority().model_dump(mode="json"),
            "provider_processing_authority": provider_reference.model_dump(mode="json"),
        }
    )
    manifest = build_reviewed_publication_manifest_v2(
        collective_unit_id=UNIT_ID,
        collective_preview_sha256=PREVIEW_SHA,
        sources=(ReviewedPublicationAuthorityRowV2(source=_substack_source(), authority=capable),),
    )
    payload = manifest.model_dump(mode="json")
    payload["sources"][0]["authority"]["provider_processing_authority"]["capability_sha256"] = (
        "7" * 64
    )
    payload["sources"] = tuple(payload["sources"])
    with pytest.raises(ValidationError, match="manifest hash"):
        ReviewedPublicationManifestV2.model_validate(payload)

    reference_payload = provider_reference.model_dump(mode="json")
    reference_payload["provider_constraints_sha256"] = "0" * 64
    with pytest.raises(ValidationError):
        ProviderProcessingCapabilityReferenceV2.model_validate(reference_payload)


def test_real_stored_artifacts_build_a_content_bound_nonexecuting_row() -> None:
    store = InMemoryEngagementStore()
    external_id = _substack_source().external_id
    draft = claim_substack_excerpt_review(
        store,
        owner_id="alice",
        idempotency_key="manifest-review-0001",
        collective_unit_id=UNIT_ID,
        collective_preview_sha256=PREVIEW_SHA,
        ref_id=_substack_source().ref_id,
        canonical_url=f"https://{external_id}",
        external_id=external_id,
        selection_text="A bounded private excerpt.",
        source_representation_sha256="e" * 64,
        source_representation_bytes=10_000,
        source_byte_start=100,
        lifetime_ms=60_000,
        now_ms=1_000,
        nonce="f" * 32,
    )
    overlay = confirm_substack_excerpt_review(
        store,
        owner_id="alice",
        review_id=draft.review_id,
        expected_review_preview_sha256=draft.review_preview_sha256,
        idempotency_key="manifest-confirm-0001",
        key_id="substack-purpose-key",
        signing_key=_KEY,
        verification_keys={"substack-purpose-key": _KEY},
        now_ms=2_000,
    )
    authorization, receipt = require_active_stored_substack_excerpt(
        store,
        owner_id="alice",
        authorization_id=overlay.authorization_id,
        expected_authorization_sha256=overlay.authorization_sha256,
        receipt_id=overlay.receipt_id,
        expected_receipt_sha256=overlay.receipt_sha256,
        verification_keys={"substack-purpose-key": _KEY},
        now_ms=2_001,
    )
    assert isinstance(authorization, SubstackUseAuthorizationV2)
    row = substack_authority_row_v2(
        source=_substack_source(),
        authorization=authorization,
        receipt=receipt,
        overlay=overlay,
    )
    assert row.authority.authorization_verification_state == ("content_bound_live_state_unverified")
    assert isinstance(
        row.authority.provider_processing_authority,
        ProviderProcessingUnavailableV2,
    )
    with pytest.raises(ValueError, match="artifact binding conflicts"):
        substack_authority_row_v2(
            source=_substack_source(),
            authorization=authorization,
            receipt=receipt.model_copy(update={"injected_at_ms": receipt.injected_at_ms + 1}),
            overlay=overlay,
        )
    payload = _substack_authority().model_dump(mode="json")
    payload.update(source_byte_start=0, source_byte_end=100, excerpt_bytes=100)
    with pytest.raises(ValidationError, match="range"):
        SubstackOwnerPrivateExcerptAuthorityV2.model_validate(payload)


def test_manifest_rejects_substitution_and_collective_drift() -> None:
    manifest = _mixed_manifest()
    payload = manifest.model_dump(mode="json")
    payload["sources"][1]["authority"]["receipt_sha256"] = "e" * 64
    payload["sources"] = tuple(payload["sources"])
    with pytest.raises(ValidationError, match="manifest hash"):
        ReviewedPublicationManifestV2.model_validate(payload)
    payload = manifest.model_dump(mode="json")
    payload["sources"][1]["authority"]["collective_preview_sha256"] = "f" * 64
    payload["sources"] = tuple(payload["sources"])
    with pytest.raises(ValidationError, match="collective binding"):
        ReviewedPublicationManifestV2.model_validate(payload)


def test_version_dispatch_rejects_duplicate_keys_and_downgrades() -> None:
    manifest = _mixed_manifest()
    raw = manifest.model_dump_json()
    with pytest.raises(ValueError, match="duplicate JSON keys"):
        parse_reviewed_publication_manifest_json(
            raw.replace('{"schema_version":2', '{"schema_version":2,"schema_version":2', 1)
        )
    payload = manifest.model_dump(mode="json")
    payload["schema_version"] = 1
    with pytest.raises(ValidationError):
        parse_reviewed_publication_manifest_json(json.dumps(payload))
    payload["schema_version"] = 3
    with pytest.raises(ValueError, match="unsupported"):
        parse_reviewed_publication_manifest_json(json.dumps(payload))


def test_duplicate_or_oversized_authority_rows_fail_closed() -> None:
    row = ReviewedPublicationAuthorityRowV2(
        source=_substack_source(), authority=_substack_authority()
    )
    with pytest.raises(ValidationError, match="unique"):
        build_reviewed_publication_manifest_v2(
            collective_unit_id=UNIT_ID,
            collective_preview_sha256=PREVIEW_SHA,
            sources=(row, row),
        )
    with pytest.raises(ValueError, match="limit"):
        build_reviewed_publication_manifest_v2(
            collective_unit_id=UNIT_ID,
            collective_preview_sha256=PREVIEW_SHA,
            sources=(row,) * 65,
        )
