from __future__ import annotations

import pytest

from substrate.engagement_spine import (
    HighlightSelection,
    InMemoryEngagementStore,
    complete_spawn,
    spawn_from_highlight_with_references,
)
from substrate.engagement_spine.authority import EngagementAuthority
from substrate.engagement_spine.collective_manifest import (
    CollectiveManifestUnavailable,
    create_collective_manifest,
    read_collective_manifest,
)
from substrate.engagement_spine.store import authorized_store


def _fixture():
    base = InMemoryEngagementStore()
    store = authorized_store(base, EngagementAuthority("alice"))
    ids = []
    for name in ("a", "b"):
        spawn = spawn_from_highlight_with_references(
            HighlightSelection(asset_id=f"asset-{name}", selection_text=name),
            store=store,
            references=[f"https://example.test/{name}"],
        )
        complete_spawn(spawn.spawn_id, output_text=f"evidence {name}", store=store)
        ids.append(spawn.spawn_id)
    return base, store, ids


def test_order_sensitive_identity_and_idempotent_replay():
    base, store, ids = _fixture()
    first = create_collective_manifest(ids, store=store)
    replay = create_collective_manifest(ids, store=store)
    reverse = create_collective_manifest(list(reversed(ids)), store=store)
    assert first == replay
    assert first.collective_id == reverse.collective_id
    assert first.manifest_id != reverse.manifest_id
    assert len(base._docs) == 2


def test_selected_corrupt_manifest_is_unavailable():
    base, store, ids = _fixture()
    manifest = create_collective_manifest(ids, store=store)
    next(iter(base._docs.values()))["membership_sha256"] = "0" * 64
    with pytest.raises(CollectiveManifestUnavailable):
        read_collective_manifest(manifest.manifest_id, store=store)


def test_creation_and_read_do_not_mutate_spawns():
    base, store, ids = _fixture()
    before = {key: dict(value) for key, value in base._spawns.items()}
    manifest = create_collective_manifest(ids, store=store)
    read_collective_manifest(manifest.manifest_id, store=store)
    assert base._spawns == before
