"""Tests for tools/fake_gate_detector.py — the bounded mutation-lite detector.

These tests assert the detector's OUTPUT on a controlled fixture mini-repo
(tools/tests/fixtures/fake_gate/). They NEVER mock the detector and never mock
the detector's internals to fake a result — they run the real engine and check
what it reports. The fixture proves BOTH halves the detector exists for:

  * a mutation a REAL behavior test KILLS    (positive control → ``killed``);
  * a mutation a FAKE mock-only test SURVIVES (negative control → ``survived``).

Plus the load-bearing SAFETY proofs (rigor #3):

  * the byte-for-byte restore holds on the normal path (sha256 before == after);
  * the restore SURVIVES A CRASH mid-run (a raising fake pytest runner) — the
    target's sha256 is unchanged afterward;
  * a corrupted restore raises ``RestoreIntegrityError`` LOUDLY (it never
    silently proceeds over a half-restored product source file);
  * the pre-flight clean-tree guard refuses to run over uncommitted edits;
  * a drifted anchor is surfaced as ``anchor-stale`` (never a false pass).

It also asserts determinism (two runs on the fixture produce an identical
machine payload) and the baseline capture/enforce/stale contract (mirroring
tools/lints/cli_with_baseline.py).
"""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from tools import fake_gate_detector as fgd

FIXTURE_DIR = Path(__file__).resolve().parent / "fixtures" / "fake_gate"
PRODUCT = FIXTURE_DIR / "product.py"


def _fixture_mutants() -> list[fgd.Mutant]:
    return fgd.load_mutants(FIXTURE_DIR)


def _by_id(mutants: list[fgd.Mutant], mid: str) -> fgd.Mutant:
    return next(m for m in mutants if m.id == mid)


# ---------------------------------------------------------------------------
# M1 — mutant format loads + validates
# ---------------------------------------------------------------------------


def test_fixture_mutants_load_in_sorted_order():
    ms = _fixture_mutants()
    assert [m.id for m in ms] == sorted(m.id for m in ms)
    assert {m.id for m in ms} == {"fixture-fake", "fixture-real", "fixture-stale"}


def test_invalid_op_is_rejected():
    with pytest.raises(ValueError, match="op"):
        fgd.Mutant(
            id="x", target="product.py", qualname="f", match="m",
            op="frobnicate", test_selector=("test_real.py",),
            rationale="r", added="2026-06-04", added_by="t",
        )


def test_empty_selector_is_rejected():
    with pytest.raises(ValueError, match="test_selector"):
        fgd.Mutant(
            id="x", target="product.py", qualname="f", match="m",
            op="noop", test_selector=(), rationale="r",
            added="2026-06-04", added_by="t",
        )


# ---------------------------------------------------------------------------
# M5 — both halves of the detector (positive + negative control) on the fixture
# ---------------------------------------------------------------------------


def test_positive_control_real_test_kills_the_mutant():
    """A mutation a REAL behavior test catches must be reported ``killed``."""
    m = _by_id(_fixture_mutants(), "fixture-real")
    r = fgd.run_mutant(m, repo=FIXTURE_DIR, timeout_s=60)
    assert r.outcome == "killed", r.detail
    assert r.n_tests == 2
    assert r.failed_tests, "killed mutant must name ≥1 failing test"


def test_negative_control_fake_test_lets_the_mutant_survive():
    """A mutation a FAKE mock-only test does NOT catch must be ``survived`` — the
    finding the whole sprint exists to surface."""
    m = _by_id(_fixture_mutants(), "fixture-fake")
    r = fgd.run_mutant(m, repo=FIXTURE_DIR, timeout_s=60)
    assert r.outcome == "survived", r.detail
    assert r.is_finding()
    assert r.n_tests == 1


def test_drifted_anchor_is_anchor_stale_not_a_false_pass():
    m = _by_id(_fixture_mutants(), "fixture-stale")
    r = fgd.run_mutant(m, repo=FIXTURE_DIR, timeout_s=60)
    assert r.outcome == "anchor-stale", r.detail
    assert not r.is_finding()  # stale is NOT a finding, but is NOT a pass either


