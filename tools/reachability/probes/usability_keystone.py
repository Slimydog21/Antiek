#!/usr/bin/env python3
"""End-to-end usability keystone — the CONJUNCTION probe (ACV SPR-08, capstone).

Every OTHER reachability probe asserts ONE leg in isolation: ``flywheel`` asserts
reuse FIRES, ``compounding`` asserts reuse PAYS, ``read`` asserts the read route is
wired, ``retrieval_gate`` asserts §9 withholds a restricted body, ``dispatch``
asserts the synthesizer pin. What NO probe asserts is the CONJUNCTION — that a
fresh test operator can, as ONE journey through the real ``create_app()`` factory:

    login   →  start a research  →  watch it COMPOUND  →  read the result
                                                          with §9 attribution intact

That conjunction is the Jobs-bar: an EXECUTABLE definition of "usable". The product
shipped DEAD in prod precisely because every BRICK was green while the JOURNEY was
broken (the cascade built the runner with ``retrieval_substrate=None``; ``/health``
showed ``knowledge_reuse_count=0`` on live prod while every unit/contract test
passed). A per-brick gate could not see that; a per-journey gate can. THIS probe is
that gate. It builds NO new feature — it COMPOSES the existing legs and makes a
broken core loop fail the deploy.

────────────────────────────────────────────────────────────────────────────
THE FIVE LEGS (each a distinct observable OUTCOME; stages run IN ORDER and stop
at the first failure — never collapse to a bare "failed"):

  login        Set a NON-empty test ANTIEK_OPERATOR_TOKEN and exercise the REAL
               middleware bearer path (app.py:1315-1340): a protected route returns
               401 WITHOUT the bearer header and 200 WITH it, verified by
               ``secrets.compare_digest`` (NOT a hand-minted bypass). The
               authenticated client (carrying the header) is carried through every
               later leg. CAVEAT (recorded, not stubbed): the magic-link / AgentMail
               email round-trip is NOT exercised in-process; the bearer-token path
               through the real middleware is the closest REAL path (a real HTTP 401
               then 200 through the same ``_operator_auth_middleware`` a browser's
               cookie path also flows through). See docs/decisions/usability-keystone.md.

  launch       Start a research via the CANONICAL prod entrypoint (POST
               /research/plans → /approve → /launch — cascade_routes.py:577-638,
               the SAME flow flywheel/compounding drive), AUTHENTICATED, then POLL
               to a TERMINAL state. In-process: poll the per-leaf event log to the
               terminal ``investigation.completed`` event (substrate/schemas/
               events.py:83). LIVE: poll the production ``GET /research/sessions/
               {session_id}`` status route (cascade_routes.py:666) until every
               research's RunState is terminal (``done``/``stopped``/``failed``/
               ``budget_halted``), and red a non-``done`` terminal. A research that
               never reaches terminal within the bounded deadline is reported as the
               ``launch`` leg (a FINDING), never a silent pass — IN BOTH MODES.
               SCOPE (disclosed up front): prod's research loop is TODAY the SYNTHETIC
               ``make_reuse_consuming_loop`` placeholder (``cost_per_step=0.01``,
               ``model="reuse_consuming_demo"`` — cascade_routes.py
               ``_research_loop_factory``), NOT a real LLM/Exa/Browserbase loop.
               "Usable" here means the wired core journey is reachable end-to-end and
               reuse is real at the GRAPH level (prior knowledge units are retrieved,
               injected, and reused) — NOT that the research produces real-quality
               answers; the real loop drops in later (out of this keystone's scope).
               See docs/decisions/usability-keystone.md.

  compound     Assert PRIOR KNOWLEDGE was genuinely REUSED by THIS investigation —
               the sum of ``len(reused_unit_ids)`` across its PER-INVESTIGATION
               ``knowledge.reused`` events is ≥ 1, NOT merely that the event fired.
               (``knowledge.reused`` fires UNCONDITIONALLY once per start whenever a
               retrieval substrate is wired — even an empty graph emits it with
               ``reused_unit_ids: []`` — so counting events would green-pass a
               zero-reuse run, proving only "the hook fired". The keystone seeds a
               grounded covering unit on ``_KEYSTONE_TOPIC`` and launches on that same
               topic, so a healthy flywheel retrieves + injects it and
               ``reused_unit_ids`` is non-empty.) In-process: read each event's
               ``reused_unit_ids`` via ``trajectory`` scoped to the leaf iid on the
               temp events dir. LIVE: fetch ``GET /trajectory/{leaf}`` (app.py:1751)
               over HTTP and sum the SAME ``reused_unit_ids`` field — the SAME
               per-investigation OUTCOME, read over the prod HTTP surface (NOT the
               frozen-at-boot /health global snapshot, NOT a bare event count). A
               global count can be true while THIS user's research compounded nothing
               — the keystone asserts the user's own journey actually reused units,
               IN BOTH MODES, so a dead flywheel on live prod REDS the live keystone.

  read         Fetch a real artifact through the real backend read/chunk HTTP
               surface — GET /chunks/{id}, a REAL authenticated HTTP fetch through
               the production route (app.py:2155-2257) — and assert a body came back.

  attribution  On that SAME fetched artifact, assert §9 attribution PRESENCE +
               well-formedness: the chunk cites its document (``document_id``
               present) AND ``ip_holder_name`` / ``ip_holder_status`` present AND
               ``servable`` / ``servability`` well-formed (servable True ⇒
               servability null; the inverse holds for a withheld source). This is
               attribution METADATA PRESENCE only (graph-only) — NO §9 serving or
               payout is activated (G2/G3 stay closed; no Stripe / serve trigger is
               touched). Distinct from ``read``: a present-but-malformed attribution
               reds HERE, not the read leg.

REACHABLE only when ALL FIVE legs hold. Each assertion is a feature OUTCOME, never
a parameter / mock. The probe boots via the bare production ``create_app()`` factory
— NO ``retrieval_substrate=`` injection, NO ``register_providers=False``, NO stubbed
providers (grep the file to prove it). That injection is the EXACT blind spot the
benchmark had and that this whole gate exists to kill; recreating it here by
stubbing a leg to green the conjunction would rebuild the disease (rigor #1).

────────────────────────────────────────────────────────────────────────────
CAVEATS (each a NAMED closest-real-path with WHY it is honest, NOT a stub — see
docs/decisions/usability-keystone.md):

  * login via BEARER, not the email round-trip. The bearer path runs through the
    real ``_operator_auth_middleware`` and is verified by ``compare_digest`` against
    a NON-empty token — a real 401→200 transition, not a parameter flip. The
    magic-link email leg needs AgentMail + a live inbox (operator-gated, networked),
    out of an in-process probe's reach. Bearer is the closest REAL auth path.

  * read via the BACKEND chunk fetch, not a headless render. A full render of the
    Vite/React reading SPA needs Playwright/chromium, not available in CI (read.py
    :47-58 documents this same caveat for the read probe). GET /chunks/{id} is a
    real HTTP fetch through the production route — the bytes really do (or do not)
    leave the backend. The render-throw failure mode is covered by the vitest suite
    (apps/reading/src/modes/Reading/Reading.test.tsx), out of CI's headless reach.

  * read leg reads a SEEDED §9-attributed source document, NOT this journey's own
    research output. The read+attribution legs fetch a separately-seeded servable
    public-domain doc (in-process: ``_seed_read_artifact``; live: a real prod
    ``ANTIEK_PROBE_READ_CHUNK_ID``), because the launched demo cascade deposits
    INSIGHTS, not a §9-readable chunk — there is no chunk of THIS journey's own
    product to read back. WHAT PROTECTIVE VALUE SURVIVES: a dead read surface (route
    moved / 404) and a stripped/malformed §9 attribution still RED here — the read
    door and the attribution shape are genuinely exercised end-to-end. WHAT IT DOES
    NOT COVER: read-back of THIS journey's own research output (that the specific
    research just launched produced a readable, attributed artifact). When the
    cascade deposits §9-readable chunks, promote the read leg to fetch one of THIS
    investigation's chunks (see Reconsider-if in the decision record).

  * the LIVE run against api.antiek.ai is OPERATOR-GATED, not executed here — but it
    asserts the SAME five legs as in-process. The base-URL parameterization
    (``ANTIEK_PROBE_BASE_URL``) runs the SAME probe against live prod post-deploy;
    the in-process mode is the pre-merge gate. Live mode does NOT skip or weaken any
    leg: login (bearer 401→200), launch (poll GET /research/sessions to terminal),
    compound (sum GET /trajectory knowledge.reused reused_unit_ids ≥ 1 for THIS
    leaf — prior units actually reused, not just the event fired), read +
    attribution (GET /chunks against a real prod chunk id). The live run writes a
    research to the prod graph + needs prod creds + prod is HELD pending §9.0, so the
    operator runs it as the documented post-deploy step (infrastructure/runbooks/
    usability-keystone-verify-live.md). This in-process gate, parameterized, IS that
    probe — no forked second impl, and no leg silently asserts less live than the
    docs claim.

────────────────────────────────────────────────────────────────────────────
§16 / §9.0 SAFETY. The probe writes only to per-PID temp paths (ANTIEK_DUCKDB_PATH
+ ANTIEK_RESEARCH_EVENTS_DIR), through the same ``connect_write`` host lock the
funnel uses (no second graph writer). It seeds + reads ONLY the way the existing
probes do (real surfaces, temp DB). The attribution leg asserts metadata PRESENCE
only — it never activates serving or payout (no payout.py / stripe_connect /
serve.py path is touched). Env is restored + the temp tree rmtree'd in ``finally``.
"""

