"""First-class internal sentinel identities in accounting validation.

Prod 2026-10: ``interfaces/research/api/app.py``'s /thought-partner endpoint
defaults a missing ``investigation_id`` to ``"__sidecar__"`` and /complete
always dispatches with ``"__complete__"``. Both ids name event-log streams,
so the note-taker replay worker discovers them and calls the ownership guard
``ByotUsageLedger.owned_wrestling_for_investigation`` — whose ``_identity``
regex rejected any leading underscore, raising
``ValueError("accounting identity is invalid")`` on every poll. The replay
looped forever ("Note-taker replay recovery remains pending for
__sidecar__ ...") and sentinel-scoped accounting writes never landed.

These tests pin, against a real temporary SQLite ledger (the real call site,
not a monkeypatched one):
- both sentinels pass validation and resolve to "no owned job" (None);
- an unknown sentinel-shaped string ("__other__") still raises;
- user data with a leading underscore still raises — the regex is not widened.
"""

from __future__ import annotations

from pathlib import Path

import pytest

from substrate.byot_usage.ledger import ByotUsageLedger


@pytest.fixture()
def ledger(tmp_path: Path) -> ByotUsageLedger:
    return ByotUsageLedger(tmp_path / "usage.sqlite3")


@pytest.mark.parametrize("sentinel", ["__sidecar__", "__complete__"])
def test_internal_sentinels_pass_identity_validation(
    ledger: ByotUsageLedger, sentinel: str
) -> None:
    """The replay ownership guard is the real call site: a sentinel stream has
    no owned-wrestling row, so the answer is None — never a ValueError."""
    assert ledger.owned_wrestling_for_investigation(sentinel) is None


def test_unknown_sentinel_shaped_identity_still_raises(ledger: ByotUsageLedger) -> None:
    """Only the two minted sentinels are admitted; any other leading-underscore
    value must keep failing, or the allowlist is a regex widening in disguise."""
    with pytest.raises(ValueError, match="accounting identity is invalid"):
        ledger.owned_wrestling_for_investigation("__other__")


def test_user_data_with_leading_underscore_still_raises(ledger: ByotUsageLedger) -> None:
    with pytest.raises(ValueError, match="accounting identity is invalid"):
        ledger.owned_wrestling_for_investigation("_owner-supplied")


def test_ordinary_investigation_ids_still_pass(ledger: ByotUsageLedger) -> None:
    """Positive control: the fix must not disturb the pre-existing contract."""
    assert ledger.owned_wrestling_for_investigation("inv-12") is None