def test_no_tests_outcome_when_selector_matches_zero_tests():
    """A selector matching zero tests is the ``no-tests`` finding (an unguarded
    load-bearing line), not a survivor."""
    m = fgd.Mutant(
        id="no-tests-probe", target="product.py", qualname="discount_price",
        match="if is_member:", op="invert_guard",
        test_selector=("-k", "this_matches_no_test_at_all_xyzzy"),
        rationale="probe", added="2026-06-04", added_by="t",
    )
    r = fgd.run_mutant(m, repo=FIXTURE_DIR, timeout_s=60)
    assert r.outcome == "no-tests", r.detail
    assert r.is_finding()


# ---------------------------------------------------------------------------
# SAFETY (rigor #3) — byte-for-byte restore, proven by sha256, even on crash
# ---------------------------------------------------------------------------


def test_restore_is_byte_for_byte_on_the_normal_path():
    before = fgd._sha256_file(PRODUCT)
    for m in _fixture_mutants():
        fgd.run_mutant(m, repo=FIXTURE_DIR, timeout_s=60)
        assert fgd._sha256_file(PRODUCT) == before, (
            f"target not restored after {m.id}"
        )
    assert fgd._sha256_file(PRODUCT) == before


def test_restore_survives_a_crash_mid_run(monkeypatch):
    """Simulate a crash mid-run (a raising pytest runner) and assert the target's
    sha256 is UNCHANGED afterward — the finally-restore held through the
    exception. This is the catastrophe the SAFETY constraint exists to prevent:
    a stranded mutated product source file."""
    before_bytes = PRODUCT.read_bytes()
    before = fgd._sha256_bytes(before_bytes)

    def _boom(*_a, **_k):
        raise RuntimeError("simulated crash inside the test runner")

    monkeypatch.setattr(fgd, "_run_pytest", _boom)
    m = _by_id(_fixture_mutants(), "fixture-real")
    with pytest.raises(RuntimeError, match="simulated crash"):
        fgd.run_mutant(m, repo=FIXTURE_DIR, timeout_s=60)
    after = fgd._sha256_file(PRODUCT)
    assert after == before, "target was NOT restored after a mid-run crash"
    assert PRODUCT.read_bytes() == before_bytes


def test_restore_survives_keyboard_interrupt(monkeypatch):
    """The finally catches BaseException, so a Ctrl-C mid-run also restores."""
    before = fgd._sha256_file(PRODUCT)

    def _interrupt(*_a, **_k):
        raise KeyboardInterrupt

    monkeypatch.setattr(fgd, "_run_pytest", _interrupt)
    m = _by_id(_fixture_mutants(), "fixture-real")
    with pytest.raises(KeyboardInterrupt):
        fgd.run_mutant(m, repo=FIXTURE_DIR, timeout_s=60)
    assert fgd._sha256_file(PRODUCT) == before


def test_corrupted_restore_raises_loudly(monkeypatch, tmp_path):
    """If the restore itself were corrupted, the post-restore sha256 check must
    RAISE RestoreIntegrityError rather than silently proceed. We simulate by
    making the runner overwrite the file with garbage AND breaking write_bytes so
    the restore writes the wrong content; the sha256 assertion catches it."""
    # Copy the fixture into a scratch repo so we never risk the real fixture.
    scratch = tmp_path / "repo"
    scratch.mkdir()
    (scratch / "product.py").write_text(PRODUCT.read_text(), encoding="utf-8")
    (scratch / "test_real.py").write_text(
        (FIXTURE_DIR / "test_real.py").read_text(), encoding="utf-8"
    )
    target = scratch / "product.py"
    original = target.read_bytes()

    real_write = Path.write_bytes

    def _corrupting_write(self, data):
        # When asked to restore the original bytes, write garbage instead — the
        # post-restore sha256 check must then fire.
        if self == target and data == original:
            return real_write(self, b"CORRUPTED-NOT-THE-ORIGINAL\n")
        return real_write(self, data)

    monkeypatch.setattr(Path, "write_bytes", _corrupting_write)
    m = fgd.Mutant(
        id="corrupt-probe", target="product.py", qualname="discount_price",
        match="if is_member:", op="invert_guard",
        test_selector=("test_real.py",), rationale="r",
        added="2026-06-04", added_by="t",
    )
    with pytest.raises(fgd.RestoreIntegrityError, match="RESTORE FAILED"):
        fgd.run_mutant(m, repo=scratch, timeout_s=60)


