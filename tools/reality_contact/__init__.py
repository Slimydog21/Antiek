"""Reality-Contact Ledger (SPR-01, keystone).

A test makes *reality contact* with a subsystem when it exercises that
subsystem's real CORE code. It is *theater* for that subsystem when it
patches/mocks a CORE symbol of the subsystem it claims to cover — so the
assertion is satisfied by the mock's own return value rather than by the real
code path. Legitimate mocking of *external boundary seams* (network, clock,
payments, third-party endpoints) is NOT theater: those seams are supposed to be
stubbed in a hermetic test.

This package emits ``tools/reality_contact/ledger.json`` — a deterministic,
fully-auditable classification of every ``test_*.py`` file into one of:

  reality / theater / mixed / n-a / indeterminate

backed by an explicit, defended boundary contract (``boundaries.yaml``).

Layering (serial dependency — each module reads the one above):

  boundaries.yaml   the CORE (never-mock) and BOUNDARY (legit-to-mock) lists
  extract.py        static (AST, never-execute) extraction of mock targets
  classifier.py     per-file + per-subsystem verdicts
  ledger.py         deterministic JSON ledger + ``python -m`` regeneration

Downstream sprints (the RCR scoreboard SPR-02, the baseline/ratchet SPR-04/05,
mutation SPR-07) READ this ledger. They do not re-derive it.

Modeled on the established AST-gate shape in ``tools/lint/serve_invariants_check.py``
and ``tools/lint/rate_governor_check.py``: same ``ast``-walk-the-tree approach,
same cited ``path:line`` offender format, same import-free posture.
"""

from __future__ import annotations

from pathlib import Path

# Repo root: tools/reality_contact/__init__.py -> tools -> repo. The two parents
# match the ``Path(__file__).resolve().parent.parent.parent`` shape the lint
# scanners use (theirs live one level deeper under tools/lint/).
REPO_ROOT: Path = Path(__file__).resolve().parent.parent.parent

# The contract file this package is computed against.
BOUNDARIES_PATH: Path = Path(__file__).resolve().parent / "boundaries.yaml"

# Where the regenerated ledger lands.
LEDGER_PATH: Path = Path(__file__).resolve().parent / "ledger.json"

__all__ = ["REPO_ROOT", "BOUNDARIES_PATH", "LEDGER_PATH"]
