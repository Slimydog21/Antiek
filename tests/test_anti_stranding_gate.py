"""Non-vacuity seed-and-catch tests for the SPR-01 anti-stranding gates.

SPR-01 (Antiek Flywheel Foundation) is THE gate that designs out the two
failure modes that killed the prior foundation: **stale-base stranding** (a
branch lapped ~+38 commits behind the line it forked from, never merged) and
**purgatory** (code shipped into a module nothing imports / a route nothing
links to). Two CI gates close those holes:

  * ``tools/lint/merge_age_gate.py``  — reds if base > N=25 behind origin/main.
  * ``tools/lint/reachability_gate.py`` — reds on a NEW zero-importer module /
    no-inbound-link route.

A gate is only worth anything if it can actually turn red. The rigor bar for
this sprint (honesty + non-vacuity) is: **for each gate, a seed that makes it
red, then a fix that makes it green** — invoking the REAL gate file as a
subprocess, never a stub. A passing test that cannot make the gate red is a
fake gate and fails the sprint.

Because the gates resolve their own repo root from ``__file__`` (3 parents up:
``<repo>/tools/lint/<gate>.py``), each seed test builds an ISOLATED tmp tree
that mirrors that layout, copies the real gate (and the ``tools/lints``
package it may depend on) into it, and runs the real gate there. This keeps the
seed module / synthetic git history from colliding with the live worktree and
guarantees the gate is exercised against exactly the condition under test.

Test (c) (shrink-only) exercises the real ``find_stale_baseline_entries``
semantics directly — the same public API the reachability baseline burn-down
rule is built on (docs/decisions/anti-stranding-gate.md).
"""

from __future__ import annotations

import os
import shutil
import subprocess
import sys
from pathlib import Path

import pytest

from tools.lints.baseline import (
    SCHEMA_VERSION,
    BaselineSchema,
    ViolationKey,
    find_stale_baseline_entries,
    load_baseline,
    write_baseline,
)

# Repo root: this file is <repo>/tests/test_anti_stranding_gate.py.
_REPO = Path(__file__).resolve().parent.parent
_MERGE_AGE_GATE = _REPO / "tools" / "lint" / "merge_age_gate.py"
_REACHABILITY_GATE = _REPO / "tools" / "lint" / "reachability_gate.py"
_REACHABILITY_BASELINE = _REPO / "tools" / "lints" / "baselines" / "reachability.json"


# --------------------------------------------------------------------------- #
# helpers
# --------------------------------------------------------------------------- #
def _run(cmd: list[str], cwd: Path) -> subprocess.CompletedProcess[str]:
    """Run a subprocess capturing text output. PYTHONPATH points at the tmp
    tree root so the copied gate can ``import tools.lints...`` if it needs to."""
    env = dict(os.environ)
    env["PYTHONPATH"] = str(cwd) + os.pathsep + env.get("PYTHONPATH", "")
    return subprocess.run(cmd, cwd=str(cwd), capture_output=True, text=True, env=env)


def _git(repo: Path, *args: str) -> subprocess.CompletedProcess[str]:
    return subprocess.run(
        ["git", "-C", str(repo), *args], capture_output=True, text=True
    )


def _mirror_tools(dest_root: Path, *, include_reachability: bool) -> None:
    """Copy the real gate file(s) + the tools/lints package into ``dest_root``
    at the same relative layout the gates resolve from (so each gate's
    ``_REPO`` points at ``dest_root``)."""
    (dest_root / "tools" / "lint").mkdir(parents=True, exist_ok=True)
    # The tools/lints package the gates / baseline helper may import.
    shutil.copytree(
        _REPO / "tools" / "lints",
        dest_root / "tools" / "lints",
        dirs_exist_ok=True,
    )
    # tools/__init__.py so `import tools.lints...` resolves from dest_root.
    tools_init = _REPO / "tools" / "__init__.py"
    if tools_init.exists():
        shutil.copy2(tools_init, dest_root / "tools" / "__init__.py")
    else:
        (dest_root / "tools" / "__init__.py").write_text("")
    shutil.copy2(_MERGE_AGE_GATE, dest_root / "tools" / "lint" / "merge_age_gate.py")
    lint_init = _REPO / "tools" / "lint" / "__init__.py"
    if lint_init.exists():
        shutil.copy2(lint_init, dest_root / "tools" / "lint" / "__init__.py")
    if include_reachability:
        shutil.copy2(
            _REACHABILITY_GATE, dest_root / "tools" / "lint" / "reachability_gate.py"
        )