from __future__ import annotations

import contextlib
import os
import shutil
import tempfile
import time

from tools.reachability.probe_runner import Probe, ProbeResult

# A NON-empty test operator token. Setting ANTIEK_OPERATOR_TOKEN to a non-empty
# value is what ENABLES the real auth enforcement (app.py:1219 — when all three
# auth env vars are empty, enforcement is bypassed and the login leg would not be
# exercised). This value is a probe-local dummy; it never reaches prod (the live
# run uses the operator's real token via ANTIEK_PROBE_OPERATOR_TOKEN — see the
# runbook). compare_digest (app.py:1322) verifies the SAME value the request
# carries, so the 401→200 transition is a real middleware decision, not a bypass.
_TEST_OPERATOR_TOKEN = "acv-spr08-usability-keystone-probe-token"  # noqa: S105 — test dummy

# A protected route to probe the auth gate against. /research/plans (POST) is a
# protected operator route (NOT in _OPERATOR_AUTH_OPEN_PATHS — /health, /auth/*
# are open). We POST it twice in the login leg: once WITHOUT the bearer header
# (expect 401 operator_auth_required) and once WITH it (expect != 401 — the
# request reaches the route). We use POST /research/plans so the SAME route that
# the launch leg drives is the one whose auth we prove.
_PROTECTED_ROUTE = "/research/plans"

# Upper bound on how long to wait for the launched research to reach the terminal
# ``investigation.completed`` event. SOURCE: identical to the compounding probe's
# deadline rationale — the reuse-consuming loop (make_reuse_consuming_loop(steps=3,
# cost_per_step=0.01)) emits at most 3 dispatch.calls with no delay and completes in
# well under 1 s in-process; the reuse hook fires synchronously inside ``start``
# BEFORE the loop runs. We POLL (not a fixed sleep) so a fast runner returns
# immediately and a slow CI runner gets headroom without a spurious RED. 8.0 s is
# generous headroom for one launch; the whole probe stays inside the runner's
# DEFAULT_PROBE_TIMEOUT_S (30 s). Matches compounding.py:_FANOUT_DEADLINE_S.
_TERMINAL_DEADLINE_S = 8.0
_TERMINAL_POLL_INTERVAL_S = 0.1

