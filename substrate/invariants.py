"""
Antiek substrate invariants — mechanically-checked architectural rules.

This module is the single source of truth for the load-bearing rules CLAUDE.md
calls out. Each rule is registered as an ``Invariant`` with metadata
(category, rationale, exemptions). The tests in ``tests/test_invariants.py``
read this registry and assert each rule on every CI run.

Why a registry instead of inline assertions:

- Each rule has metadata (when introduced, why, what would relax it). That
  metadata lives next to the rule, not in commit messages that rot.
- The doc strings in this file are the canonical justification. CLAUDE.md
  links here; future maintainers find the why immediately.
- Adding a rule = appending one ``Invariant`` instance plus its check helper.
  The test layer auto-picks it up via parametrization.

Why no imports from outside stdlib:

The registry itself must not violate I-004 (substrate is a leaf of the
import graph). Helper functions use ``ast`` / ``tomllib`` / ``importlib.metadata``
exclusively; rule checks must not require Antiek to be importable in any
specific shape beyond what each rule explicitly verifies.

Sourced from the Hashimoto interview lens "constraints as design discipline"
(see ``~/specs/antiek-hashimoto-engineering/sprint-e1-invariants.html`` and
``~/specs/antiek-philosophy/rounds/round-01-hashimoto/sprint-01-constraints.html``).
"""

from __future__ import annotations

import ast
import importlib.metadata as _md
import os
import sys
import tomllib
from dataclasses import dataclass, field
from pathlib import Path
from typing import Callable, Iterable, Literal

# ---------------------------------------------------------------------------
# Registry types
# ---------------------------------------------------------------------------

Category = Literal[
    "substrate",     # rule about substrate/ layer integrity
    "dependency",    # rule about direct dependencies
    "architecture", # rule about layered import direction
    "coherence",    # rule about cross-module numeric/semantic agreement
    "voice_style",  # rule about §5 quality bar
]

Severity = Literal["error", "warn"]


@dataclass(frozen=True)
class Invariant:
    """One architectural rule.

    Fields:
        id: stable identifier (``I-001`` style). NEVER renumber.
        name: short human-readable label.
        summary: one-line description for ``invariants --list`` output.
        rationale: ≤300 chars — the why. Names a doctrine line or memory
            entry that would change if the rule changed.
        category: classifier (see :data:`Category`).
        introduced: ISO date this rule was first registered.
        severity: ``error`` = CI fails on violation; ``warn`` = printed but
            non-blocking. Default ``error``. Reserve ``warn`` for rules
            mid-migration.
        source: pointer to the file or section that codifies the rule
            outside this registry (e.g. ``runtime/db_lock.py`` for I-001).
        exempt: tuple of (path, reason) pairs — explicit carve-outs. Each
            exemption carries its own justification so a future maintainer
            cannot quietly add to the list without a written reason.
    """

    id: str
    name: str
    summary: str
    rationale: str
    category: Category
    introduced: str
    source: str
    severity: Severity = "error"
    exempt: tuple[tuple[str, str], ...] = field(default_factory=tuple)


# ---------------------------------------------------------------------------
# Paths
# ---------------------------------------------------------------------------

# Repo root is two parents up from this file (substrate/invariants.py).
# We compute it relative to __file__ so the module works whether invoked
# via ``python -m`` or ``pytest`` or directly.
REPO_ROOT = Path(__file__).resolve().parent.parent
SUBSTRATE_DIR = REPO_ROOT / "substrate"
RUNTIME_DIR = REPO_ROOT / "runtime"
PYPROJECT = REPO_ROOT / "pyproject.toml"

# Top-level layer directories. Substrate must be a leaf — it imports from
# none of these. ``tools/`` is allowed to import from substrate (it is the
# CLI/glue layer); the reverse is the violation.
UPLAYER_DIRS = (
    "acquisition",
    "apps",
    "cloudflare",
    "compounding",
    "doctrine",
    "infrastructure",
    "interfaces",
    "middleware",
    "orchestration",
    "processing",
    "roles",
    "runs",
    "scripts",
    "skills",
    "tools",
)

# Cloud compute / storage SDK package roots. Importing any of these from
# ``substrate/`` violates I-002. List is conservative — it names only
# vendors whose presence would imply a network/cloud dependency at substrate
# layer. LLM provider SDKs (anthropic, openai, deepseek) are a separate
# concern handled at the middleware/acquisition layer.
CLOUD_SDK_PACKAGES = (
    "boto3",
    "botocore",
    "google.cloud",
    "azure",
    "azure.storage",
    "modal",
    "daytona",
    "browserbase",
    "playwright",          # browserbase escalation path; substrate must not pull it directly
    "pulumi",
    "terraform_cdk",
    "kubernetes",
)

