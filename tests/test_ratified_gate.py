"""ACV SPR-06 — self-test for the ratified-scoring gate (M3 non-vacuity).

Proves the gate's exit semantics are REAL, not vacuous (a gate that can only
ever exit 0 is the false-confidence disease this whole sprint guards against):

  * a SCORED (mock_run=false) artifact WITHOUT parameters_ratified → BLOCKED (1)
  * a SCORED artifact ratified but WITHOUT a ratification_ref → BLOCKED (1)
  * a SCORED artifact ratified WITH a ratification_ref → OK (0)
  * a MOCK (mock_run=true) artifact → OK (0), exempt
  * a malformed mock_run field → BLOCKED (1), fail-closed
  * a non-artifact JSON (no mock_run key) → skipped, OK (0)

It also asserts the CI step is BLOCKING (the workflow runs the gate as a bare
command with no `|| echo` / `continue-on-error` swallow) so a real failure reds
the build.
"""

from __future__ import annotations

import json
import subprocess
import sys
from pathlib import Path

import pytest

from tools.ratified_gate import _is_real_frozen_sha, evaluate_artifact, main, scan

_GATE = Path(__file__).resolve().parent.parent / "tools" / "ratified_gate.py"

# A real content-addressed frozen sha (sha256:<64 hex>) — the shape
# question_set.compute_frozen_sha emits. Scored fixtures must carry one (§A.6).
_REAL_SHA = "sha256:" + "a1b2c3d4" * 8  # 64 hex chars


def _scored(**over) -> dict:
    """A minimal SCORED (mock_run=false) artifact that PASSES the gate: ratified,
    referenced, and pinned to a real frozen_sha. Tests override one field to probe
    a single failure mode."""
    body = {
        "mock_run": False,
        "parameters_ratified": True,
        "ratification_ref": "pilot:deadbeef",
        "frozen_sha": _REAL_SHA,
    }
    body.update(over)
    return body


def _write(tmp_path: Path, name: str, body: dict) -> Path:
    p = tmp_path / name
    p.write_text(json.dumps(body), encoding="utf-8")
    return p


# ── the pure predicate (evaluate_artifact) ────────────────────────────────────


def test_scored_unratified_blocked():
    ok, reason = evaluate_artifact({"mock_run": False, "parameters_ratified": False})
    assert ok is False
    assert "parameters_ratified" in reason


def test_scored_ratified_without_ref_blocked():
    ok, reason = evaluate_artifact(
        {"mock_run": False, "parameters_ratified": True, "ratification_ref": ""}
    )
    assert ok is False
    assert "ratification_ref" in reason


def test_scored_ratified_with_ref_ok():
    ok, _ = evaluate_artifact(_scored(ratification_ref="pilot:abc123"))
    assert ok is True


def test_scored_missing_frozen_sha_blocked():
    """MINOR-2 (§A.6): a scored artifact ratified + referenced but with NO real
    frozen_sha is BLOCKED — the verdict must be pinned to the immutable set."""
    ok, reason = evaluate_artifact(_scored(frozen_sha=None))
    assert ok is False
    assert "frozen_sha" in reason


def test_scored_placeholder_frozen_sha_blocked():
    """A placeholder/sentinel frozen_sha (not the real content-addressed sha) is
    BLOCKED even when ratified + referenced."""
    for bad in ["", "PENDING", "sha256:" + "0" * 64, "deadbeef", "sha256:tooShort"]:
        ok, reason = evaluate_artifact(_scored(frozen_sha=bad))
        assert ok is False, f"placeholder frozen_sha {bad!r} must block"
        assert "frozen_sha" in reason


def test_real_frozen_sha_predicate():
    """The frozen_sha predicate accepts the real shape and rejects placeholders."""
    assert _is_real_frozen_sha(_REAL_SHA)
    assert not _is_real_frozen_sha(None)
    assert not _is_real_frozen_sha("")
    assert not _is_real_frozen_sha("PENDING_COMMIT")
    assert not _is_real_frozen_sha("sha256:" + "0" * 64)  # all-zero sentinel
    assert not _is_real_frozen_sha("sha256:" + "g" * 64)  # non-hex
    assert not _is_real_frozen_sha("a1b2" * 16)  # missing sha256: prefix


def test_mock_run_exempt():
    ok, reason = evaluate_artifact({"mock_run": True, "parameters_ratified": False})
    assert ok is True
    assert "exempt" in reason


def test_malformed_mock_run_fails_closed():
    ok, _ = evaluate_artifact({"mock_run": "false"})  # string, not bool
    assert ok is False


# ── the scanner over real files ───────────────────────────────────────────────


