"""
Mechanical assertion of Antiek's architectural invariants.

Each test corresponds to one rule registered in
``substrate.invariants.INVARIANTS``. Failure messages name the
invariant id, the offending file:line where applicable, and a
suggestion. The intent is that a CI failure here is debuggable
without reading any other file.

Why parametrize on the registry rather than write one test per
invariant by hand:

- Adding an invariant is a one-line append to the registry plus its
  check helper. The test layer auto-picks it up.
- The same parametrization is used by ``python -m
  substrate.invariants`` so the CLI report and the pytest output
  cannot drift.
- A maintainer who breaks an invariant sees the same id in CI as
  in the standalone CLI; no translation layer.

The check helpers themselves live in ``substrate/invariants.py``
because they are read by both the test suite and the standalone
report. Test code here is responsible for assertion plumbing
only — not for the rule logic.
"""

from __future__ import annotations

import importlib
import os
import sys

import pytest

from substrate import invariants as inv_module


# ---------------------------------------------------------------------------
# Registry sanity — these would catch a refactor that broke the registry
# shape itself, separately from any one rule.
# ---------------------------------------------------------------------------


def test_registry_module_has_no_uplayer_imports() -> None:
    """The invariants module must not violate I-004 itself.

    If the registry imported from acquisition/ or orchestration/, every
    check would transitively pull in heavy dependencies and a syntax
    error in those layers would hide a real invariant violation. We
    keep substrate/invariants.py to stdlib-only.
    """
    imports = inv_module.collect_imports(
        inv_module.SUBSTRATE_DIR / "invariants.py"
    )
    forbidden = set(inv_module.UPLAYER_DIRS)
    bad = [(name, ln) for name, ln in imports if name.split(".")[0] in forbidden]
    assert not bad, (
        "substrate/invariants.py imports from uplayer directories: "
        f"{bad}; the registry must stay leaf"
    )


def test_registry_ids_are_unique_and_sorted() -> None:
    ids = [inv.id for inv in inv_module.INVARIANTS]
    assert len(ids) == len(set(ids)), f"duplicate invariant ids: {ids}"
    # Sorted by id keeps the report deterministic. If a new invariant is
    # appended out of order this test catches it before review.
    assert ids == sorted(ids), f"INVARIANTS not sorted by id: {ids}"


def test_every_invariant_has_a_check() -> None:
    missing = [inv.id for inv in inv_module.INVARIANTS if inv.id not in inv_module.CHECKS]
    assert not missing, f"invariants with no registered check: {missing}"


def test_no_orphan_checks() -> None:
    registered_ids = {inv.id for inv in inv_module.INVARIANTS}
    orphan = [cid for cid in inv_module.CHECKS if cid not in registered_ids]
    assert not orphan, f"CHECKS keys not in INVARIANTS: {orphan}"


def test_get_invariant_round_trip() -> None:
    for inv in inv_module.INVARIANTS:
        assert inv_module.get_invariant(inv.id) is inv


def test_unknown_invariant_id_raises() -> None:
    with pytest.raises(KeyError):
        inv_module.get_invariant("I-9999-not-real")


# ---------------------------------------------------------------------------
# Per-invariant assertion. Parametrized so each id shows as its own test
# row in the pytest summary.
# ---------------------------------------------------------------------------


@pytest.mark.parametrize("inv", inv_module.INVARIANTS, ids=[i.id for i in inv_module.INVARIANTS])
def test_invariant_holds(inv: inv_module.Invariant) -> None:
    check = inv_module.CHECKS[inv.id]
    violations = check()
    if not violations:
        return
    if inv.severity == "warn":
        # Mid-migration rules: print to stderr, do not fail.
        pytest.skip(
            f"{inv.id} {inv.name} has {len(violations)} violations but severity=warn:\n  "
            + "\n  ".join(violations)
        )
    message = f"{inv.id} {inv.name} violated:\n  " + "\n  ".join(violations)
    pytest.fail(message, pytrace=False)


# ---------------------------------------------------------------------------
# Sanity tests on the helpers themselves — small unit tests that protect
# the test infrastructure from rotting.
# ---------------------------------------------------------------------------