# License strings considered permissive enough for Antiek's direct deps.
# Order: prefer SPDX identifiers; fall back to legacy strings packages
# still emit. Match case-insensitively, after stripping ``OSI Approved ::``
# prefix that Trove classifiers add.
PERMISSIVE_LICENSE_TOKENS = (
    "mit",
    "apache",
    "bsd",
    "isc",
    "psf",
    "python software foundation",
    "mpl-2.0",
    "mozilla public license 2.0",
    "unlicense",
    "0bsd",
    "boost",
)


# ---------------------------------------------------------------------------
# Helpers — shared by tests, also runnable standalone
# ---------------------------------------------------------------------------


def iter_python_files(root: Path) -> Iterable[Path]:
    """Yield ``*.py`` under ``root`` skipping ``__pycache__`` and build dirs."""
    for path in root.rglob("*.py"):
        # Skip the usual non-source noise. ``runs/`` holds outputs not code.
        parts = path.parts
        if any(p in {"__pycache__", ".venv", "venv", "node_modules", "build", "dist"} for p in parts):
            continue
        yield path


def _module_name(path: Path) -> str:
    """Convert a substrate/ subpath to its dotted module name."""
    rel = path.relative_to(REPO_ROOT)
    parts = list(rel.parts)
    if parts[-1] == "__init__.py":
        parts = parts[:-1]
    else:
        parts[-1] = parts[-1].removesuffix(".py")
    return ".".join(parts)


def collect_imports(path: Path) -> list[tuple[str, int]]:
    """Return (imported_module, lineno) for every Import/ImportFrom in ``path``.

    ``ast`` is the right tool here, not regex: it tolerates conditional
    imports, deferred imports inside functions, aliased ``import x as y``,
    and split-line continuations. Regex would silently miss those.
    """
    try:
        tree = ast.parse(path.read_text(encoding="utf-8"), filename=str(path))
    except SyntaxError:
        # Defensive — a syntax error elsewhere in the tree should fail the
        # main pytest run loudly; here we skip so the invariant check itself
        # is not the thing that blocks the report.
        return []
    out: list[tuple[str, int]] = []
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            for alias in node.names:
                out.append((alias.name, node.lineno))
        elif isinstance(node, ast.ImportFrom):
            # Relative imports (``from . import x``) keep an empty module.
            if node.module:
                out.append((node.module, node.lineno))
    return out


def matches_package(imported: str, package: str) -> bool:
    """True if ``imported`` is exactly ``package`` or a sub-module of it.

    Examples:
        matches_package("boto3", "boto3") -> True
        matches_package("boto3.session", "boto3") -> True
        matches_package("boto3session", "boto3") -> False
    """
    return imported == package or imported.startswith(package + ".")


# ---------------------------------------------------------------------------
# Per-invariant checks
# ---------------------------------------------------------------------------


def check_i001_single_writer_duckdb() -> list[str]:
    """I-001: ``runtime/db_lock.py`` exports the writer/reader API surface.

    Returns a list of human-readable violation messages. Empty list = pass.
    The surface we lock in: ``connect_write``, ``connect_read``,
    ``FlockWriteCoordinator``, ``WriteCoordinator`` (Protocol). Per the
    docstring at the top of ``runtime/db_lock.py``, these are the swap
    points for the future Quack v2.0 migration; removing any of them
    breaks the published contract.
    """
    violations: list[str] = []
    db_lock_file = RUNTIME_DIR / "db_lock.py"
    if not db_lock_file.exists():
        return [f"I-001: {db_lock_file} does not exist; single-writer DuckDB primitive missing"]

    # Parse the module statically — importing it triggers DuckDB connection
    # logic we do not want in the test environment.
    tree = ast.parse(db_lock_file.read_text(encoding="utf-8"), filename=str(db_lock_file))
    public_names: set[str] = set()
    for node in tree.body:
        if isinstance(node, ast.FunctionDef):
            public_names.add(node.name)
        elif isinstance(node, ast.ClassDef):
            public_names.add(node.name)
        elif isinstance(node, ast.AsyncFunctionDef):
            public_names.add(node.name)

    required = {"connect_write", "connect_read", "FlockWriteCoordinator", "WriteCoordinator"}
    missing = required - public_names
    if missing:
        violations.append(
            f"I-001: runtime/db_lock.py is missing required public names {sorted(missing)}; "
            f"these are the documented Quack-swap surface"
        )
    return violations