# The terminal action_type the runner persists when a leaf investigation finishes
# (host_local.py `_finish(..., ActionType.INVESTIGATION_COMPLETED, ...)`). SOURCE:
# substrate/schemas/events.py:83 INVESTIGATION_COMPLETED = "investigation.completed".
_TERMINAL_ACTION = "investigation.completed"

# LIVE mode polls GET /research/sessions/{session_id}, whose researches[].state is
# a RunState string. The terminal RunState values are the ones is_terminal() admits
# (runtime/research_runner/protocol.py:55-56): done | stopped | failed |
# budget_halted. SUCCESS-terminal is "done" — the live launch leg asserts the
# research reached a TERMINAL state (and surfaces a non-"done" terminal as a finding,
# never a silent pass). The deterministic session id is "session-{root_id}"
# (cascade_routes.py:603).
_LIVE_TERMINAL_STATES = frozenset({"done", "stopped", "failed", "budget_halted"})
_LIVE_SUCCESS_STATE = "done"

# The per-investigation reuse event the compound leg reads. SOURCE:
# substrate/schemas/events.py:180 KNOWLEDGE_REUSED = "knowledge.reused". Emitted
# once per investigation start inside runner.start (host_local.py) when the
# retrieval substrate is wired. CRITICAL: this event fires UNCONDITIONALLY whenever
# a retrieval substrate is wired — even with an EMPTY graph it is emitted with
# ``reused_unit_ids: []`` (knowledge_reuse.py:_emit_knowledge_reused, "reuse-of-
# nothing is recorded"). The compound leg therefore asserts on the OUTCOME — the
# sum of ``len(reused_unit_ids)`` across this leaf's events, i.e. prior UNITS
# genuinely reused — NOT the count of these events (which would green-pass a
# zero-reuse empty-graph run, proving only "the hook fired").
_REUSE_ACTION = "knowledge.reused"

# The topic the keystone's launched research covers AND the topic of the grounded
# prior-knowledge unit seeded before the launch. They MUST match (mirrors
# compounding.py's _WARM_TOPIC used for both seed + warm launch) so the seeded unit
# is retrieved (retrieve_prior_units), injected (assemble_context_pack_with_reuse),
# and carried into the launched research's ``knowledge.reused`` event with a
# NON-EMPTY ``reused_unit_ids`` — i.e. so REAL reuse of prior knowledge happens, not
# merely the hook firing. Drawn from the benchmark's control domain like compounding.
_KEYSTONE_TOPIC = "neutral atom qubit gate error rates fidelity scaling threshold"

# Ids for the grounded prior-knowledge unit seeded before the launch (in-process
# only; live mode cannot write the prod graph — §16 single-writer).
_PRIOR_DOC_ID = "acv-spr08-keystone-prior-doc"
_PRIOR_CHUNK_ID = "acv-spr08-keystone-prior-chunk"
_PRIOR_INVESTIGATION_ID = "prior-keystone-seed"

# The seed for the read+attribution leg: a SERVABLE public-domain document with a
# real IP-holder row, so GET /chunks/{id} returns a body AND populated attribution
# (ip_holder_name / ip_holder_status). Seeded through the REAL deposit surface
# (insert_document / insert_chunk under the host write lock), exactly as the
# retrieval_gate probe seeds (retrieval_gate.py:105-148). Public-domain so the §9
# gate SERVES it (servable True) — we assert attribution PRESENCE on a servable
# artifact; no serving/payout machinery is activated (metadata only).
_READ_DOC_ID = "acv-spr08-keystone-read-doc"
_READ_IP_HOLDER_ID = "acv-spr08-keystone-ipholder"
_READ_IP_HOLDER_NAME = "Keystone Probe Press"
_READ_CHUNK_TEXT = "Usability-keystone read artifact: a servable public-domain chunk."


# ---------------------------------------------------------------------------
# Per-leg result helper — every BLOCKED result NAMES the failing leg + reason.
# ---------------------------------------------------------------------------


def _blocked(leg: str, reason: str, failure_mode: str = "feature_dead") -> ProbeResult:
    """A BLOCKED result that NAMES the failing leg (M2): the runner prints e.g.
    ``[BLOCKED] usability_keystone: compound — 0 prior units reused ...``.
    ``failure_mode`` distinguishes boot_fail (app could not boot) from a
    feature-dead leg (booted, route responded, OUTCOME did not hold) so the two —
    which need different fixes — are never ambiguous."""
    return ProbeResult(ok=False, reason=f"{leg} — {reason}", failure_mode=failure_mode)


