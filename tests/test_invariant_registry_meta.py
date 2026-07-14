"""The anti-stub-hack meta-check — Antiek Foundation SPR-06 (KEYSTONE / M3).

For every invariant declared in ``substrate/invariants/`` this asserts the guard
is REAL: it exists, is COLLECTED by the runner (not skipped/xfail/deselected),
and is NON-VACUOUS (the declaration carries a fail-before/pass-after,
negative-control, or mutation proof, and the guard actually RUNS GREEN here so a
missing/stubbed guard cannot fake-pass). An empty body / stubbed signal = a
registry FAILURE — that is the whole point: a guard that passes on broken code
(the §14.4 fake-green failure mode) must be detectable and rejected.

This test is itself an invariant guard, so it must itself be non-vacuous. The
``Broken-fixture proofs`` section at the bottom builds deliberately-broken
declarations in a tmp registry and proves the meta-check REJECTS each failure
mode (missing guard / skipped guard / xfailed guard / xpassed guard /
stubbed-always-pass guard / vacuous
§14.4-class guard). If those proofs ever pass on a stubbed guard, the original
disease has been rebuilt.

Why run the guards in-process via ``pytest.main`` (not just ``--collect-only``):
``--collect-only`` lists a ``@pytest.mark.skip`` node too, so collection alone
does NOT prove "not skipped". Running the node and demanding an outcome of
exactly ``passed`` — AND that the node was not ``@pytest.mark.xfail`` (an xfail
marker is the maintainer's "this is not a real assertion of the invariant yet"
signal, and an xpass would otherwise sneak through as a green call report) — is
the mechanical proof that distinguishes a live guard from a skipped / xfailed /
xpassed / missing one.
"""

from __future__ import annotations

import textwrap
from pathlib import Path

import pytest

from substrate.invariants import (
    GUARD_KIND_PYTEST,
    GUARD_KIND_SCRIPT,
    REPO_ROOT,
    STATUS_GUARDED,
    STATUS_UNGUARDED,
    Invariant,
    RegistryError,
    load_registry,
)

# ──────────────────────────────────────────────────────────────────────────────
# The in-process guard runner: run ONE node id and return its outcome.
# ──────────────────────────────────────────────────────────────────────────────

_VALID_NV_METHODS = frozenset(
    {"fail_before_pass_after", "negative_control", "mutation"}
)


class _OutcomePlugin:
    """A pytest plugin that records, for a single requested node, whether it
    PASSED at call time AS A LIVE, UNQUALIFIED ASSERTION. Skipped / xfailed /
    xpassed / errored / missing all yield ``passed is False`` — exactly the
    distinction the meta-check needs.

    The ``wasxfail`` carve-out is load-bearing. pytest reports an
    ``@pytest.mark.xfail`` node two ways, and BOTH must be rejected:

    * the test genuinely fails ⇒ the call report is ``skipped`` (``passed`` is
      already False) and carries a ``wasxfail`` reason;
    * the test incidentally passes (an "xpass", the default non-strict mode)
      ⇒ the call report is ``passed`` *and still carries ``wasxfail``*.

    Without the ``wasxfail`` check the xpass case would set ``passed = True`` and
    a guard marked ``xfail`` (the maintainer's explicit "this is NOT a real
    assertion of the invariant yet" signal) would fake-pass the meta-check — the
    same disease, one neutering vector over. An xfail marker on a guard means the
    guard is NOT a live green test, regardless of which way it lands this run."""

    def __init__(self) -> None:
        self.passed = False
        self.collected = 0
        self.was_xfail = False

    def pytest_collectreport(self, report) -> None:  # noqa: ANN001
        if report.passed:
            self.collected += len(getattr(report, "result", []) or [])

    def pytest_runtest_logreport(self, report) -> None:  # noqa: ANN001
        # Any call-phase report that carries a ``wasxfail`` reason came from an
        # @pytest.mark.xfail node — covers both xfail (skipped) and xpass
        # (passed). Either way the node is not a live, unqualified guard.
        if report.when == "call" and getattr(report, "wasxfail", None) is not None:
            self.was_xfail = True
        # Only the actual call phase counts as a real pass — and only if it was
        # NOT an xfail-marked node. A skip surfaces in the setup phase with
        # ``report.skipped``; we never set passed for it.
        if report.when == "call" and report.passed and not self.was_xfail:
            self.passed = True