# =========================================================================== #
# (a) Reachability gate — seed a zero-importer module -> red, add importer ->
#     green. Runs against the REAL reachability_gate.py as a subprocess.
#     Builder A owns that file; if it is not yet in the tree (parallel build),
#     the test SKIPS with a pending-integration message rather than passing
#     vacuously — the logic that WILL exercise it is fully written below.
# =========================================================================== #
_REACHABILITY_PRESENT = _REACHABILITY_GATE.exists()
_reach_skip = pytest.mark.skipif(
    not _REACHABILITY_PRESENT,
    reason=(
        "tools/lint/reachability_gate.py not yet in tree (Builder A, SPR-01). "
        "PENDING INTEGRATION — the seed-and-catch logic below is complete and "
        "exercises the real gate as a subprocess the moment it lands."
    ),
)


def _build_reachability_tree(root: Path) -> Path:
    """Build an isolated tmp tree mirroring the layout reachability_gate.py
    scans (apps/reading/src/reading-physics/augmentations/ + App.tsx), copy the
    real gate + tools/lints into it (so the gate's _REPO resolves to ``root``),
    and DROP any inherited baseline so a fresh mint grandfathers exactly the
    clean tree. Returns the gate path inside ``root``."""
    aug = root / "apps" / "reading" / "src" / "reading-physics" / "augmentations"
    src = root / "apps" / "reading" / "src"
    aug.mkdir(parents=True)
    _mirror_tools(root, include_reachability=True)
    # Mint must start from a clean baseline: remove any baseline A shipped so
    # the mint captures exactly THIS tree, not the live worktree's findings.
    inherited = root / "tools" / "lints" / "baselines" / "reachability.json"
    if inherited.exists():
        inherited.unlink()

    # A reachable augmentation (imported by the reader surface) — keeps the
    # clean tree genuinely clean so the seed is the ONLY new finding.
    (aug / "reachable.ts").write_text("export const reachable = 1;\n")
    (src / "MasterMdViewer.tsx").write_text(
        'import { reachable } from '
        '"./reading-physics/augmentations/reachable";\n'
        "export const App = () => reachable;\n"
    )
    # A route WITH an inbound link, so route-reachability is also clean.
    (src / "App.tsx").write_text(
        '<Route path="/read" />\n<Link to="/read">read</Link>\n'
    )
    return root / "tools" / "lint" / "reachability_gate.py"