def _seed_read_artifact(db_path: str) -> str:
    """Deposit ONE servable public-domain document + IP-holder + chunk through the
    REAL deposit surface, so the read+attribution leg can fetch a real artifact with
    populated §9 attribution. Returns the chunk_id. Single-writer-safe: one
    ``connect_write`` under the host lock (mirrors retrieval_gate.py's seed)."""
    from runtime.db_lock import connect_write
    from substrate.graph.ops import insert_chunk, insert_document
    from substrate.graph.schema import init_database_at_path

    init_database_at_path(db_path)
    with connect_write(db_path, purpose="acv-spr08-keystone-read-seed") as con:
        # An ip_holders row so the LEFT JOIN in GET /chunks (app.py:2207) resolves
        # a real display_name + status — i.e. the attribution leg asserts on a
        # POPULATED owner, not the null/unknown fallthrough. status default
        # 'pre_onboarded' (schema.py:380) — the honest "account created, not
        # claimed" state (§9.10), NEVER "money waiting".
        con.execute(
            "INSERT INTO ip_holders (ip_holder_id, display_name, status) "
            "VALUES (?, ?, 'pre_onboarded') ON CONFLICT DO NOTHING",
            [_READ_IP_HOLDER_ID, _READ_IP_HOLDER_NAME],
        )
        insert_document(
            con,
            document_id=_READ_DOC_ID,
            source_tier=1,
            document_type="paper",
            title="Usability Keystone Read Artifact",
            # public_domain ⇒ §9 gate SERVES it: servable True, attribution
            # surfaced. We assert attribution PRESENCE on a servable source;
            # no serve/payout path is activated (metadata only — G2/G3 closed).
            content_class="public_domain",
            ip_holder_id=_READ_IP_HOLDER_ID,
            on_conflict="ignore",
        )
        return insert_chunk(
            con,
            document_id=_READ_DOC_ID,
            chunk_index=0,
            text=_READ_CHUNK_TEXT,
            section_path="p.1",
        )


def _seed_prior_knowledge_unit(db_path: str) -> str:
    """Deposit ONE GROUNDED prior-knowledge unit (claim→chunk→doc→insight) on the
    keystone topic through the REAL deposit surface, so the launched research can
    RETRIEVE + REUSE it — turning the compound leg from "the reuse hook fired" into
    "a prior unit was genuinely reused". Returns the deposited insight node id.

    This mirrors ``compounding.py::_seed_grounded_corpus`` exactly: the unit is
    grounded (a real claim→chunk→doc chain) because ``retrieve_prior_units``
    CORRECTLY refuses an ungrounded node (``knowledge_unit_of`` raises), so an
    ungrounded deposit would never be reused. Single-writer-safe: one
    ``connect_write`` under the host lock, one transaction (§16)."""
    from processing.embedding.embed import default_embedding_provider
    from runtime.db_lock import connect_write
    from substrate.graph.insight_question import promote_insight
    from substrate.graph.ops import insert_node
    from substrate.graph.schema import init_database

    emb = default_embedding_provider()
    text = _KEYSTONE_TOPIC + " established prior result with measured values"
    con = connect_write(db_path, purpose="acv-spr08-keystone-prior-seed")
    try:
        init_database(con)
        con.execute("BEGIN")
        con.execute(
            "INSERT INTO documents (document_id, title, source_tier, document_type, "
            "content_class) VALUES (?, ?, 1, 'paper', 'public_domain') "
            "ON CONFLICT DO NOTHING",
            [_PRIOR_DOC_ID, "keystone probe prior-knowledge seed"],
        )
        con.execute(
            "INSERT INTO chunks (chunk_id, document_id, chunk_index, text, embedding, "
            "token_count) VALUES (?, ?, 0, ?, ?, ?) ON CONFLICT DO NOTHING",
            [_PRIOR_CHUNK_ID, _PRIOR_DOC_ID, text, emb.encode(text), 20],
        )
        claim = insert_node(
            con, canonical_label="claim: " + text, node_type="claim",
            graph_scope="depth", investigation_id=_PRIOR_INVESTIGATION_ID,
            embedding=emb.encode(text), on_conflict="ignore",
        )
        nid = promote_insight(
            text=text, investigation_id=_PRIOR_INVESTIGATION_ID, confidence="high",
            supported_by=[claim], source_document_id=_PRIOR_DOC_ID,
            chunk_id=_PRIOR_CHUNK_ID, embedding_provider=emb, con=con,
        )
        con.execute("COMMIT")
    finally:
        con.close()
    return nid


def _await_terminal_leaf(
    events_dir: str, leaf_ids: list[str], *, deadline_s: float
) -> str | None:
    """Poll until at least one of the launch's leaf investigations carries the
    terminal ``investigation.completed`` event, or the deadline elapses. Returns the
    first terminal leaf id, or None if none reached terminal in time. Reading the
    PER-LAUNCH leaf ids (from the launch response) — never a process-global scan —
    keeps the assertion scoped to THIS journey's research (rigor #3)."""
    from substrate.event_log import action_counts

    end = time.monotonic() + deadline_s
    while True:
        for iid in leaf_ids:
            counts = action_counts(iid, events_dir=events_dir)
            if any(row.get("action_type") == _TERMINAL_ACTION for row in counts):
                return iid
        if time.monotonic() >= end:
            return None
        time.sleep(_TERMINAL_POLL_INTERVAL_S)


def _reused_unit_count(events_dir: str, leaf_id: str) -> int:
    """Count the PRIOR UNITS this leaf investigation actually reused — the sum of
    ``len(reused_unit_ids)`` across its ``knowledge.reused`` events.

    This is the OUTCOME the compound leg must prove, NOT the number of
    ``knowledge.reused`` events. ``knowledge.reused`` fires UNCONDITIONALLY once
    per investigation start whenever a retrieval substrate is wired (see
    substrate/context_pack/knowledge_reuse.py:_emit_knowledge_reused — even a novel
    question / empty graph emits the event with ``reused_unit_ids: []``,
    "reuse-of-nothing is recorded"). Counting events therefore green-passes on an
    EMPTY graph where ZERO knowledge was reused — proving "the hook fired", not the
    spec's criterion "demonstrably reuse PRIOR KNOWLEDGE". Summing the injected unit
    ids proves a unit was genuinely retrieved, injected, and carried into the pack.

    Reads via ``trajectory`` (the same path the compounding probe uses to read
    ``reused_unit_ids``) scoped to THIS leaf id — never a process-global counter."""
    from substrate.event_log import trajectory

    return sum(
        len(row.get("payload", {}).get("reused_unit_ids", []) or [])
        for row in trajectory(leaf_id, events_dir=events_dir)
        if row.get("action_type") == _REUSE_ACTION
    )