def _run_guard_node(node_id: str) -> _OutcomePlugin:
    """Run exactly one pytest node id in-process and return the outcome plugin.

    Disables xdist + cacheprovider so the run is hermetic and the plugin's
    reports are not swallowed by a worker boundary.
    """
    plugin = _OutcomePlugin()
    pytest.main(
        [
            node_id,
            "-q",
            "-p",
            "no:cacheprovider",
            "-p",
            "no:xdist",
            "--no-header",
        ],
        plugins=[plugin],
    )
    return plugin


# ──────────────────────────────────────────────────────────────────────────────
# M3 core: the registry as a whole is well-formed + every guarded guard is real.
# ──────────────────────────────────────────────────────────────────────────────


def test_registry_loads_clean() -> None:
    """The registry parses with no malformed declaration, and there is at least
    one declaration (an empty registry is not a passing registry)."""
    invariants = load_registry()
    assert invariants, "the invariant registry is empty — nothing is declared"


@pytest.mark.parametrize(
    "inv",
    load_registry(),
    ids=lambda inv: inv.id,
)
def test_declaration_is_well_formed(inv: Invariant) -> None:
    """Every declaration has a statement that explains WHY (rigor #5) and a
    status-consistent shape: guarded ⇒ a guard + a well-formed non-vacuity
    proof; unguarded ⇒ a named owner and NO claimed guard (cannot fake-pass)."""
    assert inv.statement, f"{inv.id}: empty statement"
    # rigor #5 — the statement must explain the cost, not just name the rule.
    assert len(inv.statement) > 40, (
        f"{inv.id}: statement too thin to explain WHY it matters (rigor #5)"
    )

    if inv.status == STATUS_GUARDED:
        assert inv.guard, f"{inv.id}: guarded invariant must name a guard"
        assert inv.non_vacuity is not None, (
            f"{inv.id}: guarded invariant must carry a [non_vacuity] proof — "
            f"a guard with no proof of teeth is a candidate fake-green"
        )
        assert inv.non_vacuity.method in _VALID_NV_METHODS, (
            f"{inv.id}: non_vacuity.method {inv.non_vacuity.method!r} invalid"
        )
        assert inv.non_vacuity.detail, f"{inv.id}: empty non_vacuity.detail"
    elif inv.status == STATUS_UNGUARDED:
        assert inv.owner, (
            f"{inv.id}: unguarded invariant MUST name an owner sprint — an "
            f"honest gap with no owner is just an omission (rigor #1)"
        )
        assert not inv.guard, (
            f"{inv.id}: unguarded invariant must NOT claim a guard (it would "
            f"fake completeness — the exact disease this registry cures)"
        )
        assert inv.non_vacuity is None, (
            f"{inv.id}: unguarded invariant must NOT carry a non-vacuity proof"
        )


_GUARDED = [inv for inv in load_registry() if inv.status == STATUS_GUARDED]


@pytest.mark.parametrize("inv", _GUARDED, ids=lambda inv: inv.id)
def test_guarded_guard_file_exists(inv: Invariant) -> None:
    """The guard's file is on disk — a registration pointing at a deleted guard
    is a silent gap (the failure mode test_integration_invariants also guards)."""
    guard_file = REPO_ROOT / inv.guard_path
    assert guard_file.exists(), (
        f"{inv.id}: guard file {inv.guard_path} does not exist"
    )


