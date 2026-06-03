#!/usr/bin/env python3
"""Flywheel reachability probe — the canonical first probe (SPR-01 M3).

Drives a MINIMAL real research launch through the production cascade
entrypoint and asserts the compounding OUTCOME: at least one
``knowledge.reused`` event was emitted (``knowledge_reuse_count > 0``).

The real path it exercises (no test-fixture injection, no
``retrieval_substrate=``, no stubbed providers):

    create_app()                          # the production factory
      -> POST /research/plans             # one explicit sub-question
      -> POST /research/plans/{id}/approve
      -> POST /research/plans/{id}/launch # builds HostLocalRunner + runs it
      -> read the per-investigation event log for knowledge.reused

It asserts on the PER-INVESTIGATION event log (action_counts over the
probe's own temp events dir), NOT a process-global /health counter: the
global counter is mutated by every other run on the box and would make the
assertion flaky (rigor #3 "flaky count"). The temp dir is created fresh per
probe run, so the count is exactly what THIS launch produced.

────────────────────────────────────────────────────────────────────────
GREEN once SPR-02 wires ``retrieval_substrate`` into
``interfaces/research/api/cascade_routes.py`` (the ``HostLocalRunner(...)``
construction at line 367 currently omits it, leaving it ``None``; the reuse
hook ``runtime/research_runner/host_local.py:259`` early-returns on
``None``, so no ``knowledge.reused`` event fires and this probe is RED).
If GREEN now, the wire already landed — confirm it (grep
cascade_routes.py for ``retrieval_substrate=``) and note it; do NOT assume
success from a green here (rigor #1: a green could also mean a stale count
or an injected substrate — neither of which this probe can produce, because
it boots via the bare factory and reads a fresh temp event log).
────────────────────────────────────────────────────────────────────────

Why this is RED today is NOT the empty-corpus condition that #68 (commit
873d95b0) correctly demoted on PROD: the reuse assembler
(``substrate/context_pack/knowledge_reuse.py:652``) emits a
``knowledge.reused`` event even with ZERO prior units ("reuse-of-nothing is
recorded, not skipped"). So this probe goes GREEN the instant the WIRE is
connected — it needs no pre-seeded corpus. It isolates the CODE defect
(the dead wire SPR-02 fixes) from the PRODUCT-maturity condition (a fed
prod corpus, which prod-parity ``--require-flywheel`` additionally requires).
"""

from __future__ import annotations

import os
import tempfile
import time

from tools.reachability.probe_runner import ProbeResult

# How long to let the background fan-out task run before reading the event
# log. SOURCE: the demo loop (cascade_routes._research_loop_factory ->
# make_demo_loop(steps=3)) emits 3 steps with delay_s=0.0 and completes in
# well under 1 s in-process; the reuse hook fires synchronously inside
# ``start`` BEFORE the loop runs, so the knowledge.reused event (when the
# wire is present) lands almost immediately. 3.0 s is generous headroom on
# the shared CI runner. The whole probe stays well inside the runner's
# DEFAULT_PROBE_TIMEOUT_S (30 s). (Measured during SPR-01 M1: ~2 s end-to-end.)
_FANOUT_SETTLE_S = 3.0


