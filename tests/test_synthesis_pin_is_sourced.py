"""The synthesis pin must be read from config, and every invariant guard must exist.

Two drift mechanisms, both found on 2026-09-20, both the same shape: a fact
RESTATED somewhere instead of READ, which then failed to move when the fact
moved.

The operator's CLAUDE-LESS directive (2026-07-06) changed
``tiers.synthesis`` from ``openrouter``/``anthropic/claude-opus-4.7`` to
``zai_reasoning``/``glm-5.2``. Three artifacts followed it: config.yaml, the
invariant TOML ``section-14-4-synthesis-pin.toml``, and the guard test (now
``..._pinned_to_glm_...``). Three did not:

  tools/reachability/probes/dispatch.py:86   hardcoded the Anthropic pair
                                              under a comment claiming it was
                                              "Sourced from ... config.yaml"
  docs/decisions/acv-spr05-dispatch-fidelity.md:1
                                              "the synthesizer Opus pin is
                                              REAL, FIXED"
  docs/decisions/2026-05-31-invariant-registry-reconcile.md:46
                                              names ``..._pinned_to_opus_...``,
                                              a test that does not exist

A reader could take any of those as licence to propose Anthropic-dependent
work, in direct contradiction of a standing operator directive. The probe
would have screamed — except no workflow references that package, so nothing
ran it.

The first test removes the restatement. The second generalises the third
failure: an invariant that names a guard which does not exist is not guarded,
whatever the registry says.
"""

from __future__ import annotations

import tomllib
from pathlib import Path

import yaml

_ROOT = Path(__file__).resolve().parents[1]
_CONFIG = _ROOT / "substrate" / "dispatch" / "config.yaml"
_INVARIANTS = _ROOT / "substrate" / "invariants"


def _synthesis_tier() -> tuple[str, str]:
    cfg = yaml.safe_load(_CONFIG.read_text(encoding="utf-8"))
    tier = cfg["tiers"]["synthesis"]
    return str(tier["provider"]), str(tier["model"])


def test_probe_pin_is_read_from_config_not_restated() -> None:
    from tools.reachability.probes import dispatch

    assert _synthesis_tier() == (dispatch._PINNED_PROVIDER, dispatch._PINNED_MODEL), (
        "the reachability probe's pinned target disagrees with "
        "substrate/dispatch/config.yaml tiers.synthesis. It must be READ from "
        "the config, never restated — a restated constant is how the Anthropic "
        "pin survived the CLAUDE-LESS directive by two months."
    )


def test_no_anthropic_in_the_synthesis_tier() -> None:
    """The standing operator directive, asserted where it is cheap to check."""
    provider, model = _synthesis_tier()
    assert "anthropic" not in provider.lower(), provider
    assert "claude" not in model.lower(), model


def test_every_invariant_guard_names_a_test_that_exists() -> None:
    """An invariant whose guard does not exist is not guarded.

    Only the file and the test function name are checked -- whether the guard
    actually asserts the right thing is the guard's own job. This is the
    lowest bar: the thing the registry points at is real.
    """
    tomls = sorted(_INVARIANTS.glob("*.toml"))
    assert len(tomls) >= 5, f"only {len(tomls)} invariant TOMLs — check is vacuous"
    missing: list[str] = []
    checked = 0
    for path in tomls:
        # The fields live under an [invariant] table, not at top level.
        # Reading them from the root inspected zero guards, which the
        # `checked >= 3` assertion below caught rather than passing silently.
        data = tomllib.loads(path.read_text(encoding="utf-8")).get("invariant", {})
        guard = data.get("guard")
        if not isinstance(guard, str) or data.get("guard_kind") != "pytest":
            continue
        file_part, _, node = guard.partition("::")
        target = _ROOT / file_part
        checked += 1
        if not target.exists():
            missing.append(f"{path.name}: guard file {file_part} does not exist")
            continue
        if node:
            func = node.split("[")[0]
            if f"def {func}" not in target.read_text(encoding="utf-8"):
                missing.append(f"{path.name}: {file_part} has no {func}")
    assert checked >= 3, f"only {checked} pytest guards inspected — check is vacuous"
    assert not missing, "invariants naming a guard that does not exist:\n  " + "\n  ".join(missing)