@pytest.mark.parametrize("inv", _GUARDED, ids=lambda inv: inv.id)
def test_guarded_guard_is_collected_and_passes(inv: Invariant) -> None:
    """The guard node is COLLECTED, NOT SKIPPED, NOT XFAIL-MARKED, and PASSES —
    the mechanical proof that the guard is a live, non-vacuous test rather than a
    skipped / xfailed / xpassed / missing / stubbed-to-skip placeholder. (A
    pytest-kind guard's own ``guard`` node IS the bite; a script-kind guard is an
    exit-code gate with no collectible node, so its non-vacuity is RUN instead via
    its declared ``non_vacuity.bite_test`` in
    ``test_script_kind_guard_bite_test_is_live`` below — NOT skipped-as-unverified.)"""
    if inv.guard_kind != GUARD_KIND_PYTEST:
        pytest.skip(
            f"{inv.id}: script-kind guard — its non-vacuity is RUN via its "
            f"bite_test in test_script_kind_guard_bite_test_is_live"
        )
    outcome = _run_guard_node(inv.guard)
    assert not outcome.was_xfail, (
        f"{inv.id}: guard {inv.guard} is @pytest.mark.xfail — an xfail marker "
        f"declares the guard is NOT a real assertion of the invariant yet "
        f"(an xpass would otherwise fake-pass as a green call report)"
    )
    assert outcome.passed, (
        f"{inv.id}: guard {inv.guard} did not PASS at call time (it is missing, "
        f"skipped, xfailed, xpassed, or errored) — a registered guard must be a "
        f"live, green, non-vacuous test"
    )


# ──────────────────────────────────────────────────────────────────────────────
# Script-kind guards: VERIFY (do not prose-trust) their non-vacuity by RUNNING
# the declared bite_test, with the SAME rigor a pytest-kind guard's node gets.
# Before this, "status = guarded" meant LESS for a script-kind invariant — the
# meta-check only checked a [non_vacuity] block was DECLARED, never RAN its proof,
# so a future script-kind guard could name a non-existent / xfail / vacuous test
# and fake-pass. That is the §14.4 disease one guard_kind over; this closes it.
# ──────────────────────────────────────────────────────────────────────────────


_SCRIPT_GUARDED = [
    inv
    for inv in load_registry()
    if inv.status == STATUS_GUARDED and inv.guard_kind == GUARD_KIND_SCRIPT
]


def _check_script_bite(inv: Invariant) -> None:
    """Run a script-kind guard's declared bite_test and demand it is a live,
    non-vacuous negative control: present, COLLECTED, NOT xfail/xpass-marked, and
    PASSES. Factored so the broken-fixture proof runs the SAME logic this
    parametrized test runs (no parallel check that could drift)."""
    assert inv.guard_kind == GUARD_KIND_SCRIPT
    assert inv.non_vacuity is not None, f"{inv.id}: missing non_vacuity proof"
    bite = inv.non_vacuity.bite_test
    assert bite, (
        f"{inv.id}: script-kind guard must declare a non_vacuity.bite_test — its "
        f"exit-code gate is never RUN by the meta-check, so a prose-only proof "
        f"could name a non-existent / xfail / vacuous test and fake-pass"
    )
    assert (REPO_ROOT / bite.split("::", 1)[0]).exists(), (
        f"{inv.id}: bite_test file {bite.split('::', 1)[0]} does not exist"
    )
    outcome = _run_guard_node(bite)
    assert not outcome.was_xfail, (
        f"{inv.id}: bite_test {bite} is @pytest.mark.xfail — an xfail marker "
        f"declares it is NOT a real negative control of the invariant yet"
    )
    assert outcome.passed, (
        f"{inv.id}: bite_test {bite} did not PASS at call time (missing, skipped, "
        f"xfailed, xpassed, or errored) — a script-kind guard's non-vacuity must "
        f"be a live, green, collected negative control, not prose"
    )


@pytest.mark.parametrize("inv", _SCRIPT_GUARDED, ids=lambda inv: inv.id)
def test_script_kind_guard_bite_test_is_live(inv: Invariant) -> None:
    """For every script-kind GUARDED invariant, its non_vacuity.bite_test is a
    present, COLLECTED, NOT-xfail/xpass-marked, PASSING pytest node — the same
    mechanical teeth a pytest-kind guard's own node gets. This RUNS the proof
    rather than trusting the prose ``detail``, closing the hole where a
    script-kind 'guarded' meant only 'a non_vacuity block is declared'."""
    _check_script_bite(inv)


# ──────────────────────────────────────────────────────────────────────────────
# Rigor #3 — the meta-check is itself non-vacuous: prove it REJECTS each failure
# mode on a deliberately-broken tmp registry. If any of these passed, the
# meta-check would be the same fake-green disease it exists to catch.
# ──────────────────────────────────────────────────────────────────────────────


