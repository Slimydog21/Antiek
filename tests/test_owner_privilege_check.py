"""Guard for the owner-privilege boundary lint — Activation SPR-owner-read.

Rigor #3 — the lint must CATCH its target. The headline proof
(``test_lint_catches_a_planted_privileged_literal``) plants a non-allowlisted
call site that passes ``policy_tag="operator_only"`` straight into ``search(...)``
WITHOUT an auth check — the exact §9.0 bypass-handed-in-unchecked failure mode —
and proves the lint FLAGS it as ``path:line``. A sibling proof shows the lint is
GREEN on the current real tree (the two owner-read sites resolve the tag through
``_owner_read_policy_tag(request)``, not a literal), so this is a
fail-on-violation / pass-on-clean negative control, not a lint that flags
everything.
"""

from __future__ import annotations

import textwrap
from pathlib import Path

from tools.lint.owner_privilege_check import find_violations, main


# ──────────────────────────────────────────────────────────────────────────────
# Pass-on-current-tree: the real owner-read sites resolve the tag via the helper.
# ──────────────────────────────────────────────────────────────────────────────


def test_lint_passes_on_the_current_tree() -> None:
    """The real tree has no privileged policy_tag LITERAL passed to a guarded
    retrieval callee outside the allowlist — the lint is GREEN. (The two
    owner-read sites pass ``_owner_read_policy_tag(request)``, a CALL, not a
    literal; if a future change hard-codes ``policy_tag="operator_only"`` at a
    non-allowlisted call site, THIS test reddens — which is the point.)"""
    violations = find_violations()
    assert violations == [], (
        "the current tree should have no privileged policy_tag literal at a "
        "non-allowlisted retrieval call site:\n" + "\n".join(violations)
    )
    assert main() == 0


def test_real_owner_read_sites_resolve_tag_via_helper_not_a_literal() -> None:
    """Non-vacuity of the GREEN result: the two legitimate owner-read call sites
    genuinely pass the tag through ``_owner_read_policy_tag(request)`` (a call),
    NOT a bare literal — so the lint is clean because of the resolved-via-auth
    shape, not because the call sites are absent. If a refactor inlined the
    literal there, the allowlist (defense in depth) still covers books.py, but
    this asserts the real sites take the auth-checked path."""
    books = (
        Path(__file__).resolve().parent.parent
        / "interfaces" / "research" / "api" / "books.py"
    ).read_text(encoding="utf-8")
    # The resolved, auth-checked shape — a helper CALL, not a literal tag.
    assert "policy_tag=_owner_read_policy_tag(request)" in books
    # And the helper is the only place the privileged tag is named as a value.
    assert '_OWNER_READ_POLICY_TAG = "operator_only"' in books


# ──────────────────────────────────────────────────────────────────────────────
# Rigor #3 headline proof — the lint CATCHES a planted unchecked privileged tag.
# ──────────────────────────────────────────────────────────────────────────────


def _write_tree(tmp_path: Path, rel: str, body: str) -> Path:
    """Write a repo-shaped file and return the repo root."""
    repo = tmp_path / "repo"
    target = repo / rel
    target.parent.mkdir(parents=True, exist_ok=True)
    target.write_text(textwrap.dedent(body), encoding="utf-8")
    return repo


def test_lint_catches_a_planted_privileged_literal(tmp_path: Path) -> None:
    """A non-allowlisted endpoint passing ``policy_tag="operator_only"`` straight
    into ``search(...)`` — the §9.0 bypass handed in WITHOUT an auth check — is
    FLAGGED as path:line."""
    repo = _write_tree(
        tmp_path,
        "interfaces/research/api/leaky.py",
        '''
        from substrate.graph.search import search

        def leaky_endpoint(con, q, model):
            # NO auth check — privileged tag hard-coded. The exact bypass.
            return search(con, q, model=model, policy_tag="operator_only")
        ''',
    )
    violations = find_violations(repo)
    assert violations, "lint failed to flag a planted unchecked privileged literal"
    joined = "\n".join(violations)
    assert "interfaces/research/api/leaky.py:" in joined
    assert "search" in joined
    assert "BYPASS" in joined


