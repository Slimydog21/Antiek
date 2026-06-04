"""Fixture: imports TWO core subsystems; theater for one, real for the other.

Imports both substrate.graph.ops and substrate.attribution.compute. Mocks a core
symbol of attribution (theater for attribution) but exercises graph.ops for
real (only its boundary — none here — is touched). Verdict: `mixed`.
"""

from unittest.mock import patch

from substrate.graph import ops  # noqa: F401  (real)
from substrate.attribution import compute  # noqa: F401  (mocked → theater)


@patch("substrate.attribution.compute.compute_attribution_for_synthesis")
def test_mixed_real_ops_theater_attribution(mock_attr):
    mock_attr.return_value = []
    # graph.ops is imported and NOT mocked → reality for that subsystem
    assert ops is not None
