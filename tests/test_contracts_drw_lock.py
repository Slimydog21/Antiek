"""Tests for the frozen DRW sprint-lock (antiek-unified SPR-01 M3).

The lock converts the biggest integration risk (a DRW renumber silently
breaking three downstream specs) into a CI invariant. Rigor #3: a test that
*mutates* a DRW sprint and asserts the citation check fails — so we know the
guard works, not just that it passes on the happy path.
"""

from __future__ import annotations

import pytest

from substrate.contracts import drw_sprint_lock as lock


def test_all_sprints_resolve():
    for n in range(1, 11):
        d = lock.resolve_drw_sprint(n)
        assert d.sprint == n
        assert d.slug and d.deliverable


def test_out_of_range_raises():
    with pytest.raises(KeyError, match="not in the frozen sprint-lock"):
        lock.resolve_drw_sprint(99)


def test_citations_resolve_clean():
    # Every DRW sprint a downstream spec cites must resolve in the lock.
    assert lock.verify_citations_resolve() == []


def test_every_cited_sprint_is_locked():
    for sprint in lock.cited_sprints():
        assert sprint in lock.DRW_SPRINTS


def test_renumber_breaks_a_downstream_citation(monkeypatch):
    # Simulate DRW dropping/renumbering SPR-10 (cited by read + write) without
    # updating the lock. The citation check must catch it.
    poisoned = dict(lock.DRW_SPRINTS)
    del poisoned[10]
    monkeypatch.setattr(lock, "DRW_SPRINTS", poisoned)
    errors = lock.verify_citations_resolve()
    assert errors, "renumbering a cited DRW sprint must produce a citation error"
    assert any("SPR-10" in e for e in errors)
    # and resolving it now raises
    with pytest.raises(KeyError):
        lock.resolve_drw_sprint(10)


def test_reading_surface_is_provisional():
    # DRW SPR-10 is not yet implemented — the lock must say so, matching
    # reading_surface.PROVISIONAL.
    assert lock.resolve_drw_sprint(10).status == "provisional"


def test_owned_contracts_reference_real_contract_names():
    from substrate import contracts as c

    for d in lock.DRW_SPRINTS.values():
        for name in d.owns_contracts:
            assert hasattr(c, name), f"lock names unknown contract {name!r}"


def test_lock_version_present():
    assert isinstance(lock.LOCK_VERSION, int) and lock.LOCK_VERSION >= 1
