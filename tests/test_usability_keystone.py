"""ACV SPR-08 — the usability keystone probe NAMES the failing leg (M2 self-test).

The keystone probe is the CONJUNCTION of five legs (login → launch → compound →
read → attribution) driven as one journey through the real ``create_app()``
factory. The #1 cheat this whole spec exists to kill is a probe that goes green by
collapsing a broken leg into a bare "failed" — or worse, by stubbing a leg so the
conjunction always greens (the harness blind spot reborn). These tests prove the
probe does NEITHER:

  * STRUCTURAL: the probe is discovered, registered as the HEADLINE (top-line),
    and boots via the bare prod factory (no retrieval_substrate= injection,
    no stubbed providers in its source).
  * NAMED-FAILURE (the M2 core): for EACH of the five legs in turn, a deliberately
    broken stub is injected at the EXACT surface that leg observes (a real surface,
    not a faked outcome), and the probe is asserted to report THAT leg's name with a
    concrete reason — and the boot failure mode is distinguished from a feature-dead
    leg. Stages run in order and stop at the first failure, so breaking leg N leaves
    legs 1..N-1 genuinely passing (proving order + short-circuit).

Each broken-leg case breaks a DIFFERENT real surface, so the test would not pass if
the probe collapsed every failure to one generic stage — it must thread the actual
stage name through. The probe's GREEN path is exercised by the live reachability job
+ the gate run (it boots create_app() + runs a real launch); these tests assert the
cheaper structural + named-failure properties without re-running the multi-second
green journey for all five cases.
"""

from __future__ import annotations

import os
import sys

_REPO = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
if _REPO not in sys.path:
    sys.path.insert(0, _REPO)

from tools.reachability.probe_runner import (  # noqa: E402
    ProbeResult,
    discover_probes,
)
from tools.reachability.probes import usability_keystone as ks  # noqa: E402

# ---------------------------------------------------------------------------
# STRUCTURAL — discovered, headline, honest boot
# ---------------------------------------------------------------------------


def test_keystone_probe_is_discovered():
    ids = {p.id for p in discover_probes()}
    assert "usability_keystone" in ids, (
        f"usability_keystone probe must be discovered, got {sorted(ids)}"
    )


def test_keystone_probe_is_the_headline_and_sorts_first():
    """The keystone is the top-line probe: it sorts FIRST (ahead of every
    non-headline probe) so a maintainer reading the gate sees the end-to-end
    'is the product usable' verdict before the per-brick probes."""
    probes = discover_probes()
    assert probes, "no probes discovered"
    assert probes[0].id == "usability_keystone", (
        f"usability_keystone must sort FIRST (headline), got order "
        f"{[p.id for p in probes]}"
    )
    ks_probe = next(p for p in probes if p.id == "usability_keystone")
    assert ks_probe.headline is True, "the keystone probe must be flagged headline=True"
    # The other probes must NOT be headline (exactly one top-line verdict).
    assert all(not p.headline for p in probes if p.id != "usability_keystone"), (
        "only the keystone may be the headline probe"
    )


def test_keystone_probe_boots_via_bare_factory_no_injection():
    """Honesty guard (rigor #1): the probe source boots via create_app() with NO
    retrieval_substrate= injection and NO register_providers=False — recreating
    that injection is the exact blind spot this gate exists to kill."""
    src = ks.__file__
    with open(src, encoding="utf-8") as fh:
        text = fh.read()
    assert "create_app()" in text, "the probe must boot via the bare create_app() factory"
    # No ACTIVE injection: the probe must never PASS retrieval_substrate= or
    # register_providers=False as a CALL kwarg. Parse the AST (immune to docstring
    # prose / comments that legitimately MENTION the forbidden kwargs in the
    # negative — "NO register_providers=False") and assert no Call node passes them.
    import ast

    tree = ast.parse(text)
    create_app_calls: list[ast.Call] = []
    for node in ast.walk(tree):
        if not isinstance(node, ast.Call):
            continue
        kwnames = {kw.arg for kw in node.keywords if kw.arg}
        # The forbidden injections: a §16/blind-spot kwarg passed to ANY call.
        assert "retrieval_substrate" not in kwnames, (
            "the probe injects retrieval_substrate= into a call — the exact "
            "blind spot this gate exists to kill"
        )
        assert "register_providers" not in kwnames, (
            "the probe passes register_providers= into a call — the boot must be "
            "the bare prod factory"
        )
        func = node.func
        if isinstance(func, ast.Name) and func.id == "create_app":
            create_app_calls.append(node)
    # And at least one create_app() call must pass NO arguments (the bare boot).
    assert any(
        not c.args and not c.keywords for c in create_app_calls
    ), "the probe must call create_app() with no arguments (the bare prod factory)"


