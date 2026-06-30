"""Tests for tools/flaky_quarantine.py — the re-run-N flaky-quarantine harness.

These tests RUN the real harness on a controlled fixture suite and assert its
OUTPUT (proposals, detection classes, reproducibility). The harness is never
mocked. Fixture files under tools/tests/fixtures/flaky/ are never edited.
"""

from __future__ import annotations

import hashlib
import subprocess
import sys
from pathlib import Path

_REPO = Path(__file__).resolve().parents[2]
if str(_REPO) not in sys.path:
    sys.path.insert(0, str(_REPO))

from tools import flaky_quarantine as fq  # noqa: E402

_FIXTURE_DIR = Path(__file__).resolve().parent / "fixtures" / "flaky"
_PYTHON = sys.executable
_FIXTURE_PATH = str(_FIXTURE_DIR.relative_to(_REPO))


def _sha256_tree(root: Path) -> str:
    digest = hashlib.sha256()
    for path in sorted(root.rglob("*.py")):
        digest.update(path.read_bytes())
    return digest.hexdigest()


def _run_cli(*args: str) -> subprocess.CompletedProcess[str]:
    return subprocess.run(
        [_PYTHON, "-m", "tools.flaky_quarantine", *args],
        cwd=_REPO,
        capture_output=True,
        text=True,
        check=False,
    )


def _propose_on_fixtures(*extra: str) -> str:
    proc = _run_cli(
        "--n",
        "3",
        "--paths",
        _FIXTURE_PATH,
        "--shuffle-seeds",
        "1,2,3",
        "--propose",
        *extra,
    )
    assert proc.returncode == 0, proc.stdout + proc.stderr
    return proc.stdout


def _parse_proposal_nodeids(toml_text: str) -> set[str]:
    nodeids: set[str] = set()
    for line in toml_text.splitlines():
        line = line.strip()
        if line.startswith('nodeid = "'):
            nodeids.add(line.split('"')[1])
    return nodeids


def _parse_proposal_reasons(toml_text: str) -> dict[str, str]:
    reasons: dict[str, str] = {}
    current: str | None = None
    for line in toml_text.splitlines():
        line = line.strip()
        if line.startswith('nodeid = "'):
            current = line.split('"')[1]
        elif line.startswith('reason = "') and current:
            reasons[current] = line.split('"')[1]
    return reasons


def test_quarantine_toml_has_policy_comment():
    text = (_REPO / "tests" / "quarantine.toml").read_text(encoding="utf-8")
    assert "never deletes" in text.lower() or "never-delete" in text.lower()
    assert "promote_when" in text
    assert "nodeid" in text


def test_load_quarantine_empty_ledger():
    entries = fq.load_quarantine(_REPO / "tests" / "quarantine.toml")
    assert entries == []


def test_detects_rng_flap_fixture():
    proposal = _propose_on_fixtures()
    reasons = _parse_proposal_reasons(proposal)
    rng_hits = [nid for nid in reasons if "rng_flap" in nid]
    assert rng_hits, proposal
    assert reasons[rng_hits[0]] == "rng-flap"


def test_detects_order_dependent_fixture():
    proposal = _propose_on_fixtures()
    reasons = _parse_proposal_reasons(proposal)
    order_hits = [nid for nid in reasons if "order_" in nid]
    assert order_hits, proposal
    assert reasons[order_hits[0]] == "order-dependent"


def test_spares_stable_fixture():
    proposal = _propose_on_fixtures()
    nodeids = _parse_proposal_nodeids(proposal)
    assert "test_always_stable" not in " ".join(nodeids)


def test_proposals_reproducible_with_same_seeds():
    first = _propose_on_fixtures()
    second = _propose_on_fixtures()
    assert first == second


def test_never_delete_proof_fixture_tree_unchanged():
    before = _sha256_tree(_FIXTURE_DIR)
    _propose_on_fixtures()
    after = _sha256_tree(_FIXTURE_DIR)
    assert before == after


