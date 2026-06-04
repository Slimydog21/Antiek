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
    Probe,
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


def test_compound_leg_named_when_reuse_count_zero(monkeypatch):
    """Break the per-investigation reuse count to 0 → the probe names the
    'compound' leg with the dead-flywheel reason (THE defect this spec exists to
    catch). Launch genuinely passed (reached terminal); only compound fails."""
    monkeypatch.setattr(ks, "_reuse_count", lambda *a, **k: 0)
    result = _run_probe_named()
    assert result.ok is False
    assert result.reason.startswith("compound —"), result
    assert "knowledge_reuse_count == 0" in result.reason, result


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
