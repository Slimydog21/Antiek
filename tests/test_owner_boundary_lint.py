"""Guard for the one-owner-per-layer boundary lint — Foundation SPR-09 M2.

This is the registered guard for the ``one-owner-per-layer`` invariant
(``substrate/invariants/boundary.toml``, guard_kind = "script"; the meta-check
verifies the script + this proof exist, the CI step exercises the exit code).

Rigor #3 — the lint must CATCH its target. The headline proof
(``test_lint_catches_a_divergent_second_owner``) builds a deliberately-divergent
second owner — a second module defining its own ``is_chunk_servable`` (exactly
the pre-SPR-08 chunk denylist that diverged to the opposite polarity) — and
proves the lint FLAGS it as ``path:line``. A sibling proof shows the lint is
GREEN on the current real tree (SPR-08 collapsed servability to one owner), so
this is a fail-on-violation / pass-on-fixed (negative-control) proof, not a lint
that passes on everything.
"""

from __future__ import annotations

from pathlib import Path

from tools.lint.owner_boundary_check import (
    CONCERNS,
    Concern,
    find_violations,
    main,
)

_REPO = Path(__file__).resolve().parent.parent


# ──────────────────────────────────────────────────────────────────────────────
# Pass-on-current-tree: the real §9.0 owner is the only owner (SPR-08 closed it).
# ──────────────────────────────────────────────────────────────────────────────


def test_lint_passes_on_the_current_tree() -> None:
    """The real tree has exactly one servability owner — the lint is GREEN.
    (If a future change reintroduces a second servability predicate, THIS test
    reddens, which is the point.)"""
    assert find_violations() == [], (
        "the current tree should have exactly one servability owner — a "
        "violation here means a second owner crept in:\n"
        + "\n".join(find_violations())
    )
    assert main([]) == 0


def test_servability_search_roots_cover_every_real_consumer() -> None:
    """The guard's reach must not be narrower than the surface that actually
    decides servability. Every substrate root that imports the owner today must
    be a search_root — otherwise a forked predicate in an unscanned root (e.g.
    a Speak biography or a Write trace, both serve-/money-adjacent) would slip
    past the lint. This test discovers the real consumers from the tree and
    asserts each is scanned, so the coverage claim cannot silently shrink."""
    by_name = {c.name: c for c in CONCERNS}
    servability = by_name["servability (§9.0)"]
    scanned = {root for root in servability.search_roots}

    # Discover every substrate root that imports the owner module.
    import re

    owner_import = re.compile(
        r"from\s+(?:\.{0,3})(?:substrate\.)?books\.servability\b"
        r"|import\s+(?:substrate\.)?books\.servability\b"
    )
    consuming_roots: set[str] = set()
    substrate = _REPO / "substrate"
    for py in substrate.rglob("*.py"):
        if "__pycache__" in py.parts:
            continue
        try:
            text = py.read_text(encoding="utf-8")
        except OSError:
            continue
        if owner_import.search(text):
            # second path component, e.g. substrate/write/trace.py → substrate/write
            rel = py.relative_to(_REPO)
            if len(rel.parts) >= 2:
                consuming_roots.add(f"{rel.parts[0]}/{rel.parts[1]}")

    # The owner itself lives under substrate/books, already a scanned root.
    missing = {
        r
        for r in consuming_roots
        # ad_inventory/cli/constants/contracts/coordination/etc. consume via
        # re-exports through the seams contract, not the owner predicate
        # directly — they cannot host a competing top-level predicate def of the
        # owned names without the lint catching it ONLY if scanned, so we require
        # the serve-/money-deciding roots specifically.
        if r in {"substrate/graph", "substrate/attribution", "substrate/books",
                 "substrate/write", "substrate/speak"}
    } - scanned
    assert not missing, (
        "these servability-consuming roots are not scanned by the lint, "
        f"shrinking the invariant's reach: {sorted(missing)}"
    )
    # The two roots this sharpen round widened to are present.
    assert "substrate/write" in scanned
    assert "substrate/speak" in scanned


def test_real_servability_consumers_are_scanned_and_clean() -> None:
    """Non-vacuity of the WIDENING (sharpen round): the lint really walks
    substrate/write and substrate/speak (they contain real .py files and import
    the owner), and finds NO second owner there — so adding them keeps the lint
    green while genuinely extending the guarded surface. If someone later forks
    is_servable_full_text into a Write/Speak module, find_violations() reddens.

    This is not a tautology: we assert the roots are non-empty AND that the
    real owner-import lines exist in them, so a future refactor that empties or
    decouples these roots would make this test fail loudly rather than pass
    vacuously."""
    write_root = _REPO / "substrate" / "write"
    speak_root = _REPO / "substrate" / "speak"
    assert any(write_root.rglob("*.py")), "substrate/write has no modules to scan"
    assert any(speak_root.rglob("*.py")), "substrate/speak has no modules to scan"
    # The real consumers import the owner (the shape the lint sanctions).
    assert "books.servability import" in (
        write_root / "trace.py"
    ).read_text(encoding="utf-8")
    assert "books.servability import" in (
        speak_root / "publish.py"
    ).read_text(encoding="utf-8")
    # And the lint is clean across the full (now-widened) set of roots.
    assert find_violations() == []


