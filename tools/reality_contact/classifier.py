"""Per-test-file reality-contact classification.

Loads the boundary contract (``boundaries.yaml``), determines which CORE
subsystems a test CLAIMS to cover (the core modules it imports), then for each
such subsystem asks: does any extracted mock target land on a CORE symbol of
that subsystem? From that, a per-subsystem label and a per-file verdict:

  reality        imports >=1 core module, mocks NONE of its imported cores'
                 symbols (and has no unresolved-on-core ambiguity).
  theater        mocks >=1 core symbol of a subsystem it imports.
  mixed          some imported subsystems are real, others are theater.
  n-a            imports NO core module (claims to cover no core subsystem).
  indeterminate  an UNRESOLVED mock target could land on a core path, so we
                 cannot prove the real core ran — NEVER emit `reality` here.

The honesty pivot: a false `reality` is the worst output. Whenever static
analysis cannot prove the real core executed (an unresolved target that might
be core), the verdict is `indeterminate`, not `reality`.

Per-subsystem labels are recorded (not just the file verdict) because SPR-02's
scoreboard needs them.
"""

from __future__ import annotations

import ast
from dataclasses import dataclass, field
from functools import lru_cache
from pathlib import Path
from typing import Any

from tools.reality_contact import BOUNDARIES_PATH
from tools.reality_contact.extract import MockTarget, extract_targets


# --------------------------------------------------------------------------- #
# Boundary contract loading
# --------------------------------------------------------------------------- #
@dataclass(frozen=True)
class BoundaryContract:
    """The loaded, validated CORE / BOUNDARY / BOUNDARY_SYMBOL lists."""

    schema_version: int
    core: tuple[str, ...]
    boundary: tuple[str, ...]
    boundary_symbols: tuple[str, ...]
    raw_text: str  # the verbatim YAML text (for the ledger content hash)

    def core_set(self) -> frozenset[str]:
        return frozenset(self.core)

    def boundary_set(self) -> frozenset[str]:
        return frozenset(self.boundary)

    def boundary_symbol_set(self) -> frozenset[str]:
        return frozenset(self.boundary_symbols)


def _parse_boundaries(text: str) -> BoundaryContract:
    import yaml  # PyYAML present per the venv

    data: dict[str, Any] = yaml.safe_load(text)
    core = tuple(sorted(e["module"] for e in data.get("core", [])))
    boundary = tuple(sorted(e["module"] for e in data.get("boundary", [])))
    boundary_symbols = tuple(sorted(e["symbol"] for e in data.get("boundary_symbols", []) or []))
    # Defensibility: every entry must carry a justification.
    for section, key in (("core", "module"), ("boundary", "module"), ("boundary_symbols", "symbol")):
        for entry in data.get(section, []) or []:
            if not entry.get("justification", "").strip():
                raise ValueError(
                    f"boundaries.yaml {section} entry {entry.get(key)!r} "
                    f"lacks a justification comment/field"
                )
    return BoundaryContract(
        schema_version=int(data["schema_version"]),
        core=core,
        boundary=boundary,
        boundary_symbols=boundary_symbols,
        raw_text=text,
    )


@lru_cache(maxsize=1)
def load_contract(path: Path = BOUNDARIES_PATH) -> BoundaryContract:
    return _parse_boundaries(Path(path).read_text(encoding="utf-8"))


# --------------------------------------------------------------------------- #
# Dotted-path prefix matching
# --------------------------------------------------------------------------- #
def _matches_module(dotted: str, module: str) -> bool:
    """True iff dotted path ``dotted`` is the module itself or a symbol/submodule
    under it: ``dotted == module`` OR ``dotted`` startswith ``module + "."``."""
    return dotted == module or dotted.startswith(module + ".")


def _which_core(dotted: str, cores: frozenset[str]) -> str | None:
    """Return the core module that ``dotted`` falls under, or None. If multiple
    cores are prefixes (they shouldn't overlap), the LONGEST match wins so the
    most specific subsystem is credited."""
    best: str | None = None
    for c in cores:
        if _matches_module(dotted, c) and (best is None or len(c) > len(best)):
            best = c
    return best


def _which_boundary(dotted: str, boundaries: frozenset[str]) -> str | None:
    best: str | None = None
    for b in boundaries:
        if _matches_module(dotted, b) and (best is None or len(b) > len(best)):
            best = b
    return best


