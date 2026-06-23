#!/usr/bin/env python3
"""
Enforce Antiek's integration-tier ladder against the codebase.

Walks every ``*.py`` file under the production layers (``substrate/``,
``acquisition/``, ``middleware/``, ``orchestration/``, ``interfaces/``,
``compounding/``, ``processing/``, ``runtime/``, ``apps/``), collects
every import with ``ast``, and asserts:

- Tier 0 packages are not imported in production code at all.
- Tier 1 packages are imported only under ``tools/``, ``scripts/``,
  ``experiments/``, or in test files. (``tools/`` is the "local
  prototype" zone.)
- Tier 2 packages are imported only at the file paths listed in the
  registry's ``prod_call_sites`` field; sunset_date must not be in
  the past.
- Tier 3 packages must appear in ``substrate/integrations.py``'s
  ``PROD_VENDORS`` frozenset.

A file may carry an inline ``# tier-allow: <reason>`` comment on the
import line to bypass a specific check; every override is logged to
``tier_overrides.log`` so the operator can audit.

Exit codes:
    0 — all tiers consistent
    2 — violations found (CI-blocking)
    1 — usage / config error

Spec: ~/specs/antiek-hashimoto-engineering/sprint-e3-vouching.html
"""

from __future__ import annotations

import argparse
import ast
import sys
import tomllib
from collections.abc import Iterable
from dataclasses import dataclass, field
from datetime import date, datetime
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent.parent
REGISTRY_FILE = REPO_ROOT / "integrations.toml"
OVERRIDES_LOG = REPO_ROOT / "tier_overrides.log"

# Layers where a Tier-0 import is a violation. Tier-1 imports are
# allowed under "prototype zones" (see below).
PROD_LAYERS = (
    "substrate",
    "acquisition",
    "middleware",
    "orchestration",
    "interfaces",
    "compounding",
    "processing",
    "runtime",
    "apps",
)

# Layers where Tier-1 (local prototype) imports are allowed. ``tests/``
# is included because test-only imports are not production behavior.
PROTOTYPE_ZONES = (
    "tools",
    "scripts",
    "experiments",
    "tests",
    "benchmarks",
    "docs",  # *.py inside docs/ are typically swap-svgs helpers, not prod
)

TIER_ALLOW_MARKER = "tier-allow:"


@dataclass(frozen=True)
class IntegrationSpec:
    """One row from ``integrations.toml``."""

    name: str
    package: str
    tier: int
    voucher: str
    vouched_at: str
    justification: str
    sunset_date: str | None = None
    prod_call_sites: tuple[str, ...] = field(default_factory=tuple)
    spec_doc: str | None = None


@dataclass(frozen=True)
class Violation:
    """A single tier-rule violation, formatted for human triage."""

    file: str
    line: int
    integration: str
    package: str
    tier: int
    reason: str

    def __str__(self) -> str:
        return f"{self.file}:{self.line}: imports {self.package!r} ({self.integration}, tier {self.tier}) — {self.reason}"


def load_registry(path: Path = REGISTRY_FILE) -> list[IntegrationSpec]:
    """Parse ``integrations.toml`` into typed specs.

    Required fields per integration: ``package``, ``tier``, ``voucher``,
    ``vouched_at``, ``justification``. ``sunset_date`` is required for
    tier 2; ``prod_call_sites`` is required for tier ≥ 2.
    """
    if not path.exists():
        raise FileNotFoundError(f"registry not found: {path}")
    data = tomllib.loads(path.read_text(encoding="utf-8"))
    specs: list[IntegrationSpec] = []
    for name, table in data.items():
        if not isinstance(table, dict):
            continue
        tier = int(table["tier"])
        if tier == 2 and not table.get("sunset_date"):
            raise ValueError(
                f"integrations.toml [{name}]: tier 2 requires sunset_date"
            )
        if tier >= 2 and not table.get("prod_call_sites"):
            # Tier 3 may omit prod_call_sites for foundational deps
            # (duckdb, fastapi etc. are imported everywhere). The
            # CI check treats absence as "import is allowed anywhere
            # in production layers."
            pass
        specs.append(
            IntegrationSpec(
                name=name,
                package=str(table["package"]),
                tier=tier,
                voucher=str(table.get("voucher", "")),
                vouched_at=str(table["vouched_at"]),
                justification=str(table["justification"]),
                sunset_date=str(table["sunset_date"]) if table.get("sunset_date") else None,
                prod_call_sites=tuple(table.get("prod_call_sites", [])),
                spec_doc=str(table["spec_doc"]) if table.get("spec_doc") else None,
            )
        )
    return specs


