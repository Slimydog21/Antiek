from __future__ import annotations

from dataclasses import asdict

from substrate.context_pack import build_canonical_recursive_pack
from substrate.engagement_spine import InMemoryEngagementStore, record_twin_insight
from substrate.research_artifact.authority import ArtifactAuthority
from substrate.research_artifact.render import render_html
from substrate.research_artifact.schema import ResearchArtifactBody
from substrate.research_artifact.storage import FilesystemArtifactStore


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


def test_owner_artifact_notes_resolve_as_canonical_units(tmp_path, monkeypatch):
    monkeypatch.setenv("ANTIEK_RESEARCH_ARTIFACTS_DIR", str(tmp_path))
    authority = ArtifactAuthority("owner-a", "research-one")
    artifact_store = FilesystemArtifactStore(tmp_path)
    artifact_store.write(
        authority,
        render_html(
            ResearchArtifactBody(
                investigation_id="research-one",
                problem_question="What changed?",
                source_event_ids=["evt-source"],
                agent_notes=["Contradictory evidence deserves a follow-up."],
            )
        ),
    )
    pack = build_canonical_recursive_pack(
        store=InMemoryEngagementStore(),
        owner_user_id="owner-a",
        asset_ids=(),
        asset_owner=lambda _asset: None,
        artifact_ids=["research-one"],
        artifact_store=artifact_store,
        goal="contradictory evidence",
    )
    assert pack.pack_ready is True
    assert len(pack.units) == 1
    unit = pack.units[0]
    assert unit.authority == "artifact_note"
    assert unit.kind == "artifact_note"
    assert unit.artifact_note_id is not None
    assert unit.twin_note_id is None and unit.graph_node_id is None
    assert unit.text == "Contradictory evidence deserves a follow-up."
    assert unit.source_event_ids == ("evt-source",)


def test_artifact_note_resolution_is_owner_scoped_and_empty_is_explicit(tmp_path, monkeypatch):
    monkeypatch.setenv("ANTIEK_RESEARCH_ARTIFACTS_DIR", str(tmp_path))
    artifact_store = FilesystemArtifactStore(tmp_path)
    artifact_store.write(
        ArtifactAuthority("owner-b", "shared"),
        render_html(
            ResearchArtifactBody(
                investigation_id="shared",
                problem_question="Private",
                agent_notes=["Owner B secret note"],
            )
        ),
    )
    artifact_store.write(
        ArtifactAuthority("owner-a", "empty"),
        render_html(ResearchArtifactBody(investigation_id="empty", problem_question="Empty")),
    )
    pack = build_canonical_recursive_pack(
        store=InMemoryEngagementStore(),
        owner_user_id="owner-a",
        asset_ids=(),
        asset_owner=lambda _asset: None,
        artifact_ids=["shared", "empty"],
        artifact_store=artifact_store,
        goal="private",
    )
    assert pack.units == ()
    assert {receipt.reason for receipt in pack.exclusions} == {
        "missing_asset",
        "no_content",
    }
    assert "Owner B secret note" not in str([asdict(item) for item in pack.exclusions])


def test_artifact_note_malformed_and_unsafe_storage_fail_as_opaque_exclusions(
    tmp_path, monkeypatch
):
    from substrate.context_pack import recursive_notes_resolvers as resolvers

    monkeypatch.setenv("ANTIEK_RESEARCH_ARTIFACTS_DIR", str(tmp_path))
    artifact_store = FilesystemArtifactStore(tmp_path)
    authority = ArtifactAuthority("owner-a", "tampered")
    artifact_store.write(
        authority,
        render_html(
            ResearchArtifactBody(
                investigation_id="tampered",
                problem_question="Tampered",
                agent_notes=["Must never survive tampering"],
            )
        ),
    )
    authority.artifact_path(tmp_path).write_text("invalid bytes", encoding="utf-8")
    monkeypatch.setattr(resolvers, "MAX_ARTIFACT_HTML_BYTES", 4)
    pack = build_canonical_recursive_pack(
        store=InMemoryEngagementStore(),
        owner_user_id="owner-a",
        asset_ids=(),
        asset_owner=lambda _asset: None,
        artifact_ids=["bad\x00id", "tampered"],
        artifact_store=artifact_store,
        goal="safe",
    )
    assert pack.units == ()
    assert {receipt.reason for receipt in pack.exclusions} == {
        "malformed",
        "resolver_unavailable",
    }
    encoded = str([asdict(item) for item in pack.exclusions])
    assert "bad\x00id" not in encoded
    assert "Must never" not in encoded


