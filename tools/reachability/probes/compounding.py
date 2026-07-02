#!/usr/bin/env python3
"""Compounding reachability probe — reuse PAYS, not merely FIRES (ACV SPR-06 M5).

Distinct from the SPR-02 ``flywheel`` probe — DO NOT collapse the two:

  * ``flywheel`` asserts reuse FIRED: ``knowledge_reuse_count > 0`` (a
    ``knowledge.reused`` event was emitted). That goes green the instant the
    wire is connected, even with an EMPTY corpus (reuse-of-nothing is recorded).
  * ``compounding`` (THIS probe) asserts reuse PAID: a warm research that reuses
    prior knowledge does measurably LESS work — ``cost_warm < cost_cold`` BEYOND
    the benchmark's material floor — than a cold one. A run can FIRE reuse and
    still pay nothing (the reuse-blind demo loop's keystone null); this probe
    fails in that case, which is exactly the gap SPR-06 closes.

The real path it exercises (no test-fixture injection, no ``retrieval_substrate=``,
no stubbed providers):

    create_app()                            # the production factory
      -> seed a small GROUNDED corpus via the REAL deposit surface
         (promote_insight with a claim->chunk->doc chain — the SAME surface the
         benchmark harness uses; "warm seeded ONLY through the real surface,
         never by hand-injecting an answer")
      -> POST a COLD cascade launch on an UNRELATED topic   (corpus covers
         nothing -> the reuse-consuming loop does full work)
      -> POST a WARM cascade launch on the SEEDED topic      (corpus covers the
         planned sub-questions -> the loop short-circuits them -> less work)
      -> read the per-investigation event logs and compare summed dispatch.call
         cost: assert cost_warm < cost_cold beyond the floor.

Why seed the corpus rather than rely on the cold run's own deposit: the
host-local browse loop (demo OR reuse-consuming) deposits insights via the
promotion funnel's ``ctx.note`` -> ``promote_insight`` path, which produces an
UNGROUNDED insight (no claim->chunk->doc chain). ``retrieve_prior_units``
CORRECTLY refuses an ungrounded node (``knowledge_unit_of`` raises), so a placeholder
loop's own deposit is not reusable — grounding a deposit is a REAL-browse-loop
capability (it fetches the document), out of SPR-06's scope. So this probe seeds
the prior knowledge through the sanctioned real deposit surface (exactly the
"corpus accumulates across back-to-back investigations" of decision-0.2 Part C),
then asserts the REAL factory's reuse path + the reuse-consuming loop turn that
prior knowledge into a measured cost reduction. The reuse SUBSTRATE itself is
built by the prod factory (``build_prod_retrieval_substrate``) reading the seeded
graph — NEVER injected by this probe.

The assertion is on a real cost OUTCOME beyond the floor
(``cost_cold − cost_warm`` exceeds ``MATERIAL_FLOOR_USD``), never the mere
presence of ``knowledge.reused`` (that is the flywheel probe), never a parameter,
never a mocked substrate.

§16: the seed write goes through the single host write connection
(``connect_write`` under the same lock the funnel uses) — no second runtime
writer. The cold/warm launches drive the EXISTING HostLocalRunner via the real
cascade routes.
"""

from __future__ import annotations

import glob
import os
import shutil
import tempfile
import time

from tools.reachability.probe_runner import Probe, ProbeResult

# Upper bound on how long to wait for a background fan-out to produce a COMPLETED
# leaf investigation before giving up. SOURCE: the reuse-consuming loop
# (cascade_routes._research_loop_factory -> make_reuse_consuming_loop(steps=3))
# emits at most 3 dispatch.calls with no delay and completes in well under 1 s
# in-process; the reuse hook fires synchronously inside ``start`` BEFORE the loop
# runs. We POLL (below) rather than sleep a fixed interval, so a fast runner
# returns immediately and a slow CI runner gets headroom up to this deadline
# without a spurious RED. 8.0 s is generous headroom for TWO launches; the whole
# probe stays well inside the runner's DEFAULT_PROBE_TIMEOUT_S (30 s).
_FANOUT_DEADLINE_S = 8.0
# How often to poll for the leaf JSONL to appear + complete. Small enough that a
# sub-second in-process completion is detected promptly.
_FANOUT_POLL_INTERVAL_S = 0.1

