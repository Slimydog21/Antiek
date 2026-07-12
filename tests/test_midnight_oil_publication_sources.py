from __future__ import annotations

import hashlib
import json

import pytest
from pydantic import ValidationError

from substrate.engagement_spine.source_refs import parse_source_reference
from substrate.engagement_spine.store import InMemoryEngagementStore
from substrate.midnight_oil.live_roles import (
    CanonicalSourceReceipt,
    publication_source_receipt_id,
)
from substrate.midnight_oil.publication_sources import (
    MAX_EXCERPT_BYTES,
    AcquiredPublicationExcerpt,
    ReviewedPublicationManifest,
    acquire_reviewed_publications,
    acquire_reviewed_publications_durably,
    acquired_excerpt,
    build_reviewed_publication_manifest,
    manifest_from_authority,
)


def _row(raw: str) -> dict[str, object]:
    return parse_source_reference(raw).to_dict()


def test_manifest_is_canonical_bounded_and_content_addressed() -> None:
    manifest = build_reviewed_publication_manifest([_row("arxiv:1706.03762")])
    assert [row.kind for row in manifest.sources] == ["arxiv"]
    assert len(manifest.manifest_sha256) == 64
    assert manifest == build_reviewed_publication_manifest([_row("arxiv:1706.03762")])


def test_generic_urls_are_explicitly_excluded() -> None:
    with pytest.raises(ValueError, match="unsupported"):
        build_reviewed_publication_manifest([_row("https://example.com/report")])


def test_custom_domain_substack_inference_is_rejected() -> None:
    with pytest.raises(ValueError, match="authorization receipt"):
        build_reviewed_publication_manifest([_row("https://publisher.example/p/post")])


def test_canonical_substack_requires_explicit_authorization_receipt() -> None:
    with pytest.raises(ValueError, match="authorization receipt"):
        build_reviewed_publication_manifest(
            [_row("https://example.substack.com/p/research-note")]
        )


def test_durable_ref_id_is_recomputed() -> None:
    row = _row("arxiv:1706.03762")
    row["ref_id"] = "sref_0000000000000000"
    with pytest.raises(ValueError, match="ref id"):
        build_reviewed_publication_manifest([row])


def test_persisted_manifest_type_recomputes_identity_rules() -> None:
    manifest = build_reviewed_publication_manifest([_row("arxiv:1706.03762")])
    payload = manifest.model_dump(mode="json")
    payload["sources"][0]["ref_id"] = "sref_0000000000000000"
    with pytest.raises(ValidationError, match="canonical"):
        ReviewedPublicationManifest.model_validate(
            {**payload, "sources": tuple(payload["sources"])}
        )
    with pytest.raises(ValidationError, match="canonical"):
        manifest_from_authority(
            {
                "publication_manifest_json": json.dumps(payload),
                "publication_manifest_sha256": manifest.manifest_sha256,
            }
        )


def test_duplicate_identity_and_source_limit_fail_closed() -> None:
    row = _row("arxiv:1706.03762")
    with pytest.raises(ValidationError, match="unique"):
        build_reviewed_publication_manifest([row, row])
    with pytest.raises(ValueError, match="limit"):
        build_reviewed_publication_manifest(
            [_row(f"arxiv:2401.{index:05d}") for index in range(65)]
        )


def test_connector_cannot_substitute_identity_or_unknown_rights() -> None:
    manifest = build_reviewed_publication_manifest([_row("arxiv:1706.03762")])
    source = manifest.sources[0]
    valid = acquired_excerpt(
        source,
        text="A bounded abstract.",
        connector="acquisition.arxiv",
        rights_tier="T1",
        truncated=False,
    )
    assert acquire_reviewed_publications(manifest, acquire=lambda _: valid) == (valid,)
    unknown = valid.model_copy(update={"rights_tier": "T3"})
    with pytest.raises(ValueError, match="rights"):
        acquire_reviewed_publications(manifest, acquire=lambda _: unknown)
    substituted = valid.model_copy(update={"external_id": "2401.00001"})
    with pytest.raises(ValueError, match="escaped"):
        acquire_reviewed_publications(manifest, acquire=lambda _: substituted)