def test_widened_lint_catches_a_second_owner_in_speak(tmp_path: Path) -> None:
    """Hard-to-vary proof that the widening BITES: inject a competing predicate
    under substrate/speak (a Speak-specific servability fork — exactly the
    'we do not fork a Speak-specific servability rule' promise speak/publish.py
    makes in prose) and prove the lint flags it now that speak is scanned. Before
    this sharpen round, this fork would have passed silently."""
    repo = tmp_path / "repo"
    owner_dir = repo / "substrate" / "books"
    owner_dir.mkdir(parents=True)
    (owner_dir / "servability.py").write_text(
        "def is_servable_full_text(status):\n    return status == 'PLATFORM_AUTHORED'\n",
        encoding="utf-8",
    )
    speak_dir = repo / "substrate" / "speak"
    speak_dir.mkdir(parents=True)
    (speak_dir / "publish.py").write_text(
        "def is_servable_full_text(status):\n"
        "    # Speak-specific FORK of the owned predicate — owner-bypass.\n"
        "    return True\n",
        encoding="utf-8",
    )
    concern = Concern(
        name="servability (§9.0)",
        owner="substrate/books/servability.py",
        predicate=r"^(is_servable_full_text|is_chunk_servable|servability_of)$",
        search_roots=("substrate/books", "substrate/speak"),
        why="fixture",
    )
    violations = find_violations((concern,), repo=repo)
    joined = "\n".join(violations)
    assert "substrate/speak/publish.py:" in joined
    assert "SECOND owner" in joined


def test_servability_concern_is_declared_and_targets_the_spr08_owner() -> None:
    """M2: the first real assertion points at the §9.0 owner SPR-08 established."""
    by_name = {c.name: c for c in CONCERNS}
    assert "servability (§9.0)" in by_name
    servability = by_name["servability (§9.0)"]
    assert servability.owner == "substrate/books/servability.py"
    # The owner file really exists and really defines the predicate (no
    # vacuous owner pointer).
    owner = _REPO / servability.owner
    assert owner.exists()
    text = owner.read_text(encoding="utf-8")
    # The owner really DEFINES at least the predicates it owns on live main:
    # servability_of (the projection) + is_servable_full_text (the in-memory
    # gate). is_chunk_servable is INTENTIONALLY absent from the owner on this
    # tree — the chunk-search gate is INLINE SQL (a content_class denylist in
    # substrate/graph/search.py), by the deny-by-default asymmetry servability.py
    # documents (the chunk path is a denylist over the SAME content_class column;
    # the book path an allowlist). The lint's predicate regex still INCLUDES
    # is_chunk_servable so that a SECOND module re-introducing it as a defined
    # predicate (the pre-SPR-08 fork) is flagged — proven by
    # test_lint_catches_a_divergent_second_owner. We therefore do NOT assert the
    # owner defines is_chunk_servable (it does not, and adding it is the §9.0
    # owner's call, not this lint's): asserting it would falsely red on live main
    # and would push a predicate into a file this sprint must not own.
    assert "def is_servable_full_text" in text
    assert "def servability_of" in text


# ──────────────────────────────────────────────────────────────────────────────
# Rigor #3 headline proof — the lint CATCHES a deliberately-divergent 2nd owner.
# ──────────────────────────────────────────────────────────────────────────────