# ---------------------------------------------------------------------------
# Pre-flight clean-tree guard
# ---------------------------------------------------------------------------


def test_clean_tree_guard_refuses_on_uncommitted_target(tmp_path):
    """A git repo with an uncommitted change to a target makes the pre-flight
    refuse (DirtyTreeError) so a crash can't strand a half-mutated file."""
    import subprocess

    repo = tmp_path / "repo"
    repo.mkdir()
    subprocess.run(["git", "init", "-q"], cwd=repo, check=True)
    subprocess.run(["git", "config", "user.email", "t@t"], cwd=repo, check=True)
    subprocess.run(["git", "config", "user.name", "t"], cwd=repo, check=True)
    f = repo / "product.py"
    f.write_text("x = 1\n", encoding="utf-8")
    subprocess.run(["git", "add", "."], cwd=repo, check=True)
    subprocess.run(["git", "commit", "-qm", "init"], cwd=repo, check=True)
    # Dirty it.
    f.write_text("x = 2\n", encoding="utf-8")
    with pytest.raises(fgd.DirtyTreeError, match="uncommitted"):
        fgd.assert_clean_tree(["product.py"], repo=repo)


def test_clean_tree_guard_passes_on_committed_target(tmp_path):
    import subprocess

    repo = tmp_path / "repo"
    repo.mkdir()
    subprocess.run(["git", "init", "-q"], cwd=repo, check=True)
    subprocess.run(["git", "config", "user.email", "t@t"], cwd=repo, check=True)
    subprocess.run(["git", "config", "user.name", "t"], cwd=repo, check=True)
    f = repo / "product.py"
    f.write_text("x = 1\n", encoding="utf-8")
    subprocess.run(["git", "add", "."], cwd=repo, check=True)
    subprocess.run(["git", "commit", "-qm", "init"], cwd=repo, check=True)
    # No exception.
    fgd.assert_clean_tree(["product.py"], repo=repo)


# ---------------------------------------------------------------------------
# Determinism
# ---------------------------------------------------------------------------


def test_two_runs_produce_identical_machine_payload():
    ms = _fixture_mutants()
    r1 = fgd.run_all(ms, repo=FIXTURE_DIR, timeout_s=60)
    r2 = fgd.run_all(ms, repo=FIXTURE_DIR, timeout_s=60)
    p1 = fgd.dumps_payload(fgd.results_to_payload(r1))
    p2 = fgd.dumps_payload(fgd.results_to_payload(r2))
    assert p1 == p2


def test_payload_has_no_wallclock_field():
    """The machine payload must omit any wall-clock field so a two-run diff is
    empty (determinism)."""
    ms = _fixture_mutants()
    payload = fgd.results_to_payload(fgd.run_all(ms, repo=FIXTURE_DIR, timeout_s=60))
    text = json.dumps(payload)
    assert "generated_at" not in text and "captured_at" not in text


# ---------------------------------------------------------------------------
# Baseline capture / enforce / stale (mirrors tools/lints/cli_with_baseline.py)
# ---------------------------------------------------------------------------


def test_capture_then_enforce_exits_clean(tmp_path):
    """--capture writes the survivors; --enforce against that baseline finds NO
    new survivor → exit 0 (the grandfather pattern)."""
    ms = _fixture_mutants()
    results = fgd.run_all(ms, repo=FIXTURE_DIR, timeout_s=60)
    baseline = tmp_path / "survivors_baseline.json"
    n = fgd.write_baseline(baseline, results, capture_date="2026-06-04")
    assert n >= 1, "fixture must produce ≥1 survivor to grandfather"
    loaded = fgd.load_baseline(baseline)
    new_only = fgd.filter_to_new_only(results, loaded)
    assert new_only == [], "no NEW survivor after grandfathering the same set"