@pytest.mark.parametrize(
    "imported,package,expected",
    [
        ("boto3", "boto3", True),
        ("boto3.session", "boto3", True),
        ("boto3session", "boto3", False),
        ("google.cloud", "google.cloud", True),
        ("google.cloud.storage", "google.cloud", True),
        ("googlecloud", "google.cloud", False),
        ("", "boto3", False),
    ],
)
def test_matches_package_semantics(imported: str, package: str, expected: bool) -> None:
    assert inv_module.matches_package(imported, package) is expected


def test_run_all_produces_a_dict_keyed_by_invariant_id() -> None:
    results = inv_module.run_all()
    assert set(results.keys()) == {i.id for i in inv_module.INVARIANTS}
    for k, v in results.items():
        assert isinstance(v, list), f"check {k} returned {type(v).__name__}, expected list"


def test_format_report_includes_every_invariant() -> None:
    results = inv_module.run_all()
    text = inv_module._format_report(results)
    for inv in inv_module.INVARIANTS:
        assert inv.id in text, f"report missing {inv.id}"
    assert "invariants checked" in text


# ---------------------------------------------------------------------------
# Coverage gate — the report's exit code must reflect the assertions.
# ---------------------------------------------------------------------------


def test_main_returns_zero_when_all_invariants_pass(monkeypatch: pytest.MonkeyPatch) -> None:
    """If every check returns no violations, main() exits 0."""

    def fake_run_all() -> dict[str, list[str]]:
        return {inv.id: [] for inv in inv_module.INVARIANTS}

    monkeypatch.setattr(inv_module, "run_all", fake_run_all)
    assert inv_module.main() == 0


def test_main_returns_two_when_error_invariant_fails(monkeypatch: pytest.MonkeyPatch) -> None:
    """An error-severity violation produces exit code 2."""

    def fake_run_all() -> dict[str, list[str]]:
        out = {inv.id: [] for inv in inv_module.INVARIANTS}
        # I-001 is error-severity by construction.
        out["I-001"] = ["synthetic violation for test"]
        return out

    monkeypatch.setattr(inv_module, "run_all", fake_run_all)
    assert inv_module.main() == 2


def test_main_returns_zero_when_only_warn_invariant_fails(monkeypatch: pytest.MonkeyPatch) -> None:
    """A warn-severity violation prints but does not fail CI.

    We need at least one warn-severity invariant in the registry to fully
    exercise this path. If none exists today, the test still asserts the
    branching logic by injecting a synthetic warn-severity row into the
    registry locally.
    """

    warn_invariant = inv_module.Invariant(
        id="I-TEST-WARN",
        name="synthetic-warn",
        summary="test-only warn-severity row",
        rationale="protects the main() exit-code path",
        category="substrate",
        introduced="2026-05-24",
        source="tests/test_invariants.py",
        severity="warn",
    )
    monkeypatch.setattr(
        inv_module,
        "INVARIANTS",
        inv_module.INVARIANTS + (warn_invariant,),
    )
    monkeypatch.setitem(
        inv_module.CHECKS,
        "I-TEST-WARN",
        lambda: ["synthetic warn violation"],
    )
    assert inv_module.main() == 0


# ---------------------------------------------------------------------------
# Smoke test for the AST walker — guards against an upgrade of the
# stdlib ast module changing node shape unexpectedly.
# ---------------------------------------------------------------------------


def test_collect_imports_finds_function_local_imports(tmp_path) -> None:
    """``collect_imports`` must find imports anywhere in the module, not
    just top-level. A future maintainer might be tempted to scope it to
    top-level imports for speed; this test prevents that regression
    because deferred imports are exactly the kind of thing that hides
    cloud-SDK use under conditional code paths.
    """
    f = tmp_path / "sample.py"
    f.write_text(
        "import os\n"
        "def f():\n"
        "    import boto3.session  # deferred import\n"
        "    return boto3.session\n"
        "from x import y\n"
    )
    names = {name for name, _ in inv_module.collect_imports(f)}
    assert "os" in names
    assert "boto3.session" in names
    assert "x" in names
