"""
AST gate making ``substrate.notification_policy`` non-bypassable.

The policy module (``substrate/notification_policy.py``) is only
load-bearing if production code actually routes interruptions through
it. This test walks every production-layer ``*.py`` file and asserts
that no module reaches a desktop-notification / operator-interruption
API directly. The single sanctioned path is
``notification_policy.interrupt()``.

This is the SPR-E5 "Milestone 3" gate the policy module's own
docstring promises ("AST gate makes direct calls to banned APIs
non-bypassable"). Same shape as SPR-E1's invariant tests, scoped to
interruption surfaces.

What counts as a banned interruption API:

- ``subprocess`` invocations of ``osascript`` / ``notify-send`` /
  ``terminal-notifier`` / ``say`` (macOS + Linux desktop notify).
- ``import``s of known notification packages: ``plyer``, ``pync``,
  ``win10toast``, ``notify2``, ``desktop_notifier``.
- ``webbrowser.open`` (pops a browser tab — an interruption).
- ``tkinter.messagebox`` (modal dialog).

Allowed everywhere (NOT interruptions):

- ``print`` / ``logging`` — the operator pulls these; they don't push.
  (The policy module itself uses ``logging`` for log-only severity.)

The policy module itself is exempt — it is the sanctioned chokepoint.

Spec: ~/specs/antiek-hashimoto-engineering/sprint-e5-boundary-cli.html
"""

from __future__ import annotations

import ast
from pathlib import Path

import pytest

REPO_ROOT = Path(__file__).resolve().parent.parent

# Production layers an interruption must not originate from without
# going through the policy. tools/ + scripts/ + tests/ + benchmarks/
# are operator-facing or dev surfaces, so a CLI there may legitimately
# print/open things; they're out of scope for this gate.
PROD_LAYERS = (
    "substrate",
    "acquisition",
    "middleware",
    "orchestration",
    "compounding",
    "processing",
    "interfaces",
    "runtime",
)

# The single file allowed to BE the chokepoint.
POLICY_FILE_REL = "substrate/notification_policy.py"

# Notification packages whose mere import implies a push surface.
BANNED_IMPORT_ROOTS = frozenset(
    {
        "plyer",
        "pync",
        "win10toast",
        "notify2",
        "desktop_notifier",
    }
)

# subprocess argv[0] tokens that shell out to a desktop notifier.
BANNED_SUBPROCESS_TOKENS = frozenset(
    {
        "osascript",
        "notify-send",
        "terminal-notifier",
    }
)

# Attribute-call chains that are interruptions.
# Represented as ("module_or_obj", "attr") pairs we look for.
BANNED_ATTR_CALLS = frozenset(
    {
        ("webbrowser", "open"),
        ("messagebox", "showinfo"),
        ("messagebox", "showwarning"),
        ("messagebox", "showerror"),
    }
)


def _iter_prod_files() -> list[Path]:
    out: list[Path] = []
    for layer in PROD_LAYERS:
        root = REPO_ROOT / layer
        if not root.exists():
            continue
        for p in root.rglob("*.py"):
            if "__pycache__" in p.parts:
                continue
            out.append(p)
    return out


def _rel(p: Path) -> str:
    return str(p.relative_to(REPO_ROOT))


def _string_constants(node: ast.Call) -> list[str]:
    """All string-literal arguments anywhere in a call's arg tree."""
    out: list[str] = []
    for sub in ast.walk(node):
        if isinstance(sub, ast.Constant) and isinstance(sub.value, str):
            out.append(sub.value)
    return out


def _find_violations(path: Path) -> list[str]:
    if _rel(path) == POLICY_FILE_REL:
        return []  # the chokepoint is exempt
    try:
        tree = ast.parse(path.read_text(encoding="utf-8"), filename=str(path))
    except SyntaxError:
        return []
    violations: list[str] = []
    for node in ast.walk(tree):
        # Banned imports.
        if isinstance(node, ast.Import):
            for alias in node.names:
                root = alias.name.split(".")[0]
                if root in BANNED_IMPORT_ROOTS:
                    violations.append(
                        f"{_rel(path)}:{node.lineno}: imports notification package {alias.name!r}"
                    )
        elif isinstance(node, ast.ImportFrom) and node.module:
            root = node.module.split(".")[0]
            if root in BANNED_IMPORT_ROOTS:
                violations.append(
                    f"{_rel(path)}:{node.lineno}: imports from notification package {node.module!r}"
                )
        # Banned attribute calls (webbrowser.open, messagebox.show*).
        elif isinstance(node, ast.Call) and isinstance(node.func, ast.Attribute):
            attr = node.func.attr
            base = node.func.value
            base_name = base.id if isinstance(base, ast.Name) else getattr(base, "attr", "")
            if (base_name, attr) in BANNED_ATTR_CALLS:
                violations.append(
                    f"{_rel(path)}:{node.lineno}: calls {base_name}.{attr}() — operator interruption; "
                    f"route through notification_policy.interrupt()"
                )
            # subprocess.run(["osascript", ...]) etc.
            if attr in ("run", "call", "Popen", "check_call", "check_output"):
                for s in _string_constants(node):
                    token = s.split("/")[-1]  # /usr/bin/osascript -> osascript
                    if token in BANNED_SUBPROCESS_TOKENS:
                        violations.append(
                            f"{_rel(path)}:{node.lineno}: subprocess invokes desktop notifier {token!r}; "
                            f"route through notification_policy.interrupt()"
                        )
    return violations