@_reach_skip
def test_reachability_seeds_red_then_green(tmp_path: Path) -> None:
    """NEW zero-importer AUGMENTATION reds; adding an inbound import greens.

    Matches the real Builder-A contract: the gate scans .ts augmentation
    modules under apps/reading/src/reading-physics/augmentations/ for ZERO
    importers anywhere in apps/reading/src/. Isolated tmp tree: mint a clean
    baseline first (grandfather the clean tree), then introduce the seed.
    """
    root = tmp_path / "tree"
    gate = _build_reachability_tree(root)
    aug = root / "apps" / "reading" / "src" / "reading-physics" / "augmentations"
    src = root / "apps" / "reading" / "src"

    # 1. Mint the baseline on the clean tree (grandfather whatever is here now).
    mint = _run([sys.executable, str(gate), "--write-baseline"], cwd=root)
    assert mint.returncode == 0, (
        f"baseline mint failed: rc={mint.returncode}\n"
        f"stdout={mint.stdout}\nstderr={mint.stderr}"
    )

    # 2. Clean run after mint must be green (nothing NEW).
    clean = _run([sys.executable, str(gate)], cwd=root)
    assert clean.returncode == 0, (
        f"expected clean=0 after mint, got {clean.returncode}\n"
        f"stdout={clean.stdout}\nstderr={clean.stderr}"
    )

    # 3. SEED: a NEW zero-importer augmentation that nothing imports -> RED (1).
    (aug / "orphan_seed.ts").write_text("export const stranded = 42;\n")
    red = _run([sys.executable, str(gate)], cwd=root)
    assert red.returncode == 1, (
        f"expected RED=1 on a NEW zero-importer augmentation, got {red.returncode}\n"
        f"stdout={red.stdout}\nstderr={red.stderr}"
    )
    combined = red.stdout + red.stderr
    # Contract: prints `path:line: message` naming the offending module.
    assert "orphan_seed.ts" in combined, (
        f"expected the offending path in output, got:\n{combined}"
    )
    assert "orphan_seed.ts:1:" in combined, (
        f"expected the path:line: shape, got:\n{combined}"
    )

    # 4. FIX: add an inbound import from the surface -> GREEN (0). Same gate.
    (src / "MasterMdViewer.tsx").write_text(
        'import { reachable } from '
        '"./reading-physics/augmentations/reachable";\n'
        'import { stranded } from '
        '"./reading-physics/augmentations/orphan_seed";\n'
        "export const App = () => reachable + stranded;\n"
    )
    green = _run([sys.executable, str(gate)], cwd=root)
    assert green.returncode == 0, (
        f"expected GREEN=0 after adding an inbound import, got {green.returncode}\n"
        f"stdout={green.stdout}\nstderr={green.stderr}"
    )


@_reach_skip
def test_reachability_seeds_red_then_green_route(tmp_path: Path) -> None:
    """NEW no-inbound-link ROUTE reds; adding an inbound <Link> greens.

    Exercises the gate's SECOND finding shape (route reachability) so both
    enforced shapes have a fail-before/pass-after seed.
    """
    root = tmp_path / "tree"
    gate = _build_reachability_tree(root)
    src = root / "apps" / "reading" / "src"

    # Mint baseline on the clean tree (the one /read route already has a link).
    assert _run([sys.executable, str(gate), "--write-baseline"], cwd=root).returncode == 0

    # SEED: add a NEW route with NO inbound link/navigate -> RED (1).
    (src / "App.tsx").write_text(
        '<Route path="/read" />\n<Link to="/read">read</Link>\n'
        '<Route path="/orphan-route" />\n'
    )
    red = _run([sys.executable, str(gate)], cwd=root)
    assert red.returncode == 1, (
        f"expected RED=1 on a NEW no-inbound-link route, got {red.returncode}\n"
        f"stdout={red.stdout}\nstderr={red.stderr}"
    )
    combined = red.stdout + red.stderr
    assert "/orphan-route" in combined and "App.tsx:" in combined, (
        f"expected the offending route + path:line in output, got:\n{combined}"
    )

    # FIX: add an inbound <Link> to the new route -> GREEN (0).
    (src / "App.tsx").write_text(
        '<Route path="/read" />\n<Link to="/read">read</Link>\n'
        '<Route path="/orphan-route" />\n<Link to="/orphan-route">go</Link>\n'
    )
    green = _run([sys.executable, str(gate)], cwd=root)
    assert green.returncode == 0, (
        f"expected GREEN=0 after adding an inbound <Link>, got {green.returncode}\n"
        f"stdout={green.stdout}\nstderr={green.stderr}"
    )


