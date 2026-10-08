"""Only ONE §9.3 implementation may be reachable from production code.

Two modules implement master-spec §9.3 options A/B/C with different maths:

* `substrate/ad_inventory/attribution.py` — `compute_attribution_option_*`.
  Live. Reached from `POST /attribution/compute`, `contracts/accrual.py`,
  `speak/contributor.py`, `marketplace_metrics/publisher_escrow.py`.
* `substrate/attribution/algorithms.py` — `attribution_option_*`. Provenance
  lineage; called by nothing outside `tests/`.

They disagree on the default confidence for a missing value (0.5 vs 0.4), on the
confidence domain (raw float vs a 4-value string scale mapped through
`CONFIDENCE_WEIGHTS`), and on tier clamping. The names differ only by a
`compute_` prefix, so importing the wrong one is a plausible slip that would
silently reprice payouts rather than fail.

This does not forbid the second implementation — it is covered by
`tests/test_attribution.py` and documented in `substrate/attribution/README.md`.
It forbids production code reaching it, so the payout path stays single.
"""
import ast
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
NON_PAYOUT_NAMES = {"attribution_option_a", "attribution_option_b", "attribution_option_c"}
#: The package may re-export its own functions; only callers outside it matter.
EXEMPT_PREFIXES = ("tests/", "benchmarks/", "substrate/attribution/")


def _tracked_python_files() -> list[Path]:
    """Every production .py file under the repo root.

    Exclusions are computed from the path RELATIVE to the root. An absolute-path
    check (``".claude" not in path.parts``) silently matched every file when the
    checkout itself lived under ``~/.claude/jobs/``, and the gate then scanned
    nothing while still passing — which is why
    ``test_the_gate_scans_a_non_empty_file_set`` exists.
    """
    files: list[Path] = []
    for path in sorted(ROOT.rglob("*.py")):
        rel = path.relative_to(ROOT)
        if any(part.startswith(".") for part in rel.parts):
            continue                      # .venv, .git, any dot-directory
        if "node_modules" in rel.parts:
            continue
        if any(rel.as_posix().startswith(prefix) for prefix in EXEMPT_PREFIXES):
            continue
        files.append(path)
    return files


def _label(path: Path) -> str:
    """Repo-relative where possible; absolute for files outside it (the control)."""
    try:
        return path.relative_to(ROOT).as_posix()
    except ValueError:
        return path.as_posix()


def _non_payout_importers(files: list[Path]) -> list[str]:
    offenders: list[str] = []
    for path in files:
        try:
            tree = ast.parse(path.read_text(), filename=str(path))
        except (SyntaxError, UnicodeDecodeError):
            continue
        for node in ast.walk(tree):
            if isinstance(node, ast.ImportFrom):
                module = node.module or ""
                if module == "substrate.attribution" or module.startswith("substrate.attribution."):
                    hit = NON_PAYOUT_NAMES.intersection({alias.name for alias in node.names})
                    if hit:
                        offenders.append(f"{_label(path)}:{node.lineno} imports {sorted(hit)}")
            elif isinstance(node, ast.Attribute) and node.attr in NON_PAYOUT_NAMES:
                offenders.append(f"{_label(path)}:{node.lineno} references {node.attr}")
    return sorted(offenders)


def test_production_code_never_reaches_the_non_payout_implementation():
    assert _non_payout_importers(_tracked_python_files()) == []


def test_the_gate_can_actually_see_an_offender(tmp_path):
    """A gate that scans nothing passes forever. Prove it fires."""
    offender = tmp_path / "some_service.py"
    offender.write_text("from substrate.attribution import attribution_option_b\n")
    found = _non_payout_importers([offender])
    assert len(found) == 1 and "attribution_option_b" in found[0]


def test_the_gate_scans_a_non_empty_file_set():
    """Guards against an exemption pattern silently swallowing the whole tree."""
    files = _tracked_python_files()
    assert len(files) > 100, f"only {len(files)} files scanned — exemptions too broad"
    assert any("ad_inventory" in path.as_posix() for path in files)


def test_the_live_payout_names_are_the_prefixed_ones():
    """Pins the naming asymmetry this gate exists to protect."""
    from substrate.ad_inventory import compute_attribution_option_b
    from substrate.attribution import attribution_option_b

    assert compute_attribution_option_b is not attribution_option_b
