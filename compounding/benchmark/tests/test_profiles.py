"""AFF SPR-11 M1 — the ADDITIVE prod-shape profile selector.

These tests prove, WITHOUT any live dispatch, that:

  1. ``profiles/prod.toml`` loads into a BenchmarkProfile whose config is
     REAL-dispatch — ``mock_run=False`` and ``dispatch_mode="real"`` — so
     selecting it flips the harness OFF the reuse-blind demo-loop mocks. This
     is the M1 acceptance criterion ("selecting --profile prod flips the
     config to real-dispatch (mock_run=False, no fixtures)").
  2. The built-in ``dev`` profile is the existing autonomous MOCK path
     (``mock_run=True``), so ``--profile dev`` is a no-op relative to today.
  3. ``run.py`` REFUSES to execute a prod (real-dispatch) profile from this
     build environment (exit 2) and prints the operator-window command — it
     does NOT silently fall back to mocks (rigor #1). The dev profile still
     produces the recorded artifact.
  4. A typo'd / missing profile name is rejected loudly (no silent
     mock-default that could yield a vacuous "prod" run).

The live prod RUN is DEFERRED to the operator window (creds + box + a
reuse-consuming browse loop). Nothing here exercises live dispatch.
"""

from __future__ import annotations

import os
import sys

import pytest

_HERE = os.path.dirname(os.path.abspath(__file__))
_REPO = os.path.dirname(os.path.dirname(os.path.dirname(_HERE)))
if _REPO not in sys.path:
    sys.path.insert(0, _REPO)

from compounding.benchmark import run as runmod  # noqa: E402
from compounding.benchmark.profiles import (  # noqa: E402
    DEV_PROFILE,
    available_profiles,
    load_profile,
)

# ── M1 acceptance: --profile prod flips to real dispatch (mock_run=False) ─


def test_prod_profile_flips_to_real_dispatch():
    prof = load_profile("prod")
    assert prof.mock_run is False, "prod profile MUST set mock_run=False (not the demo-loop mock)"
    assert prof.dispatch_mode == "real", "prod profile dispatch_mode must be 'real'"
    assert prof.uses_real_dispatch is True, (
        "the prod profile must report uses_real_dispatch — the single boolean "
        "the harness wiring branches on"
    )
    # The diff-able twin of the dev artifact.
    assert prof.out_filename("abc1234") == "prod-abc1234.json"
    # Prod tiers are recorded so the live run dispatches against them.
    assert prof.model_tiers, "prod profile must name the prod model tiers"


def test_dev_profile_is_the_existing_mock_path():
    prof = load_profile("dev")
    assert prof is DEV_PROFILE
    assert prof.mock_run is True, "dev profile is the autonomous mock path"
    assert prof.dispatch_mode == "mock"
    assert prof.uses_real_dispatch is False
    assert prof.out_filename("abc1234") == "spr09_run.json"


def test_prod_toml_is_discoverable():
    assert "prod" in available_profiles()


def test_unknown_profile_is_rejected_loudly():
    with pytest.raises(FileNotFoundError):
        load_profile("does-not-exist")


# ── M1: run.py routing — prod REFUSES (no mock fallback), dev runs ────────


def test_run_prod_profile_refuses_and_does_not_mock_around(capsys):
    # --profile prod must exit 2 (could-not-complete) WITHOUT writing a
    # results artifact — it prints the operator-window command instead of
    # falling back to the mock demo loop.
    rc = runmod.main(["--profile", "prod"])
    assert rc == 2, "a prod-shaped live run must be REFUSED from the build env (exit 2)"
    out = capsys.readouterr().out
    assert "REFUSED" in out
    assert "operator window" in out.lower()
    # The exact run command + the diff-able artifact path are surfaced.
    assert "--profile prod" in out
    assert "prod-" in out and ".json" in out
    # Non-negotiable: it did NOT quietly run the mocks to fake a green.
    assert "wrote" not in out.lower(), "prod refusal must NOT have written an artifact"


def test_run_dev_profile_writes_mock_artifact(tmp_path):
    out = tmp_path / "dev_run.json"
    # --n 2 (the bootstrap minimum): this test proves the SELECTOR routes
    # --profile dev to the mock path and writes the artifact — it is NOT a
    # full statistical run (SPR-09's test_run_mock covers the n=20 mock). A
    # small n keeps the CI keystone job fast: the full default n=20 over 12
    # questions x 3 arms ran ~150s on its own — far too heavy for a
    # selector-routing assertion, and it blew the keystone job's timeout on CI.
    rc = runmod.main(["--profile", "dev", "--out", str(out), "--n", "2"])
    assert rc == 0, "the dev (mock) profile still produces the recorded artifact"
    assert out.is_file(), "dev profile writes the mock artifact"


def test_default_profile_is_dev(tmp_path):
    # No --profile flag → dev (the existing default behaviour, unchanged).
    # --n 2: asserts the DEFAULT routes to the dev mock path AND runs to a
    # written artifact — not the full statistical benchmark (kept fast for the
    # CI keystone job; see the note in the sibling test above).
    out = tmp_path / "default_run.json"
    rc = runmod.main(["--out", str(out), "--n", "2"])
    assert rc == 0
    assert out.is_file()