def test_keystone_feature_names_the_five_legs():
    """The feature string + docstring must name the journey so a maintainer
    cannot mistake the keystone for a single-brick probe."""
    feature = next(p.feature for p in discover_probes() if p.id == "usability_keystone")
    low = feature.lower()
    for leg in ("login", "launch", "compound", "read", "attribution"):
        assert leg in low, f"the keystone feature must name the {leg!r} leg: {feature!r}"


# ---------------------------------------------------------------------------
# NAMED-FAILURE — break each leg at its real surface; assert the named stage.
# ---------------------------------------------------------------------------
#
# We run the WHOLE probe (boot create_app() + drive the real journey) with ONE
# real surface broken per case, and assert the probe stops at that leg and names
# it. Breaking a surface (not faking an outcome) keeps the legs before it genuinely
# passing, proving the in-order short-circuit.


def _run_probe_named() -> ProbeResult:
    """Run the keystone probe in-process and return its ProbeResult (named-leg
    reason). We call _probe() directly (not through the runner) so the reason is
    inspectable; the runner's exit semantics are covered by
    test_reachability_runner.py."""
    return ks._probe()


def test_boot_failure_is_named_boot_and_distinct_from_feature_dead(monkeypatch):
    """A create_app() that raises is a BOOT failure (failure_mode boot_fail),
    NOT a feature-dead leg — the two need different fixes and must not be
    conflated."""
    import interfaces.research.api.app as app_mod

    def _boom(*a, **k):
        raise RuntimeError("simulated boot crash")

    monkeypatch.setattr(app_mod, "create_app", _boom)
    result = _run_probe_named()
    assert result.ok is False
    assert result.failure_mode == "boot_fail", result
    assert result.reason.startswith("boot —"), result


def test_login_leg_named_when_bearer_rejected(monkeypatch):
    """Break the auth compare so a VALID bearer token is rejected → the login leg
    stays 401 WITH the header → the probe names the 'login' leg."""
    import secrets as _secrets

    # compare_digest is imported inside the middleware as `secrets.compare_digest`;
    # patch the module function so the bearer never matches.
    monkeypatch.setattr(_secrets, "compare_digest", lambda a, b: False)
    result = _run_probe_named()
    assert result.ok is False
    assert result.reason.startswith("login —"), result
    assert "401" in result.reason or "REJECTED" in result.reason, result


def test_launch_leg_named_when_research_never_reaches_terminal(monkeypatch):
    """Break the terminal poll so no leaf reaches investigation.completed → the
    probe names the 'launch' leg as a bounded-poll finding (not a silent pass)."""
    monkeypatch.setattr(ks, "_await_terminal_leaf", lambda *a, **k: None)
    result = _run_probe_named()
    assert result.ok is False
    assert result.reason.startswith("launch —"), result
    assert "terminal" in result.reason.lower(), result
    # A research that never completes is a timeout-class finding, not feature_dead.
    assert result.failure_mode == "timeout", result


def test_compound_leg_named_when_reused_unit_count_zero(monkeypatch):
    """Break the per-investigation REUSED-UNIT count to 0 → the probe names the
    'compound' leg with the dead-flywheel reason (THE defect this spec exists to
    catch). Launch genuinely passed (reached terminal); only compound fails."""
    monkeypatch.setattr(ks, "_reused_unit_count", lambda *a, **k: 0)
    result = _run_probe_named()
    assert result.ok is False
    assert result.reason.startswith("compound —"), result
    assert "0 prior units reused" in result.reason, result


def test_compound_leg_REDS_when_event_fired_but_zero_units_reused(monkeypatch):
    """TEETH (the MAJOR fix): the compound leg must RED when a knowledge.reused
    event DID fire but its reused_unit_ids is EMPTY — i.e. the exact case that was
    OLD-GREEN (the leg counted events) and is NOW-RED (the leg counts units reused).

    We reproduce it WITHOUT stubbing the count helper: skip the prior-knowledge
    seed so the launch runs against an EMPTY graph. On an empty graph the real
    knowledge.reused hook STILL fires (unconditional once a retrieval substrate is
    wired) with reused_unit_ids: [] — so the OLD event-counting leg would have
    green-passed here. The NEW units-reused leg reds. This proves the new assertion
    has teeth the old one lacked (the honesty guard: a real outcome, on the real
    factory — only the seed is removed)."""
    # No-op the prior-knowledge seed → the launch covers nothing → real reuse hook
    # fires with an EMPTY reused_unit_ids (verified: the empty-graph case).
    monkeypatch.setattr(ks, "_seed_prior_knowledge_unit", lambda db_path: "")
    result = _run_probe_named()
    assert result.ok is False, (
        "compound MUST red when knowledge.reused fired but reused_unit_ids is empty "
        "(the old event-counting leg green-passed this exact case)"
    )
    assert result.reason.startswith("compound —"), result
    assert "0 prior units reused" in result.reason, result


