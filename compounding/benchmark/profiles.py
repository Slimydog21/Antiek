"""AFF SPR-11 — benchmark profile selector (ADDITIVE; the measurement core is untouched).

SPR-09 proved the compounding instrument is falsifiable, but its recorded
run is the MOCK path: ``make_demo_loop`` is reuse-blind and makes no
provider ``dispatch.call``, so every delta is ~0. The keystone caveat
(documented in ``harness.py`` and ``run.py``) is that REAL compounding can
only be measured by a ``mock_run=false`` run with a reuse-CONSUMING browse
loop + prod model tiers + provider credentials — the operator-window run.

SPR-11 (the EXIT) defends exactly one failure mode: *"it compounds in dev,
but not on prod."* This module is the ADDITIVE selector that lets the EXISTING
harness be pointed at a prod-shaped configuration without editing the
measurement core (``harness.py`` / ``measure.py`` are byte-unchanged —
verified by ``git diff origin/main``). A profile is a small bundle of config
the orchestration entrypoint (``run.py``) reads:

  * ``mock_run``  — False for prod (flips ``run_benchmark(mock_run=...)``),
    True for the dev/mock profile (the only path that runs autonomously here).
  * ``dispatch_mode`` — "real" for prod (the live dispatch path + a
    reuse-consuming browse loop), "mock" for the demo loop. This is the
    field a test asserts to prove ``--profile prod`` flips OFF the mocks.
  * ``model_tiers`` — the prod tier registry the live run dispatches against
    (recorded on the profile; the live run reads it, this sprint does not).
  * ``n`` / ``material_floor`` / ``control_tolerance`` — operator-ratified
    scored-run parameters (decision §0.2). Baked into the profile so the
    operator window's command is exact, never re-derived ad hoc.
  * ``out_filename_template`` — ``prod-{sha}.json`` for prod (the diff-able
    twin of the dev ``spr09_run.json``).

WHAT THIS SPRINT DOES vs DEFERS (the phase split, honored exactly):

  * BUILD (autonomous): this loader + ``profiles/prod.toml`` + the
    ``--profile`` wiring in ``run.py`` + a unit test proving ``--profile
    prod`` yields ``mock_run=False`` / ``dispatch_mode="real"`` (no fixtures
    loaded). Provable WITHOUT live dispatch.
  * DEFER (operator window): the actual LIVE prod-shaped RUN. It needs prod
    model-tier credentials, the box, AND a reuse-consuming browse loop that
    does not exist yet. This module REFUSES to execute it (and never falls
    back to mocks to fake a green) — it prints the exact run command for the
    operator instead. A fabricated ``prod-<sha>.json`` would re-create the
    exact failure SPR-09/SPR-11 exist to prevent (rigor #1).

§16: this module is pure config (TOML read + a dataclass). It launches no
process, registers no remote-exec provider, and adds no second runtime
entrypoint — the live run, when the operator runs it, drives the SAME
``runtime.research_runner.HostLocalRunner`` the dev run uses.
"""

from __future__ import annotations

import os
import tomllib
from dataclasses import dataclass, field
from typing import Any

PROFILES_DIR = os.path.join(os.path.dirname(os.path.abspath(__file__)), "profiles")

# The default mock profile parameters, kept in lock-step with run.py's
# MOCK_N / DEFAULT_BOOTSTRAP_RESAMPLES so selecting --profile dev is
# byte-equivalent to the existing default path.
_MOCK_N = 20


@dataclass(frozen=True)
class BenchmarkProfile:
    """A named benchmark configuration. ``mock_run`` / ``dispatch_mode`` are
    the load-bearing fields the EXIT turns on: a prod profile flips
    ``mock_run`` False and ``dispatch_mode`` to "real" (the live dispatch +
    reuse-consuming loop), the dev profile keeps the demo-loop mocks."""

    name: str
    mock_run: bool
    dispatch_mode: str  # "real" | "mock"
    model_tiers: dict[str, str] = field(default_factory=dict)
    n: int = _MOCK_N
    material_floor: float = 0.0
    control_tolerance: float = 0.0
    parameters_ratified: bool = False
    out_filename_template: str = "spr09_run.json"
    description: str = ""

    @property
    def uses_real_dispatch(self) -> bool:
        """True iff this profile measures REAL compounding (no demo-loop
        mocks). The single boolean the ``--profile prod`` acceptance test
        asserts: a prod profile is real-dispatch, a dev profile is not."""
        return self.dispatch_mode == "real" and not self.mock_run

    def out_filename(self, sha: str) -> str:
        """Resolve the output artifact filename, substituting the short sha
        into the template (e.g. ``prod-{sha}.json`` → ``prod-abc1234.json``)
        so the dev and prod curves are diff-able by name."""
        return self.out_filename_template.format(sha=sha)