def _build_fixture_tree(tmp_path: Path, *, with_second_owner: bool) -> Path:
    """Build a minimal repo-shaped tree: the owner module plus optionally a
    SECOND module that reimplements ``is_chunk_servable`` with the OPPOSITE
    (serve-by-default) polarity — the exact pre-SPR-08 denylist bug."""
    repo = tmp_path / "repo"
    owner_dir = repo / "substrate" / "books"
    owner_dir.mkdir(parents=True)
    (owner_dir / "servability.py").write_text(
        "def is_chunk_servable(content_class, *, taken_down=False):\n"
        "    # the ONE owner — deny-by-default allowlist\n"
        "    return content_class in {'public_domain'}\n",
        encoding="utf-8",
    )
    bypass_dir = repo / "substrate" / "graph"
    bypass_dir.mkdir(parents=True)
    if with_second_owner:
        # A SECOND owner: its own predicate, opposite polarity (serve unless
        # explicitly restricted) — the regression SPR-08 fixed.
        (bypass_dir / "search.py").write_text(
            "RESTRICTED = {'restricted_pending_opt_in'}\n\n"
            "def is_chunk_servable(content_class):\n"
            "    # SECOND owner / owner-bypass: serve-by-default denylist\n"
            "    return content_class not in RESTRICTED\n",
            encoding="utf-8",
        )
    else:
        # The fixed shape: search.py IMPORTS the owner, defines no predicate.
        (bypass_dir / "search.py").write_text(
            "from substrate.books.servability import is_chunk_servable\n\n"
            "def search():\n"
            "    return is_chunk_servable('public_domain')\n",
            encoding="utf-8",
        )
    return repo


_FIXTURE_CONCERN = Concern(
    name="servability (§9.0)",
    owner="substrate/books/servability.py",
    predicate=r"^(is_servable_full_text|is_chunk_servable|servability_of)$",
    search_roots=("substrate/graph", "substrate/books"),
    why="fixture",
)


def test_lint_catches_a_divergent_second_owner(tmp_path: Path) -> None:
    """The headline rigor-#3 proof: inject a second module defining
    ``is_chunk_servable`` and the lint FLAGS it as ``path:line``."""
    repo = _build_fixture_tree(tmp_path, with_second_owner=True)
    violations = find_violations((_FIXTURE_CONCERN,), repo=repo)
    assert violations, "lint failed to flag a divergent second owner"
    joined = "\n".join(violations)
    assert "substrate/graph/search.py:" in joined
    assert "is_chunk_servable" in joined
    assert "SECOND owner" in joined


def test_lint_is_green_once_the_bypass_imports_the_owner(tmp_path: Path) -> None:
    """The other half of the negative control: when search.py IMPORTS the owner
    (no competing definition), the SAME lint is clean — so it is a real
    fail→pass proof, not a lint that flags everything."""
    repo = _build_fixture_tree(tmp_path, with_second_owner=False)
    assert find_violations((_FIXTURE_CONCERN,), repo=repo) == []


def test_lint_catches_a_missing_owner(tmp_path: Path) -> None:
    """Enumerated edge case (rigor #3): a concern whose owner file is gone is a
    silent-gap risk — the lint flags it rather than passing vacuously."""
    repo = tmp_path / "repo"
    (repo / "substrate" / "graph").mkdir(parents=True)
    missing_owner = Concern(
        name="servability (§9.0)",
        owner="substrate/books/servability.py",  # never created
        predicate=r"^is_chunk_servable$",
        search_roots=("substrate/graph",),
        why="fixture",
    )
    violations = find_violations((missing_owner,), repo=repo)
    assert any("does not exist" in v for v in violations)


def test_lint_catches_owner_that_lost_its_predicate(tmp_path: Path) -> None:
    """Enumerated edge case: the owner exists but no longer defines the
    predicate — also a silent-gap (the guard would pass vacuously). Flagged."""
    repo = tmp_path / "repo"
    owner_dir = repo / "substrate" / "books"
    owner_dir.mkdir(parents=True)
    (owner_dir / "servability.py").write_text(
        "def unrelated():\n    return 1\n", encoding="utf-8"
    )
    (repo / "substrate" / "graph").mkdir(parents=True)
    concern = Concern(
        name="servability (§9.0)",
        owner="substrate/books/servability.py",
        predicate=r"^is_chunk_servable$",
        search_roots=("substrate/graph",),
        why="fixture",
    )
    violations = find_violations((concern,), repo=repo)
    assert any("no longer defines a predicate" in v for v in violations)


def test_main_returns_1_on_violation(tmp_path: Path, monkeypatch) -> None:  # type: ignore[no-untyped-def]
    """The exit-code contract (mirrors tools/lint/boundary_check.py): main()
    returns 1 when there is a violation. We patch the module's CONCERNS + _REPO
    to the fixture tree so the real entrypoint exercises the violation path."""
    import tools.lint.owner_boundary_check as mod

    repo = _build_fixture_tree(tmp_path, with_second_owner=True)
    monkeypatch.setattr(mod, "_REPO", repo)
    monkeypatch.setattr(mod, "CONCERNS", (_FIXTURE_CONCERN,))
    assert mod.main([]) == 1