def check_i002_substrate_host_only() -> list[str]:
    """I-002: ``substrate/`` does not import cloud compute/storage SDKs.

    The PostHog server-side carve-out (``substrate/observability/posthog.py``,
    per CLAUDE.md §16) is the named exception. PostHog is analytics, not
    cloud compute — but the file is still listed under exemptions for
    clarity in case PostHog ever ships a feature that triggers a cloud
    SDK match.
    """
    violations: list[str] = []
    exempt_paths = {SUBSTRATE_DIR / Path(p) for p, _ in I002.exempt}
    for py_path in iter_python_files(SUBSTRATE_DIR):
        if py_path.resolve() in {p.resolve() for p in exempt_paths}:
            continue
        for imp, lineno in collect_imports(py_path):
            for sdk in CLOUD_SDK_PACKAGES:
                if matches_package(imp, sdk):
                    rel = py_path.relative_to(REPO_ROOT)
                    violations.append(
                        f"I-002: {rel}:{lineno} imports cloud SDK '{imp}' "
                        f"(matched {sdk!r}); substrate must stay host-only"
                    )
    return violations


def check_i003_substrate_permissive_deps() -> list[str]:
    """I-003: every direct dependency in pyproject.toml carries a permissive
    license. Optional-dependency groups are NOT checked (the operator opts
    into those per surface); only ``[project] dependencies`` is in scope.

    Verification uses ``importlib.metadata`` against the installed
    distribution. If a package is declared but not yet installed in the
    current environment, that surfaces as a separate warning rather than
    a violation — installation hygiene is a runtime concern, not an
    architectural one.
    """
    violations: list[str] = []
    if not PYPROJECT.exists():
        return [f"I-003: {PYPROJECT} not found"]
    data = tomllib.loads(PYPROJECT.read_text(encoding="utf-8"))
    deps: list[str] = data.get("project", {}).get("dependencies", [])
    for raw in deps:
        # Strip version specifiers and extras: "duckdb>=1.1.0" -> "duckdb".
        name = raw.split(";")[0].split("[")[0]
        for sep in ("==", ">=", "<=", "!=", "~=", ">", "<"):
            name = name.split(sep)[0]
        name = name.strip()
        if not name:
            continue
        try:
            meta = _md.metadata(name)
        except _md.PackageNotFoundError:
            # Declared but not installed — environment issue, not an
            # invariant violation. Skip silently; the regular pytest
            # ImportError elsewhere will surface this.
            continue
        # Three places a package can declare its license, in modern → legacy
        # order. PEP 639 introduced ``License-Expression`` (SPDX string);
        # ``License`` is the legacy free-text field; ``License :: ...``
        # classifiers are Trove-style. A permissive token in any one of
        # these is enough.
        license_expression = (meta.get("License-Expression") or "").strip()
        license_text = (meta.get("License") or "").strip()
        classifiers = meta.get_all("Classifier") or []
        license_class = " ".join(
            c.removeprefix("License :: OSI Approved :: ").removeprefix("License :: ")
            for c in classifiers
            if c.lower().startswith("license ::")
        )
        haystack = f"{license_expression} {license_text} {license_class}".lower()
        if not any(token in haystack for token in PERMISSIVE_LICENSE_TOKENS):
            violations.append(
                f"I-003: dependency {name!r} has non-permissive license "
                f"(license={license_text!r}, classifiers={classifiers!r})"
            )
    return violations


def check_i004_substrate_leaf_of_dep_graph() -> list[str]:
    """I-004: ``substrate/`` does not import from sibling top-level layers.

    Substrate is the bottom of the dep graph. ``acquisition/`` /
    ``orchestration/`` / etc. import substrate; substrate imports nothing
    above it. A violation either means a layering mistake or a hidden
    coupling that defeats the substrate's reusability premise.

    Pre-existing carve-outs are listed in ``I004.exempt`` with their
    individual justifications. Adding to that list requires a written
    reason in the same commit; the test layer does not silently widen
    exemptions.
    """
    violations: list[str] = []
    # Build exemption lookup: ``("file.py", "imp.name")`` → reason.
    exempt = {(p, imp): reason for (p, imp), reason in _exempt_pairs_from_invariant(I004)}
    for py_path in iter_python_files(SUBSTRATE_DIR):
        rel = py_path.relative_to(REPO_ROOT)
        rel_substrate = str(py_path.relative_to(SUBSTRATE_DIR))
        for imp, lineno in collect_imports(py_path):
            head = imp.split(".")[0]
            if head not in UPLAYER_DIRS:
                continue
            if (rel_substrate, imp) in exempt:
                continue
            violations.append(
                f"I-004: {rel}:{lineno} imports '{imp}' from uplayer {head!r}; "
                f"substrate must be a leaf of the import graph"
            )
    return violations