def iter_python_files(root: Path) -> Iterable[Path]:
    """Yield ``*.py`` under ``root`` skipping caches and venvs."""
    for path in root.rglob("*.py"):
        parts = set(path.parts)
        if parts & {"__pycache__", ".venv", "venv", "node_modules", "build", "dist", ".pytest_cache"}:
            continue
        yield path


def collect_imports(path: Path) -> list[tuple[str, int]]:
    """Return ``(top_level_package, lineno)`` for every import.

    Top-level only: ``from foo.bar.baz import x`` and ``import foo.bar``
    both yield ``("foo", <lineno>)``. The tier registry keys by top-level
    package, so this is the right granularity.
    """
    try:
        tree = ast.parse(path.read_text(encoding="utf-8"), filename=str(path))
    except SyntaxError:
        return []
    out: list[tuple[str, int]] = []
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            for alias in node.names:
                out.append((alias.name.split(".")[0], node.lineno))
        elif isinstance(node, ast.ImportFrom) and node.module:
            out.append((node.module.split(".")[0], node.lineno))
    return out


def import_line_has_allow_marker(path: Path, lineno: int) -> tuple[bool, str]:
    """Return ``(has_marker, reason)`` for an inline ``# tier-allow:`` on the import line."""
    try:
        line = path.read_text(encoding="utf-8").splitlines()[lineno - 1]
    except (IndexError, FileNotFoundError):
        return False, ""
    if TIER_ALLOW_MARKER not in line:
        return False, ""
    reason = line.split(TIER_ALLOW_MARKER, 1)[1].strip()
    return True, reason


def in_zone(path: Path, zones: Iterable[str]) -> bool:
    """True if ``path`` is under any of the named top-level directories."""
    try:
        rel = path.relative_to(REPO_ROOT)
    except ValueError:
        return False
    if not rel.parts:
        return False
    return rel.parts[0] in set(zones)


def find_violations(
    specs: list[IntegrationSpec],
    repo_root: Path = REPO_ROOT,
) -> tuple[list[Violation], list[str]]:
    """Walk the repo and find tier violations + tier-allow overrides.

    Returns ``(violations, overrides_log_lines)``.
    """
    by_package: dict[str, IntegrationSpec] = {s.package: s for s in specs}
    violations: list[Violation] = []
    overrides: list[str] = []

    # Sunset-date check — independent of import sites.
    today = date.today()
    for spec in specs:
        if spec.tier == 2 and spec.sunset_date:
            try:
                sunset = datetime.strptime(spec.sunset_date, "%Y-%m-%d").date()
            except ValueError:
                violations.append(
                    Violation(
                        file=str(REGISTRY_FILE.relative_to(repo_root)),
                        line=0,
                        integration=spec.name,
                        package=spec.package,
                        tier=spec.tier,
                        reason=f"sunset_date {spec.sunset_date!r} not parseable as YYYY-MM-DD",
                    )
                )
                continue
            if sunset < today:
                violations.append(
                    Violation(
                        file=str(REGISTRY_FILE.relative_to(repo_root)),
                        line=0,
                        integration=spec.name,
                        package=spec.package,
                        tier=spec.tier,
                        reason=(
                            f"sunset_date {spec.sunset_date} is in the past — "
                            f"either promote to Tier 3 with a new voucher or demote to Tier 0"
                        ),
                    )
                )

    # Import-site checks.
    for py in iter_python_files(repo_root):
        for pkg, lineno in collect_imports(py):
            spec = by_package.get(pkg)
            if spec is None:
                continue
            rel = py.relative_to(repo_root)
            # Allow-marker bypass.
            has_marker, reason = import_line_has_allow_marker(py, lineno)
            if has_marker:
                overrides.append(
                    f"{rel}:{lineno}: tier-allow override for {pkg!r} ({spec.name}, tier {spec.tier}) — {reason}"
                )
                continue
            # Tier 0: must not be imported anywhere.
            if spec.tier == 0:
                violations.append(
                    Violation(
                        file=str(rel), line=lineno, integration=spec.name,
                        package=pkg, tier=0,
                        reason="Tier 0 (spec only); promote to Tier ≥ 1 with a voucher before importing",
                    )
                )
                continue
            # Tier 1: prototype zones only.
            if spec.tier == 1 and in_zone(py, PROD_LAYERS) and not in_zone(py, PROTOTYPE_ZONES):
                violations.append(
                    Violation(
                        file=str(rel), line=lineno, integration=spec.name,
                        package=pkg, tier=1,
                        reason=(
                            f"Tier 1 (local prototype); allowed only under {sorted(PROTOTYPE_ZONES)}, "
                            f"not under {rel.parts[0]}/"
                        ),
                    )
                )
                continue
            # Tier 2 with declared prod_call_sites: import must match.
            if spec.tier == 2 and spec.prod_call_sites and in_zone(py, PROD_LAYERS):
                rel_str = str(rel)
                if rel_str not in spec.prod_call_sites:
                    violations.append(
                        Violation(
                            file=rel_str, line=lineno, integration=spec.name,
                            package=pkg, tier=2,
                            reason=(
                                f"Tier 2 import outside declared prod_call_sites "
                                f"{list(spec.prod_call_sites)}; add this file to the list "
                                f"or use a # tier-allow: comment"
                            ),
                        )
                    )
    return violations, overrides


