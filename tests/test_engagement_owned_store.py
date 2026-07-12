from __future__ import annotations

from pathlib import Path
from typing import Any

import pytest

from substrate.engagement_spine.store import (
    FileEngagementStore,
    InMemoryEngagementStore,
    owned_document_id,
)


@pytest.mark.parametrize("store_kind", ["memory", "file"])
def test_owned_document_prefix_listing_is_paged_and_owner_closed(tmp_path, store_kind):
    store = (
        InMemoryEngagementStore()
        if store_kind == "memory"
        else FileEngagementStore(tmp_path / "engagement")
    )
    for owner in ("alice", "bob"):
        for suffix in ("1111", "2222", "3333"):
            unit_id = f"cunit_{suffix}"
            store.mutate_owned_document(
                unit_id,
                owner,
                lambda _current, uid=unit_id: {
                    "document_type": "collective_research_unit",
                    "collective_unit_id": uid,
                },
            )
    store.mutate_owned_document(
        "collective_draft_ignore",
        "alice",
        lambda _current: {"document_type": "collective_written_analysis"},
    )

    first = store.list_owned_documents(
        "alice", logical_prefix="cunit_", after_logical_id=None, limit=2
    )
    second = store.list_owned_documents(
        "alice",
        logical_prefix="cunit_",
        after_logical_id=first[-1][0],
        limit=2,
    )
    assert [row["collective_unit_id"] for _logical_id, row in [*first, *second]] == [
        "cunit_1111",
        "cunit_2222",
        "cunit_3333",
    ]
    assert all(row["owner_id"] == "alice" for _logical_id, row in [*first, *second])
    with pytest.raises(ValueError, match="cursor is not available"):
        store.list_owned_documents(
            "alice",
            logical_prefix="cunit_",
            after_logical_id="cunit_foreign",
            limit=2,
        )
    with pytest.raises(ValueError, match="outside the listing contract"):
        store.list_owned_documents("alice", logical_prefix="../", after_logical_id=None, limit=2)


@pytest.mark.parametrize("backend", ["memory", "file"])
def test_owned_document_fails_closed_on_embedded_owner_drift(backend: str, tmp_path: Path) -> None:
    store: Any = (
        InMemoryEngagementStore()
        if backend == "memory"
        else FileEngagementStore(tmp_path / "engagement")
    )
    physical_id = owned_document_id("alice", "asset-1")
    store.put_document(physical_id, {"document_id": physical_id, "owner_id": "bob"})

    assert store.get_owned_document("asset-1", "alice") is None
    with pytest.raises(ValueError, match="conflicting embedded owner"):
        store.mutate_owned_document(
            "asset-1", "alice", lambda _current: {"document_id": physical_id}
        )
    with pytest.raises(ValueError, match="listing requires reconciliation"):
        store.list_owned_documents("alice", logical_prefix="asset", after_logical_id=None, limit=2)
    assert store.get_document(physical_id)["owner_id"] == "bob"


@pytest.mark.parametrize("backend", ["memory", "file"])
def test_only_operator_can_adopt_ownerless_legacy_document(backend: str, tmp_path: Path) -> None:
    store: Any = (
        InMemoryEngagementStore()
        if backend == "memory"
        else FileEngagementStore(tmp_path / "engagement")
    )
    store.put_document("legacy-1", {"document_id": "legacy-1"})

    assert store.get_owned_document("legacy-1", "__operator__") is not None
    adopted = store.mutate_owned_document(
        "legacy-1", "__operator__", lambda current: dict(current or {})
    )
    assert adopted["owner_id"] == "__operator__"
