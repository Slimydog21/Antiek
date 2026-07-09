"""Consumer double-run launch for Antiek-bench public entries.

Fixed fixtures → stable run_id and suite_version across two independent runs.
"""

from __future__ import annotations

import os
import sys

_REPO = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
if _REPO not in sys.path:
    sys.path.insert(0, _REPO)

from substrate.antiek_bench import (  # noqa: E402
    InMemoryBenchStore,
    SuiteRegistry,
    approve_and_promote,
    default_core_suite,
    project_run_html,
    propose_suite_delta,
    register_suite,
    run_suite,
)
from substrate.antiek_bench.run import keyword_stub_provider  # noqa: E402


def _run_once() -> dict[str, object]:
    reg = SuiteRegistry()
    register_suite(default_core_suite(), registry=reg, make_active=True)
    store = InMemoryBenchStore()
    result = run_suite(
        model_id="launch-model",
        week_id="2026-W28",
        store=store,
        registry=reg,
        provider_fn=keyword_stub_provider("launch-model", quality=0.9),
    )
    html = project_run_html(result.run_id, store=store)
    assert result.suite_version == "suite-v1"
    assert result.week_id == "2026-W28"
    assert "distill" in result.by_task_class
    assert "synthesize" in result.by_task_class
    assert "launch-model" in html
    assert "suite-v1" in html
    assert not html.lstrip().lower().startswith("%pdf")

    # Propose without activate
    prop = propose_suite_delta(
        [
            {
                "task_class": "distill",
                "outcome": "failed",
                "prompt_hint": "Distill launch regression on citation fidelity",
            }
        ],
        store=store,
        registry=reg,
    )
    assert reg.active_version == "suite-v1"
    # Approve → promote
    promoted = approve_and_promote(prop.proposal_id, store=store, registry=reg, approve=True)
    assert promoted.suite_version == prop.proposed_suite_version
    assert reg.active_version == prop.proposed_suite_version

    return {
        "run_id": result.run_id,
        "suite_version": result.suite_version,
        "mean_score": result.mean_score,
        "html_len": len(html),
        "proposal_id": prop.proposal_id,
        "promoted_version": promoted.suite_version,
    }


def test_consumer_launch_double_run_stable():
    a = _run_once()
    b = _run_once()
    assert a["run_id"] == b["run_id"]
    assert a["suite_version"] == b["suite_version"] == "suite-v1"
    assert a["mean_score"] == b["mean_score"]
    assert a["html_len"] == b["html_len"]
    assert str(a["run_id"]).startswith("brun_")
    from substrate.antiek_bench.run import _run_id

    expected = _run_id("2026-W28", "suite-v1", "launch-model")
    assert a["run_id"] == expected == b["run_id"]
    assert a["proposal_id"] == b["proposal_id"]
    assert a["promoted_version"] == b["promoted_version"]