def _write_decl(dir_: Path, name: str, body: str) -> Path:
    p = dir_ / f"{name}.toml"
    p.write_text(textwrap.dedent(body), encoding="utf-8")
    return p


def _check_guarded(inv: Invariant) -> None:
    """The exact guarded-invariant assertions, factored so the broken-fixture
    proofs run the SAME logic the parametrized tests run (no parallel check that
    could drift). Raises AssertionError / RegistryError on a bad declaration."""
    # well-formedness (re-uses the same predicates as test_declaration_*)
    assert inv.status == STATUS_GUARDED
    assert inv.guard, f"{inv.id}: missing guard"
    assert inv.non_vacuity is not None, f"{inv.id}: missing non_vacuity proof"
    assert inv.non_vacuity.method in _VALID_NV_METHODS
    # file exists
    assert (REPO_ROOT / inv.guard_path).exists(), f"{inv.id}: guard file missing"
    # collected + not xfail-marked + passes (the anti-stub-hack teeth)
    if inv.guard_kind == GUARD_KIND_PYTEST:
        outcome = _run_guard_node(inv.guard)
        assert not outcome.was_xfail, f"{inv.id}: guard is xfail-marked"
        assert outcome.passed, f"{inv.id}: guard not green"


def test_meta_check_rejects_missing_guard(tmp_path: Path) -> None:
    """Failure mode 1 — a registration pointing at a non-existent test FAILS."""
    _write_decl(
        tmp_path,
        "broken-missing",
        """
        [invariant]
        id = "broken-missing"
        status = "guarded"
        statement = "A registration that points at a guard file that does not exist."
        guard = "tests/test_DOES_NOT_EXIST.py::test_nope"
        assertion = "nothing — the file is absent"
        [non_vacuity]
        method = "negative_control"
        detail = "claims a proof it cannot have"
        """,
    )
    (inv,) = load_registry(tmp_path)
    with pytest.raises(AssertionError, match="guard file"):
        _check_guarded(inv)


def test_meta_check_rejects_skipped_guard(tmp_path: Path) -> None:
    """Failure mode 2 — a guard that is @pytest.mark.skip (an unjustified skip /
    xfail placeholder) FAILS the meta-check. We point at a real prod-only
    skipped node and prove it is rejected."""
    _write_decl(
        tmp_path,
        "broken-skipped",
        """
        [invariant]
        id = "broken-skipped"
        status = "guarded"
        statement = "A registration whose guard node is decorated skip — collected but never run."
        guard = "tests/test_bernays_public_domain.py::test_live_network_ingest_bernays_titles"
        assertion = "nothing — the node is skipped"
        [non_vacuity]
        method = "negative_control"
        detail = "claims teeth but the node never runs"
        """,
    )
    (inv,) = load_registry(tmp_path)
    with pytest.raises(AssertionError, match="not green"):
        _check_guarded(inv)


def test_meta_check_rejects_xfailed_guard(tmp_path: Path) -> None:
    """Failure mode 2b — a guard marked @pytest.mark.xfail that GENUINELY FAILS
    is rejected. The xfail report lands as a call-phase ``skipped`` carrying
    ``wasxfail``: ``passed`` is already False, but we assert on the xfail signal
    so the rejection reason is honest (the guard is a known-broken placeholder,
    not a live assertion)."""
    xfail_guard = REPO_ROOT / "tests" / "_meta_tmp_xfail_guard.py"
    xfail_guard.write_text(
        "import pytest\n\n"
        '@pytest.mark.xfail(reason="placeholder: invariant not really guarded yet")\n'
        "def test_xfail_placeholder():\n"
        "    assert False  # genuinely fails -> reported xfailed\n",
        encoding="utf-8",
    )
    try:
        _write_decl(
            tmp_path,
            "broken-xfailed",
            """
            [invariant]
            id = "broken-xfailed"
            status = "guarded"
            statement = "A guard marked xfail that genuinely fails — a known-broken placeholder, not a live assertion of the invariant."
            guard = "tests/_meta_tmp_xfail_guard.py::test_xfail_placeholder"
            assertion = "nothing — the node is xfail-marked"
            [non_vacuity]
            method = "negative_control"
            detail = "claims teeth but the node is xfail-marked"
            """,
        )
        (inv,) = load_registry(tmp_path)
        outcome = _run_guard_node(inv.guard)
        assert outcome.was_xfail and not outcome.passed, (
            "sanity: a genuinely-failing xfail node lands as xfailed (wasxfail "
            "set, not passed) — the meta-check must reject it on the xfail signal"
        )
        with pytest.raises(AssertionError, match="xfail-marked"):
            _check_guarded(inv)
    finally:
        xfail_guard.unlink(missing_ok=True)