def test_enforce_reds_on_a_new_survivor(tmp_path):
    """A survivor NOT in the baseline is a NEW fake gate → it appears in
    filter_to_new_only (the thing --enforce exits 1 on)."""
    ms = _fixture_mutants()
    results = fgd.run_all(ms, repo=FIXTURE_DIR, timeout_s=60)
    baseline = tmp_path / "survivors_baseline.json"
    fgd.write_baseline(baseline, results, capture_date="2026-06-04")
    loaded = fgd.load_baseline(baseline)
    # Drop the grandfathered survivor → it now looks NEW.
    shrunk = {k for k in loaded if k.id != "fixture-fake"}
    new_only = fgd.filter_to_new_only(results, shrunk)
    assert any(k.id == "fixture-fake" for k in new_only)


def test_stale_reports_a_grandfathered_finding_now_gone(tmp_path):
    """A baseline entry whose finding is gone (e.g. only the real-test mutant is
    run, so the fake-test survivor never appears) is reported stale so the
    baseline can shrink."""
    ms = _fixture_mutants()
    results = fgd.run_all(ms, repo=FIXTURE_DIR, timeout_s=60)
    baseline = tmp_path / "survivors_baseline.json"
    fgd.write_baseline(baseline, results, capture_date="2026-06-04")
    loaded = fgd.load_baseline(baseline)
    # Re-run ONLY the real-test mutant → the fake survivor is absent now.
    only_real = fgd.run_all(ms, repo=FIXTURE_DIR, timeout_s=60, only="fixture-real")
    stale = fgd.find_stale_baseline_entries(only_real, loaded)
    assert any(k.id == "fixture-fake" for k in stale)


def test_baseline_records_path_line_rationale_and_date(tmp_path):
    ms = _fixture_mutants()
    results = fgd.run_all(ms, repo=FIXTURE_DIR, timeout_s=60)
    baseline = tmp_path / "survivors_baseline.json"
    fgd.write_baseline(baseline, results, capture_date="2026-06-04")
    data = json.loads(baseline.read_text())
    assert data["schema_version"] == fgd.BASELINE_SCHEMA_VERSION
    surv = data["survivors"]
    assert surv, "expected ≥1 grandfathered survivor"
    for entry in surv:
        assert entry["path_line"]
        assert entry["rationale"]
        assert entry["captured_at"] == "2026-06-04"


# ---------------------------------------------------------------------------
# Report contract — findings first, path:line, exit-code semantics
# ---------------------------------------------------------------------------


def test_report_surfaces_findings_first_with_path_line():
    ms = _fixture_mutants()
    report = fgd.render_report(fgd.run_all(ms, repo=FIXTURE_DIR, timeout_s=60))
    assert "FINDINGS" in report
    assert "FAKE GATE" in report
    assert "product.py:" in report  # path:line contract


def test_apply_op_invert_guard_changes_behavior():
    """White-box: invert_guard on the fixture guard produces parseable source
    whose guard is logically flipped."""
    m = _by_id(_fixture_mutants(), "fixture-fake")
    src = PRODUCT.read_text()
    anchor = fgd.resolve_anchor(src, m)
    mutated = fgd.apply_op(src, m, anchor)
    assert "if not (is_member):" in mutated


def test_collection_error_is_not_counted_as_a_kill():
    """A pre-existing COLLECTION error (a bad selector / a missing optional dep)
    reds whether or not the code is mutated, so it must NEVER be a kill — counting
    it as one would mask a fake gate (rigor #1). We feed _parse_pytest_output a
    realistic 'errors during collection' transcript and assert it reports zero
    runnable tests + zero runtime failures (so run_mutant maps it to no-tests)."""
    transcript = (
        "ERROR tests/test_merge_staging.py\n"
        "ERROR tests/test_open_access_ingest.py\n"
        "!!!!!!!! Interrupted: 2 errors during collection !!!!!!!!\n"
        "2 errors in 0.30s\n"
    )
    run = fgd._parse_pytest_output(transcript)
    assert run.n_ran == 0
    assert run.n_failed_runtime == 0
    assert run.collection_errors == 2