def _live_await_terminal_session(
    client: object, session_id: str, *, deadline_s: float
) -> tuple[str | None, dict[str, str]]:
    """LIVE launch-poll (the analogue of ``_await_terminal_leaf``, over HTTP).

    Polls ``GET /research/sessions/{session_id}`` until EVERY research carries a
    terminal RunState, or the deadline elapses. Returns ``(terminal_leaf_id,
    states)`` where ``terminal_leaf_id`` is the first research that reached a
    terminal state (or None if none did within the deadline) and ``states`` maps
    every investigation_id → its last-seen state. Same bounded-deadline + "finding
    not silent pass" discipline as the in-process poll — a research that never
    reaches terminal returns ``(None, …)`` so the caller reds the launch leg.

    The route is the production status surface (``cascade_routes.py:666``): a live
    session reports ``researches[].state`` directly; after eviction/restart it
    reconstructs the same shape from the event log (``all_terminal``). We treat a
    research as terminal on its RunState alone, so both the live and the
    recovered-from-log responses are handled identically."""
    end = time.monotonic() + deadline_s
    last_states: dict[str, str] = {}
    while True:
        resp = client.get(f"/research/sessions/{session_id}")
        if resp.status_code == 200:
            try:
                body = resp.json()
            except Exception:  # noqa: BLE001
                body = {}
            researches = body.get("researches") or []
            last_states = {
                r.get("investigation_id"): r.get("state")
                for r in researches
                if r.get("investigation_id")
            }
            terminal = [
                iid for iid, st in last_states.items() if st in _LIVE_TERMINAL_STATES
            ]
            # Only declare "reached terminal" when ALL researches are terminal —
            # the journey is the whole fan-out, not the first leaf to finish.
            if last_states and len(terminal) == len(last_states):
                return terminal[0], last_states
        if time.monotonic() >= end:
            return None, last_states
        time.sleep(_TERMINAL_POLL_INTERVAL_S)


def _live_reused_unit_count(client: object, leaf_id: str) -> int:
    """LIVE compound signal (the analogue of ``_reused_unit_count``, over HTTP).

    Fetches ``GET /trajectory/{leaf_id}`` — the production per-investigation event
    log surface (``app.py:1751``) — and sums ``len(reused_unit_ids)`` across THIS
    leaf's ``knowledge.reused`` events. This is the SAME per-investigation OUTCOME
    the in-process mode asserts (prior UNITS actually reused, read off each event's
    ``reused_unit_ids`` payload), just over HTTP instead of off the temp events dir.
    It is NOT the count of ``knowledge.reused`` events (which fires unconditionally
    even on an empty graph), and NOT the process-global ``/health
    knowledge_reuse_count`` snapshot (frozen at boot, cannot move during a run) — it
    is this user's own research's reused units, the only signal that means "the
    journey compounded by reusing prior knowledge." Returns 0 on any non-200 /
    malformed body (the caller reds compound on 0)."""
    resp = client.get(f"/trajectory/{leaf_id}")
    if resp.status_code != 200:
        return 0
    try:
        body = resp.json()
    except Exception:  # noqa: BLE001
        return 0
    return sum(
        len((ev.get("payload") or {}).get("reused_unit_ids", []) or [])
        for ev in (body.get("events") or [])
        if ev.get("action_type") == _REUSE_ACTION
    )