def test_meta_check_rejects_xpassed_guard(tmp_path: Path) -> None:
    """Failure mode 2c (the sharpen-round hole) — a guard marked @pytest.mark.xfail
    that INCIDENTALLY PASSES (an "xpass", default non-strict) is rejected. This is
    the dangerous one: pytest reports the call phase as ``passed`` (so a naive
    plugin would set ``passed = True``), but the report still carries ``wasxfail``.
    An xfail marker is the maintainer's "this is not a real assertion yet" signal;
    an xpass must NOT fake-pass the meta-check just because it happened to go green
    this run. Without the ``wasxfail`` carve-out this would have leaked — that is
    exactly the §14.4-class fake-green, one neutering vector over."""
    xpass_guard = REPO_ROOT / "tests" / "_meta_tmp_xpass_guard.py"
    xpass_guard.write_text(
        "import pytest\n\n"
        '@pytest.mark.xfail(reason="placeholder: expected to fail but incidentally passes")\n'
        "def test_xpass_placeholder():\n"
        "    assert True  # incidentally passes -> reported xpassed\n",
        encoding="utf-8",
    )
    try:
        _write_decl(
            tmp_path,
            "broken-xpassed",
            """
            [invariant]
            id = "broken-xpassed"
            status = "guarded"
            statement = "A guard marked xfail that incidentally passes (an xpass) — green this run, but xfail-marked means it is not a live assertion of the invariant."
            guard = "tests/_meta_tmp_xpass_guard.py::test_xpass_placeholder"
            assertion = "nothing real — it is xfail-marked and only incidentally green"
            [non_vacuity]
            method = "negative_control"
            detail = "claims teeth but the node is xfail-marked"
            """,
        )
        (inv,) = load_registry(tmp_path)
        outcome = _run_guard_node(inv.guard)
        # The teeth of this fixture: the call report is PASSED yet wasxfail is set.
        assert outcome.was_xfail, (
            "sanity: an xpass node carries wasxfail on a passed call report — "
            "without the carve-out the meta-check would treat it as a live guard"
        )
        assert not outcome.passed, (
            "the wasxfail carve-out must suppress the pass — an xfail-marked node "
            "is never a live green guard, even when it incidentally passes"
        )
        with pytest.raises(AssertionError, match="xfail-marked"):
            _check_guarded(inv)
    finally:
        xpass_guard.unlink(missing_ok=True)


def test_meta_check_rejects_stubbed_always_pass_guard(tmp_path: Path) -> None:
    """Failure mode 3 / rigor #3 — a guard with NO non-vacuity proof (the data
    signature of a stub-to-always-pass) FAILS well-formedness. The §14.4-class
    fake-green is exactly this: a guard that passes on broken code with nothing
    proving it would fail on the bug. An always-pass test file would also fail
    the runtime check below if it carried a proof it cannot honor — but the
    first line of defence is: NO PROOF ⇒ REJECTED."""
    # Write a real always-pass guard module + a declaration that omits the proof.
    stub = REPO_ROOT / "tests" / "_meta_tmp_always_pass_guard.py"
    stub.write_text(
        "def test_always_pass():\n    assert True  # stub: passes on anything\n",
        encoding="utf-8",
    )
    try:
        _write_decl(
            tmp_path,
            "broken-stub",
            """
            [invariant]
            id = "broken-stub"
            status = "guarded"
            statement = "A stubbed guard that asserts True — passes on broken code."
            guard = "tests/_meta_tmp_always_pass_guard.py::test_always_pass"
            assertion = "nothing — it asserts True"
            """,
        )
        (inv,) = load_registry(tmp_path)
        # No [non_vacuity] table ⇒ the well-formedness gate rejects it. This is
        # the anti-stub-hack: a guard with no proof of teeth is NOT declared.
        assert inv.non_vacuity is None
        with pytest.raises(AssertionError, match="non_vacuity"):
            _check_guarded(inv)
    finally:
        stub.unlink(missing_ok=True)