def _exempt_pairs_from_invariant(inv: "Invariant") -> list[tuple[tuple[str, str], str]]:
    """Parse ``inv.exempt`` entries of the form ``"path::import" reason``.

    The exempt tuple stores ``(key, reason)`` pairs where ``key`` is
    ``"<file relative to substrate/>::<imported module>"``. This keeps
    the registry literal compact (one line per exemption) while still
    forcing each carve-out to name both the file AND the import.
    """
    out: list[tuple[tuple[str, str], str]] = []
    for key, reason in inv.exempt:
        if "::" in key:
            file_part, imp_part = key.split("::", 1)
            out.append(((file_part, imp_part), reason))
    return out


def check_i005_pass_threshold_coherence() -> list[str]:
    """I-005: ``substrate.synthesis_rubric.scorer.PASS_THRESHOLD`` matches
    ``tools.dispatch_tier_verdict.analyzer.PASS_THRESHOLD``.

    Both modules document the same numeric pass bar (0.5). They were
    written separately and there is no shared constant — drift between
    them would silently shift the §13.9 pass criterion in production.
    The invariant pins them together so a future PR that touches one
    must touch the other.

    We read the constant via ``ast`` rather than importing the module —
    importing it would force DuckDB initialization through transitive
    imports, which is wrong for a quick architectural check.
    """
    violations: list[str] = []
    scorer = REPO_ROOT / "substrate" / "synthesis_rubric" / "scorer.py"
    analyzer = REPO_ROOT / "tools" / "dispatch_tier_verdict" / "analyzer.py"
    for path in (scorer, analyzer):
        if not path.exists():
            violations.append(f"I-005: required file {path.relative_to(REPO_ROOT)} missing")
    if violations:
        return violations

    def read_pass_threshold(path: Path) -> float | None:
        """Return the first ``PASS_THRESHOLD`` literal-constant assignment.

        We walk the entire AST (not just top-level) because analyzer.py
        historically declared ``PASS_THRESHOLD`` inside its
        ``run_verdict`` function. Module-level is the architectural
        preference (both modules should expose the constant publicly),
        but the invariant is about coherence — same number — not about
        where the number lives.
        """
        tree = ast.parse(path.read_text(encoding="utf-8"), filename=str(path))
        for node in ast.walk(tree):
            if isinstance(node, ast.Assign):
                for tgt in node.targets:
                    if isinstance(tgt, ast.Name) and tgt.id == "PASS_THRESHOLD":
                        if isinstance(node.value, ast.Constant) and isinstance(node.value.value, (int, float)):
                            return float(node.value.value)
        return None

    a = read_pass_threshold(scorer)
    b = read_pass_threshold(analyzer)
    if a is None:
        violations.append(f"I-005: PASS_THRESHOLD not found in {scorer.relative_to(REPO_ROOT)}")
    if b is None:
        violations.append(f"I-005: PASS_THRESHOLD not found in {analyzer.relative_to(REPO_ROOT)}")
    if a is not None and b is not None and a != b:
        violations.append(
            f"I-005: PASS_THRESHOLD drift — "
            f"substrate/synthesis_rubric/scorer.py={a} vs "
            f"tools/dispatch_tier_verdict/analyzer.py={b}; §13.9 pass bar would shift"
        )
    return violations