# =========================================================================== #
# (b) Merge-age gate — synthesize a base 30 commits behind a fake origin/main
#     -> red with the distance in the message; rebase to tip -> green.
#     Runs against the REAL merge_age_gate.py (Builder B; already in tree).
# =========================================================================== #
def test_merge_age_seeds_red_at_30_behind_then_green(tmp_path: Path) -> None:
    if not _MERGE_AGE_GATE.exists():
        pytest.skip(
            "tools/lint/merge_age_gate.py not yet in tree (Builder B, SPR-01). "
            "PENDING INTEGRATION — logic below exercises the real gate."
        )
    work = tmp_path / "ma"
    origin = work / "origin.git"
    repo = work / "repo"
    work.mkdir()

    assert _git(work, "init", "-q", "--bare", str(origin)).returncode == 0
    assert _git(work, "init", "-q", str(repo)).returncode == 0
    _git(repo, "config", "user.email", "t@t.t")
    _git(repo, "config", "user.name", "t")
    _git(repo, "remote", "add", "origin", str(origin))

    # Place the real gate at tools/lint/merge_age_gate.py so its _REPO == repo.
    _mirror_tools(repo, include_reachability=False)
    gate = repo / "tools" / "lint" / "merge_age_gate.py"

    # Shared base commit.
    (repo / "f.txt").write_text("base\n")
    _git(repo, "add", "-A")
    _git(repo, "commit", "-q", "-m", "base")
    base = _git(repo, "rev-parse", "HEAD").stdout.strip()

    # Publish base as origin/main, then advance origin/main 30 commits WITHOUT
    # moving the base branch — i.e. a base that is 30 behind origin/main.
    assert _git(repo, "push", "-q", "origin", "HEAD:main").returncode == 0
    _git(repo, "checkout", "-q", "-b", "advance")
    for i in range(1, 31):
        (repo / f"c{i}.txt").write_text(f"c{i}\n")
        _git(repo, "add", "-A")
        _git(repo, "commit", "-q", "-m", f"c{i}")
    assert _git(repo, "push", "-q", "origin", "advance:main").returncode == 0

    # Detach onto the stale base (30 behind origin/main) + refresh the ref.
    _git(repo, "checkout", "-q", base)
    refresh = _git(
        repo,
        "fetch",
        "-q",
        "origin",
        "+refs/heads/main:refs/remotes/origin/main",
    )
    assert refresh.returncode == 0, refresh.stderr
    distance = _git(repo, "rev-list", "--count", f"{base}..origin/main")
    assert distance.returncode == 0 and distance.stdout.strip() == "30", (
        distance.stdout,
        distance.stderr,
    )

    # RED: 30 > N(=25) -> exit 1 with the distance in the message.
    red = _run([sys.executable, str(gate)], cwd=repo)
    assert red.returncode == 1, (
        f"expected RED=1 at 30-behind, got {red.returncode}\n"
        f"stdout={red.stdout}\nstderr={red.stderr}"
    )
    combined = red.stdout + red.stderr
    assert "30 commits behind origin/main" in combined, (
        f"expected the 30-commit distance in the message, got:\n{combined}"
    )
    assert "git rebase origin/main" in combined, (
        f"expected the rebase remediation in the message, got:\n{combined}"
    )

    # GREEN: rebase to tip (checkout origin/main) -> exit 0.
    _git(repo, "checkout", "-q", "origin/main")
    green = _run([sys.executable, str(gate)], cwd=repo)
    assert green.returncode == 0, (
        f"expected GREEN=0 at the tip, got {green.returncode}\n"
        f"stdout={green.stdout}\nstderr={green.stderr}"
    )


def test_merge_age_unresolvable_origin_fails_loud(tmp_path: Path) -> None:
    """Defensibility: no origin/main -> NON-ZERO (never a silent pass)."""
    if not _MERGE_AGE_GATE.exists():
        pytest.skip("merge_age_gate.py not yet in tree — PENDING INTEGRATION.")
    repo = tmp_path / "noremote"
    repo.mkdir()
    _git(repo, "init", "-q", str(repo))
    _git(repo, "config", "user.email", "t@t.t")
    _git(repo, "config", "user.name", "t")
    _mirror_tools(repo, include_reachability=False)
    gate = repo / "tools" / "lint" / "merge_age_gate.py"
    (repo / "f.txt").write_text("x\n")
    _git(repo, "add", "-A")
    _git(repo, "commit", "-q", "-m", "only")
    res = _run([sys.executable, str(gate)], cwd=repo)
    assert res.returncode != 0, (
        f"unresolvable origin/main MUST fail loud, got rc={res.returncode}\n"
        f"stdout={res.stdout}\nstderr={res.stderr}"
    )