def test_meta_check_rejects_vacuous_section_14_4_guard(tmp_path: Path) -> None:
    """Rigor #3 (the headline proof) — register §14.4 with a deliberately-VACUOUS
    guard (a test that passes against a SYNTHETIC config and never loads the real
    one — the exact original fake-green) and show the meta-check rejects it.

    The vacuous guard PASSES on its own (that is what made it dangerous), so
    collection + run would go green. The registry catches it because the
    declaration cannot honestly carry a real fail-before/pass-after proof: a
    guard that never exercised the real config has no broken-state it ever
    failed on. We model that as: the vacuous guard's declaration omits a valid
    non-vacuity proof → REJECTED. (A maintainer who fabricates a proof detail is
    out of scope of a mechanical check; the on-ramp requires the proof be a real
    recorded artifact, and SPR-09's upstream-watcher is the human-review backstop.)"""
    vacuous = REPO_ROOT / "tests" / "_meta_tmp_vacuous_14_4_guard.py"
    vacuous.write_text(
        # The original disease: asserts the pin against a SYNTHETIC dict, never
        # touching the real config.yaml. It passes — and proves nothing.
        "def test_synthesis_pin_FAKE_GREEN():\n"
        "    synthetic_config = {'synthesis': {'primary': 'anthropic/claude-opus'}}\n"
        "    assert synthetic_config['synthesis']['primary'].startswith('anthropic/')\n",
        encoding="utf-8",
    )
    try:
        _write_decl(
            tmp_path,
            "broken-14-4-vacuous",
            """
            [invariant]
            id = "broken-14-4-vacuous"
            status = "guarded"
            statement = "§14.4 with a fake-green guard that asserts against a synthetic config and never loads the real config.yaml — the original disease."
            guard = "tests/_meta_tmp_vacuous_14_4_guard.py::test_synthesis_pin_FAKE_GREEN"
            assertion = "nothing real — it never loads config.yaml"
            """,
        )
        (inv,) = load_registry(tmp_path)
        # The vacuous guard would RUN GREEN — collection is not enough. The
        # registry rejects it because it carries no valid non-vacuity proof.
        assert _run_guard_node(inv.guard).passed, (
            "sanity: the vacuous guard does pass on its own (that is why it was "
            "dangerous) — the registry must reject it on the PROOF, not the run"
        )
        with pytest.raises(AssertionError, match="non_vacuity"):
            _check_guarded(inv)
    finally:
        vacuous.unlink(missing_ok=True)


def test_meta_check_rejects_unguarded_that_claims_a_guard(tmp_path: Path) -> None:
    """Rigor #1 — an @unguarded entry that sneaks in a guard (to look complete)
    is rejected. An unguarded invariant must be HONESTLY unguarded."""
    _write_decl(
        tmp_path,
        "broken-fake-complete",
        """
        [invariant]
        id = "broken-fake-complete"
        status = "unguarded"
        owner = "SPR-99"
        statement = "Pretends to be unguarded while claiming a guard to look complete."
        guard = "tests/test_seam_no_copy.py::test_read_to_write_copy_fails_the_guard"
        assertion = "fake-complete"
        """,
    )
    (inv,) = load_registry(tmp_path)

    # Re-run the same unguarded predicate the parametrized test uses.
    def _check_unguarded(i: Invariant) -> None:
        assert i.status == STATUS_UNGUARDED
        assert i.owner, f"{i.id}: unguarded must name an owner"
        assert not i.guard, (
            f"{i.id}: unguarded must NOT claim a guard (fake completeness)"
        )

    with pytest.raises(AssertionError, match="NOT claim a guard|must NOT claim"):
        _check_unguarded(inv)


def test_meta_check_rejects_malformed_toml(tmp_path: Path) -> None:
    """A declaration whose id does not match its filename stem is a malformed
    registry (a programming error) → RegistryError, never a silent skip."""
    _write_decl(
        tmp_path,
        "broken-id-mismatch",
        """
        [invariant]
        id = "this-id-does-not-match-the-filename"
        status = "guarded"
        statement = "id mismatch should be a loud RegistryError, not a silent pass."
        guard = "tests/x.py::t"
        assertion = "x"
        [non_vacuity]
        method = "mutation"
        detail = "x"
        """,
    )
    with pytest.raises(RegistryError, match="must match filename stem"):
        load_registry(tmp_path)