def _probe(base_url: str | None = None) -> ProbeResult:
    """Run the five-leg keystone journey.

    ``base_url`` parameterizes the ONE probe across two modes (M3 — no forked
    second impl):
      * None (default; read from env ANTIEK_PROBE_BASE_URL) → in-process
        ``TestClient(create_app())`` — the bare production factory, the pre-merge
        gate. This is the mode the runner invokes.
      * a URL (operator's live run, post-deploy) → ``httpx.Client(base_url=...)``
        against the live API. SAME routes, SAME assertions, SAME credential path.

    Live mode asserts the SAME five legs, over the prod HTTP surface — no leg is
    skipped or weakened:
      * launch  → poll GET /research/sessions/{id} to a terminal RunState.
      * compound→ sum GET /trajectory/{leaf} knowledge.reused reused_unit_ids ≥ 1
                  for THIS leaf (prior units actually reused, not just event-fired).
    Two live differences, both §16-forced (the probe cannot write the prod graph):
      * the PRIOR-KNOWLEDGE seed is skipped in-process — live prod already carries
        accumulated prior knowledge in its own graph, and the operator points the
        launch at a topic the prod graph covers (the runbook), so the compound leg
        still asserts a real reused-units OUTCOME over GET /trajectory.
      * the READ-LEG seed is skipped — the operator supplies a real prod chunk id
        via ANTIEK_PROBE_READ_CHUNK_ID and the read leg GETs it (see the runbook).
    The in-process mode (the merge gate this sprint proves RED-capable) seeds its own
    grounded prior unit + read artifact so it is hermetic. Note (read-leg
    caveat above): the read leg reads a SEEDED §9-attributed source document, not
    this journey's own research output, because the cascade deposits insights, not a
    §9-readable chunk."""
    base_url = base_url if base_url is not None else os.environ.get("ANTIEK_PROBE_BASE_URL")
    live = bool(base_url)

    pid = os.getpid()
    tmp_root = tempfile.mkdtemp(prefix=f"acv-keystone-probe-{pid}-")
    tmp_db = os.path.join(tmp_root, f"keystone-probe-{pid}.db")
    tmp_events = os.path.join(tmp_root, "events")
    os.makedirs(tmp_events, exist_ok=True)

    saved = {
        k: os.environ.get(k)
        for k in (
            "ANTIEK_DUCKDB_PATH",
            "ANTIEK_RESEARCH_EVENTS_DIR",
            # Defence-in-depth: keep paid providers OUT of the boot so a leaky
            # path fails fast rather than spending operator credentials.
            "DEEPSEEK_API_KEY",
            "OPENROUTER_API_KEY",
            "ANTHROPIC_API_KEY",
            "HERMES_API_KEY",
            "XAI_API_KEY",
            "OPENAI_API_KEY",
            "ANTIEK_OPERATOR_TOKEN",
        )
    }
    # In-process mode isolates ALL substrate writes to per-PID temp paths (same
    # contract as every other probe). Live mode does NOT redirect these (the live
    # API owns its own paths on the box); we only manage the operator token there.
    if not live:
        os.environ["ANTIEK_DUCKDB_PATH"] = tmp_db
        os.environ["ANTIEK_RESEARCH_EVENTS_DIR"] = tmp_events
        for key in (
            "DEEPSEEK_API_KEY", "OPENROUTER_API_KEY", "ANTHROPIC_API_KEY",
            "HERMES_API_KEY", "XAI_API_KEY", "OPENAI_API_KEY",
        ):
            os.environ[key] = ""
        # ENABLE real auth enforcement: a NON-empty token makes the middleware
        # demand a credential (app.py:1219). Without this the login leg is vacuous.
        os.environ["ANTIEK_OPERATOR_TOKEN"] = _TEST_OPERATOR_TOKEN
        operator_token = _TEST_OPERATOR_TOKEN
    else:
        # Live mode: the operator supplies the real prod token out-of-band so the
        # probe never mints a prod credential itself (scope boundary). The live
        # API already enforces auth; we just present the token.
        operator_token = os.environ.get("ANTIEK_PROBE_OPERATOR_TOKEN", "")

    auth_headers = {"Authorization": f"Bearer {operator_token}"}

    try:
        # ── boot / connect (failure mode: boot_fail) ──
        try:
            if live:
                import httpx

                client = httpx.Client(base_url=base_url, timeout=30.0)
                close_client = client.close
            else:
                from fastapi.testclient import TestClient

                from interfaces.research.api.app import create_app

                # NO retrieval_substrate=, NO register_providers=False, NO stubbed
                # providers — the bare prod factory. (grep this file to prove it.)
                app = create_app()
                client = TestClient(app)
                close_client = lambda: None  # noqa: E731 — TestClient needs no close
        except Exception as exc:  # noqa: BLE001
            return _blocked(
                "boot",
                f"could not boot/connect the app: {type(exc).__name__}: {exc}",
                failure_mode="boot_fail",
            )

        # ── seed a GROUNDED, covering prior-knowledge unit BEFORE the launch ──
        # In-process only (§16: the probe never writes the prod graph; the live API
        # owns its own graph + already-deposited prior knowledge). This makes the
        # compound leg prove REAL reuse: the launched research (driven on the SAME
        # _KEYSTONE_TOPIC) retrieves + injects this seeded unit, so its
        # knowledge.reused event carries a NON-EMPTY reused_unit_ids. Without this
        # seed the launch runs against an EMPTY graph and the event fires with
        # reused_unit_ids: [] — which is exactly the "hook fired, nothing reused"
        # green-pass the new OUTCOME assertion (and its self-test) now rejects.
        if not live:
            try:
                _seed_prior_knowledge_unit(tmp_db)
            except Exception as exc:  # noqa: BLE001
                return _blocked(
                    "compound",
                    f"could not seed the grounded prior-knowledge unit: "
                    f"{type(exc).__name__}: {exc} — the compound leg cannot prove "
                    f"real reuse without a covering prior unit to reuse.",
                    failure_mode="error",
                )

        try:
            # ════════════════════════ LEG 1: login ════════════════════════
            # The protected route returns 401 WITHOUT the bearer header and a
            # non-401 WITH it — the REAL middleware bearer path (compare_digest).
            r_unauth = client.post(
                _PROTECTED_ROUTE,
                json={"problem": "keystone auth probe (no credential)",
                      "sub_questions": ["a"], "max_depth": 1},
            )
            if r_unauth.status_code != 401:
                return _blocked(
                    "login",
                    f"{_PROTECTED_ROUTE} WITHOUT a bearer token returned "
                    f"{r_unauth.status_code}, expected 401 — operator auth is NOT "
                    f"enforced (a protected route is open). Body: {r_unauth.text[:160]}",
                )
            err = {}
            with contextlib.suppress(Exception):
                err = r_unauth.json().get("error", {})
            if err.get("code") != "operator_auth_required":
                return _blocked(
                    "login",
                    f"401 returned but not the operator_auth_required contract: "
                    f"{r_unauth.text[:160]}",
                )
            # WITH the bearer header: the request must reach the route (NOT 401).
            # This authenticated plan is ALSO the plan the launch leg drives, so its
            # problem + sub-question are pinned to _KEYSTONE_TOPIC — the SAME topic
            # the prior-knowledge unit was seeded on (mirrors compounding.py picking
            # _WARM_TOPIC for both seed + launch) — so the launched research genuinely
            # COVERS the seeded unit and reuses it (non-empty reused_unit_ids), the
            # OUTCOME the compound leg asserts.
            r_auth = client.post(
                _PROTECTED_ROUTE,
                json={"problem": f"keystone journey: {_KEYSTONE_TOPIC}",
                      "sub_questions": [_KEYSTONE_TOPIC], "max_depth": 1},
                headers=auth_headers,
            )
            if r_auth.status_code == 401:
                return _blocked(
                    "login",
                    "the bearer token was REJECTED (still 401 WITH the header) — the "
                    "compare_digest path (app.py:1322) did not accept a valid token. "
                    f"Body: {r_auth.text[:160]}",
                )
            if r_auth.status_code != 200:
                return _blocked(
                    "login",
                    f"authenticated {_PROTECTED_ROUTE} returned {r_auth.status_code} "
                    f"(not 401, but not 200) — the route is reachable but failed: "
                    f"{r_auth.text[:160]}",
                )

            # ════════════════════════ LEG 2: launch ═══════════════════════
            # Start a research via the canonical prod entrypoint, AUTHENTICATED,
            # then poll to terminal. (We reuse r_auth's plan as the started plan —
            # it is a real POST /research/plans through the authed client.)
            try:
                root_id = r_auth.json()["root_node_id"]
            except Exception as exc:  # noqa: BLE001
                return _blocked(
                    "launch",
                    f"POST /research/plans response lacked root_node_id: "
                    f"{type(exc).__name__}: {exc} — {r_auth.text[:160]}",
                )
            r = client.post(
                f"/research/plans/{root_id}/approve",
                json={"approver": "__keystone_probe__"},
                headers=auth_headers,
            )
            if r.status_code != 200:
                return _blocked(
                    "launch",
                    f"approve -> {r.status_code}: {r.text[:160]}",
                    failure_mode="route_404" if r.status_code == 404 else "feature_dead",
                )
            r = client.post(
                f"/research/plans/{root_id}/launch",
                json={"per_research_budget_usd": 1.0, "aggregate_budget_usd": 5.0},
                headers=auth_headers,
            )
            if r.status_code != 200:
                return _blocked(
                    "launch",
                    f"launch -> {r.status_code}: {r.text[:160]}",
                    failure_mode="route_404" if r.status_code == 404 else "feature_dead",
                )
            leaf_ids = [
                res["investigation_id"]
                for res in (r.json().get("researches") or [])
                if res.get("investigation_id")
            ]
            if not leaf_ids:
                return _blocked(
                    "launch",
                    f"launch returned no researches[].investigation_id — the cascade "
                    f"entrypoint changed shape: {r.text[:160]}",
                )
            # BOTH modes poll the launched research to a TERMINAL state — never
            # accept-on-launch. In-process reads the per-leaf event log directly;
            # live polls the production GET /research/sessions/{id} status route
            # (the SAME assertion, over HTTP). A research that never reaches terminal
            # within the bounded deadline is a launch FINDING, not a silent pass.
            if live:
                session_id = f"session-{root_id}"
                terminal_leaf, live_states = _live_await_terminal_session(
                    client, session_id, deadline_s=_TERMINAL_DEADLINE_S
                )
                if terminal_leaf is None:
                    return _blocked(
                        "launch",
                        f"no research in session {session_id!r} reached a terminal "
                        f"state within {_TERMINAL_DEADLINE_S:.0f}s via "
                        f"GET /research/sessions (states={live_states or 'none'}) — the "
                        f"research started but never completed (bounded-poll finding "
                        f"on the live status route, not a silent pass).",
                        failure_mode="timeout",
                    )
                # A terminal-but-non-"done" state (failed / budget_halted / stopped)
                # is reached-but-not-successful — surface it as a finding, never a
                # silent green.
                if live_states.get(terminal_leaf) != _LIVE_SUCCESS_STATE:
                    return _blocked(
                        "launch",
                        f"research {terminal_leaf!r} reached terminal state "
                        f"{live_states.get(terminal_leaf)!r} (not {_LIVE_SUCCESS_STATE!r}) "
                        f"— the launch completed unsuccessfully on prod "
                        f"(states={live_states}).",
                    )
            else:
                terminal_leaf = _await_terminal_leaf(
                    tmp_events, leaf_ids, deadline_s=_TERMINAL_DEADLINE_S
                )
                if terminal_leaf is None:
                    return _blocked(
                        "launch",
                        f"no leaf research reached the terminal "
                        f"{_TERMINAL_ACTION!r} event within {_TERMINAL_DEADLINE_S:.0f}s "
                        f"(leaves={leaf_ids}) — the research started but never "
                        f"completed (bounded-poll finding, not a silent pass).",
                        failure_mode="timeout",
                    )

            # ═══════════════════════ LEG 3: compound ══════════════════════
            # Assert PRIOR KNOWLEDGE was genuinely REUSED for THIS investigation —
            # the sum of len(reused_unit_ids) across its per-investigation
            # knowledge.reused events is ≥ 1. NOT the count of knowledge.reused
            # events: that event fires UNCONDITIONALLY once per start whenever a
            # retrieval substrate is wired (empty graph ⇒ reused_unit_ids: []), so
            # counting events green-passes a zero-reuse run ("the hook fired"). We
            # seeded a grounded covering unit on _KEYSTONE_TOPIC and launched on the
            # same topic, so a healthy flywheel injects it and reused_unit_ids is
            # non-empty. BOTH modes assert the SAME per-investigation OUTCOME:
            # in-process reads each event's reused_unit_ids off the temp event log;
            # live fetches GET /trajectory/{leaf} over HTTP and sums the same field.
            # A live dead flywheel (the cascade launch omitting retrieval_substrate,
            # OR firing the event with an empty reused_unit_ids) therefore REDS the
            # live keystone — the prod gate genuinely catches the dead-flywheel
            # incident.
            if live:
                reused = _live_reused_unit_count(client, terminal_leaf)
            else:
                reused = _reused_unit_count(tmp_events, terminal_leaf)
            if reused <= 0:
                return _blocked(
                    "compound",
                    f"0 prior units reused for investigation {terminal_leaf!r} — "
                    f"the research ran and the knowledge.reused hook fired, but its "
                    f"reused_unit_ids was EMPTY: ZERO prior knowledge was actually "
                    f"reused. Either the flywheel is dead at the prod entrypoint "
                    f"(cascade_routes.py launch omitted retrieval_substrate) or the "
                    f"seeded covering unit was not retrieved/injected. This is THE "
                    f"dead-flywheel defect — the journey did not compound.",
                )

            # ════════════════ LEG 4 + 5: read + attribution ════════════════
            # In-process: seed a servable artifact, then fetch it AUTHENTICATED
            # through the real GET /chunks/{id} route. Live: the operator supplies a
            # real prod chunk id via ANTIEK_PROBE_READ_CHUNK_ID (the probe never
            # writes the prod graph — §16 single-writer).
            if live:
                read_chunk_id = os.environ.get("ANTIEK_PROBE_READ_CHUNK_ID", "")
                if not read_chunk_id:
                    return _blocked(
                        "read",
                        "live mode requires ANTIEK_PROBE_READ_CHUNK_ID (a real prod "
                        "chunk id to fetch) — the probe does not write the prod graph "
                        "(§16). Supply it per the runbook.",
                        failure_mode="error",
                    )
            else:
                try:
                    read_chunk_id = _seed_read_artifact(tmp_db)
                except Exception as exc:  # noqa: BLE001
                    return _blocked(
                        "read",
                        f"could not seed the read artifact: {type(exc).__name__}: {exc}",
                        failure_mode="error",
                    )

            r = client.get(f"/chunks/{read_chunk_id}", headers=auth_headers)
            if r.status_code == 404:
                return _blocked(
                    "read",
                    f"GET /chunks/{read_chunk_id} 404'd — the read/chunk route "
                    f"moved/renamed, or the artifact is absent.",
                    failure_mode="route_404",
                )
            if r.status_code != 200:
                return _blocked(
                    "read",
                    f"GET /chunks/{read_chunk_id} -> {r.status_code}: {r.text[:160]}",
                )
            try:
                body = r.json()
            except Exception as exc:  # noqa: BLE001
                return _blocked(
                    "read",
                    f"GET /chunks/{read_chunk_id} returned non-JSON: "
                    f"{type(exc).__name__}: {exc}",
                )
            # READ leg: an actual artifact came back through the read surface.
            if not body.get("document_id"):
                return _blocked(
                    "read",
                    f"the read artifact has NO document_id — the chunk does not "
                    f"resolve to a source document: {str(body)[:200]}",
                )
            if not body.get("chunk_id"):
                return _blocked(
                    "read",
                    f"the read artifact has NO chunk_id — empty/malformed result: "
                    f"{str(body)[:200]}",
                )

            # ATTRIBUTION leg (distinct from read): §9 attribution PRESENCE +
            # well-formedness on the SAME artifact. servable/servability must be a
            # well-formed pair; for a SERVABLE source the owner attribution is
            # present (in-process seeds a servable public-domain doc with an IP
            # holder); a WITHHELD source correctly withholds owner + body, which is
            # itself well-formed §9 behaviour.
            servable = body.get("servable")
            servability = body.get("servability")
            if servable not in (True, False):
                return _blocked(
                    "attribution",
                    f"servable is not a well-formed boolean ({servable!r}) — the §9 "
                    f"gate verdict did not ride to the surface: {str(body)[:200]}",
                )
            if servable is True and servability is not None:
                return _blocked(
                    "attribution",
                    f"servable=True but servability={servability!r} (expected null) "
                    f"— the §9 verdict pair is malformed: {str(body)[:200]}",
                )
            if servable is False and servability not in (
                "restricted", "taken_down", "personal_readable",
            ):
                return _blocked(
                    "attribution",
                    f"servable=False but servability={servability!r} is not a known "
                    f"withhold label — the §9 verdict pair is malformed: "
                    f"{str(body)[:200]}",
                )
            if servable is True:
                # The artifact the journey reads is servable, so its owner
                # attribution must be PRESENT + well-formed (name + status).
                if not body.get("ip_holder_name"):
                    return _blocked(
                        "attribution",
                        f"servable artifact has NO ip_holder_name — '§9 whose work "
                        f"grounds this' attribution is missing: {str(body)[:200]}",
                    )
                if not body.get("ip_holder_status"):
                    return _blocked(
                        "attribution",
                        f"servable artifact has ip_holder_name but NO "
                        f"ip_holder_status — the §9.10 lifecycle word is missing "
                        f"(escrow framing would be ambiguous): {str(body)[:200]}",
                    )
            else:
                # A WITHHELD source MUST withhold owner attribution alongside the
                # body (app.py:2254 — protected attribution stays with the body).
                # This is well-formed §9 behaviour, not a failure — assert it holds.
                if body.get("ip_holder_name") is not None:
                    return _blocked(
                        "attribution",
                        f"a WITHHELD source leaked its ip_holder_name "
                        f"({body.get('ip_holder_name')!r}) — protected attribution "
                        f"must be withheld with the body (§9.0): {str(body)[:200]}",
                    )

            # All five legs held: login (401→200 bearer) → launch (terminal) →
            # compound (reuse>0) → read (real artifact) → attribution (§9 present +
            # well-formed). The product is USABLE end-to-end through the real
            # factory. REACHABLE.
            return ProbeResult(ok=True, failure_mode="reachable")
        finally:
            close_client()
    finally:
        # Restore env (the runner may run more probes after this one) + clean up.
        for key, val in saved.items():
            if val is None:
                os.environ.pop(key, None)
            else:
                os.environ[key] = val
        shutil.rmtree(tmp_root, ignore_errors=True)


PROBE = Probe(
    id="usability_keystone",
    feature=(
        "usability keystone (login → launch → compound → read → §9 attribution, "
        "as ONE journey through the real create_app() factory)"
    ),
    headline=True,
    run=_probe,
)