def test_merge_age_N_constant_matches_doc() -> None:
    """No drift: the N in merge_age_gate.py (=25) == the N in the decision doc."""
    if not _MERGE_AGE_GATE.exists():
        pytest.skip("merge_age_gate.py not yet in tree — PENDING INTEGRATION.")
    import importlib.util

    spec = importlib.util.spec_from_file_location("_ma_gate", _MERGE_AGE_GATE)
    assert spec and spec.loader
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    assert mod.MAX_BEHIND == 25, mod.MAX_BEHIND

    doc = (_REPO / "docs" / "decisions" / "anti-stranding-gate.md").read_text()
    assert "N (= 25)" in doc or "N = 25" in doc, "doc must state N=25"
    # First-red arithmetic must be stated and consistent.
    assert "+26" in doc, "doc must state the first-red distance (N+1 = +26)"
    assert "+38" in doc, "doc must tie N to the prior +38 stranding"


# =========================================================================== #
# (c) Shrink-only baseline rule — a GROWN baseline (extra entry whose violation
#     no longer exists) is flagged stale/rejected; a SHRUNK baseline (fixed
#     entry removed) is accepted. Reuses find_stale_baseline_entries semantics
#     from tools/lints/baseline.py (the burn-down rule in the decision doc).
# =========================================================================== #
def _key(path: str, line: int = 1) -> ViolationKey:
    return ViolationKey(path=path, line=line, col=0, kind="reachability:zero-importer")


def test_grown_baseline_is_flagged_stale_shrink_only(tmp_path: Path) -> None:
    """A baseline that GREW (an entry whose violation no longer exists) is
    rejected: find_stale_baseline_entries returns the phantom entry."""
    bfile = tmp_path / "reachability.json"
    # Current real state: only `live.py` is still a violation.
    current = [_key("pkg/live.py")]
    # GROWN baseline: someone added `phantom.py` whose violation does not exist.
    grown = [_key("pkg/live.py"), _key("pkg/phantom.py")]
    write_baseline(bfile, lint="reachability", violations=grown)

    baseline = load_baseline(bfile)
    stale = find_stale_baseline_entries(current=current, baseline=baseline)
    # The phantom entry is flagged stale -> a grown baseline is forbidden.
    assert stale == [_key("pkg/phantom.py")], stale
    assert stale, "a grown baseline MUST be flagged stale (shrink-only rule)"


def test_shrunk_baseline_is_accepted_shrink_only(tmp_path: Path) -> None:
    """A baseline that SHRANK (a fixed entry removed) is accepted: no stale
    entries, and the remaining grandfathered violation is not re-flagged."""
    bfile = tmp_path / "reachability.json"
    # `fixed.py` gained an importer (no longer a violation); `still.py` remains.
    current = [_key("pkg/still.py")]
    # SHRUNK baseline: the operator removed the fixed entry, kept the live one.
    shrunk = [_key("pkg/still.py")]
    write_baseline(bfile, lint="reachability", violations=shrunk)

    baseline = load_baseline(bfile)
    stale = find_stale_baseline_entries(current=current, baseline=baseline)
    assert stale == [], f"shrunk baseline must have no stale entries, got {stale}"
    # And the surviving grandfathered entry is not treated as NEW.
    from tools.lints.baseline import filter_to_new_only

    new_only = filter_to_new_only(current=current, baseline=baseline)
    assert new_only == [], f"grandfathered entry must not be NEW, got {new_only}"


def test_shrink_only_fail_before_pass_after() -> None:
    """Explicit fail-before/pass-after for the shrink-only rule, mirroring the
    seed-and-catch shape of (a)/(b): the grown baseline is the 'red' (stale
    detected), shrinking it to match reality is the 'green' (no stale)."""
    baseline_grown = BaselineSchema(
        schema_version=SCHEMA_VERSION,
        lint="reachability",
        generated_at="",
        violations=[_key("pkg/live.py"), _key("pkg/phantom.py")],
    )
    current = [_key("pkg/live.py")]
    # RED: grown baseline -> stale phantom detected.
    assert find_stale_baseline_entries(current=current, baseline=baseline_grown)
    # GREEN: shrink the baseline to match reality -> no stale.
    baseline_shrunk = BaselineSchema(
        schema_version=SCHEMA_VERSION,
        lint="reachability",
        generated_at="",
        violations=[_key("pkg/live.py")],
    )
    assert not find_stale_baseline_entries(current=current, baseline=baseline_shrunk)
