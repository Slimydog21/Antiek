"""The CI-green-means invariant registry — Antiek Foundation SPR-06 (KEYSTONE).

This session proved CI could be *fake-green* on Antiek's most consequential
invariant: the §14.4 synthesizer pin once had a "seam test" that asserted
DeepSeek-as-desired against a *synthetic* config and never loaded the real
``config.yaml`` — so a money/provenance/measurement displacement bug passed CI
for weeks. Five independent brainstorm lenses (Hashimoto, Rust-discipline, DHH,
Karpathy, Yegge) converged on the same missing clause: a single registry
enumerating every load-bearing invariant, each guarded by a test that genuinely
fails when violated, with an empty/stub signal counting as NOT declared.

This package is that registry. It does **not** re-test anything — it asserts
that for every invariant the project claims to protect, a real, *collected*,
*non-vacuous* guard test exists. "Non-vacuous" is the whole point: a guard that
passes on broken code (the §14.4 failure mode) must be detectable and rejected.

Design (mirrors the proven single-source disciplines in this tree —
``tools/codegen/check_conformance.py`` 's registry-of-rows and
``tests/test_integration_invariants.py`` 's data-manifest):

* **One file per invariant** — ``substrate/invariants/<id>.toml``. One declaration
  per file keeps later registrants (SPR-08/09/10) *file-disjoint*, so they land
  in parallel with no shared manifest to serialize on.
* **Data, not prose** — TOML, parsed with the stdlib ``tomllib``. The meta-check
  (``tests/test_invariant_registry_meta.py``) consumes the parsed declarations
  mechanically; no human-readable manifest is the source of truth.
* **Honest gaps are a feature** — an invariant whose real guard does not exist
  yet (§9.0 until SPR-08, §5 voice) is declared ``status = "unguarded"`` with a
  named ``owner`` sprint. A fake-complete registry is the disease this cures; an
  honest ``unguarded`` is the cure.

Public surface
--------------
``load_registry()`` returns the parsed, validated declarations. ``Invariant``
is the per-entry shape. ``RegistryError`` is raised on a malformed declaration
(a programming error in a ``.toml`` file — fix it before trusting the registry).

The *enforcement* (guard exists / is collected / is non-vacuous) lives in the
meta-check test, not here — this module is the loader + the shape, kept import-
light (stdlib only) so the meta-check can run in pytest-free environments too.
"""

from __future__ import annotations

import tomllib
from dataclasses import dataclass, field
from pathlib import Path

# The registry directory is this package's own directory.
REGISTRY_DIR = Path(__file__).resolve().parent
# Repo root = three levels up (substrate/invariants/__init__.py → repo).
REPO_ROOT = REGISTRY_DIR.parent.parent

# Allowed declaration statuses. "guarded" => a real, collected, non-vacuous
# guard MUST be proven. "unguarded" => an honest gap with a named owner sprint;
# the meta-check asserts it does NOT claim a guard (so it cannot fake-pass).
STATUS_GUARDED = "guarded"
STATUS_UNGUARDED = "unguarded"
_STATUSES = frozenset({STATUS_GUARDED, STATUS_UNGUARDED})

# A guard whose target is a script (exit-code gate) rather than a pytest node.
GUARD_KIND_PYTEST = "pytest"
GUARD_KIND_SCRIPT = "script"
_GUARD_KINDS = frozenset({GUARD_KIND_PYTEST, GUARD_KIND_SCRIPT})


class RegistryError(ValueError):
    """A declaration file is malformed — a programming error in the registry
    itself (not a violated invariant). Fix the ``.toml`` before trusting CI."""


@dataclass(frozen=True)
class NonVacuityProof:
    """Evidence that a guard is not a §14.4-class fake-green — i.e. it actually
    fails on broken code. Exactly one proof method is recorded per guard.

    method:
      * ``fail_before_pass_after`` — the recorded fail count before the fix and
        pass count after, with the commit the proof was taken at. The canonical
        proof for the staged Wave-1 guards (SPR-01 recorded "7 fail → 27 pass").
      * ``negative_control`` — the guard's own test imports a deliberately-broken
        input and asserts the guard rejects it (a teeth-in-the-same-file proof,
        as ``test_integration_invariants`` does with ``pytest.raises``).
      * ``mutation`` — a named mutation of the guarded code that the guard catches.

    detail: free text describing the proof (e.g. "fail_before=7 pass_after=27 @7dc7ed5").
    """

    method: str
    detail: str


