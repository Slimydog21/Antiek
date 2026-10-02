"""A failed probe must report unknown, never "yes".

``/health`` publishes turbopuffer_duckdb_is_sot and
turbopuffer_thought_partner_hybrid_wired. Both used to resolve True on the
probe's EXCEPT branch — two properties asserted as satisfied precisely when the
code had just failed to check either one. A health field that says yes on its
own failure path is worse than no field, because a reader cannot tell the
difference between verified and unverifiable.
"""

from __future__ import annotations

import os
import sys

import pytest
from fastapi.testclient import TestClient

_HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, os.path.dirname(_HERE))

from substrate.graph.retrieval_adapters import turbopuffer as tpuf  # noqa: E402


def test_failed_probe_reports_unknown_not_true(monkeypatch):
    """Force the probe to raise; the two claims must come back None."""

    def boom(*_a, **_kw):
        raise RuntimeError("injected probe failure")

    # The probe imports this INSIDE the function, so patch it at its source
    # module rather than on the adapter.
    from substrate.graph import retrieval_substrate

    monkeypatch.setattr(
        retrieval_substrate, "resolve_reuse_substrate_kind", boom
    )

    out = tpuf.probe_turbopuffer_health(db_path="/nonexistent/x.duckdb")

    assert out.get("error"), "the probe must record that it failed"
    assert out["thought_partner_hybrid_wired"] is None, (
        "a failed probe asserted the thought-partner hybrid was wired"
    )
    assert out["duckdb_is_sot"] is None, (
        "a failed probe asserted DuckDB was the source of truth"
    )
    # The safety-shaped booleans stay False: false is the correct answer to
    # "is this feature live" when nothing could be confirmed.
    assert out["hybrid_ready"] is False
    assert out["resolved_kind"] == "brute_force"


def test_health_route_does_not_launder_unknown_into_a_boolean(
    tmp_path, monkeypatch
):
    """The /health handler must pass None through rather than bool() it."""
    from interfaces.research.api.app import create_app
    from substrate.graph.schema import init_database_at_path

    db_path = tmp_path / "graph.duckdb"
    init_database_at_path(str(db_path))
    monkeypatch.setenv("ANTIEK_DUCKDB_PATH", str(db_path))
    monkeypatch.setenv("ANTIEK_RESEARCH_EVENTS_DIR", str(tmp_path / "events"))

    app = create_app(
        register_wrestling=False, register_providers=False, cors_origins=[]
    )
    # Simulate a probe that never ran: the keys are simply absent.
    app.state.turbopuffer_health = {}

    body = TestClient(app).get("/health").json()

    assert body["turbopuffer_duckdb_is_sot"] is None, (
        "an absent probe result defaulted to True"
    )
    assert body["turbopuffer_thought_partner_hybrid_wired"] is None, (
        "an absent probe result defaulted to True"
    )


@pytest.mark.parametrize(
    "field",
    ["thought_partner_hybrid_wired", "duckdb_is_sot"],
)
def test_the_constants_are_labelled_as_constants(field):
    """These two are literals in the success branch, not measurements.

    That is defensible — one is a design invariant, the other a structural
    claim — but only while the source says so. If someone deletes the comment
    and leaves the literal, the next reader has no way to tell this field from
    the computed ones beside it.
    """
    import inspect

    src = inspect.getsource(tpuf.probe_turbopuffer_health)
    assert "CONSTANTS, not measurements" in src, (
        f"{field} is a hardcoded literal in the success branch and the note "
        "explaining that has been removed"
    )
