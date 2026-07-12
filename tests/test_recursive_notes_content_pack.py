from __future__ import annotations

from dataclasses import asdict

from substrate.context_pack import (
    build_canonical_recursive_pack,
    digest_text,
)
from substrate.engagement_spine import (
    InMemoryEngagementStore,
    record_twin_insight,
    record_twin_question,
)


class _Graph:
    def __init__(self, rows):
        self.rows = rows

    def execute(self, _query, _parameters=None):
        return self

    def fetchall(self):
        return list(self.rows)


class _UnavailableGraph:
    def execute(self, _query, _parameters=None):
        raise OSError("offline")


def test_canonical_pack_returns_consumable_content_with_provenance_and_digests():
    store = InMemoryEngagementStore()
    insight = record_twin_insight(
        "canonical/a",
        "Prior evidence contradicts the rollout thesis.",
        store=store,
        investigation_id="inv-1",
    )
    question = record_twin_question(
        "canonical/a",
        "Which adoption cohort would falsify the thesis?",
        store=store,
        source_spawn_id="spn-1",
    )
    pack = build_canonical_recursive_pack(
        store=store,
        owner_user_id="owner-1",
        asset_ids=["canonical/a"],
        asset_owner=lambda asset_id: "owner-1" if asset_id == "canonical/a" else None,
        goal="Assess adoption evidence and falsify the thesis",
        explicit_note_ids=[insight.note_id],
    )

    assert pack.pack_ready is True
    assert [unit.twin_note_id for unit in pack.units] == [
        insight.note_id,
        question.note_id,
    ]
    assert all(unit.text and unit.text_digest == digest_text(unit.text) for unit in pack.units)
    assert all(
        unit.account_scope_digest and unit.rights_label == "owner_readable" for unit in pack.units
    )
    assert pack.units[0].source_event_ids == ()
    assert pack.units[1].source_event_ids == ()
    assert pack.token_estimate <= pack.token_budget


def test_graph_content_deduplicates_against_its_canonical_twin():
    store = InMemoryEngagementStore()
    note = record_twin_insight("canonical/a", "Same promoted content.", store=store)
    graph = _Graph(
        [
            (
                "node-1",
                "insight",
                note.text,
                {
                    "origin": "twin_note",
                    "twin_asset_id": "canonical/a",
                    "twin_note_id": note.note_id,
                },
                "2026-07-12T00:00:00Z",
            )
        ]
    )
    pack = build_canonical_recursive_pack(
        store=store,
        con=graph,
        owner_user_id="owner-1",
        asset_ids=["canonical/a"],
        asset_owner=lambda _asset_id: "owner-1",
        goal="promoted content",
    )
    assert len(pack.units) == 1
    assert pack.units[0].text == note.text
    assert any(receipt.reason == "duplicate_content" for receipt in pack.exclusions)


def test_bounds_diversity_and_order_are_deterministic():
    store = InMemoryEngagementStore()
    notes = []
    for index in range(8):
        record = record_twin_question if index % 2 else record_twin_insight
        notes.append(
            record(
                f"asset-{index // 3}",
                ("relevant " if index in {2, 4} else "other ") + "x" * (20 + index),
                store=store,
            )
        )

    def owner(_asset: str) -> str:
        return "owner"

    first = build_canonical_recursive_pack(
        store=store,
        owner_user_id="owner",
        asset_ids=["asset-0", "asset-1", "asset-2"],
        asset_owner=owner,
        goal="relevant",
        explicit_note_ids=[notes[5].note_id],
        token_budget=30,
        max_unit_bytes=80,
        max_units=4,
        per_asset_limit=1,
    )
    second = build_canonical_recursive_pack(
        store=store,
        owner_user_id="owner",
        asset_ids=["asset-2", "asset-1", "asset-0"],
        asset_owner=owner,
        goal="relevant",
        explicit_note_ids=[notes[5].note_id],
        token_budget=30,
        max_unit_bytes=80,
        max_units=4,
        per_asset_limit=1,
    )
    assert first == second
    assert first.units[0].twin_note_id == notes[5].note_id
    assert len({unit.asset_id for unit in first.units}) == len(first.units)
    assert first.token_estimate <= 30
    assert first.truncated is True


def test_pack_ready_cannot_survive_content_dropping():
    store = InMemoryEngagementStore()
    record_twin_insight("a", "usable", store=store)
    pack = build_canonical_recursive_pack(
        store=store,
        owner_user_id="owner",
        asset_ids=["a"],
        asset_owner=lambda _asset: "owner",
        goal="usable",
    )
    assert pack.pack_ready
    dropped = type(pack)(
        units=(),
        exclusions=pack.exclusions,
        token_estimate=0,
        token_budget=pack.token_budget,
        candidate_count=pack.candidate_count,
    )
    assert dropped.pack_ready is False
    assert "usable" not in str([asdict(receipt) for receipt in dropped.exclusions])


def test_forged_or_malformed_graph_rows_are_receipted_not_consumed():
    store = InMemoryEngagementStore()
    note = record_twin_insight("asset", "Canonical exact text.", store=store)
    graph = _Graph(
        [
            (
                "forged",
                "insight",
                "Substituted text.",
                {
                    "origin": "twin_note",
                    "twin_asset_id": "asset",
                    "twin_note_id": note.note_id,
                },
                "2026-07-12T00:00:00Z",
            ),
            ("bad-metadata", "insight", note.text, [], None),
            ("short-row",),
        ]
    )
    pack = build_canonical_recursive_pack(
        store=store,
        con=graph,
        owner_user_id="owner",
        asset_ids=["asset"],
        asset_owner=lambda _asset: "owner",
        goal="canonical",
    )

    assert [unit.text for unit in pack.units] == [note.text]
    assert sum(receipt.reason == "malformed" for receipt in pack.exclusions) == 3


def test_malformed_twin_rows_fail_closed_while_valid_rows_survive():
    store = InMemoryEngagementStore()
    valid = record_twin_insight("asset", "Trusted row.", store=store)
    store.put_twin({"note_id": "forged", "asset_id": "asset", "kind": "bogus"})
    pack = build_canonical_recursive_pack(
        store=store,
        owner_user_id="owner",
        asset_ids=["asset"],
        asset_owner=lambda _asset: "owner",
        goal="trusted",
    )

    assert [unit.twin_note_id for unit in pack.units] == [valid.note_id]
    assert any(receipt.reason == "malformed" for receipt in pack.exclusions)


def test_graph_outage_preserves_canonical_twins_and_is_receipted():
    store = InMemoryEngagementStore()
    note = record_twin_insight("asset", "Still available.", store=store)
    pack = build_canonical_recursive_pack(
        store=store,
        con=_UnavailableGraph(),
        owner_user_id="owner",
        asset_ids=["asset"],
        asset_owner=lambda _asset: "owner",
        goal="available",
    )

    assert [unit.twin_note_id for unit in pack.units] == [note.note_id]
    assert any(receipt.reason == "resolver_unavailable" for receipt in pack.exclusions)