def test_compound_leg_GREEN_when_a_unit_is_genuinely_reused():
    """Companion to the teeth test: with the prior-knowledge unit seeded (the
    DEFAULT probe behaviour), real reuse happens — the launched research retrieves +
    injects the seeded covering unit, so reused_unit_ids is NON-EMPTY and the whole
    journey is REACHABLE. This is the positive control proving the keystone is green
    because a unit was actually reused, NOT merely because the hook fired."""
    result = _run_probe_named()
    assert result.ok is True, (
        f"the in-process keystone must be REACHABLE — a grounded covering unit is "
        f"seeded on the launch topic, so real reuse happens. Got: {result}"
    )
    assert result.failure_mode == "reachable", result


def test_read_leg_named_when_artifact_absent(monkeypatch):
    """Seed a chunk id that does not exist → GET /chunks/{id} 404s → the probe
    names the 'read' leg. Login/launch/compound genuinely passed first."""
    monkeypatch.setattr(
        ks, "_seed_read_artifact", lambda db_path: "no-such-chunk-id-keystone-test"
    )
    result = _run_probe_named()
    assert result.ok is False
    assert result.reason.startswith("read —"), result
    assert result.failure_mode == "route_404", result


def test_attribution_leg_named_when_owner_missing(monkeypatch):
    """Seed a SERVABLE artifact WITHOUT an IP holder → the read leg passes (a real
    body returns) but the attribution leg fails (servable source with no
    ip_holder_name) → the probe names the 'attribution' leg, DISTINCT from read."""
    from runtime.db_lock import connect_write
    from substrate.graph.ops import insert_chunk, insert_document
    from substrate.graph.schema import init_database_at_path

    def _seed_no_owner(db_path: str) -> str:
        # A servable public_domain doc with NO ip_holder_id → GET /chunks returns
        # a body (read leg passes) but ip_holder_name is null (attribution fails).
        init_database_at_path(db_path)
        with connect_write(db_path, purpose="keystone-attr-test") as con:
            insert_document(
                con,
                document_id="keystone-attr-noowner-doc",
                source_tier=1,
                document_type="paper",
                title="No-owner servable artifact",
                content_class="public_domain",  # servable → owner SHOULD be present
                on_conflict="ignore",
            )
            return insert_chunk(
                con,
                document_id="keystone-attr-noowner-doc",
                chunk_index=0,
                text="Servable chunk with no IP holder — attribution must red.",
                section_path="p.1",
            )

    monkeypatch.setattr(ks, "_seed_read_artifact", _seed_no_owner)
    result = _run_probe_named()
    assert result.ok is False
    assert result.reason.startswith("attribution —"), result
    assert "ip_holder_name" in result.reason, result


# ---------------------------------------------------------------------------
# LIVE-MODE HELPERS — the live launch-poll + live compound assert the SAME legs
# as in-process, over a mocked HTTP surface (no network). These prove the live
# path that the operator runs is REAL (not a skipped/accept-on-launch shortcut)
# without hitting api.antiek.ai.
# ---------------------------------------------------------------------------


class _FakeResponse:
    def __init__(self, status_code: int, payload: dict):
        self.status_code = status_code
        self._payload = payload

    def json(self) -> dict:
        return self._payload


class _FakeSessionClient:
    """A fake httpx client for GET /research/sessions/{id}: returns ``running``
    until ``flip_after`` calls, then the supplied terminal ``states``."""

    def __init__(self, terminal_states: dict, *, flip_after: int = 1):
        self._terminal = terminal_states
        self._flip_after = flip_after
        self.calls = 0

    def get(self, path: str) -> _FakeResponse:
        self.calls += 1
        if self.calls <= self._flip_after:
            running = {iid: "running" for iid in self._terminal}
            researches = [{"investigation_id": i, "state": s} for i, s in running.items()]
        else:
            researches = [{"investigation_id": i, "state": s}
                          for i, s in self._terminal.items()]
        return _FakeResponse(200, {"researches": researches})