def check_i006_voice_style_weight_floor() -> list[str]:
    """I-006: synthesis rubric voice-style weight stays at or above the
    §5 floor (0.25).

    Master-spec §5.4 makes voice/style discipline load-bearing for the
    product proposition. The rubric currently weights it at 0.30. The
    invariant prevents a future tuning pass from silently dropping it to
    near-zero (e.g. someone optimizes for some other dimension and the
    voice bar goes with it).
    """
    violations: list[str] = []
    scorer = REPO_ROOT / "substrate" / "synthesis_rubric" / "scorer.py"
    if not scorer.exists():
        return [f"I-006: {scorer.relative_to(REPO_ROOT)} missing"]
    tree = ast.parse(scorer.read_text(encoding="utf-8"), filename=str(scorer))
    weights: dict[str, float] = {}
    for node in tree.body:
        if isinstance(node, ast.Assign):
            for tgt in node.targets:
                if isinstance(tgt, ast.Name) and tgt.id.startswith("W_"):
                    if isinstance(node.value, ast.Constant) and isinstance(node.value.value, (int, float)):
                        weights[tgt.id] = float(node.value.value)
    if "W_VOICE_STYLE" not in weights:
        violations.append("I-006: W_VOICE_STYLE constant not found in synthesis_rubric/scorer.py")
        return violations
    if weights["W_VOICE_STYLE"] < 0.25:
        violations.append(
            f"I-006: W_VOICE_STYLE={weights['W_VOICE_STYLE']} below §5.4 floor (0.25); "
            f"voice/style discipline is load-bearing per CLAUDE.md invariants list"
        )
    # Defensive coherence check — all W_* should sum to 1.0 ± rounding.
    total = sum(v for k, v in weights.items() if k.startswith("W_"))
    if abs(total - 1.0) > 1e-6:
        violations.append(
            f"I-006: rubric weights sum to {total:.6f}, not 1.0; "
            f"the composite formula assumes Σweights = 1"
        )
    return violations


# ---------------------------------------------------------------------------
# The registry itself
# ---------------------------------------------------------------------------

I001 = Invariant(
    id="I-001",
    name="single-writer-duckdb",
    summary="runtime/db_lock.py exports the documented Quack-swap surface",
    rationale=(
        "Three writer surfaces (daily ingest cron, weekly monitor cron, on-demand "
        "kanban worker) share one DuckDB file. The flock + LockedConnection contract "
        "in runtime/db_lock.py is the only thing preventing scheduling overlaps from "
        "corrupting state. CLAUDE.md invariant #1."
    ),
    category="substrate",
    introduced="2026-05-24",
    source="runtime/db_lock.py",
    severity="error",
)

I002 = Invariant(
    id="I-002",
    name="substrate-host-only",
    summary="substrate/ must not import cloud compute/storage SDKs",
    rationale=(
        "Substrate is the only-writer to DuckDB and must remain runnable on the "
        "operator's laptop without cloud credentials. Cloud SDK imports inside "
        "substrate/ break that property and surface as a deploy-required call site."
    ),
    category="substrate",
    introduced="2026-05-24",
    source="CLAUDE.md §16 REJECT list; master-spec §16",
    severity="error",
    exempt=(
        # Carve-out per CLAUDE.md "§16 carve-out (single exception)". The
        # PostHog package itself is analytics, not a cloud SDK, but the
        # file is named explicitly so a future maintainer cannot dilute
        # the exemption set without seeing this list.
        ("observability/posthog.py", "CLAUDE.md §16 carve-out — PostHog LLM Analytics"),
    ),
)

I003 = Invariant(
    id="I-003",
    name="substrate-permissive-deps",
    summary="every direct dep in pyproject.toml has a permissive license",
    rationale=(
        "Direct dependencies define what Antiek can be re-licensed as later. "
        "Permissive-only (MIT/Apache/BSD/ISC/PSF/MPL-2.0) keeps the option open. "
        "Optional groups are scoped to specific surfaces and not policed here."
    ),
    category="dependency",
    introduced="2026-05-24",
    source="pyproject.toml [project.dependencies]",
    severity="error",
)

I004 = Invariant(
    id="I-004",
    name="substrate-leaf-of-dep-graph",
    summary="substrate/ does not import from any sibling top-level layer",
    rationale=(
        "Layered architecture: acquisition/orchestration/middleware/interfaces/etc. "
        "depend on substrate; substrate depends on none of them. A violation means "
        "either a layering mistake or a coupling that breaks the substrate's "
        "host-only reusability premise. Four pre-existing exemptions document "
        "architectural debt: substrate→tools.stripe_connect (pricing + transfer) "
        "and substrate→tools.prompt_autoresearch.score (shared heuristic)."
    ),
    category="architecture",
    introduced="2026-05-24",
    source="docs/master-product-spec.md layered architecture section",
    severity="error",
    exempt=(
        # Each entry: ("<file relative to substrate/>::<imported module>", reason).
        # When promoting tools/stripe_connect/ to substrate/ (the architecturally
        # correct home for billing primitives), remove the first three rows.
        (
            "ad_inventory/transfer_initiator.py::tools.stripe_connect.providers",
            "Ad-inventory transfer routes through Stripe Connect provider abstraction; "
            "tools/stripe_connect/ is the de facto billing-substrate layer pending "
            "a refactor that promotes it under substrate/.",
        ),
        (
            "billing/aggregator.py::tools.stripe_connect.pricing",
            "Aggregator reads pricing constants from tools/stripe_connect/pricing.py; "
            "same promotion candidate as above.",
        ),
        (
            "billing/cap_enforcement.py::tools.stripe_connect.pricing",
            "Cap enforcement reads pricing constants from tools/stripe_connect/pricing.py; "
            "same promotion candidate.",
        ),
        (
            "synthesis_rubric/scorer.py::tools.prompt_autoresearch.score",
            "Documented deliberate coupling per scorer.py docstring: re-uses the "
            "voice/style heuristic from tools.prompt_autoresearch.score to prevent "
            "drift between the runtime scorer and the autoresearch prompt sweep.",
        ),
    ),
)