def test_artifact_resolution_enforces_one_cumulative_candidate_bound(tmp_path, monkeypatch):
    from substrate.context_pack import recursive_notes_resolvers as resolvers

    monkeypatch.setenv("ANTIEK_RESEARCH_ARTIFACTS_DIR", str(tmp_path))
    store = FilesystemArtifactStore(tmp_path)
    for artifact_id in ("first", "second"):
        store.write(
            ArtifactAuthority("owner-a", artifact_id),
            render_html(
                ResearchArtifactBody(
                    investigation_id=artifact_id,
                    problem_question="Bounded",
                    agent_notes=[f"note from {artifact_id}"],
                )
            ),
        )
    monkeypatch.setattr(resolvers, "MAX_CANDIDATES", 1)
    pack = build_canonical_recursive_pack(
        store=InMemoryEngagementStore(),
        owner_user_id="owner-a",
        asset_ids=(),
        asset_owner=lambda _asset: None,
        artifact_ids=["first", "second"],
        artifact_store=store,
        goal="note",
    )
    assert len(pack.units) == 1
    assert any(item.reason == "aggregate_budget" for item in pack.exclusions)


def test_artifact_resolution_enforces_one_cumulative_byte_bound(tmp_path, monkeypatch):
    from substrate.context_pack import recursive_notes_resolvers as resolvers

    monkeypatch.setenv("ANTIEK_RESEARCH_ARTIFACTS_DIR", str(tmp_path))
    store = FilesystemArtifactStore(tmp_path)
    rendered: dict[str, str] = {}
    for artifact_id in ("first", "second"):
        rendered[artifact_id] = render_html(
            ResearchArtifactBody(
                investigation_id=artifact_id,
                problem_question="Bounded",
                agent_notes=[f"note from {artifact_id}"],
            )
        )
        store.write(ArtifactAuthority("owner-a", artifact_id), rendered[artifact_id])

    monkeypatch.setattr(
        resolvers,
        "MAX_AGGREGATE_ARTIFACT_HTML_BYTES",
        len(rendered["first"].encode("utf-8")),
    )
    pack = build_canonical_recursive_pack(
        store=InMemoryEngagementStore(),
        owner_user_id="owner-a",
        asset_ids=(),
        asset_owner=lambda _asset: None,
        artifact_ids=["first", "second"],
        artifact_store=store,
        goal="note",
    )

    assert [unit.asset_id for unit in pack.units] == ["first"]
    assert sum(item.reason == "aggregate_budget" for item in pack.exclusions) == 1


def test_private_context_and_exclusion_digests_are_owner_unlinkable(tmp_path, monkeypatch):
    monkeypatch.setenv("ANTIEK_RESEARCH_ARTIFACTS_DIR", str(tmp_path))
    store = FilesystemArtifactStore(tmp_path)
    for owner in ("owner-a", "owner-b"):
        store.write(
            ArtifactAuthority(owner, "same"),
            render_html(
                ResearchArtifactBody(
                    investigation_id="same",
                    problem_question="Same",
                    agent_notes=["same low entropy private note"],
                )
            ),
        )

    def pack(owner: str):
        return build_canonical_recursive_pack(
            store=InMemoryEngagementStore(),
            owner_user_id=owner,
            asset_ids=["missing"],
            asset_owner=lambda _asset: None,
            artifact_ids=["same"],
            artifact_store=store,
            goal="same",
        )

    alice, bob = pack("owner-a"), pack("owner-b")
    assert alice.units[0].text_digest != bob.units[0].text_digest
    assert alice.units[0].unit_id != bob.units[0].unit_id
    assert alice.exclusions[0].candidate_digest != bob.exclusions[0].candidate_digest