def test_live_await_terminal_session_polls_to_terminal_done():
    """The live launch-poll returns the first terminal leaf + every state once ALL
    researches are terminal — a REAL bounded poll, not accept-on-launch."""
    client = _FakeSessionClient({"leaf-0": "done"}, flip_after=1)
    leaf, states = ks._live_await_terminal_session(client, "session-x", deadline_s=2.0)
    assert leaf == "leaf-0", (leaf, states)
    assert states == {"leaf-0": "done"}
    assert client.calls >= 2, "must have polled at least once past the running state"


def test_live_await_terminal_session_times_out_to_none():
    """A research that never reaches terminal returns (None, last_states) so the
    caller reds the launch leg — the bounded-poll finding, not a silent pass."""
    client = _FakeSessionClient({"leaf-0": "done"}, flip_after=10_000)  # never flips
    leaf, states = ks._live_await_terminal_session(client, "session-x", deadline_s=0.25)
    assert leaf is None, (leaf, states)
    assert states == {"leaf-0": "running"}


def test_live_await_terminal_session_waits_for_ALL_leaves():
    """A partially-terminal fan-out (one done, one still running) is NOT terminal —
    the journey is the whole fan-out."""
    class _Partial:
        def get(self, path):
            return _FakeResponse(200, {"researches": [
                {"investigation_id": "leaf-0", "state": "done"},
                {"investigation_id": "leaf-1", "state": "running"},
            ]})
    leaf, states = ks._live_await_terminal_session(_Partial(), "s", deadline_s=0.25)
    assert leaf is None, (leaf, states)
    assert states == {"leaf-0": "done", "leaf-1": "running"}


def test_live_reused_unit_count_sums_this_leafs_reused_unit_ids():
    """The live compound signal SUMS len(reused_unit_ids) across THIS leaf's
    knowledge.reused events from GET /trajectory/{leaf} — the SAME per-investigation
    OUTCOME (prior UNITS reused) as in-process, over HTTP (NOT the frozen /health
    global snapshot, NOT a bare event count)."""
    class _Traj:
        def get(self, path):
            assert path == "/trajectory/leaf-0", path
            return _FakeResponse(200, {"events": [
                {"action_type": "investigation.start_requested"},
                {"action_type": "knowledge.reused",
                 "payload": {"reused_unit_ids": ["insight-a", "insight-b"]}},
                {"action_type": "knowledge.reused",
                 "payload": {"reused_unit_ids": ["insight-c"]}},
                {"action_type": "investigation.completed"},
            ]})
    # 2 + 1 = 3 prior units reused across this leaf's two events.
    assert ks._live_reused_unit_count(_Traj(), "leaf-0") == 3


def test_live_reused_unit_count_zero_when_event_fired_but_no_units():
    """TEETH (live analogue): a live research whose knowledge.reused event FIRED but
    carries an EMPTY reused_unit_ids yields 0 — the dead-flywheel signal that REDS
    the live compound leg. The OLD event-counting live signal would have returned
    1 (the event count) and green-passed; the NEW units-reused signal reds."""
    class _EventNoUnits:
        def get(self, path):
            return _FakeResponse(200, {"events": [
                {"action_type": "investigation.start_requested"},
                {"action_type": "knowledge.reused", "payload": {"reused_unit_ids": []}},
                {"action_type": "investigation.completed"},
            ]})
    assert ks._live_reused_unit_count(_EventNoUnits(), "leaf-0") == 0


def test_live_reused_unit_count_zero_on_dead_flywheel():
    """A live research whose trajectory carries NO knowledge.reused event yields 0
    — the dead-flywheel signal that REDS the live compound leg (the whole point:
    a dead flywheel on prod cannot green-pass the live keystone)."""
    class _NoReuse:
        def get(self, path):
            return _FakeResponse(200, {"events": [
                {"action_type": "investigation.start_requested"},
                {"action_type": "investigation.completed"},
            ]})
    assert ks._live_reused_unit_count(_NoReuse(), "leaf-0") == 0


def test_live_reused_unit_count_zero_on_non_200():
    """A non-200 trajectory fetch yields 0 (reds compound) rather than raising."""
    class _Err:
        def get(self, path):
            return _FakeResponse(404, {})
    assert ks._live_reused_unit_count(_Err(), "leaf-0") == 0