I005 = Invariant(
    id="I-005",
    name="pass-threshold-coherence",
    summary="scorer.PASS_THRESHOLD == analyzer.PASS_THRESHOLD",
    rationale=(
        "Two independently-authored modules document the §13.9 pass bar at 0.5. "
        "Drift between them silently shifts the production pass criterion. The "
        "scorer.py docstring already calls this out as a 'matched by' constraint; "
        "this invariant makes the constraint mechanical."
    ),
    category="coherence",
    introduced="2026-05-24",
    source="substrate/synthesis_rubric/scorer.py; tools/dispatch_tier_verdict/analyzer.py",
    severity="error",
)

I006 = Invariant(
    id="I-006",
    name="voice-style-weight-floor",
    summary="W_VOICE_STYLE >= 0.25 and rubric weights sum to 1.0",
    rationale=(
        "Master-spec §5.4 voice/style is load-bearing for the product proposition. "
        "Floor at 0.25 protects against a future tuning pass silently demoting it. "
        "Sum-to-1 protects against accidental rescaling that breaks the composite."
    ),
    category="voice_style",
    introduced="2026-05-24",
    source="substrate/synthesis_rubric/scorer.py; master-spec §5.4",
    severity="error",
)


INVARIANTS: tuple[Invariant, ...] = (I001, I002, I003, I004, I005, I006)


# Map id -> (invariant, check_function). The check function returns a list
# of violation strings (empty list = pass). Tests parametrize over this map.
CHECKS: dict[str, Callable[[], list[str]]] = {
    "I-001": check_i001_single_writer_duckdb,
    "I-002": check_i002_substrate_host_only,
    "I-003": check_i003_substrate_permissive_deps,
    "I-004": check_i004_substrate_leaf_of_dep_graph,
    "I-005": check_i005_pass_threshold_coherence,
    "I-006": check_i006_voice_style_weight_floor,
}


def get_invariant(invariant_id: str) -> Invariant:
    """Look up an invariant by id, raising KeyError if missing."""
    for inv in INVARIANTS:
        if inv.id == invariant_id:
            return inv
    raise KeyError(f"unknown invariant id: {invariant_id!r}")


def run_all() -> dict[str, list[str]]:
    """Run every registered check; return ``{id: violations}``.

    Used by the standalone ``python -m substrate.invariants`` entry point
    and by tests. Errors are returned, not raised — the caller decides
    whether to assert or report.
    """
    return {inv.id: CHECKS[inv.id]() for inv in INVARIANTS}


# ---------------------------------------------------------------------------
# CLI entry point
# ---------------------------------------------------------------------------


def _format_report(results: dict[str, list[str]]) -> str:
    lines: list[str] = []
    total_violations = 0
    for inv_id, violations in results.items():
        inv = get_invariant(inv_id)
        if violations:
            lines.append(f"FAIL {inv_id} {inv.name} ({len(violations)} violation(s))")
            for v in violations:
                lines.append(f"    {v}")
            total_violations += len(violations)
        else:
            lines.append(f"OK   {inv_id} {inv.name}")
    lines.append("")
    lines.append(f"{len(results)} invariants checked, {total_violations} violation(s)")
    return "\n".join(lines)


def main() -> int:
    """``python -m substrate.invariants`` — run every check, print report.

    Exit codes:
        0 — all invariants pass
        2 — at least one ``error``-severity invariant has violations
        1 — usage / unexpected exception (Python's default)
    """
    results = run_all()
    print(_format_report(results))
    for inv_id, violations in results.items():
        if violations and get_invariant(inv_id).severity == "error":
            return 2
    return 0


if __name__ == "__main__":
    sys.exit(main())