def test_runtime_failure_is_a_kill_signal():
    """A test that RAN and FAILED is the kill signal — n_failed_runtime > 0."""
    transcript = (
        "FAILED tests/test_x.py::test_a - AssertionError\n"
        "1 failed, 3 passed in 0.10s\n"
    )
    run = fgd._parse_pytest_output(transcript)
    assert run.n_ran == 4
    assert run.n_failed_runtime == 1
    assert run.collection_errors == 0
    assert "tests/test_x.py::test_a" in run.failed_nodes


def test_parse_layer_is_neutral_about_node_errors():
    """The PARSE layer is deliberately NEUTRAL about node-level setup ERRORs: it
    harvests them into ``node_error_nodes`` for the kill decision + reporting, but
    does NOT fold them into ``n_ran`` / ``n_failed_runtime`` / ``failed_nodes``,
    because whether a node ERROR is a kill turns on mutation-causation — which only
    ``run_mutant`` can resolve against the clean tree. A test-body FAILED in the
    same run is counted on its own (that's a real runtime failure), but the node
    ERROR is NOT auto-credited here."""
    transcript = (
        "FAILED tests/test_x.py::test_a - AssertionError\n"
        "ERROR tests/test_x.py::test_b - fixture failed\n"
        "1 failed, 1 error in 0.10s\n"
    )
    run = fgd._parse_pytest_output(transcript)
    # The runtime FAILED is counted; the node ERROR is NOT folded into the kill
    # ledger at the parse layer.
    assert run.n_failed_runtime == 1, run
    assert run.n_ran == 1, run
    assert run.failed_nodes == ("tests/test_x.py::test_a",)
    assert run.node_error_nodes == ("tests/test_x.py::test_b",)
    assert run.collection_errors == 0


def test_bare_node_error_is_not_a_kill_at_the_parse_layer():
    """THE CARDINAL-RISK GUARD (round-2 sharpen), parse half. A node-level ERROR
    (``ERROR tests/x.py::test_foo``) is a setup/fixture ERROR that a PRE-EXISTING
    broken fixture on a survivor's selector would emit IDENTICALLY, mutation or
    not. Counting it as a kill would be a FALSE kill, and a false kill MASKS a fake
    gate (the exact disease this tool fights). So the parse layer must NOT credit a
    bare node ERROR as a runtime failure: it contributes ZERO to n_ran /
    n_failed_runtime and is NOT laundered into the failed_nodes kill ledger.

    This test FAILS on the pre-round-2 code (which folded node errors straight into
    n_failed_runtime / n_ran / failed_nodes) and PASSES on the round-2 rule."""
    transcript = (
        "ERROR tests/test_x.py::test_a - fixture failed\n"
        "1 error in 0.10s\n"
    )
    run = fgd._parse_pytest_output(transcript)
    # SURFACED for reporting / the kill decision…
    assert run.node_error_nodes == ("tests/test_x.py::test_a",)
    # …but NOT a kill at the parse layer.
    assert run.n_failed_runtime == 0, run
    assert run.n_ran == 0, run
    assert "tests/test_x.py::test_a" not in run.failed_nodes


def test_preexisting_node_error_run_maps_to_non_kill_outcome():
    """END-TO-END biting test (the cardinal-risk guard, run-half). A mutant whose
    selector ERRORs on a node IDENTICALLY on the CLEAN tree (a pre-existing broken
    fixture) must NOT resolve to ``killed`` — that would be a FALSE kill masking a
    fake gate. We monkeypatch the pytest runner to return the SAME bare-node-ERROR
    transcript for BOTH the mutated run AND the clean-tree re-run, so every node
    error is pre-existing → run_mutant must report a NON-kill (``no-tests``).

    On the pre-round-2 code this resolved to ``killed`` (node errors were credited
    unconditionally); on the round-2 rule it is ``no-tests``."""
    before = fgd._sha256_file(PRODUCT)
    bare_node_error = (
        "ERROR tests/test_x.py::test_a - fixture failed\n"
        "1 error in 0.10s\n"
    )
    parsed = fgd._parse_pytest_output(bare_node_error)

    def _fake_run(_selector, _repo, _timeout):
        # Same node errors mutated AND clean → all pre-existing.
        return 1, parsed, bare_node_error

    m = _by_id(_fixture_mutants(), "fixture-real")
    with _MonkeyOn(fgd, "_run_pytest", _fake_run):
        r = fgd.run_mutant(m, repo=FIXTURE_DIR, timeout_s=60)
    assert r.outcome != "killed", r.detail
    assert r.outcome == "no-tests", r.detail
    assert "PRE-EXISTING" in r.detail, r.detail
    assert fgd._sha256_file(PRODUCT) == before, "tree must be restored"