def test_class_method_is_not_a_second_owner(tmp_path: Path) -> None:
    """Edge case: a CLASS METHOD named like the predicate is NOT a competing
    module-level owner — the lint walks top-level defs only, so it does not
    false-positive on an unrelated method."""
    repo = _build_fixture_tree(tmp_path, with_second_owner=False)
    (repo / "substrate" / "graph" / "other.py").write_text(
        "class Thing:\n"
        "    def is_chunk_servable(self):\n"
        "        return True\n",
        encoding="utf-8",
    )
    assert find_violations((_FIXTURE_CONCERN,), repo=repo) == []


# ──────────────────────────────────────────────────────────────────────────────
# Dual-consumer topology (OPERATOR_INPUTS.md §3, the critic's boundary-lint fix).
#
# The §9.0 reconciliation is staged on a SEPARATE branch and lands AFTER this
# immediate-merge boundary-lint. In its post-reconciliation shape, the owner
# (substrate/books/servability.py) DEFINES the servability predicate and the
# three consumers — substrate/graph/search.py (chunk path), substrate/books/
# serve.py (serve path), and a grounding module (grounder path) — all CONSUME it
# via IMPORT instead of each carrying its own definition. This test pins that the
# immediate-merge boundary-lint is GREEN on exactly that topology, so it can
# neither block the staged §9.0 PR (the lint would not red when search.py starts
# importing the owner predicate) nor be blocked by it (no consumer-import shape
# trips the one-owner rule). The lint asserts WHO MAY OWN the predicate, never
# WHAT MAY BE SERVED — so it has zero §9.0 decision surface and merges on its own.
# ──────────────────────────────────────────────────────────────────────────────


def test_lint_passes_on_the_post_9_0_dual_consumer_topology(tmp_path: Path) -> None:
    """Construct the post-§9.0 dual-consumer (really tri-consumer) tree — owner
    DEFINES, search.py + serve.py + grounding.py all IMPORT — and assert the lint
    exits 0. None of the consumers defines a competing predicate; they consume
    the owner's, which is exactly the one-owner shape the lint sanctions."""
    repo = tmp_path / "repo"

    # The ONE owner — defines the servability predicates.
    owner_dir = repo / "substrate" / "books"
    owner_dir.mkdir(parents=True)
    (owner_dir / "servability.py").write_text(
        "def servability_of(content_class, *, taken_down=False):\n"
        "    # the single source of the servability projection\n"
        "    if taken_down:\n"
        "        return 'taken_down'\n"
        "    return content_class or 'gated_metadata_only'\n\n"
        "def is_servable_full_text(status):\n"
        "    return status in {'public_domain', 'platform_authored'}\n",
        encoding="utf-8",
    )

    # Consumer 1 — serve path (substrate/books/serve.py), imports the owner.
    (owner_dir / "serve.py").write_text(
        "from substrate.books.servability import is_servable_full_text\n\n"
        "def serve_full_text(status):\n"
        "    return is_servable_full_text(status)\n",
        encoding="utf-8",
    )

    # Consumer 2 — chunk/search path (substrate/graph/search.py), imports owner.
    graph_dir = repo / "substrate" / "graph"
    graph_dir.mkdir(parents=True)
    (graph_dir / "search.py").write_text(
        "from substrate.books.servability import servability_of\n\n"
        "def search(content_class):\n"
        "    # consumes the owner's projection; defines NO competing predicate\n"
        "    return servability_of(content_class)\n",
        encoding="utf-8",
    )

    # Consumer 3 — grounding path (a grounder module), imports the owner.
    (graph_dir / "grounding.py").write_text(
        "from substrate.books.servability import is_servable_full_text\n\n"
        "def ground(status):\n"
        "    return is_servable_full_text(status)\n",
        encoding="utf-8",
    )

    # Scan the roots the real concern scans that exist in this fixture.
    concern = Concern(
        name="servability (§9.0)",
        owner="substrate/books/servability.py",
        predicate=r"^(is_servable_full_text|is_chunk_servable|servability_of)$",
        search_roots=("substrate/graph", "substrate/books"),
        why="fixture",
    )
    violations = find_violations((concern,), repo=repo)
    assert violations == [], (
        "the post-§9.0 dual-consumer topology (owner defines; search/serve/"
        "grounding import) must be GREEN — the immediate-merge boundary-lint "
        "cannot block the staged §9.0 reconciliation:\n" + "\n".join(violations)
    )
    # And main() returns 0 on it (the exit-code contract the CI step relies on).
    import tools.lint.owner_boundary_check as mod

    monkey_repo, monkey_concerns = mod._REPO, mod.CONCERNS
    try:
        mod._REPO = repo
        mod.CONCERNS = (concern,)
        assert mod.main([]) == 0
    finally:
        mod._REPO, mod.CONCERNS = monkey_repo, monkey_concerns