def _write_temp_quarantine(tmp_path: Path, entries: list[dict]) -> Path:
    lines = ["# temp quarantine for plugin test\n"]
    for e in entries:
        lines.extend(
            [
                "[[quarantine]]",
                f'nodeid = "{e["nodeid"]}"',
                f'reason = "{e["reason"]}"',
                f'evidence = "{e["evidence"]}"',
                f'quarantined_at = "{e["quarantined_at"]}"',
                f'quarantined_by = "{e["quarantined_by"]}"',
                f'promote_when = "{e["promote_when"]}"',
                f"ignore_failures = {'true' if e.get('ignore_failures', True) else 'false'}",
                "",
            ]
        )
    path = tmp_path / "quarantine.toml"
    path.write_text("\n".join(lines), encoding="utf-8")
    return path


def _run_pytest_with_plugin(
    node_selector: str,
    quarantine_toml: Path,
) -> subprocess.CompletedProcess[str]:
    return subprocess.run(
        [
            _PYTHON,
            "-m",
            "pytest",
            "-q",
            "-p",
            "no:xdist",
            "-p",
            "tools.pytest_quarantine_plugin",
            "--override-ini",
            f"quarantine_toml={quarantine_toml}",
            node_selector,
        ],
        cwd=_REPO,
        capture_output=True,
        text=True,
        check=False,
    )


def test_quarantined_flap_runs_without_failing_gate(tmp_path: Path):
    toml = _write_temp_quarantine(
        tmp_path,
        [
            {
                "nodeid": f"{_FIXTURE_PATH}/test_rng_flap.py::test_rng_flap",
                "reason": "rng-flap",
                "evidence": "fixture",
                "quarantined_at": "2026-06-30",
                "quarantined_by": "test",
                "promote_when": "passes 3 consecutive shuffled runs",
                "ignore_failures": True,
            }
        ],
    )
    proc = _run_pytest_with_plugin(f"{_FIXTURE_PATH}/test_rng_flap.py::test_rng_flap", toml)
    combined = proc.stdout + proc.stderr
    assert "test_rng_flap" in combined
    assert proc.returncode == 0, combined


def test_quarantined_always_failing_still_surfaces(tmp_path: Path):
    toml = _write_temp_quarantine(
        tmp_path,
        [
            {
                "nodeid": f"{_FIXTURE_PATH}/test_always_fails.py::test_always_fails",
                "reason": "unknown-flap",
                "evidence": "fixture",
                "quarantined_at": "2026-06-30",
                "quarantined_by": "test",
                "promote_when": "passes 3 consecutive shuffled runs",
                "ignore_failures": False,
            }
        ],
    )
    proc = _run_pytest_with_plugin(
        f"{_FIXTURE_PATH}/test_always_fails.py::test_always_fails",
        toml,
    )
    combined = proc.stdout + proc.stderr
    assert "test_always_fails" in combined
    assert proc.returncode != 0, combined


def _collection_count(summary_line: str) -> int:
    token = summary_line.strip().split()[0]
    return int(token)


def test_default_run_collection_count_unchanged_without_plugin():
    """Plugin is opt-in: importing it must not register hooks on default pytest runs."""
    target = _FIXTURE_PATH
    without = subprocess.run(
        [_PYTHON, "-m", "pytest", "--collect-only", "-q", target],
        cwd=_REPO,
        capture_output=True,
        text=True,
        check=False,
    )
    assert without.returncode == 0, without.stderr
    count_without = _collection_count(without.stdout.strip().splitlines()[-1])
    import tools.pytest_quarantine_plugin  # noqa: F401

    after = subprocess.run(
        [_PYTHON, "-m", "pytest", "--collect-only", "-q", target],
        cwd=_REPO,
        capture_output=True,
        text=True,
        check=False,
    )
    count_after = _collection_count(after.stdout.strip().splitlines()[-1])
    assert count_without == count_after


def test_cli_help():
    proc = _run_cli("--help")
    assert proc.returncode == 0
    assert "--propose" in proc.stdout
    assert "--check" in proc.stdout
    assert "--shuffle-seeds" in proc.stdout


def test_detect_flappers_unit_on_fixtures():
    findings = fq.detect_flappers(
        [_FIXTURE_PATH],
        n=3,
        seeds=[1, 2, 3],
        repo=_REPO,
        timeout_s=120,
        spr03={},
    )
    nodeids = {f.nodeid for f in findings}
    assert any("rng_flap" in n for n in nodeids)
    assert any("order_" in n for n in nodeids)
    assert all("always_stable" not in n for n in nodeids)