# The built-in DEV profile mirrors run.py's existing default path exactly, so
# ``--profile dev`` is a no-op relative to today's behaviour (the autonomous,
# mock, recorded artifact). It is defined in code (not TOML) so the default
# path has no file dependency.
DEV_PROFILE = BenchmarkProfile(
    name="dev",
    mock_run=True,
    dispatch_mode="mock",
    n=_MOCK_N,
    out_filename_template="spr09_run.json",
    description=(
        "The SPR-09 autonomous mock run on the reuse-blind demo loop "
        "(make_demo_loop). delta ~= 0 by construction; the keystone null."
    ),
)


def _coerce_profile(name: str, data: dict[str, Any]) -> BenchmarkProfile:
    """Build a BenchmarkProfile from a parsed TOML table. Unknown keys are
    rejected loudly so a typo in prod.toml can never silently fall back to a
    mock default (that would be a vacuous prod run — rigor #3)."""
    allowed = {
        "mock_run",
        "dispatch_mode",
        "model_tiers",
        "n",
        "material_floor",
        "control_tolerance",
        "parameters_ratified",
        "out_filename_template",
        "description",
    }
    unknown = set(data) - allowed
    if unknown:
        raise ValueError(
            f"profile {name!r}: unknown keys {sorted(unknown)} "
            f"(allowed: {sorted(allowed)})"
        )
    if "mock_run" not in data or "dispatch_mode" not in data:
        raise ValueError(
            f"profile {name!r}: must declare both 'mock_run' and "
            "'dispatch_mode' (no silent defaulting — a prod profile that "
            "forgot mock_run could vacuously fall back to mocks)"
        )
    return BenchmarkProfile(
        name=name,
        mock_run=bool(data["mock_run"]),
        dispatch_mode=str(data["dispatch_mode"]),
        model_tiers=dict(data.get("model_tiers", {})),
        n=int(data.get("n", _MOCK_N)),
        material_floor=float(data.get("material_floor", 0.0)),
        control_tolerance=float(data.get("control_tolerance", 0.0)),
        parameters_ratified=bool(data.get("parameters_ratified", False)),
        out_filename_template=str(data.get("out_filename_template", "spr09_run.json")),
        description=str(data.get("description", "")),
    )


def load_profile(name: str, *, profiles_dir: str | None = None) -> BenchmarkProfile:
    """Load a profile by name. ``dev`` is the built-in mock profile; any other
    name is read from ``profiles/{name}.toml``. Raises ``FileNotFoundError`` for
    an unknown profile name (never silently mock-defaults)."""
    if name == "dev":
        return DEV_PROFILE
    base = profiles_dir or PROFILES_DIR
    path = os.path.join(base, f"{name}.toml")
    if not os.path.isfile(path):
        raise FileNotFoundError(
            f"no benchmark profile {name!r} at {path} "
            f"(available: {['dev'] + available_profiles(profiles_dir=base)})"
        )
    with open(path, "rb") as f:
        data = tomllib.load(f)
    # Allow either a flat table or a single [profile] section.
    if "profile" in data and isinstance(data["profile"], dict):
        data = data["profile"]
    return _coerce_profile(name, data)


def available_profiles(*, profiles_dir: str | None = None) -> list[str]:
    """The TOML-backed profile names discoverable in ``profiles/`` (excludes
    the built-in ``dev``)."""
    base = profiles_dir or PROFILES_DIR
    if not os.path.isdir(base):
        return []
    return sorted(
        fn[: -len(".toml")] for fn in os.listdir(base) if fn.endswith(".toml")
    )