# The material floor the cost reduction must clear to count as a paid saving (not
# noise). SOURCE: matches the reuse-consuming loop's cost_per_step (0.01 USD,
# runtime/research_runner/browse_loop.py DEFAULT_COST_PER_STEP_USD) — a real
# saving must skip at least one full sub-question's worth of work, so the floor
# is one step's cost. A cold run does 3 steps (0.03); a warm run that genuinely
# reuses skips >=1, so cost_cold − cost_warm >= 0.01 when reuse pays. Set at one
# step so a single genuinely-covered sub-question already clears it.
MATERIAL_FLOOR_USD = 0.01

# The seeded topic the WARM launch reuses + an UNRELATED topic for the COLD
# launch (zero salient-token overlap with the seed, so the corpus covers nothing
# for it — the cold baseline does full work). Drawn from the benchmark's own
# zero-overlap control domains so the disjointness is the same the §2 control
# relies on.
_WARM_TOPIC = "neutral atom qubit gate error rates fidelity scaling threshold"
_COLD_TOPIC = "roman concrete seawater durability pozzolanic ash crystal growth"


def _seed_grounded_corpus(db_path: str) -> str:
    """Deposit ONE grounded knowledge unit (claim->chunk->doc->insight) on the
    warm topic through the REAL deposit surface, so a warm research can retrieve +
    reuse it. Returns the deposited insight node id. Single-writer-safe: one
    ``connect_write`` under the host lock, one transaction (mirrors the benchmark
    harness's ``_seed_units``)."""
    from processing.embedding.embed import default_embedding_provider
    from runtime.db_lock import connect_write
    from substrate.graph.insight_question import promote_insight
    from substrate.graph.ops import insert_node
    from substrate.graph.schema import init_database

    emb = default_embedding_provider()
    text = _WARM_TOPIC + " established prior result with measured values"
    con = connect_write(db_path, purpose="compounding_probe_seed")
    try:
        init_database(con)
        con.execute("BEGIN")
        con.execute(
            "INSERT INTO documents (document_id, title, source_tier, document_type, "
            "content_class) VALUES (?, ?, 1, 'paper', 'public_domain')",
            ["doc-compounding-seed", "compounding probe seed"],
        )
        con.execute(
            "INSERT INTO chunks (chunk_id, document_id, chunk_index, text, embedding, "
            "token_count) VALUES (?, ?, 0, ?, ?, ?)",
            ["chunk-compounding-seed", "doc-compounding-seed", text, emb.encode(text), 20],
        )
        claim = insert_node(
            con, canonical_label="claim: " + text, node_type="claim",
            graph_scope="depth", investigation_id="prior-compounding-seed",
            embedding=emb.encode(text), on_conflict="ignore",
        )
        nid = promote_insight(
            text=text, investigation_id="prior-compounding-seed", confidence="high",
            supported_by=[claim], source_document_id="doc-compounding-seed",
            chunk_id="chunk-compounding-seed", embedding_provider=emb, con=con,
        )
        con.execute("COMMIT")
    finally:
        con.close()
    return nid


def _leaf_cost(events_dir: str, leaf_ids: list[str]) -> tuple[float, list[str]]:
    """Sum ``dispatch.call`` cost_usd over the given leaf investigations (the
    reuse-consuming loop's real spend) and collect any reused_unit_ids. Reads via
    the shipped trajectory reader (the SAME path the measurement uses), scoped to
    THIS launch's leaf ids — never a process-global counter (rigor #3)."""
    from substrate.event_log import trajectory

    total = 0.0
    reused: list[str] = []
    for iid in leaf_ids:
        for row in trajectory(iid, events_dir=events_dir):
            if row.get("action_type") == "dispatch.call":
                total += float(row.get("payload", {}).get("cost_usd", 0.0) or 0.0)
            elif row.get("action_type") == "knowledge.reused":
                reused += list(row.get("payload", {}).get("reused_unit_ids", []) or [])
    return total, reused