def test_meta_check_rejects_script_guard_without_bite_test(tmp_path: Path) -> None:
    """Failure mode 4 (the SPR-09 hole) — a GUARDED script-kind invariant that
    declares a [non_vacuity] block but NO structured bite_test FAILS TO LOAD. A
    script-kind guard's exit-code gate is never RUN by the meta-check, so a
    prose-only proof could name a non-existent / xfail / vacuous test and the old
    meta-check would still pass it ('guarded' meant LESS for script-kind). The
    loader rejects it loudly (RegistryError) so the disease cannot reappear one
    guard_kind over."""
    _write_decl(
        tmp_path,
        "broken-script-no-bite",
        """
        [invariant]
        id = "broken-script-no-bite"
        status = "guarded"
        guard = "tools/lint/owner_boundary_check.py"
        guard_kind = "script"
        statement = "A script-kind guard with a prose-only non_vacuity and no structured bite_test — never RUN, so prose could lie."
        assertion = "an exit-code gate whose teeth are only described in prose"
        [non_vacuity]
        method = "negative_control"
        detail = "claims a test proves teeth but names no runnable node"
        """,
    )
    with pytest.raises(RegistryError, match="bite_test"):
        load_registry(tmp_path)


def test_meta_check_rejects_script_guard_with_dead_bite_test(tmp_path: Path) -> None:
    """Failure mode 4b — a GUARDED script-kind invariant whose bite_test names a
    node that does NOT EXIST (the same shape a stub / xfail / vacuous node takes
    once RUN) is rejected at verification time. The declaration LOADS (it has a
    structured bite_test, so the loader's required-field gate is satisfied), but
    _check_script_bite RUNS the named node and rejects it because it is not a
    live, green, collected negative control — exactly the rigor pytest-kind
    guards get, now applied to script-kind. This is what makes the new bite_test
    contract have teeth rather than being a second prose field."""
    _write_decl(
        tmp_path,
        "broken-script-dead-bite",
        """
        [invariant]
        id = "broken-script-dead-bite"
        status = "guarded"
        guard = "tools/lint/owner_boundary_check.py"
        guard_kind = "script"
        statement = "A script-kind guard whose bite_test names a node that does not exist — the proof is never actually a live negative control."
        assertion = "an exit-code gate whose declared bite_test cannot be collected"
        [non_vacuity]
        method = "negative_control"
        bite_test = "tests/test_DOES_NOT_EXIST.py::test_nope"
        detail = "names a bite_test that cannot be collected — never proves teeth"
        """,
    )
    (inv,) = load_registry(tmp_path)
    # Sanity: a dead bite node is not collected/green, so the run is not a pass.
    assert not _run_guard_node(inv.non_vacuity.bite_test).passed, (
        "sanity: a non-existent bite_test node cannot pass — the meta-check must "
        "reject the declaration on RUNNING it, not on trusting the prose detail"
    )
    with pytest.raises(AssertionError, match="bite_test"):
        _check_script_bite(inv)


