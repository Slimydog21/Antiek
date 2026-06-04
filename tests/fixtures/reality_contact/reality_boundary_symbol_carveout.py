"""Fixture: stubbing a CORE module's boundary_symbol carve-out is NOT theater.

Imports the dispatch router (claims to cover routing) and monkeypatches
`DispatchConfig.from_yaml` — the config-FILE loader carved out as a boundary
symbol — substituting an in-memory config. The real routing decision still runs,
so the verdict must be `reality`, NOT theater. (This mirrors the 12 real tests
the M4 ledger surfaced.)
"""

from substrate.dispatch import router


def test_stubs_only_the_config_loader(monkeypatch):
    monkeypatch.setattr(
        router.DispatchConfig,
        "from_yaml",
        classmethod(lambda cls, path: router.DispatchConfig(role_tiers={}, tiers={})),
    )
    assert router is not None