# The terminal action_type the runner persists when a leaf investigation finishes
# (host_local.py `_finish(..., ActionType.INVESTIGATION_COMPLETED, ...)`). SOURCE:
# substrate/schemas/events.py:83 `INVESTIGATION_COMPLETED = "investigation.completed"`.
# Once this row is present, every dispatch.call has been written and the leaf's
# summed cost is final.
_LEAF_DONE_ACTION = "investigation.completed"


def _leaf_is_done(events_dir: str, iid: str) -> bool:
    """True once the leaf investigation's JSONL carries the runner's terminal
    ``investigation.completed`` event — i.e. every dispatch.call has been written
    and cost is fully captured. Reading cost before this can undercount.
    Best-effort: a read error on a mid-write file is treated as not-yet-done (we
    poll again)."""
    from substrate.event_log import trajectory

    try:
        for row in trajectory(iid, events_dir=events_dir):
            if row.get("action_type") == _LEAF_DONE_ACTION:
                return True
    except Exception:  # noqa: BLE001 — mid-write/partial file → not done yet
        return False
    return False


def _await_completed_leaves(
    events_dir: str, before: set[str], *, deadline_s: float
) -> list[str]:
    """Poll until at least one NEW ``leaf`` investigation has appeared AND
    completed (terminal ``done`` event), or the deadline elapses. Returns the new
    completed leaf ids (possibly empty if the deadline passed with none done).

    Replaces a fixed ``time.sleep``: a fast in-process run returns in one poll; a
    slow CI runner gets headroom up to ``deadline_s`` without a spurious RED, and
    we never read a leaf's cost before its trajectory is fully written."""
    end = time.monotonic() + deadline_s
    while True:
        after = {
            os.path.basename(p)[:-6]
            for p in glob.glob(os.path.join(events_dir, "*.jsonl"))
        }
        new_leaves = [i for i in (after - before) if "leaf" in i]
        done_leaves = [i for i in new_leaves if _leaf_is_done(events_dir, i)]
        if done_leaves:
            return done_leaves
        if time.monotonic() >= end:
            # Deadline reached: return whatever new leaves exist (even if not
            # observed done) so the caller's existing "could not identify a leaf"
            # diagnostic still fires honestly rather than hanging.
            return new_leaves
        time.sleep(_FANOUT_POLL_INTERVAL_S)