def test_unicode_excerpt_cap_is_bytes_not_characters() -> None:
    manifest = build_reviewed_publication_manifest([_row("arxiv:1706.03762")])
    source = manifest.sources[0]
    with pytest.raises(ValidationError):
        acquired_excerpt(
            source,
            text="🧠" * (MAX_EXCERPT_BYTES // 2),
            connector="acquisition.arxiv",
            rights_tier="T1",
            truncated=False,
        )


def test_excerpt_hash_and_byte_count_are_not_caller_claims() -> None:
    manifest = build_reviewed_publication_manifest([_row("arxiv:1706.03762")])
    excerpt = acquired_excerpt(
        manifest.sources[0],
        text="Abstract evidence",
        connector="acquisition.arxiv",
        rights_tier="T1",
        truncated=False,
    )
    with pytest.raises(ValidationError, match="bytes conflict"):
        AcquiredPublicationExcerpt.model_validate(
            {**excerpt.model_dump(mode="json"), "excerpt_bytes": excerpt.excerpt_bytes + 1}
        )


def test_durable_acquisition_replays_bytes_without_connector_recall() -> None:
    manifest = build_reviewed_publication_manifest([_row("arxiv:1706.03762")])
    store = InMemoryEngagementStore()
    calls = 0

    def acquire(source):  # type: ignore[no-untyped-def]
        nonlocal calls
        calls += 1
        return acquired_excerpt(
            source,
            text="Pinned abstract bytes",
            connector="acquisition.arxiv",
            rights_tier="T1",
            truncated=False,
        )

    first = acquire_reviewed_publications_durably(
        manifest, owner_id="alice", job_id="moil_job_1", store=store, acquire=acquire
    )
    second = acquire_reviewed_publications_durably(
        manifest, owner_id="alice", job_id="moil_job_1", store=store, acquire=acquire
    )
    assert first == second
    assert calls == 1


def test_ambiguous_connector_claim_never_refetches() -> None:
    manifest = build_reviewed_publication_manifest([_row("arxiv:1706.03762")])
    store = InMemoryEngagementStore()
    calls = 0

    def fail(_source):  # type: ignore[no-untyped-def]
        nonlocal calls
        calls += 1
        raise TimeoutError("ambiguous connector outcome")

    with pytest.raises(TimeoutError):
        acquire_reviewed_publications_durably(
            manifest, owner_id="alice", job_id="moil_job_2", store=store, acquire=fail
        )
    with pytest.raises(ValueError, match="reconciliation"):
        acquire_reviewed_publications_durably(
            manifest, owner_id="alice", job_id="moil_job_2", store=store, acquire=fail
        )
    assert calls == 1


def test_publication_receipt_recomputes_execution_scope() -> None:
    fields = {
        "owner_scope_sha256": "1" * 64,
        "execution_id": "cexec_1",
        "job_id": "moil_job_1",
        "stage_key": "stage_1",
        "router_role": "gatherer",
        "route_plan_sha256": "2" * 64,
        "question_id": "q-1",
        "publication_manifest_sha256": "3" * 64,
        "reviewed_ref_id": "sref_1111111111111111",
        "excerpt_sha256": "4" * 64,
    }
    receipt = CanonicalSourceReceipt(
        source_receipt_id=publication_source_receipt_id(**fields),  # type: ignore[arg-type]
        document_id=fields["reviewed_ref_id"],
        chunk_id="acquisition.arxiv:1706.03762",
        source_type="publication",
        connector="acquisition.arxiv",
        canonical_url="https://arxiv.org/abs/1706.03762",
        acquisition_mode="arxiv_abstract",
        rights_use="metadata_abstract_research",
        rights_tier="T1",
        truncated=False,
        excerpt_bytes=20,
        connector_version="injected-v1",
        extraction_mode="metadata_abstract",
        truncation_reason="not_applicable",
        **fields,  # type: ignore[arg-type]
    )
    with pytest.raises(ValidationError, match="execution scope"):
        CanonicalSourceReceipt.model_validate(
            {**receipt.model_dump(mode="json"), "job_id": "moil_other"}
        )


def test_applied_checkpoint_revalidates_rights_policy() -> None:
    manifest = build_reviewed_publication_manifest([_row("arxiv:1706.03762")])
    store = InMemoryEngagementStore()
    acquire_reviewed_publications_durably(
        manifest,
        owner_id="alice",
        job_id="moil_job_3",
        store=store,
        acquire=lambda source: acquired_excerpt(
            source,
            text="Pinned abstract",
            connector="acquisition.arxiv",
            rights_tier="T1",
            truncated=False,
        ),
    )
    logical_id = "psacq_" + hashlib.sha256(
        f"antiek:publication-acquisition:v1\0alice\0moil_job_3\0{manifest.manifest_sha256}".encode()
    ).hexdigest()[:24]

    def corrupt(current):  # type: ignore[no-untyped-def]
        assert current is not None
        rows = [dict(row) for row in current["results"]]
        rows[0]["rights_tier"] = "T3"
        return {**current, "results": rows}

    store.mutate_owned_document(logical_id, "alice", corrupt)
    with pytest.raises(ValueError, match="rights"):
        acquire_reviewed_publications_durably(
            manifest,
            owner_id="alice",
            job_id="moil_job_3",
            store=store,
            acquire=lambda _source: (_ for _ in ()).throw(
                AssertionError("applied replay must not call connector")
            ),
        )