def test_mutation_caused_node_error_is_a_kill():
    """The COMPLEMENT of the guard: a node error that is NEW under mutation (does
    NOT appear on the clean tree) IS a legitimate kill. We monkeypatch the runner
    so the MUTATED run ERRORs on a node but the CLEAN re-run is all-green — so the
    node error is mutation-caused → ``killed``. This is the exact shape of the real
    db_lock early_return mutant (connect_write→None makes fixtures ERROR), and it
    proves the round-2 rule did not throw the baby out with the bathwater."""
    before = fgd._sha256_file(PRODUCT)
    mutated_out = (
        "ERROR tests/test_x.py::test_a - TypeError: got NoneType\n"
        "1 error in 0.10s\n"
    )
    clean_out = "1 passed in 0.10s\n"
    mutated_parsed = fgd._parse_pytest_output(mutated_out)
    clean_parsed = fgd._parse_pytest_output(clean_out)
    calls = {"n": 0}

    def _fake_run(_selector, _repo, _timeout):
        calls["n"] += 1
        # 1st call = the mutated run; 2nd call = the clean re-run.
        if calls["n"] == 1:
            return 1, mutated_parsed, mutated_out
        return 0, clean_parsed, clean_out

    m = _by_id(_fixture_mutants(), "fixture-real")
    with _MonkeyOn(fgd, "_run_pytest", _fake_run):
        r = fgd.run_mutant(m, repo=FIXTURE_DIR, timeout_s=60)
    assert r.outcome == "killed", r.detail
    assert "mutation-caused node-level setup ERROR" in r.detail, r.detail
    assert "tests/test_x.py::test_a" in r.failed_tests
    assert calls["n"] == 2, "the clean re-run must have happened"
    assert fgd._sha256_file(PRODUCT) == before, "tree must be restored"


def test_clean_run_timeout_does_not_credit_node_errors_as_a_kill():
    """BITING TEST (the cardinal-risk guard's UNCERTAINTY direction, round-3).

    The mutated run produced node-level setup ERRORs but the CLEAN re-run — the
    one that would prove those errors are mutation-caused vs pre-existing — TIMES
    OUT. There is NO test-BODY failure. On uncertainty, a fake-gate detector must
    SURFACE a possible fake gate, never silently credit a kill: crediting the node
    errors here (treating an empty/unknown clean set as ``every node error is
    new``) would MASK a fake gate (rigor #1).

    This MUST FAIL on the pre-round-3 code (which returned the EMPTY frozenset on a
    clean-run timeout, so every mutated node error counted as mutation-caused →
    ``killed``) and PASS on the fix (``clean-run-timeout``, a NON-kill finding).
    The COMPLEMENT — a real test-body failure under the same timeout — is still a
    genuine kill and is covered separately below."""
    import subprocess

    before = fgd._sha256_file(PRODUCT)
    mutated_out = (
        "ERROR tests/test_x.py::test_a - fixture failed\n"
        "1 error in 0.10s\n"
    )
    mutated_parsed = fgd._parse_pytest_output(mutated_out)
    assert mutated_parsed.n_failed_runtime == 0, "no test-BODY failure in the setup"
    assert mutated_parsed.node_error_nodes, "a node-level ERROR is present"
    calls = {"n": 0}

    def _fake_run(_selector, _repo, _timeout):
        calls["n"] += 1
        # 1st call = the mutated run (node errors, no body failure).
        if calls["n"] == 1:
            return 1, mutated_parsed, mutated_out
        # 2nd call = the clean re-run → TIMES OUT (cannot adjudicate).
        raise subprocess.TimeoutExpired(cmd="pytest", timeout=_timeout)

    m = _by_id(_fixture_mutants(), "fixture-real")
    with _MonkeyOn(fgd, "_run_pytest", _fake_run):
        r = fgd.run_mutant(m, repo=FIXTURE_DIR, timeout_s=60)
    assert calls["n"] == 2, "the clean re-run must have been attempted"
    # The cardinal assertion: an UNADJUDICATED node error is NOT a kill.
    assert r.outcome != "killed", r.detail
    assert r.outcome == "clean-run-timeout", r.detail
    assert r.is_finding(), "an unadjudicated possible fake gate must be SURFACED"
    assert "TIMED OUT" in r.detail and "MASK a fake gate" in r.detail, r.detail
    assert r.failed_tests == (), "no node error may be credited as a killing test"
    assert fgd._sha256_file(PRODUCT) == before, "tree must be restored"