def test_live_mode_compound_reds_on_dead_flywheel(monkeypatch):
    """END-TO-END live path (mocked HTTP, no network): drive _probe(base_url=...)
    with a fake httpx client whose trajectory FIRED a knowledge.reused event but with
    an EMPTY reused_unit_ids → the live keystone names the 'compound' leg. This is
    the live analogue of the MAJOR fix's teeth: the OLD event-counting live signal
    would have GREEN-PASSED (one event present), the NEW units-reused signal REDS.
    Proves the runbook's live 'compound — 0 prior units reused' RED example is
    genuinely reproducible (it was a dead `pass` before this sprint)."""

    class _LiveClient:
        """Minimal live API double: login 401→200, plan/approve/launch ok, the
        session poll reaches 'done', the trajectory FIRES knowledge.reused but with
        an EMPTY reused_unit_ids (the dead-flywheel-as-zero-reuse case), and /chunks
        would return a body — but compound reds first."""
        def __init__(self):
            self.closed = False

        def post(self, path, json=None, headers=None):
            if path == "/research/plans":
                if not headers or "Bearer livetoken" not in headers.get("Authorization", ""):
                    return _FakeResponse(401, {"error": {"code": "operator_auth_required"}})
                return _FakeResponse(200, {"root_node_id": "root-1"})
            if path.endswith("/approve") or path.endswith("/launch"):
                return _FakeResponse(200, {"researches": [
                    {"investigation_id": "session-root-1-leaf-0",
                     "sub_question": "q", "question_node_id": "n"}]}
                    if path.endswith("/launch") else {})
            return _FakeResponse(200, {})

        def get(self, path, headers=None):
            if path.startswith("/research/sessions/"):
                return _FakeResponse(200, {"researches": [
                    {"investigation_id": "session-root-1-leaf-0", "state": "done"}]})
            if path.startswith("/trajectory/"):
                # dead flywheel: knowledge.reused FIRED but reused_unit_ids is EMPTY
                # — the hook fired, zero prior units were reused.
                return _FakeResponse(200, {"events": [
                    {"action_type": "knowledge.reused", "payload": {"reused_unit_ids": []}},
                    {"action_type": "investigation.completed"}]})
            return _FakeResponse(200, {})

        def close(self):
            self.closed = True

    fake = _LiveClient()
    import httpx
    monkeypatch.setattr(httpx, "Client", lambda *a, **k: fake)
    monkeypatch.setenv("ANTIEK_PROBE_OPERATOR_TOKEN", "livetoken")
    result = ks._probe(base_url="https://example.invalid")
    assert result.ok is False, result
    assert result.reason.startswith("compound —"), result
    assert "0 prior units reused" in result.reason, result
    assert fake.closed is True, "the live client must be closed in finally"


def test_live_mode_launch_reds_when_never_terminal(monkeypatch):
    """Live path: a session whose researches never leave 'running' reds the launch
    leg via the live status poll (the runbook's live 'launch — never terminal'
    example) — proving live launch is a REAL poll, not accept-on-launch."""

    class _LiveClient:
        def post(self, path, json=None, headers=None):
            if path == "/research/plans":
                if not headers or "Bearer livetoken" not in headers.get("Authorization", ""):
                    return _FakeResponse(401, {"error": {"code": "operator_auth_required"}})
                return _FakeResponse(200, {"root_node_id": "root-1"})
            if path.endswith("/launch"):
                return _FakeResponse(200, {"researches": [
                    {"investigation_id": "session-root-1-leaf-0",
                     "sub_question": "q", "question_node_id": "n"}]})
            return _FakeResponse(200, {})

        def get(self, path, headers=None):
            if path.startswith("/research/sessions/"):
                return _FakeResponse(200, {"researches": [
                    {"investigation_id": "session-root-1-leaf-0", "state": "running"}]})
            return _FakeResponse(200, {})

        def close(self):
            pass

    import httpx
    monkeypatch.setattr(httpx, "Client", lambda *a, **k: _LiveClient())
    monkeypatch.setenv("ANTIEK_PROBE_OPERATOR_TOKEN", "livetoken")
    # Shrink the deadline so the test does not wait 8s.
    monkeypatch.setattr(ks, "_TERMINAL_DEADLINE_S", 0.3)
    result = ks._probe(base_url="https://example.invalid")
    assert result.ok is False, result
    assert result.reason.startswith("launch —"), result
    assert result.failure_mode == "timeout", result


def test_each_broken_leg_reports_a_distinct_stage(monkeypatch):
    """Cross-check: the five named stages are genuinely distinct strings — the
    probe threads the actual stage, it does not collapse to one generic label."""
    stages = {"boot", "login", "launch", "compound", "read", "attribution"}
    # The probe's _blocked() prefixes the reason with "<leg> —"; assert the helper
    # itself preserves the leg name (a fast unit check on the naming contract).
    for leg in stages:
        r = ks._blocked(leg, "reason-text")
        assert r.reason.startswith(f"{leg} —"), r
        assert r.ok is False
