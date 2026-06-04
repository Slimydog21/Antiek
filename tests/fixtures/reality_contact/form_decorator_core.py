"""Fixture: @patch decorator targeting a CORE symbol → theater.

The test below imports a core subsystem (orchestrator) and patches a symbol
under it with the decorator form. The classifier must label it `theater`.
This is fixture DATA parsed by the extractor; it is never executed.
"""

from unittest.mock import patch

from orchestration.loop_one import orchestrator  # noqa: F401  (claims to cover it)


@patch("orchestration.loop_one.orchestrator._run_investigation")
def test_decorator_patches_core(mock_run):
    mock_run.return_value = None
    assert True