def test_clean_run_timeout_with_a_real_body_failure_is_still_a_kill():
    """The COMPLEMENT of the uncertainty guard: even when the clean re-run times
    out, a real test-BODY failure under the mutation is a genuine kill on its own
    merit (the kill stands without relying on the unadjudicated node errors). This
    path is UNCHANGED by the round-3 fix — it proves the fix did not make the tool
    miss a real kill."""
    import subprocess

    before = fgd._sha256_file(PRODUCT)
    mutated_out = (
        "FAILED tests/test_x.py::test_body - assert 1 == 2\n"
        "ERROR tests/test_x.py::test_a - fixture failed\n"
        "1 failed, 1 error in 0.10s\n"
    )
    mutated_parsed = fgd._parse_pytest_output(mutated_out)
    assert mutated_parsed.n_failed_runtime == 1, "a real test-BODY failure is present"
    assert mutated_parsed.node_error_nodes, "a node-level ERROR is also present"

    def _fake_run(_selector, _repo, _timeout):
        # node errors → triggers the clean re-run, which TIMES OUT.
        raise_on_second = getattr(_fake_run, "_called", False)
        _fake_run._called = True  # type: ignore[attr-defined]
        if raise_on_second:
            raise subprocess.TimeoutExpired(cmd="pytest", timeout=_timeout)
        return 1, mutated_parsed, mutated_out

    m = _by_id(_fixture_mutants(), "fixture-real")
    with _MonkeyOn(fgd, "_run_pytest", _fake_run):
        r = fgd.run_mutant(m, repo=FIXTURE_DIR, timeout_s=60)
    assert r.outcome == "killed", r.detail
    assert "tests/test_x.py::test_body" in r.failed_tests, r.failed_tests
    assert fgd._sha256_file(PRODUCT) == before, "tree must be restored"


class _MonkeyOn:
    """Tiny context-manager monkeypatch (so the assertion holds inside a `with`
    and is cleanly reverted afterwards, even on failure)."""

    def __init__(self, obj, name, value):
        self._obj, self._name, self._value = obj, name, value

    def __enter__(self):
        self._orig = getattr(self._obj, self._name)
        setattr(self._obj, self._name, self._value)
        return self

    def __exit__(self, *exc):
        setattr(self._obj, self._name, self._orig)
        return False


def test_real_mutant_set_loads_and_resolves_on_the_tree():
    """Every committed mutants/*.toml mutant loads, and its anchor resolves +
    mutates to parseable source against the current tree (a stale/typo'd seed
    mutant is caught here, not only at run time)."""
    repo = Path(fgd._REPO)
    mutants = fgd.load_mutants()
    assert len(mutants) >= 8, "the seed set must carry ≥8 mutants"
    for m in mutants:
        target = repo / m.target
        assert target.exists(), f"{m.id}: target {m.target} missing"
        src = target.read_text(encoding="utf-8")
        anchor = fgd.resolve_anchor(src, m)  # raises AnchorError if stale
        fgd.apply_op(src, m, anchor)  # raises if it produces unparseable source
