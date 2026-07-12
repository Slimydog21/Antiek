from __future__ import annotations

from dataclasses import asdict

from substrate.context_pack import build_canonical_recursive_pack
from substrate.engagement_spine import InMemoryEngagementStore, record_twin_insight


def test_only_authority_resolved_builder_is_publicly_exported():
    import substrate.context_pack as context_pack

    assert not hasattr(context_pack, "ContentCandidate")
    assert not hasattr(context_pack, "assemble_recursive_notes_pack")


def test_foreign_missing_artifact_and_caller_text_fail_closed_without_leaking():
    store = InMemoryEngagementStore()
    record_twin_insight("foreign-secret", "Private acquisition thesis.", store=store)
    owner_by_asset = {"foreign-secret": "owner-b"}
    pack = build_canonical_recursive_pack(
        store=store,
        owner_user_id="owner-a",
        asset_ids=["foreign-secret", "missing-secret"],
        asset_owner=owner_by_asset.get,
        artifact_ids=["artifact-private-1"],
        caller_advisory_text=["Caller says this is canonical secret text"],
        goal="private thesis",
    )
    assert pack.pack_ready is False
    assert pack.units == ()
    assert len(pack.advisory_previews) == 1
    assert pack.advisory_previews[0].authority == "caller_supplied_advisory"
    assert pack.advisory_previews[0].text == "Caller says this is canonical secret text"
    assert pack.token_estimate == 0
    assert pack.advisory_token_estimate > 0
    assert pack.token_estimate + pack.advisory_token_estimate <= pack.token_budget
    assert {receipt.reason for receipt in pack.exclusions} == {
        "foreign_owner",
        "missing_asset",
        "resolver_unavailable",
        "caller_supplied_advisory",
    }
    encoded = str([asdict(receipt) for receipt in pack.exclusions])
    assert "Private acquisition thesis" not in encoded
    assert "Caller says" not in encoded
    assert "foreign-secret" not in encoded
    assert "artifact-private-1" not in encoded


def test_owner_scope_digest_changes_without_exposing_owner_identity():
    store = InMemoryEngagementStore()
    record_twin_insight("asset", "Owner-readable context.", store=store)
    a = build_canonical_recursive_pack(
        store=store,
        owner_user_id="owner-a@example.com",
        asset_ids=["asset"],
        asset_owner=lambda _asset: "owner-a@example.com",
        goal="context",
    )
    b = build_canonical_recursive_pack(
        store=store,
        owner_user_id="owner-b@example.com",
        asset_ids=["asset"],
        asset_owner=lambda _asset: "owner-b@example.com",
        goal="context",
    )
    assert a.units[0].account_scope_digest != b.units[0].account_scope_digest
    assert "owner-a@example.com" not in str(asdict(a.units[0]))
    assert "owner-b@example.com" not in str(asdict(b.units[0]))


def test_utf8_byte_limit_excludes_oversized_unit():
    store = InMemoryEngagementStore()
    record_twin_insight("asset", "مرحبا" * 20, store=store)
    pack = build_canonical_recursive_pack(
        store=store,
        owner_user_id="owner",
        asset_ids=["asset"],
        asset_owner=lambda _asset: "owner",
        goal="مرحبا",
        max_unit_bytes=32,
    )
    assert pack.units == ()
    assert any(receipt.reason == "per_unit_limit" for receipt in pack.exclusions)