@dataclass(frozen=True)
class Invariant:
    """One load-bearing invariant declaration.

    id:        stable slug (matches the filename stem).
    statement: WHY it matters — the cost if violated, not just a name (rigor #5).
    status:    "guarded" | "unguarded".
    guard:     the test node id (``path::node``) or script path that fails when
               the invariant is violated. Empty for ``unguarded``.
    guard_kind:"pytest" (a collected node) or "script" (an exit-code gate).
    assertion: what the guard proves, in one line.
    sunset:    when the invariant retires, or "" if permanent.
    owner:     for ``unguarded`` — the sprint that will supply the real guard.
    non_vacuity: the fake-green proof (required for ``guarded``).
    source_file: the .toml this was parsed from (for error messages).
    """

    id: str
    statement: str
    status: str
    assertion: str
    guard: str = ""
    guard_kind: str = GUARD_KIND_PYTEST
    sunset: str = ""
    owner: str = ""
    non_vacuity: NonVacuityProof | None = None
    source_file: Path | None = field(default=None, compare=False)

    @property
    def is_guarded(self) -> bool:
        return self.status == STATUS_GUARDED

    @property
    def guard_path(self) -> str:
        """The file portion of a pytest ``path::node`` guard (or the script path)."""
        return self.guard.split("::", 1)[0] if self.guard else ""


def _require(data: dict, key: str, src: Path) -> object:
    if key not in data:
        raise RegistryError(f"{src.name}: missing required key {key!r}")
    return data[key]


def _parse_one(src: Path) -> Invariant:
    """Parse + validate one declaration file. Raises RegistryError on malformed
    data so a typo in a .toml is a loud programming error, never a silent skip."""
    try:
        data = tomllib.loads(src.read_text(encoding="utf-8"))
    except tomllib.TOMLDecodeError as exc:  # pragma: no cover - exercised via fixture
        raise RegistryError(f"{src.name}: invalid TOML — {exc}") from exc

    inv = data.get("invariant")
    if not isinstance(inv, dict):
        raise RegistryError(f"{src.name}: missing [invariant] table")

    inv_id = str(_require(inv, "id", src))
    if inv_id != src.stem:
        raise RegistryError(
            f"{src.name}: id {inv_id!r} must match filename stem {src.stem!r} "
            f"(one-file-per-invariant — the filename IS the id)"
        )

    status = str(_require(inv, "status", src))
    if status not in _STATUSES:
        raise RegistryError(
            f"{src.name}: status {status!r} not in {sorted(_STATUSES)}"
        )

    statement = str(_require(inv, "statement", src)).strip()
    if not statement:
        raise RegistryError(f"{src.name}: statement must explain WHY (rigor #5)")
    assertion = str(_require(inv, "assertion", src)).strip()
    if not assertion:
        raise RegistryError(f"{src.name}: assertion must say what the guard proves")

    guard = str(inv.get("guard", "")).strip()
    guard_kind = str(inv.get("guard_kind", GUARD_KIND_PYTEST)).strip()
    if guard_kind not in _GUARD_KINDS:
        raise RegistryError(
            f"{src.name}: guard_kind {guard_kind!r} not in {sorted(_GUARD_KINDS)}"
        )
    sunset = str(inv.get("sunset", "")).strip()
    owner = str(inv.get("owner", "")).strip()

    non_vacuity: NonVacuityProof | None = None
    nv = data.get("non_vacuity")
    if isinstance(nv, dict):
        non_vacuity = NonVacuityProof(
            method=str(_require(nv, "method", src)).strip(),
            detail=str(_require(nv, "detail", src)).strip(),
        )

    return Invariant(
        id=inv_id,
        statement=statement,
        status=status,
        assertion=assertion,
        guard=guard,
        guard_kind=guard_kind,
        sunset=sunset,
        owner=owner,
        non_vacuity=non_vacuity,
        source_file=src,
    )


def load_registry(registry_dir: Path | None = None) -> list[Invariant]:
    """Load + validate every ``*.toml`` declaration in the registry directory.

    Returns the invariants sorted by id (deterministic order for the meta-check
    and for human reading). Raises ``RegistryError`` on the FIRST malformed file
    — a malformed declaration is a programming error, not a violated invariant.
    """
    base = registry_dir or REGISTRY_DIR
    files = sorted(p for p in base.glob("*.toml"))
    invariants = [_parse_one(p) for p in files]

    seen: dict[str, Path] = {}
    for inv in invariants:
        if inv.id in seen:
            raise RegistryError(
                f"duplicate invariant id {inv.id!r} in {seen[inv.id].name} and "
                f"{inv.source_file.name if inv.source_file else '?'}"
            )
        seen[inv.id] = inv.source_file  # type: ignore[assignment]
    return invariants


__all__ = [
    "Invariant",
    "NonVacuityProof",
    "RegistryError",
    "load_registry",
    "REGISTRY_DIR",
    "REPO_ROOT",
    "STATUS_GUARDED",
    "STATUS_UNGUARDED",
    "GUARD_KIND_PYTEST",
    "GUARD_KIND_SCRIPT",
]
