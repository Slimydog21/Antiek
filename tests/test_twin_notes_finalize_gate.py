"""Red-proofs for provisional draft finalize gate (no I/O, no parent mutation)."""

from __future__ import annotations

import pytest

from substrate.twin_notes.finalize_gate import (
    FinalizeGateError,
    authorize_finalize,
)


def test_authorize_happy_path() -> None:
    auth = authorize_finalize(
        draft_id="draft-abc",
        parent_asset_id="parent-1",
        provisional=True,
        operator_accepted=True,
        twin_ids=["t1"],
        twin_parent_ids=["parent-1"],
    )
    assert auth.authorized is True
    assert auth.reason == "ok"
    assert auth.draft_id == "draft-abc"
    assert "not performed here" in " ".join(auth.notes)


def test_rejects_non_provisional() -> None:
    auth = authorize_finalize(
        draft_id="d",
        parent_asset_id="p",
        provisional=False,
        operator_accepted=True,
    )
    assert auth.authorized is False
    assert auth.reason == "not_provisional_draft"


def test_requires_operator_accept() -> None:
    auth = authorize_finalize(
        draft_id="d",
        parent_asset_id="p",
        provisional=True,
        operator_accepted=False,
    )
    assert auth.authorized is False
    assert auth.reason == "operator_accept_required"


def test_cross_parent_rejected() -> None:
    auth = authorize_finalize(
        draft_id="d",
        parent_asset_id="p1",
        provisional=True,
        operator_accepted=True,
        twin_parent_ids=["p1", "p2"],
    )
    assert auth.authorized is False
    assert auth.reason == "cross_parent_twins"


def test_empty_twin_ids_when_provided() -> None:
    auth = authorize_finalize(
        draft_id="d",
        parent_asset_id="p",
        provisional=True,
        operator_accepted=True,
        twin_ids=[],
    )
    assert auth.authorized is False
    assert auth.reason == "no_twins"


def test_malformed_ids_raise() -> None:
    with pytest.raises(FinalizeGateError, match="draft_id"):
        authorize_finalize(
            draft_id="  ",
            parent_asset_id="p",
            provisional=True,
            operator_accepted=True,
        )
    with pytest.raises(FinalizeGateError, match="parent_asset_id"):
        authorize_finalize(
            draft_id="d",
            parent_asset_id="",
            provisional=True,
            operator_accepted=True,
        )


def test_no_parent_mutation_side_effects() -> None:
    """Gate returns authorization only — does not import store or write files."""
    import inspect

    import substrate.twin_notes.finalize_gate as mod

    src = inspect.getsource(mod)
    assert "TwinNotesStore" not in src
    assert "open(" not in src
    assert "Path(" not in src
    assert ".write" not in src
    assert "store." not in src