def test_meta_check_rejects_script_guard_with_xfail_bite_test(tmp_path: Path) -> None:
    """Failure mode 4c — a GUARDED script-kind invariant whose bite_test points at
    an @pytest.mark.xfail node (an xpass that incidentally goes green this run) is
    rejected. An xfail marker is the maintainer's 'not a real negative control
    yet' signal; it must NOT fake-pass the script-kind contract just because it
    happened to pass. This inherits the wasxfail carve-out _run_guard_node already
    proves for pytest-kind guards — the SAME machinery, now load-bearing for
    script-kind too."""
    xpass_bite = REPO_ROOT / "tests" / "_meta_tmp_script_xpass_bite.py"
    xpass_bite.write_text(
        "import pytest\n\n"
        '@pytest.mark.xfail(reason="placeholder: not a real negative control yet")\n'
        "def test_xpass_bite():\n"
        "    assert True  # incidentally passes -> reported xpassed\n",
        encoding="utf-8",
    )
    try:
        _write_decl(
            tmp_path,
            "broken-script-xfail-bite",
            """
            [invariant]
            id = "broken-script-xfail-bite"
            status = "guarded"
            guard = "tools/lint/owner_boundary_check.py"
            guard_kind = "script"
            statement = "A script-kind guard whose bite_test is xfail-marked — green this run, but xfail means it is not a live negative control of the invariant."
            assertion = "an exit-code gate whose bite_test is an xfail placeholder"
            [non_vacuity]
            method = "negative_control"
            bite_test = "tests/_meta_tmp_script_xpass_bite.py::test_xpass_bite"
            detail = "names an xfail-marked bite_test — not a live negative control"
            """,
        )
        (inv,) = load_registry(tmp_path)
        outcome = _run_guard_node(inv.non_vacuity.bite_test)
        # The teeth: the call report is PASSED yet wasxfail is set — without the
        # carve-out the script-kind contract would treat it as a live bite.
        assert outcome.was_xfail and not outcome.passed, (
            "sanity: an xpass bite node carries wasxfail on a passed call report; "
            "the carve-out must suppress the pass so the meta-check rejects it"
        )
        with pytest.raises(AssertionError, match="xfail"):
            _check_script_bite(inv)
    finally:
        xpass_bite.unlink(missing_ok=True)


# ──────────────────────────────────────────────────────────────────────────────
# The Wave-1 expectation (verification gate "Wave-1 registered").
# ──────────────────────────────────────────────────────────────────────────────


def test_wave_1_invariants_are_registered() -> None:
    """The Wave-1 invariants, RECONCILED to live main (SPR-02).

    Three guards land guarded because their guard nodes genuinely exist and pass
    on main: §14.4 synthesis pin, provenance no-copy seams, and single-graph
    writer through the remote-exec funnel.

    Two staged invariants flip to @unguarded because their guards target
    production code that stranded with the prior foundation and is NOT on main —
    so the guard fails at COLLECTION (ImportError), which would be a fake-green
    registration if declared guarded (see
    docs/decisions/2026-05-31-invariant-registry-reconcile.md):

      * single-writer-per-graph        → substrate/graph_handle.py absent (owner SPR-04)
      * providers-pinned-primary-fails → require_pinned / ProviderRegistrationError
                                          / scripts/dev_bootstrap.py absent (owner operator)

    The §9.0 and First-Light owners are re-pointed to THIS spec's reality: §9.0 →
    SPR-03 (this spec's servability sprint); First Light → operator (no
    First-Light sprint in this spec). §5 voice stays operator-owned. All are
    present @unguarded with a named owner — NOT silently omitted (rigor #1)."""
    by_id = {inv.id: inv for inv in load_registry()}

    # Guards whose nodes genuinely collect + pass against live main.
    must_be_guarded = {
        "section-14-4-synthesis-pin",
        "provenance-chain-no-copy",
        "single-writer-remote-exec",
    }
    for inv_id in must_be_guarded:
        assert inv_id in by_id, f"Wave-1 invariant {inv_id} not registered"
        assert by_id[inv_id].status == STATUS_GUARDED, f"{inv_id} not guarded"

    # Honest gaps — present @unguarded with a named owner, never omitted. The
    # owner is matched by prefix so the meaningful owner stays pinned while the
    # parenthetical rationale on flag-for-ratification entries may evolve.
    must_be_unguarded_with_owner = {
        "single-writer-per-graph": "SPR-04",
        "providers-pinned-primary-fails-loud": "operator",
        "section-9-0-servability-polarity": "SPR-03",
        "first-light-e2e": "operator",
        "section-5-voice-style": "operator",
    }
    for inv_id, expected_owner in must_be_unguarded_with_owner.items():
        assert inv_id in by_id, f"{inv_id} must be registered @unguarded, not omitted"
        inv = by_id[inv_id]
        assert inv.status == STATUS_UNGUARDED, f"{inv_id} should be @unguarded"
        assert inv.owner, f"{inv_id} @unguarded must name an owner"
        assert inv.owner.startswith(expected_owner), (
            f"{inv_id} owner {inv.owner!r} does not start with expected "
            f"{expected_owner!r}"
        )