def test_scan_blocks_scored_unratified_fixture(tmp_path):
    _write(tmp_path, "prod-bad.json", {"mock_run": False, "parameters_ratified": False})
    scored, mock_exempt, skipped, failures = scan([tmp_path / "prod-bad.json"])
    assert scored == 1
    assert failures, "a scored-unratified artifact MUST produce a failure"


def test_scan_passes_scored_ratified_fixture(tmp_path):
    _write(tmp_path, "prod-good.json", _scored())
    scored, mock_exempt, skipped, failures = scan([tmp_path / "prod-good.json"])
    assert scored == 1
    assert not failures


def test_scan_passes_mock_fixture(tmp_path):
    _write(tmp_path, "dev.json", {"mock_run": True, "parameters_ratified": False})
    scored, mock_exempt, skipped, failures = scan([tmp_path / "dev.json"])
    assert scored == 0
    assert not failures


def test_scan_skips_non_artifact(tmp_path):
    _write(tmp_path, "other.json", {"some": "unrelated", "shape": 1})
    scored, mock_exempt, skipped, failures = scan([tmp_path / "other.json"])
    assert skipped == 1
    assert not failures


# ── the CLI exit codes (end-to-end, the contract CI relies on) ────────────────


def test_cli_exits_1_on_scored_unratified(tmp_path):
    bad = _write(tmp_path, "prod-bad.json", {"mock_run": False, "parameters_ratified": False})
    assert main([str(bad)]) == 1


def test_cli_exits_0_on_scored_ratified(tmp_path):
    good = _write(tmp_path, "prod-good.json", _scored(ratification_ref="pilot:1"))
    assert main([str(good)]) == 0


def test_cli_exits_0_on_mock(tmp_path):
    mock = _write(tmp_path, "dev.json", {"mock_run": True})
    assert main([str(mock)]) == 0


def test_cli_subprocess_exit_code(tmp_path):
    """Run the gate as a real subprocess (the exact CI invocation shape) and
    assert the process exit code is 1 on a scored-unratified fixture."""
    bad = _write(tmp_path, "prod-bad.json", {"mock_run": False, "parameters_ratified": False})
    proc = subprocess.run(
        [sys.executable, str(_GATE), str(bad)],
        capture_output=True,
        text=True,
    )
    assert proc.returncode == 1, proc.stdout + proc.stderr
    assert "BLOCKED" in proc.stdout


# ── the gate is BLOCKING in CI (no swallow) ───────────────────────────────────


def test_ci_step_is_blocking():
    """The CI workflow must run the gate as a BARE command — no `|| echo`,
    `continue-on-error`, or `::warning::`-only — so its exit code reds the build.
    Mirrors how the reachability/keystone gates assert their own blocking-ness."""
    ci = Path(__file__).resolve().parent.parent / ".github" / "workflows" / "ci.yml"
    text = ci.read_text(encoding="utf-8")
    assert "ratified_gate.py" in text, "the ratified-scoring gate must be wired into CI"
    # Find the line invoking the gate and assert it is not swallowed.
    invoking = [ln for ln in text.splitlines() if "ratified_gate.py" in ln and "python" in ln]
    assert invoking, "the CI must invoke the gate via python"
    for ln in invoking:
        assert "|| echo" not in ln and "|| true" not in ln, f"gate must not be swallowed: {ln}"
    # The step must not be marked continue-on-error. Inspect the gate's STEP block
    # (from its `- name:` to the next `- name:`) and reject only a real YAML
    # `continue-on-error:` KEY (a non-comment line), not the phrase appearing in a
    # comment that documents the no-swallow policy.
    lines = text.splitlines()
    run_idx = next(i for i, ln in enumerate(lines) if "ratified_gate.py" in ln and "python" in ln)
    # Walk back to this step's `- name:`.
    start = next(i for i in range(run_idx, -1, -1) if lines[i].lstrip().startswith("- name:"))
    # Walk forward to the next step boundary.
    end = next(
        (i for i in range(run_idx + 1, len(lines)) if lines[i].lstrip().startswith("- name:")),
        len(lines),
    )
    for ln in lines[start:end]:
        stripped = ln.strip()
        if stripped.startswith("#"):
            continue  # a comment documenting the policy is fine
        assert not stripped.startswith("continue-on-error"), (
            f"the ratified gate step must block (no continue-on-error): {ln}"
        )


def test_committed_artifact_passes_gate():
    """The committed spr09_run.json (a mock run) passes the gate — sanity that the
    repo's own artifact is gate-clean."""
    art = Path(__file__).resolve().parent.parent / "compounding" / "benchmark" / "results" / "spr09_run.json"
    if not art.exists():
        pytest.skip("committed artifact not present")
    data = json.loads(art.read_text(encoding="utf-8"))
    ok, reason = evaluate_artifact(data)
    assert ok, reason