def _probe() -> ProbeResult:
    pid = os.getpid()
    tmp_root = tempfile.mkdtemp(prefix=f"acv-compounding-probe-{pid}-")
    tmp_db = os.path.join(tmp_root, f"compounding-probe-{pid}.db")
    tmp_events = os.path.join(tmp_root, "events")
    os.makedirs(tmp_events, exist_ok=True)

    saved = {
        k: os.environ.get(k)
        for k in (
            "ANTIEK_DUCKDB_PATH",
            "ANTIEK_RESEARCH_EVENTS_DIR",
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
        "DEEPSEEK_API_KEY", "OPENROUTER_API_KEY", "ANTHROPIC_API_KEY",
        "HERMES_API_KEY", "XAI_API_KEY", "OPENAI_API_KEY", "ANTIEK_OPERATOR_TOKEN",
    ):
        os.environ[key] = ""

    try:
        # ── boot the app the PRODUCTION way (failure mode: boot_fail) ──
        try:
            from fastapi.testclient import TestClient

            from interfaces.research.api.app import create_app

            app = create_app()  # NO retrieval_substrate=, NO register_providers=False
            client = TestClient(app)
        except Exception as exc:  # noqa: BLE001
            return ProbeResult(
                ok=False,
                reason=f"create_app() failed to boot: {type(exc).__name__}: {exc}",
                failure_mode="boot_fail",
            )

        # ── seed the grounded corpus the WARM launch reuses (real surface) ──
        try:
            _seed_grounded_corpus(tmp_db)
        except Exception as exc:  # noqa: BLE001
            return ProbeResult(
                ok=False,
                reason=f"could not seed the grounded corpus: {type(exc).__name__}: {exc}",
                failure_mode="error",
            )

        def _launch(problem: str, sub_question: str) -> ProbeResult | list[str]:
            """Drive one real cascade launch; return its leaf investigation ids,
            or a ProbeResult on a route failure."""
            before = {
                os.path.basename(p)[:-6]
                for p in glob.glob(os.path.join(tmp_events, "*.jsonl"))
            }
            r = client.post(
                "/research/plans",
                json={"problem": problem, "sub_questions": [sub_question], "max_depth": 1},
            )
            if r.status_code == 404:
                return ProbeResult(ok=False, reason="POST /research/plans 404'd", failure_mode="route_404")
            if r.status_code != 200:
                return ProbeResult(
                    ok=False, reason=f"POST /research/plans -> {r.status_code}: {r.text[:160]}",
                    failure_mode="feature_dead",
                )
            root_id = r.json()["root_node_id"]
            r = client.post(f"/research/plans/{root_id}/approve", json={"approver": "__probe__"})
            if r.status_code != 200:
                return ProbeResult(
                    ok=False, reason=f"approve -> {r.status_code}: {r.text[:160]}",
                    failure_mode="feature_dead" if r.status_code != 404 else "route_404",
                )
            r = client.post(
                f"/research/plans/{root_id}/launch",
                json={"per_research_budget_usd": 1.0, "aggregate_budget_usd": 5.0},
            )
            if r.status_code != 200:
                return ProbeResult(
                    ok=False, reason=f"launch -> {r.status_code}: {r.text[:160]}",
                    failure_mode="feature_dead" if r.status_code != 404 else "route_404",
                )
            # Poll until the leaf investigation appears AND completes (terminal
            # ``done`` event) rather than sleeping a fixed interval — so a slow CI
            # runner cannot RED spuriously and cost is read only after it is fully
            # written.
            return _await_completed_leaves(
                tmp_events, before, deadline_s=_FANOUT_DEADLINE_S
            )

        # ── COLD launch on the UNRELATED topic (full work) ──
        cold = _launch("compounding probe (cold): " + _COLD_TOPIC, _COLD_TOPIC)
        if isinstance(cold, ProbeResult):
            return cold
        cost_cold, _ = _leaf_cost(tmp_events, cold)

        # ── WARM launch on the SEEDED topic (reuse pays) ──
        warm = _launch("compounding probe (warm): " + _WARM_TOPIC, _WARM_TOPIC)
        if isinstance(warm, ProbeResult):
            return warm
        cost_warm, warm_reused = _leaf_cost(tmp_events, warm)

        # ── assert the OUTCOME: reuse PAID, beyond the floor ──
        saving = cost_cold - cost_warm
        if not cold or not warm:
            return ProbeResult(
                ok=False,
                reason=(
                    f"could not identify a leaf investigation for both launches "
                    f"(cold={cold}, warm={warm}) — the cascade entrypoint may have "
                    f"changed shape"
                ),
                failure_mode="feature_dead",
            )
        if saving >= MATERIAL_FLOOR_USD and cost_warm < cost_cold:
            return ProbeResult(ok=True, failure_mode="reachable")
        return ProbeResult(
            ok=False,
            reason=(
                f"cost_warm >= cost_cold (or saving below floor): cost_cold="
                f"{cost_cold:.6g}, cost_warm={cost_warm:.6g}, saving={saving:.6g} "
                f"< floor {MATERIAL_FLOOR_USD:.6g}; warm reused_unit_ids={warm_reused}. "
                f"Reuse may have FIRED (the flywheel probe) but did not PAY — the "
                f"reuse-consuming loop did not short-circuit work for the warm "
                f"research, OR the seeded unit was not retrieved/covered."
            ),
            failure_mode="feature_dead",
        )
    finally:
        for key, val in saved.items():
            if val is None:
                os.environ.pop(key, None)
            else:
                os.environ[key] = val
        shutil.rmtree(tmp_root, ignore_errors=True)


PROBE = Probe(
    id="compounding",
    feature="compounding (reuse REDUCES cost — paid, not merely fired)",
    run=_probe,
)