def _probe() -> ProbeResult:
    # Isolate ALL substrate writes to per-PID temp paths so the probe never
    # touches the live shared DuckDB (held under the --workers 1 single-writer
    # lock by ~4 concurrent sessions) and reads a clean event log it alone
    # wrote. ANTIEK_DUCKDB_PATH redirects substrate.graph.default_db_path();
    # ANTIEK_RESEARCH_EVENTS_DIR redirects the event log dir. Both verified in
    # SPR-01 M1. We set them in os.environ for the duration of this probe and
    # restore on exit (the runner may run other probes after us).
    pid = os.getpid()
    tmp_root = tempfile.mkdtemp(prefix=f"antiek-probe-{pid}-")
    tmp_db = os.path.join(tmp_root, f"antiek-probe-{pid}.db")
    tmp_events = os.path.join(tmp_root, "events")
    os.makedirs(tmp_events, exist_ok=True)

    saved = {
        k: os.environ.get(k)
        for k in (
            "ANTIEK_DUCKDB_PATH",
            "ANTIEK_RESEARCH_EVENTS_DIR",
            # Defence-in-depth: keep paid providers OUT of the boot so a
            # leaky path fails fast rather than spending operator credentials.
            "DEEPSEEK_API_KEY",
            "OPENROUTER_API_KEY",
            "ANTHROPIC_API_KEY",
            "HERMES_API_KEY",
            "XAI_API_KEY",
            "OPENAI_API_KEY",
            "ANTIEK_OPERATOR_TOKEN",
        )
    }
    os.environ["ANTIEK_DUCKDB_PATH"] = tmp_db
    os.environ["ANTIEK_RESEARCH_EVENTS_DIR"] = tmp_events
    for key in (
        "DEEPSEEK_API_KEY",
        "OPENROUTER_API_KEY",
        "ANTHROPIC_API_KEY",
        "HERMES_API_KEY",
        "XAI_API_KEY",
        "OPENAI_API_KEY",
        "ANTIEK_OPERATOR_TOKEN",
    ):
        os.environ[key] = ""

    try:
        # ── boot the app the PRODUCTION way (failure mode: boot_fail) ──
        try:
            from interfaces.research.api.app import create_app
            from fastapi.testclient import TestClient

            app = create_app()  # NO retrieval_substrate=, NO register_providers=False
            client = TestClient(app)
        except Exception as exc:  # noqa: BLE001
            return ProbeResult(
                ok=False,
                reason=f"create_app() failed to boot: {type(exc).__name__}: {exc}",
                failure_mode="boot_fail",
            )

        # ── drive the real cascade entrypoint (failure mode: route_404) ──
        # Explicit sub_questions avoid the live LLM decomposer (no paid call).
        r = client.post(
            "/research/plans",
            json={
                "problem": "reachability probe: minimal compounding launch",
                "sub_questions": ["a single minimal sub-question for the flywheel probe"],
                "max_depth": 1,
            },
        )
        if r.status_code == 404:
            return ProbeResult(
                ok=False,
                reason="POST /research/plans 404'd — the cascade entrypoint moved",
                failure_mode="route_404",
            )
        if r.status_code != 200:
            return ProbeResult(
                ok=False,
                reason=f"POST /research/plans -> {r.status_code}: {r.text[:200]}",
                failure_mode="feature_dead",
            )
        root_id = r.json()["root_node_id"]

        r = client.post(f"/research/plans/{root_id}/approve", json={"approver": "__probe__"})
        if r.status_code == 404:
            return ProbeResult(
                ok=False,
                reason=f"POST /research/plans/{{id}}/approve 404'd for {root_id}",
                failure_mode="route_404",
            )
        if r.status_code != 200:
            return ProbeResult(
                ok=False,
                reason=f"approve -> {r.status_code}: {r.text[:200]}",
                failure_mode="feature_dead",
            )

        r = client.post(
            f"/research/plans/{root_id}/launch",
            json={"per_research_budget_usd": 1.0, "aggregate_budget_usd": 5.0},
        )
        if r.status_code == 404:
            return ProbeResult(
                ok=False,
                reason=f"POST /research/plans/{{id}}/launch 404'd for {root_id}",
                failure_mode="route_404",
            )
        if r.status_code != 200:
            return ProbeResult(
                ok=False,
                reason=f"launch -> {r.status_code}: {r.text[:200]}",
                failure_mode="feature_dead",
            )

        # The launch schedules the fan-out as a background asyncio task; let
        # it settle. The reuse hook fires synchronously inside runner.start
        # (before the demo loop), so when the wire is present the event is
        # already written; this settle is headroom, not a race fix.
        # TODO(SPR-02, when this probe goes GREEN): replace the fixed sleep
        # with a poll of the event log for the knowledge.reused row until a
        # timeout, so a fast box returns immediately and a slow box still gets
        # its full window — the fixed sleep is correct for the RED assertion
        # today (we expect ZERO reuse rows, so there is nothing to poll for)
        # but becomes a flat latency tax / flake risk once the wire lands and
        # we are waiting for a row to appear. See the "Handoff to SPR-02"
        # section of docs/decisions/reachability-gate.md.
        time.sleep(_FANOUT_SETTLE_S)

        # ── assert the OUTCOME on the PER-INVESTIGATION event log ──
        # (failure mode: feature_dead — booted + launched, but no reuse event)
        from substrate.event_log import action_counts

        counts = action_counts(events_dir=tmp_events)
        reused = sum(
            int(row.get("count", 0) or 0)
            for row in counts
            if row.get("action_type") == "knowledge.reused"
        )
        if reused > 0:
            return ProbeResult(ok=True, failure_mode="reachable")
        return ProbeResult(
            ok=False,
            reason=(
                "knowledge_reuse_count == 0 — the launch ran but emitted NO "
                "knowledge.reused event. The flywheel is dead at the prod "
                "entrypoint: cascade_routes.py:367 builds HostLocalRunner "
                "without retrieval_substrate, so host_local.py:259 early-returns "
                "the reuse hook. SPR-02 wires it -> this goes GREEN."
            ),
            failure_mode="feature_dead",
        )
    finally:
        # Restore env (the runner may run more probes after this one).
        for key, val in saved.items():
            if val is None:
                os.environ.pop(key, None)
            else:
                os.environ[key] = val
        # Best-effort cleanup of the temp tree.
        import shutil

        shutil.rmtree(tmp_root, ignore_errors=True)


# Imported lazily so this top-level import is cheap; build the descriptor here.
from tools.reachability.probe_runner import Probe  # noqa: E402

PROBE = Probe(
    id="flywheel",
    feature="flywheel (compounding knowledge.reused emission)",
    run=_probe,
)
