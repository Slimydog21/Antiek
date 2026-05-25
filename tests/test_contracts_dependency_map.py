"""Tests for the cross-spec dependency DAG (antiek-unified SPR-01 M4).

Rigor #3 for this sprint: a guard you have not seen fail is a guard you do not
know works. So acyclicity is not merely asserted on the real graph — a
deliberately-injected cycle is asserted to *fail*.
"""

from __future__ import annotations

import pytest

from substrate.contracts import dependency_map as dm


def test_real_dag_is_acyclic():
    order = dm.verify_acyclic()
    # Every node appears exactly once in the topological order.
    assert len(order) == len(dm.nodes())
    assert set(order) == dm.nodes()


def test_injected_cycle_fails():
    # drw:1 → drw:3 already exists (drw:3 depends on drw:1). Add the reverse
    # to force a 2-cycle and assert the guard catches it.
    poisoned = dm.EDGES + (dm.Edge("drw:1", "drw:3", "(injected cycle)"),)
    with pytest.raises(ValueError, match="not acyclic"):
        dm.verify_acyclic(poisoned)


def test_critical_path_is_the_drw_spine():
    # The acceptance criterion: SPR-01 → SPR-03 → SPR-10, provider-first.
    assert dm.critical_path() == ["drw:1", "drw:3", "drw:10"]


def test_critical_path_nodes_are_load_bearing():
    cp = set(dm.critical_path())
    assert {"drw:1", "drw:3", "drw:10"} <= cp
    # and they are real nodes in the graph
    assert {"drw:1", "drw:3", "drw:10"} <= dm.nodes()


def test_every_edge_names_a_contract():
    # Diligence: no edge is encoded without naming what flows across it.
    for e in dm.EDGES:
        assert e.contract, f"edge {e.consumer}->{e.provider} carries no contract"


def test_products_depend_on_drw_not_the_reverse():
    # The dependency direction must be product→DRW (consumer→provider), never
    # DRW→product — DRW is the critical path, nothing upstream of it.
    for e in dm.EDGES:
        if e.provider.startswith(("read", "write", "speak")):
            assert not e.consumer.startswith("drw:"), (
                f"DRW must not depend on a product: {e.consumer}->{e.provider}"
            )
