"""Guard for the retrieval-gate UNIQUENESS lint — Antiek Convergence SPR-03.

The §9.0 retrieval gate was forked across two parallel implementations and
reconsolidated to a single canonical home by #65 (``b27b9df``). This lint
(``tools/lint/retrieval_gate_uniqueness.py``) is the never-re-fork guard: each
gate symbol (``non_privileged_chunk_sql_clause`` / ``is_chunk_body_withheld``)
must have EXACTLY ONE definition.

Rigor #3 — the lint must CATCH its target. Two proofs:

  * pass-on-current-tree: the real tree has exactly one definition of each
    symbol (#65 already consolidated them), so the lint is GREEN;
  * catches-a-fork: a synthetic root with a SECOND ``def is_chunk_body_withheld``
    is FLAGGED as ``path:line`` (the pre-#65 re-fork shape) — proving this is a
    fail-on-violation / pass-on-fixed check, not one that passes on everything.

A third proof pins the ZERO-definition case (the canonical home vanishing) reds
too, so the check is symmetric: ≠ 1 in EITHER direction fails.
"""

from __future__ import annotations

from pathlib import Path

from tools.lint.retrieval_gate_uniqueness import (
    _CANONICAL_HOME,
    _WATCHED_SYMBOLS,
    find_definitions,
    find_violations,
    main,
)

_REPO = Path(__file__).resolve().parent.parent


# ──────────────────────────────────────────────────────────────────────────────
# Pass-on-current-tree: #65 consolidated each symbol to exactly one definition.
# ──────────────────────────────────────────────────────────────────────────────


def test_lint_passes_on_the_current_tree() -> None:
    """The real tree has exactly one definition of each gate symbol — the lint
    is GREEN. (If a future change re-forks the gate by adding a second
    definition, THIS test reddens, which is the point.)"""
    assert find_violations() == [], (
        "the current tree should have exactly one definition of each retrieval-"
        "gate symbol — a violation here means the gate re-forked:\n"
        + "\n".join(find_violations())
    )
    assert main([]) == 0


def test_each_symbol_resolves_to_the_canonical_home() -> None:
    """Belt-and-braces: not just COUNT one, but confirm the single definition of
    each symbol lives in the canonical module #65 consolidated to. A second home
    (even at count one, were a symbol moved AND re-forked) would surface here."""
    defs = find_definitions()
    for sym in _WATCHED_SYMBOLS:
        assert len(defs[sym]) == 1, f"{sym} has {len(defs[sym])} defs: {defs[sym]}"
        assert defs[sym][0].startswith(_CANONICAL_HOME + ":"), (
            f"{sym} is defined at {defs[sym][0]}, not the canonical "
            f"{_CANONICAL_HOME}"
        )


# ──────────────────────────────────────────────────────────────────────────────
# Catches-a-fork: a synthetic root with a SECOND definition is FLAGGED.
# ──────────────────────────────────────────────────────────────────────────────


def _write_canonical_gate(graph_dir: Path) -> None:
    """A minimal stand-in for substrate/graph/retrieval_gate.py defining each
    watched symbol exactly once."""
    graph_dir.mkdir(parents=True, exist_ok=True)
    (graph_dir / "retrieval_gate.py").write_text(
        "def non_privileged_chunk_sql_clause(*, table_alias='d',\n"
        "                                    policy_tag='attribution_eligible'):\n"
        "    return '', []\n"
        "\n\n"
        "def is_chunk_body_withheld(content_class, *, taken_down=False):\n"
        "    return False, None\n",
        encoding="utf-8",
    )


def test_lint_catches_a_second_definition(tmp_path: Path) -> None:
    """A second module under substrate/graph/ that re-defines a gate symbol is
    the pre-#65 re-fork shape. The lint must FLAG both definition sites as
    ``path:line`` and ``main`` must exit 1."""
    graph_dir = tmp_path / "substrate" / "graph"
    _write_canonical_gate(graph_dir)
    # The re-fork: a second def of is_chunk_body_withheld in a sibling module.
    (graph_dir / "rogue_gate.py").write_text(
        "def is_chunk_body_withheld(content_class, *, taken_down=False):\n"
        "    # a divergent second home a caller could import the wrong one from\n"
        "    return True, 'rogue'\n",
        encoding="utf-8",
    )

    violations = find_violations(root=tmp_path)
    assert violations, "the lint must flag the re-forked second definition"
    # Both definition sites are reported as path:line.
    joined = "\n".join(violations)
    assert "substrate/graph/rogue_gate.py:1:" in joined, joined
    assert "substrate/graph/retrieval_gate.py:6:" in joined, joined
    assert "is_chunk_body_withheld" in joined
    # non_privileged_chunk_sql_clause is still singular here → not flagged.
    assert "non_privileged_chunk_sql_clause' is defined" not in joined


def test_lint_catches_zero_definitions(tmp_path: Path) -> None:
    """The symmetric failure: if the canonical home VANISHES (zero definitions),
    the lint reds too — ≠ 1 in either direction fails closed, so a refactor that
    deletes the gate without a replacement cannot pass silently."""
    graph_dir = tmp_path / "substrate" / "graph"
    graph_dir.mkdir(parents=True, exist_ok=True)
    # Only ONE symbol defined; the other has zero definitions.
    (graph_dir / "retrieval_gate.py").write_text(
        "def non_privileged_chunk_sql_clause(*, table_alias='d',\n"
        "                                    policy_tag='attribution_eligible'):\n"
        "    return '', []\n",
        encoding="utf-8",
    )

    violations = find_violations(root=tmp_path)
    assert violations, "zero definitions of a gate symbol must red"
    joined = "\n".join(violations)
    assert "ZERO definitions" in joined
    assert "is_chunk_body_withheld" in joined


def test_tests_are_excluded_from_the_count(tmp_path: Path) -> None:
    """A test file defining a same-named local helper / fixture must NOT count as
    a second definition — exercising the gate is not re-forking it."""
    graph_dir = tmp_path / "substrate" / "graph"
    _write_canonical_gate(graph_dir)
    # A test file under substrate/graph that defines the symbol — must be ignored.
    (graph_dir / "test_local_helper.py").write_text(
        "def is_chunk_body_withheld(content_class, *, taken_down=False):\n"
        "    return False, None  # local test helper, not a real second owner\n",
        encoding="utf-8",
    )

    assert find_violations(root=tmp_path) == [], (
        "a test file's same-named helper must be excluded from the uniqueness "
        "count (tests legitimately define local helpers)"
    )