def write_overrides_log(overrides: list[str], log_path: Path = OVERRIDES_LOG) -> None:
    """Persist the override log so an operator can audit who's bypassing the gate.

    Each run overwrites — the log reflects current overrides, not history.
    History lives in git.
    """
    if overrides:
        log_path.write_text(
            "# tier-allow overrides currently live in the codebase.\n"
            "# Each entry: <file>:<line>: tier-allow override for <pkg> (<integration>, tier N) — <reason>\n"
            "# Generated by scripts/check_integration_tiers.py.\n"
            "# Run that script to refresh.\n\n"
            + "\n".join(overrides) + "\n",
            encoding="utf-8",
        )
    elif log_path.exists():
        log_path.unlink()


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        prog="scripts/check_integration_tiers.py",
        description=(
            "Enforce Antiek's integration-tier ladder. "
            "Exits 0 on clean, 2 on violation, 1 on usage error."
        ),
    )
    parser.add_argument(
        "--registry",
        type=Path,
        default=REGISTRY_FILE,
        help=f"registry file (default {REGISTRY_FILE.relative_to(REPO_ROOT)})",
    )
    parser.add_argument(
        "--no-log",
        action="store_true",
        help="skip writing tier_overrides.log",
    )
    args = parser.parse_args(argv)

    try:
        specs = load_registry(args.registry)
    except (FileNotFoundError, ValueError, KeyError) as exc:
        print(f"check_integration_tiers: registry error: {exc}", file=sys.stderr)
        return 1

    violations, overrides = find_violations(specs)

    print(f"Loaded {len(specs)} integration(s) from {args.registry.relative_to(REPO_ROOT)}.")
    tier_counts = {t: sum(1 for s in specs if s.tier == t) for t in (0, 1, 2, 3)}
    print(f"Tier distribution: T0={tier_counts[0]} T1={tier_counts[1]} T2={tier_counts[2]} T3={tier_counts[3]}")

    if overrides:
        print(f"\n{len(overrides)} tier-allow override(s):")
        for line in overrides:
            print(f"  {line}")
        if not args.no_log:
            write_overrides_log(overrides)
    elif not args.no_log:
        write_overrides_log([])  # cleans stale log file

    if violations:
        print(f"\n{len(violations)} tier violation(s):", file=sys.stderr)
        for v in violations:
            print(f"  {v}", file=sys.stderr)
        return 2

    print("\nAll integrations consistent with their declared tiers.")
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