def _is_boundary_symbol(dotted: str, boundary_symbols: frozenset[str]) -> bool:
    """True iff ``dotted`` is (or is a strict child of) a per-symbol carve-out
    that lives inside a core module but is itself an I/O boundary seam. Checked
    BEFORE the core-module match so a hit is classed boundary, not theater."""
    return any(_matches_module(dotted, s) for s in boundary_symbols)


# --------------------------------------------------------------------------- #
# Imports a test claims to cover
# --------------------------------------------------------------------------- #
def imported_dotted_paths(tree: ast.Module) -> set[str]:
    """Every dotted path the module pulls in, at module OR function scope.

    ``import a.b.c`` -> {"a.b.c"}; ``from a.b import c`` -> {"a.b", "a.b.c"}.
    We add BOTH the package and the package.symbol so a ``from substrate.graph
    import ops`` registers ``substrate.graph.ops`` (the core module) as imported.
    Function-local imports count too (a test may import its subsystem inside the
    test function)."""
    paths: set[str] = set()
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            for alias in node.names:
                paths.add(alias.name)
        elif isinstance(node, ast.ImportFrom):
            if node.module is None or node.level:
                continue
            paths.add(node.module)
            for alias in node.names:
                paths.add(f"{node.module}.{alias.name}")
    return paths


def imported_core_subsystems(tree: ast.Module, cores: frozenset[str]) -> set[str]:
    """The set of CORE modules this test imports (claims to cover)."""
    imported = imported_dotted_paths(tree)
    covered: set[str] = set()
    for p in imported:
        c = _which_core(p, cores)
        if c is not None:
            covered.add(c)
    return covered


# --------------------------------------------------------------------------- #
# Classification result types
# --------------------------------------------------------------------------- #
@dataclass(frozen=True)
class CoreMockEvidence:
    """A mock target that landed on a core symbol (the theater evidence)."""

    subsystem: str       # the core module mocked
    target: str          # the dotted path mocked (subsystem or a symbol under it)
    form: str            # extraction form
    lineno: int
    raw: str


@dataclass
class FileClassification:
    path: str
    verdict: str                       # reality|theater|mixed|n-a|indeterminate
    subsystem_labels: dict[str, str]   # core module -> reality|theater|indeterminate
    core_mock_evidence: list[CoreMockEvidence] = field(default_factory=list)
    unresolved_on_core: list[MockTarget] = field(default_factory=list)
    # The boundary modules this file mocks (resolved targets under a BOUNDARY
    # entry) — sorted, for the ledger's known-blind-spots roll-up. NOT used in
    # the verdict (boundary mocks are legit, never theater); it exists so the
    # ledger can report how many tests mock the LLM/TTS provider boundary, the
    # pattern the metric is BY DESIGN blind to.
    boundary_mock_modules: list[str] = field(default_factory=list)
    parse_error: str | None = None


_INDETERMINATE = "indeterminate"
_REALITY = "reality"
_THEATER = "theater"
_MIXED = "mixed"
_NA = "n-a"


def _unresolved_could_be_core(t: MockTarget, cores: frozenset[str], boundaries: frozenset[str]) -> bool:
    """An unresolved target makes a subsystem indeterminate UNLESS we can prove
    it is harmless. For a fully-unresolved target (no dotted path at all) we
    CANNOT prove it isn't core, so it is treated as possibly-core (honesty:
    never assume a boundary). We only exclude an unresolved target if its raw
    description names a clearly-boundary attribute — but to stay safe we do NOT
    do that here; any unresolved target is possibly-core."""
    return t.target is None


