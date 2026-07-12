from __future__ import annotations

from pathlib import Path
from typing import Any

import pytest

from substrate.engagement_spine.store import (
    FileEngagementStore,
    InMemoryEngagementStore,
    owned_document_id,
)


@pytest.mark.parametrize("backend", ["memory", "file"])
def test_owned_document_fails_closed_on_embedded_owner_drift(
    backend: str, tmp_path: Path
) -> None:
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
    assert store.get_document(physical_id)["owner_id"] == "bob"


@pytest.mark.parametrize("backend", ["memory", "file"])
def test_only_operator_can_adopt_ownerless_legacy_document(
    backend: str, tmp_path: Path
) -> None:
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