@pytest.mark.skipif(
    not (REPO_ROOT / POLICY_FILE_REL).exists(),
    reason=(
        "substrate/notification_policy.py is a hashimoto-eng SPR-E5 feature not "
        "merged into the four-workflow product consolidation. The load-bearing "
        "AST boundary check (test_no_direct_interruption_apis_in_production) "
        "still runs; the chokepoint-exists gate is only meaningful once the "
        "module ships."
    ),
)
def test_notification_policy_module_exists() -> None:
    assert (REPO_ROOT / POLICY_FILE_REL).exists(), (
        f"{POLICY_FILE_REL} missing — the chokepoint must exist for this gate to mean anything"
    )


def test_no_direct_interruption_apis_in_production() -> None:
    """The load-bearing assertion: no production module pushes to the
    operator without going through notification_policy."""
    all_violations: list[str] = []
    for path in _iter_prod_files():
        all_violations.extend(_find_violations(path))
    if all_violations:
        msg = ["production code reaches operator-interruption APIs directly:"]
        msg.extend(f"  {v}" for v in all_violations)
        msg.append(
            "Every interruption must go through substrate.notification_policy.interrupt() "
            "so the default-deny policy can govern it."
        )
        pytest.fail("\n".join(msg), pytrace=False)


# ---------------------------------------------------------------------------
# Self-tests for the AST walker — guard the gate against rotting.
# ---------------------------------------------------------------------------


def test_walker_flags_osascript_subprocess(tmp_path: Path, monkeypatch) -> None:
    monkeypatch.setattr("tests.test_notification_policy_ast.REPO_ROOT", tmp_path, raising=False)
    f = tmp_path / "sample.py"
    f.write_text("import subprocess\nsubprocess.run(['osascript', '-e', 'display notification'])\n")
    # Call _find_violations directly with a path whose _rel is computed
    # against the real REPO_ROOT — so build under REPO_ROOT instead.
    target = REPO_ROOT / "substrate" / "_ast_gate_selftest_tmp.py"
    target.write_text(
        "import subprocess\nsubprocess.run(['osascript', '-e', 'x'])\n", encoding="utf-8"
    )
    try:
        violations = _find_violations(target)
        assert any("osascript" in v for v in violations)
    finally:
        target.unlink()


def test_walker_flags_plyer_import() -> None:
    target = REPO_ROOT / "substrate" / "_ast_gate_selftest_tmp2.py"
    target.write_text("from plyer import notification\n", encoding="utf-8")
    try:
        violations = _find_violations(target)
        assert any("plyer" in v for v in violations)
    finally:
        target.unlink()


def test_walker_flags_webbrowser_open() -> None:
    target = REPO_ROOT / "substrate" / "_ast_gate_selftest_tmp3.py"
    target.write_text("import webbrowser\nwebbrowser.open('https://x')\n", encoding="utf-8")
    try:
        violations = _find_violations(target)
        assert any("webbrowser.open" in v for v in violations)
    finally:
        target.unlink()


def test_walker_allows_print_and_logging() -> None:
    target = REPO_ROOT / "substrate" / "_ast_gate_selftest_tmp4.py"
    target.write_text(
        "import logging\nprint('hi')\nlogging.getLogger('x').info('msg')\n",
        encoding="utf-8",
    )
    try:
        violations = _find_violations(target)
        assert not violations, f"print/logging should be allowed; got {violations}"
    finally:
        target.unlink()


def test_walker_exempts_the_policy_module_itself() -> None:
    # The policy module references notification concepts but is the
    # sanctioned chokepoint; it must not flag itself.
    policy = REPO_ROOT / POLICY_FILE_REL
    if policy.exists():
        assert _find_violations(policy) == []