def classify_source(path: str, source: str, contract: BoundaryContract | None = None) -> FileClassification:
    """Classify one test file's source text."""
    contract = contract or load_contract()
    cores = contract.core_set()
    boundaries = contract.boundary_set()
    boundary_symbols = contract.boundary_symbol_set()

    try:
        tree = ast.parse(source)
    except SyntaxError as exc:
        return FileClassification(
            path=path,
            verdict="parse-error",
            subsystem_labels={},
            parse_error=f"{type(exc).__name__}: {exc.msg} (line {exc.lineno})",
        )

    covered = imported_core_subsystems(tree, cores)
    targets = extract_targets(source)

    # Bucket every resolved target by the core subsystem (if any) it mocks.
    evidence_by_subsystem: dict[str, list[CoreMockEvidence]] = {c: [] for c in covered}
    all_evidence: list[CoreMockEvidence] = []
    for t in targets:
        if t.target is None:
            continue
        if _is_boundary_symbol(t.target, boundary_symbols):
            continue  # surgical loader/seam carve-out under a core module — not theater
        c = _which_core(t.target, cores)
        if c is None:
            continue  # boundary mock or non-core symbol — not theater
        ev = CoreMockEvidence(subsystem=c, target=t.target, form=t.form, lineno=t.lineno, raw=t.raw)
        all_evidence.append(ev)
        evidence_by_subsystem.setdefault(c, []).append(ev)

    # Unresolved targets that could land on a core path → ambiguity.
    unresolved_on_core = [
        t for t in targets if _unresolved_could_be_core(t, cores, boundaries)
    ]

    # Boundary mocks (resolved targets under a BOUNDARY entry). A boundary mock
    # is legit, never theater — this is recorded ONLY so the ledger can report
    # how many tests mock the LLM/TTS provider boundary, the very pattern this
    # metric is by design blind to.
    boundary_hits: set[str] = set()
    for t in targets:
        if t.target is None:
            continue
        b = _which_boundary(t.target, boundaries)
        if b is not None:
            boundary_hits.add(b)
    boundary_mock_modules = sorted(boundary_hits)

    # --- n-a: imports no core subsystem ------------------------------------ #
    if not covered:
        # Even with no covered core, an unresolved target can't promote this to
        # reality (there's nothing to be real about) — it's genuinely n-a. But
        # if there is core-mock evidence on a subsystem NOT imported, that's an
        # odd case; we still credit it as theater for that subsystem so it isn't
        # silently lost. (Rare: patching a core module a test doesn't import.)
        if all_evidence:
            theater_labels = {ev.subsystem: _THEATER for ev in all_evidence}
            return FileClassification(
                path=path,
                verdict=_THEATER,
                subsystem_labels=theater_labels,
                core_mock_evidence=all_evidence,
                boundary_mock_modules=boundary_mock_modules,
            )
        return FileClassification(
            path=path,
            verdict=_NA,
            subsystem_labels={},
            boundary_mock_modules=boundary_mock_modules,
        )

    # --- per-subsystem labels --------------------------------------------- #
    labels: dict[str, str] = {}
    for c in covered:
        if evidence_by_subsystem.get(c):
            labels[c] = _THEATER
        else:
            labels[c] = _REALITY  # provisional; may drop to indeterminate below

    # Unresolved-on-core ambiguity. A fully-unresolved target could mock ANY
    # imported core subsystem — we cannot attribute it to one, so every
    # provisionally-`reality` covered subsystem becomes `indeterminate`. (A
    # subsystem already proven `theater` stays theater — the worst label.)
    if unresolved_on_core:
        for c in covered:
            if labels[c] == _REALITY:
                labels[c] = _INDETERMINATE

    # Any core-mock evidence on a subsystem NOT in `covered` (patched but not
    # imported) — record it as theater too.
    for ev in all_evidence:
        if ev.subsystem not in labels:
            labels[ev.subsystem] = _THEATER

    # --- roll up the file verdict ----------------------------------------- #
    label_values = set(labels.values())
    has_theater = _THEATER in label_values
    has_reality = _REALITY in label_values
    has_indeterminate = _INDETERMINATE in label_values

    if has_theater and (has_reality or has_indeterminate):
        verdict = _MIXED
    elif has_theater:
        verdict = _THEATER
    elif has_indeterminate:
        verdict = _INDETERMINATE
    else:
        verdict = _REALITY

    return FileClassification(
        path=path,
        verdict=verdict,
        subsystem_labels=labels,
        core_mock_evidence=all_evidence,
        unresolved_on_core=unresolved_on_core,
        boundary_mock_modules=boundary_mock_modules,
    )


def classify_file(path: Path, repo_root: Path, contract: BoundaryContract | None = None) -> FileClassification:
    """Classify a file on disk; ``path`` recorded relative to ``repo_root``."""
    rel = path.relative_to(repo_root).as_posix()
    try:
        source = path.read_text(encoding="utf-8")
    except OSError as exc:
        return FileClassification(
            path=rel,
            verdict="parse-error",
            subsystem_labels={},
            parse_error=f"OSError: {exc}",
        )
    return classify_source(rel, source, contract)
