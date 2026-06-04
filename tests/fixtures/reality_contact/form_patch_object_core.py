"""Fixture: `patch.object(Module, "attr")` form → theater.

`compute` is bound (via import) to substrate.attribution.compute, so
patch.object(compute, "compute_attribution_for_synthesis") resolves to
substrate.attribution.compute.compute_attribution_for_synthesis — a core symbol.
"""

from unittest.mock import patch

from substrate.attribution import compute


def test_patch_object_core():
    with patch.object(compute, "compute_attribution_for_synthesis") as m:
        m.return_value = []
        assert True