def test_lint_catches_private_research_literal(tmp_path: Path) -> None:
    """The OTHER privileged tag (``private_research``), passed to the OTHER
    guarded callee (``answer_book_question``), is caught too."""
    repo = _write_tree(
        tmp_path,
        "interfaces/research/api/leaky_ask.py",
        '''
        from substrate.books.book_qa import answer_book_question

        def leaky_ask(con, document_id, question, model):
            return answer_book_question(
                con, document_id=document_id, question=question, model=model,
                policy_tag="private_research",  # bypass, no auth check
            )
        ''',
    )
    violations = find_violations(repo)
    joined = "\n".join(violations)
    assert "interfaces/research/api/leaky_ask.py:" in joined
    assert "answer_book_question" in joined


def test_lint_catches_named_constant_form(tmp_path: Path) -> None:
    """The named-constant form ``policy_tag=_OWNER_READ_POLICY_TAG`` (whose value
    IS ``operator_only``) is the same bypass as the string literal — flagged."""
    repo = _write_tree(
        tmp_path,
        "interfaces/research/api/leaky_named.py",
        '''
        from substrate.graph.search import search

        _OWNER_READ_POLICY_TAG = "operator_only"

        def leaky(con, q, model):
            return search(con, q, model=model, policy_tag=_OWNER_READ_POLICY_TAG)
        ''',
    )
    violations = find_violations(repo)
    assert violations, "lint failed to flag the named-constant privileged tag"
    assert "interfaces/research/api/leaky_named.py:" in "\n".join(violations)


def test_lint_is_green_when_tag_resolved_via_helper(tmp_path: Path) -> None:
    """The other half of the negative control: a call site that resolves the tag
    through an auth-checked helper CALL (the shape the real owner-read sites use)
    is NOT flagged — so the lint is a real fail→pass control, not one that flags
    every privileged-looking call."""
    repo = _write_tree(
        tmp_path,
        "interfaces/research/api/safe.py",
        '''
        from substrate.graph.search import search

        def _owner_read_policy_tag(request):
            return "operator_only" if request else "attribution_eligible"

        def safe_endpoint(con, q, model, request):
            # Tag resolved through the auth-checked helper — NOT a literal.
            return search(con, q, model=model, policy_tag=_owner_read_policy_tag(request))
        ''',
    )
    assert find_violations(repo) == []


def test_lint_ignores_privileged_literal_at_unguarded_callee(tmp_path: Path) -> None:
    """A privileged literal passed to some OTHER function (not search /
    answer_book_question) is not this lint's concern — it never reaches the §9.0
    retrieval gate. Scoping to the two guarded callees keeps the lint precise."""
    repo = _write_tree(
        tmp_path,
        "interfaces/research/api/other.py",
        '''
        def some_other_helper(*, policy_tag):
            return policy_tag

        def caller():
            # Not a retrieval callee — not flagged.
            return some_other_helper(policy_tag="operator_only")
        ''',
    )
    assert find_violations(repo) == []


def test_lint_skips_test_files_and_scanners(tmp_path: Path) -> None:
    """Test files (which pass privileged literals to exercise the owner path) and
    lint scanners (which NAME the literals in their own logic) are skipped — the
    same allowlisting precedent every sibling scanner follows."""
    repo = tmp_path / "repo"
    # A test file with the exact bypass shape — must be skipped.
    test_dir = repo / "tests"
    test_dir.mkdir(parents=True)
    (test_dir / "test_thing.py").write_text(
        "from substrate.graph.search import search\n\n"
        "def test_owner_path(con, q, model):\n"
        '    return search(con, q, model=model, policy_tag="operator_only")\n',
        encoding="utf-8",
    )
    # A lint scanner naming the literal — must be skipped.
    lint_dir = repo / "tools" / "lint"
    lint_dir.mkdir(parents=True)
    (lint_dir / "some_check.py").write_text(
        '_PRIVILEGED = {"operator_only", "private_research"}\n'
        "def search(*a, **k):\n"
        '    return search(policy_tag="operator_only")\n',
        encoding="utf-8",
    )
    assert find_violations(repo) == []


def test_main_returns_1_on_violation(tmp_path: Path, monkeypatch) -> None:  # type: ignore[no-untyped-def]
    """The exit-code contract (mirrors tools/lint/serve_guard_check.py): main()
    returns 1 when there is a violation. Patch the module's _REPO to the fixture
    tree so the real entrypoint exercises the violation path."""
    import tools.lint.owner_privilege_check as mod

    repo = _write_tree(
        tmp_path,
        "interfaces/research/api/leaky.py",
        '''
        from substrate.graph.search import search

        def leaky(con, q, model):
            return search(con, q, model=model, policy_tag="operator_only")
        ''',
    )
    monkeypatch.setattr(mod, "_REPO", repo)
    assert mod.main() == 1
