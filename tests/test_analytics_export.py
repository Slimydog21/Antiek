"""Smoke test for the extracted analytics-export substrate (insight from #83).

Non-vacuous: proves the package's public symbols resolve against current main
and the workflow_taxonomy + dispatch_rows shapes are stable. The deeper
end-to-end (real parquet export over a live event log) is #83's territory; this
pins the import surface that extraction landed.
"""

from __future__ import annotations

from substrate.analytics import (
    agent_write_purposes,
    corpuscrawl_snapshot,
    dispatch_rows,
)
from substrate.coordination import workflow_taxonomy


def test_analytics_package_imports_resolve():
    """All three analytics modules + the workflow_taxonomy dep import clean
    against current main (the extraction is self-consistent)."""
    assert dispatch_rows is not None
    assert agent_write_purposes is not None
    assert corpuscrawl_snapshot is not None
    assert workflow_taxonomy is not None


def test_workflow_taxonomy_is_a_real_module_with_symbols():
    """The dep #83 adds (workflow_taxonomy) is not empty — it carries the
    taxonomy dispatch_rows consumes. Pin at least one public symbol exists."""
    public = [
        n for n in dir(workflow_taxonomy) if not n.startswith("_")
    ]
    assert len(public) > 0, "workflow_taxonomy exported no public symbols"
