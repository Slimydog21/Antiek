"""Seed-and-catch contract tests for the Python-surface reachability gate.

``tools/lint/reachability_gate_py.py`` is the backend sibling of the reading-
surface reachability gate. It closes the "build the module, never wire it"
failure that shipped three green-CI-but-unreachable money-safety lanes this
session (#712 completion, #710 spend guard, #739→#742 exec authority).

A gate is worth nothing if it cannot actually turn red. The rigor bar (honesty
+ non-vacuity, mirroring ``tests/test_anti_stranding_gate.py``) is: **for each
check, a seed that makes the REAL gate red, then a fix that makes it green** —
invoking the real gate file as a subprocess, never a stub.

Because the gate resolves its own repo root from ``__file__`` (3 parents up:
``<repo>/tools/lint/reachability_gate_py.py``), each test builds an ISOLATED tmp
tree mirroring that layout, copies the real gate + the ``tools/lints`` package
into it (so the gate's ``_REPO`` points at the tmp tree), and runs the real gate
there. This keeps the seed modules from colliding with the live worktree and
guarantees the gate is exercised against exactly the condition under test.

The three motivating symbols (``execute_authorized_call``,
``create_multimedia_execution_router``, ``complete_spawn``) live on UNMERGED
branches, not on ``main`` — so live re-detection of *those exact* symbols cannot
run here. The ``#739-742-shape`` fixture below reconstructs their shape (an
exported ``execute_authorized_call``-like symbol with no caller + a
``create_*_router`` factory never mounted) and proves the gate reports BOTH,
run with NO baseline — the fixture IS the re-detection proof.
"""

from __future__ import annotations

import json
import os
import shutil
import subprocess
import sys
from pathlib import Path

# Repo root: this file is <repo>/tests/test_reachability_gate_py.py.
_REPO = Path(__file__).resolve().parent.parent
_GATE = _REPO / "tools" / "lint" / "reachability_gate_py.py"


# --------------------------------------------------------------------------- #
# helpers
# --------------------------------------------------------------------------- #
def _run(cmd: list[str], cwd: Path) -> subprocess.CompletedProcess[str]:
    """Run a subprocess capturing text output. PYTHONPATH points at the tmp
    tree root so the copied gate can ``import tools.lints...``."""
    env = dict(os.environ)
    env["PYTHONPATH"] = str(cwd) + os.pathsep + env.get("PYTHONPATH", "")
    return subprocess.run(cmd, cwd=str(cwd), capture_output=True, text=True, env=env)


def _mirror_gate(root: Path) -> Path:
    """Copy the real gate + the tools/lints package into ``root`` at the layout
    the gate resolves ``_REPO`` from. Returns the gate path inside ``root``."""
    (root / "tools" / "lint").mkdir(parents=True, exist_ok=True)
    shutil.copytree(
        _REPO / "tools" / "lints", root / "tools" / "lints", dirs_exist_ok=True
    )
    # Drop any inherited baseline so a fresh mint captures exactly THIS tree.
    inherited = root / "tools" / "lints" / "baselines" / "reachability_py.json"
    if inherited.exists():
        inherited.unlink()
    tools_init = _REPO / "tools" / "__init__.py"
    if tools_init.exists():
        shutil.copy2(tools_init, root / "tools" / "__init__.py")
    else:
        (root / "tools" / "__init__.py").write_text("")
    lint_init = _REPO / "tools" / "lint" / "__init__.py"
    if lint_init.exists():
        shutil.copy2(lint_init, root / "tools" / "lint" / "__init__.py")
    shutil.copy2(_GATE, root / "tools" / "lint" / "reachability_gate_py.py")
    return root / "tools" / "lint" / "reachability_gate_py.py"


def _write(path: Path, text: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(text, encoding="utf-8")


# The clean baseline the seed tests grandfather from: a mounted router and a
# called enforcement export, so the tree is genuinely clean before the seed.
_CLEAN_ROUTES = '''\
from fastapi import APIRouter, FastAPI

good_router = APIRouter(prefix="/good")


@good_router.get("/ping")
def ping() -> dict[str, str]:
    return {"ok": "yes"}


def register_good_routes(app: FastAPI) -> None:
    app.include_router(good_router)
'''

_CLEAN_ENFORCEMENT = '''\
__all__ = ["enforce_the_gate"]


def enforce_the_gate(x: int) -> int:
    return x + 1
'''

# A non-test product module that CALLS the clean enforcement export (so it is
# referenced) — mirrors a real product path consuming the seam.
_CLEAN_CONSUMER = '''\
from fastapi import FastAPI
from interfaces.research.api.good_routes import register_good_routes
from substrate.enforcement.gatekeeper import enforce_the_gate


def run(x: int) -> int:
    return enforce_the_gate(x)


def create_app() -> FastAPI:
    app = FastAPI()
    _ = run(1)
    register_good_routes(app)
    return app
'''


def _build_clean_tree(root: Path) -> Path:
    gate = _mirror_gate(root)
    _write(root / "interfaces" / "research" / "api" / "good_routes.py", _CLEAN_ROUTES)
    _write(
        root / "substrate" / "enforcement" / "gatekeeper.py", _CLEAN_ENFORCEMENT
    )
    _write(root / "interfaces" / "research" / "api" / "app.py", _CLEAN_CONSUMER)
    return gate


# =========================================================================== #
# (a) Check B — seed an uncalled __all__ enforcement export -> red; add a
#     non-test caller -> green. Real gate, subprocess.
# =========================================================================== #
def test_uncalled_enforcement_export_reds_then_greens(tmp_path: Path) -> None:
    root = tmp_path / "tree"
    root.mkdir()
    gate = _build_clean_tree(root)

    # 1. Mint the baseline on the clean tree.
    mint = _run([sys.executable, str(gate), "--write-baseline"], cwd=root)
    assert mint.returncode == 0, f"mint failed:\n{mint.stdout}\n{mint.stderr}"

    # 2. Clean run after mint must be green.
    clean = _run([sys.executable, str(gate)], cwd=root)
    assert clean.returncode == 0, (
        f"expected clean=0 after mint, got {clean.returncode}\n"
        f"{clean.stdout}\n{clean.stderr}"
    )

    # 3. SEED: a NEW exported enforcement callable nothing (non-test) calls -> RED.
    #    'execute_authorized_call' matches the lexicon (execut + authoriz) and is
    #    only exercised by a test file -> zero non-test callers.
    _write(
        root / "substrate" / "multimedia" / "execution_authorization.py",
        '__all__ = ["execute_authorized_call"]\n\n\n'
        "def execute_authorized_call(payload: dict) -> dict:\n"
        "    return payload\n",
    )
    # A test that DOES call it — must NOT rescue it from the finding.
    _write(
        root / "tests" / "test_exec_auth.py",
        "from substrate.multimedia.execution_authorization import "
        "execute_authorized_call\n\n\n"
        "def test_it() -> None:\n"
        "    assert execute_authorized_call({}) == {}\n",
    )
    red = _run([sys.executable, str(gate)], cwd=root)
    assert red.returncode == 1, (
        f"expected RED=1 on a NEW uncalled enforcement export, got "
        f"{red.returncode}\n{red.stdout}\n{red.stderr}"
    )
    combined = red.stdout + red.stderr
    assert "execute_authorized_call" in combined, combined
    assert "execution_authorization.py:" in combined, combined

    # 4. FIX: a non-test product module calls it -> GREEN.
    _write(
        root / "interfaces" / "research" / "api" / "exec_caller.py",
        "from fastapi import FastAPI\n"
        "from substrate.multimedia.execution_authorization import "
        "execute_authorized_call\n\n\n"
        "def create_app() -> FastAPI:\n"
        "    app = FastAPI()\n"
        "    _ = execute_authorized_call({})\n"
        "    return app\n\n\n"
        "app = create_app()\n",
    )
    green = _run([sys.executable, str(gate)], cwd=root)
    assert green.returncode == 0, (
        f"expected GREEN=0 after adding a non-test caller, got "
        f"{green.returncode}\n{green.stdout}\n{green.stderr}"
    )


# =========================================================================== #
# (b) Check A — seed an unmounted router factory -> red; mount it via
#     include_router -> green. Real gate, subprocess.
# =========================================================================== #
def test_unmounted_router_reds_then_greens(tmp_path: Path) -> None:
    root = tmp_path / "tree"
    root.mkdir()
    gate = _build_clean_tree(root)

    assert (
        _run([sys.executable, str(gate), "--write-baseline"], cwd=root).returncode == 0
    )
    assert _run([sys.executable, str(gate)], cwd=root).returncode == 0

    # SEED: a router-factory in *_routes.py that nothing include_router's -> RED.
    _write(
        root / "interfaces" / "research" / "api" / "orphan_routes.py",
        "from fastapi import APIRouter\n\n\n"
        "def create_orphan_router() -> APIRouter:\n"
        '    router = APIRouter(prefix="/orphan")\n\n'
        '    @router.get("/x")\n'
        "    def x() -> dict:\n"
        '        return {"x": 1}\n\n'
        "    return router\n",
    )
    red = _run([sys.executable, str(gate)], cwd=root)
    assert red.returncode == 1, (
        f"expected RED=1 on a NEW unmounted router, got {red.returncode}\n"
        f"{red.stdout}\n{red.stderr}"
    )
    combined = red.stdout + red.stderr
    assert "create_orphan_router" in combined, combined
    assert "orphan_routes.py:" in combined, combined

    # FIX: mount it via include_router in a non-test module -> GREEN.
    _write(
        root / "interfaces" / "research" / "api" / "mount.py",
        "from fastapi import FastAPI\n"
        "from .orphan_routes import create_orphan_router\n\n\n"
        "def create_app() -> FastAPI:\n"
        "    app = FastAPI()\n"
        "    app.include_router(create_orphan_router())\n"
        "    return app\n\n\n"
        "app = create_app()\n",
    )
    green = _run([sys.executable, str(gate)], cwd=root)
    assert green.returncode == 0, (
        f"expected GREEN=0 after mounting the router, got {green.returncode}\n"
        f"{green.stdout}\n{green.stderr}"
    )


def test_uncalled_registration_wrapper_reds_then_greens(tmp_path: Path) -> None:
    """A local include_router is not production wiring until its wrapper runs."""
    root = tmp_path / "tree"
    root.mkdir()
    gate = _build_clean_tree(root)
    assert (
        _run([sys.executable, str(gate), "--write-baseline"], cwd=root).returncode == 0
    )

    _write(
        root / "interfaces" / "research" / "api" / "dormant_routes.py",
        "from fastapi import APIRouter, FastAPI\n\n"
        "dormant_router = APIRouter(prefix='/dormant')\n\n\n"
        "def register_dormant_routes(app: FastAPI) -> None:\n"
        "    app.include_router(dormant_router)\n",
    )
    red = _run([sys.executable, str(gate)], cwd=root)
    assert red.returncode == 1, red.stdout + red.stderr
    combined = red.stdout + red.stderr
    assert "register_dormant_routes" in combined
    assert "registration wrapper" in combined

    _write(
        root / "interfaces" / "research" / "api" / "mount_dormant.py",
        "from fastapi import FastAPI\n"
        "from .dormant_routes import register_dormant_routes as mount_dormant\n\n\n"
        "def create_app() -> FastAPI:\n"
        "    app = FastAPI()\n"
        "    mount_dormant(app)\n"
        "    return app\n\n\n"
        "app = create_app()\n",
    )
    green = _run([sys.executable, str(gate)], cwd=root)
    assert green.returncode == 0, green.stdout + green.stderr


# =========================================================================== #
# (c) #739-742-shape fixture — the exec-authority lane's shape (an exported
#     execute_authorized_call-like symbol with NO caller + a create_*_router
#     never mounted), run WITH NO BASELINE, must report BOTH. This is the live
#     re-detection proof for the motivating cases, which live on unmerged
#     branches and cannot be re-detected against main directly.
# =========================================================================== #
def test_739_742_shape_detected_without_baseline(tmp_path: Path) -> None:
    root = tmp_path / "tree"
    root.mkdir()
    gate = _mirror_gate(root)

    # The exported-but-uncalled authority symbol (Check B).
    _write(
        root / "substrate" / "multimedia" / "execution_authorization.py",
        '__all__ = ["execute_authorized_call", "make_hmac_receipt"]\n\n\n'
        "def execute_authorized_call(payload: dict) -> dict:\n"
        '    """21 green tests, HMAC receipts correct — but 0 non-test callers."""\n'
        "    return payload\n\n\n"
        "def make_hmac_receipt(payload: dict) -> str:\n"
        '    return "receipt"\n',
    )
    # The router factory never include_router'd (Check A).
    _write(
        root / "interfaces" / "research" / "api" / "multimedia_execution_routes.py",
        "from fastapi import APIRouter\n\n\n"
        "def create_multimedia_execution_router() -> APIRouter:\n"
        '    router = APIRouter(prefix="/multimedia/execution")\n\n'
        '    @router.post("/authorize")\n'
        "    def authorize() -> dict:\n"
        '        return {"ok": True}\n\n'
        "    return router\n",
    )
    # Tests that exercise both (must NOT rescue them).
    _write(
        root / "tests" / "test_exec_authority.py",
        "from substrate.multimedia.execution_authorization import "
        "execute_authorized_call\n"
        "from interfaces.research.api.multimedia_execution_routes import "
        "create_multimedia_execution_router\n\n\n"
        "def test_call() -> None:\n"
        "    assert execute_authorized_call({}) == {}\n\n\n"
        "def test_router() -> None:\n"
        "    assert create_multimedia_execution_router() is not None\n",
    )

    # Run WITH NO baseline: every finding is NEW -> RED, and BOTH shapes report.
    res = _run([sys.executable, str(gate)], cwd=root)
    assert res.returncode == 1, (
        f"expected RED=1 with no baseline, got {res.returncode}\n"
        f"{res.stdout}\n{res.stderr}"
    )
    combined = res.stdout + res.stderr
    assert "execute_authorized_call" in combined, (
        f"Check B must re-detect the uncalled authority export:\n{combined}"
    )
    assert "create_multimedia_execution_router" in combined, (
        f"Check A must re-detect the unmounted execution router:\n{combined}"
    )


# =========================================================================== #
# (d) The lexicon is token-prefix, not raw substring: 'aggregate_annual_payouts'
#     (which merely CONTAINS 'gate') must NOT be flagged, while a genuine
#     'guard'-prefixed export IS. Guards the false-positive class the lexicon
#     refinement fixed.
# =========================================================================== #
def test_lexicon_token_prefix_not_substring(tmp_path: Path) -> None:
    root = tmp_path / "tree"
    root.mkdir()
    gate = _mirror_gate(root)

    # 'aggregate_annual_payouts' contains 'gate' as a substring but no TOKEN
    # starts with a lexicon entry -> out of scope -> not flagged even uncalled.
    _write(
        root / "substrate" / "billing" / "tax_reports.py",
        '__all__ = ["aggregate_annual_payouts"]\n\n\n'
        "def aggregate_annual_payouts(rows: list) -> int:\n"
        "    return len(rows)\n",
    )
    # 'guarded_send' -> token 'guarded' starts with 'guard' -> in scope, uncalled.
    _write(
        root / "substrate" / "payouts" / "contact_guard.py",
        '__all__ = ["guarded_send"]\n\n\n'
        "def guarded_send(msg: str) -> None:\n"
        "    return None\n",
    )
    res = _run([sys.executable, str(gate)], cwd=root)
    assert res.returncode == 1, f"{res.stdout}\n{res.stderr}"
    combined = res.stdout + res.stderr
    assert "guarded_send" in combined, f"guard-prefixed export must flag:\n{combined}"
    assert "aggregate_annual_payouts" not in combined, (
        f"'aggregate' (mere substring of 'gate') must NOT flag:\n{combined}"
    )


# =========================================================================== #
# (e) FIX #1 — shrink-only --write-baseline is ENFORCED, not help text. A run
#     that would ADD a key is refused (exit 1, key printed, baseline unchanged);
#     --force-baseline is the loud escape.
# =========================================================================== #
def test_write_baseline_refuses_new_key_without_force(tmp_path: Path) -> None:
    root = tmp_path / "tree"
    root.mkdir()
    gate = _build_clean_tree(root)
    baseline = root / "tools" / "lints" / "baselines" / "reachability_py.json"

    # Mint a clean (empty) baseline first — no new keys, so no --force needed.
    assert (
        _run(
            [sys.executable, str(gate), "--write-baseline", str(baseline)], cwd=root
        ).returncode
        == 0
    )

    # SEED a NEW uncalled enforcement export.
    _write(
        root / "substrate" / "authz" / "authority.py",
        '__all__ = ["execute_authorized_call"]\n\n\n'
        "def execute_authorized_call(x: int) -> int:\n    return x\n",
    )

    # --write-baseline WITHOUT --force must REFUSE (exit 1) and NOT add the key.
    refuse = _run(
        [sys.executable, str(gate), "--write-baseline", str(baseline)], cwd=root
    )
    assert refuse.returncode == 1, (
        f"shrink-only add must be refused, got {refuse.returncode}\n"
        f"{refuse.stdout}\n{refuse.stderr}"
    )
    combined = refuse.stdout + refuse.stderr
    assert "shrink-only" in combined, combined
    assert "execute_authorized_call" in combined, combined
    data = json.loads(baseline.read_text())
    assert all(
        "execute_authorized_call" not in v["kind"] for v in data["violations"]
    ), f"refused key must NOT be in the baseline:\n{data}"

    # --force-baseline is the loud escape: it DOES write the new key.
    forced = _run(
        [
            sys.executable,
            str(gate),
            "--write-baseline",
            str(baseline),
            "--force-baseline",
        ],
        cwd=root,
    )
    assert forced.returncode == 0, f"{forced.stdout}\n{forced.stderr}"
    data2 = json.loads(baseline.read_text())
    assert any(
        "execute_authorized_call" in v["kind"] for v in data2["violations"]
    ), f"--force-baseline must add the key:\n{data2}"


def test_write_baseline_removal_only_shrink_succeeds(tmp_path: Path) -> None:
    """A shrink (current findings are a SUBSET of the baseline — a fixed entry
    dropped) is accepted without --force: removals are always allowed."""
    root = tmp_path / "tree"
    root.mkdir()
    gate = _build_clean_tree(root)
    baseline = root / "tools" / "lints" / "baselines" / "reachability_py.json"

    # One genuine uncalled export -> exactly one current finding.
    _write(
        root / "substrate" / "authz" / "authority.py",
        '__all__ = ["guard_the_thing"]\n\n\n'
        "def guard_the_thing(x: int) -> int:\n    return x\n",
    )
    # Force-mint the real finding, then hand-add a PHANTOM (already-fixed) entry.
    assert (
        _run(
            [
                sys.executable,
                str(gate),
                "--write-baseline",
                str(baseline),
                "--force-baseline",
            ],
            cwd=root,
        ).returncode
        == 0
    )
    data = json.loads(baseline.read_text())
    data["violations"].append(
        {
            "col": 0,
            "kind": "export:uncalled:phantom_fixed",
            "line": 1,
            "path": "substrate/authz/authority.py",
        }
    )
    baseline.write_text(json.dumps(data))

    # --write-baseline WITHOUT --force: current (1 real) ⊆ baseline (2) -> allowed;
    # the phantom is dropped (shrink), the live entry kept.
    shrink = _run(
        [sys.executable, str(gate), "--write-baseline", str(baseline)], cwd=root
    )
    assert shrink.returncode == 0, (
        f"removal-only shrink must succeed, got {shrink.returncode}\n"
        f"{shrink.stdout}\n{shrink.stderr}"
    )
    kinds = {v["kind"] for v in json.loads(baseline.read_text())["violations"]}
    assert "export:uncalled:phantom_fixed" not in kinds, f"phantom must be dropped: {kinds}"
    assert any("guard_the_thing" in k for k in kinds), f"live entry must remain: {kinds}"


# =========================================================================== #
# (f) FIX #2 — an IMPORT is not a caller. An import-only reference must NOT
#     clear the finding; an actual call clears it.
# =========================================================================== #
def test_import_only_reference_still_flagged_call_clears(tmp_path: Path) -> None:
    root = tmp_path / "tree"
    root.mkdir()
    gate = _mirror_gate(root)

    _write(
        root / "substrate" / "authz" / "execution.py",
        '__all__ = ["execute_authorized_call"]\n\n\n'
        "def execute_authorized_call(x: int) -> int:\n    return x\n",
    )
    # A non-test product module that IMPORTS but NEVER CALLS it (the evasion).
    _write(
        root / "interfaces" / "research" / "api" / "importer.py",
        "from substrate.authz.execution import execute_authorized_call  # noqa: F401\n",
    )
    red = _run([sys.executable, str(gate)], cwd=root)  # no baseline -> all NEW
    assert red.returncode == 1, (
        f"import-only reference must NOT clear the finding, got {red.returncode}\n"
        f"{red.stdout}\n{red.stderr}"
    )
    assert "execute_authorized_call" in red.stdout + red.stderr

    # Add an actual CALL in a product module -> cleared.
    _write(
        root / "interfaces" / "research" / "api" / "caller.py",
        "from fastapi import FastAPI\n"
        "from substrate.authz.execution import execute_authorized_call\n\n\n"
        "def create_app() -> FastAPI:\n"
        "    app = FastAPI()\n"
        "    _ = execute_authorized_call(1)\n"
        "    return app\n\n\n"
        "app = create_app()\n",
    )
    green = _run([sys.executable, str(gate)], cwd=root)
    assert green.returncode == 0, (
        f"a real call must clear the finding, got {green.returncode}\n"
        f"{green.stdout}\n{green.stderr}"
    )


# =========================================================================== #
# (g) FIX #3 — module-aware mount detection. Two modules each define a `router`;
#     one is mounted, one is not. The unmounted one must still be flagged (the
#     mounted same-named router must NOT mask it via global bare-name collision).
# =========================================================================== #
def test_module_aware_mount_no_bare_name_collision(tmp_path: Path) -> None:
    root = tmp_path / "tree"
    root.mkdir()
    gate = _mirror_gate(root)

    # Module A: defines `router`, mounted same-module.
    _write(
        root / "interfaces" / "research" / "api" / "a_routes.py",
        "from fastapi import APIRouter, FastAPI\n\n"
        "app = FastAPI()\n"
        'router = APIRouter(prefix="/a")\n\n\n'
        "app.include_router(router)\n",
    )
    # Module B: defines an identically-named `router`, NEVER mounted.
    _write(
        root / "interfaces" / "research" / "api" / "b_routes.py",
        'from fastapi import APIRouter\n\nrouter = APIRouter(prefix="/b")\n',
    )
    res = _run([sys.executable, str(gate)], cwd=root)  # no baseline -> NEW
    assert res.returncode == 1, (
        f"B's unmounted router must red, got {res.returncode}\n"
        f"{res.stdout}\n{res.stderr}"
    )
    combined = res.stdout + res.stderr
    assert "b_routes.py:" in combined, (
        f"B's router must be flagged despite A's mounted same-named router:\n{combined}"
    )
    assert "a_routes.py:" not in combined, (
        f"A's router is mounted same-module and must NOT be flagged:\n{combined}"
    )

    # Also assert the cross-module import mount clears: a third module mounts B
    # by importing FROM b_routes.
    _write(
        root / "interfaces" / "research" / "api" / "mount_b.py",
        "from fastapi import FastAPI\n"
        "from .b_routes import router as b_router\n\n\n"
        "def create_app() -> FastAPI:\n"
        "    app = FastAPI()\n"
        "    app.include_router(b_router)\n"
        "    return app\n\n\n"
        "app = create_app()\n",
    )
    green = _run([sys.executable, str(gate)], cwd=root)
    assert green.returncode == 0, (
        f"cross-module import mount must clear B, got {green.returncode}\n"
        f"{green.stdout}\n{green.stderr}"
    )


# =========================================================================== #
# (h) FIX #2r-1 — Check B aliased-call must CLEAR the original. An
#     ``import X as run; run()`` credits X (not a false 'uncalled'); an aliased
#     import that is NEVER used still flags X (fix #2 preserved).
# =========================================================================== #
def test_aliased_call_clears_unused_alias_import_still_flags(tmp_path: Path) -> None:
    root = tmp_path / "tree"
    root.mkdir()
    gate = _mirror_gate(root)

    _write(
        root / "substrate" / "authz" / "execution.py",
        '__all__ = ["execute_authorized_call"]\n\n\n'
        "def execute_authorized_call(x: int) -> int:\n    return x\n",
    )
    # A non-test product module that IMPORTS it under an alias but NEVER uses it.
    _write(
        root / "interfaces" / "research" / "api" / "unused_alias.py",
        "from substrate.authz.execution import execute_authorized_call as run  "
        "# noqa: F401\n",
    )
    red = _run([sys.executable, str(gate)], cwd=root)  # no baseline -> all NEW
    assert red.returncode == 1, (
        f"an UNUSED aliased import must NOT clear the finding, got "
        f"{red.returncode}\n{red.stdout}\n{red.stderr}"
    )
    assert "execute_authorized_call" in red.stdout + red.stderr

    # Now actually CALL it through the alias -> the ORIGINAL is credited -> green.
    _write(
        root / "interfaces" / "research" / "api" / "aliased_caller.py",
        "from fastapi import FastAPI\n"
        "from substrate.authz.execution import execute_authorized_call as run\n\n\n"
        "def create_app() -> FastAPI:\n"
        "    app = FastAPI()\n"
        "    _ = run(1)\n"
        "    return app\n\n\n"
        "app = create_app()\n",
    )
    green = _run([sys.executable, str(gate)], cwd=root)
    assert green.returncode == 0, (
        f"a call through an alias must credit the original symbol, got "
        f"{green.returncode}\n{green.stdout}\n{green.stderr}"
    )


# =========================================================================== #
# (i) FIX #2r-2 — Check A package-barrel re-export. A router defined in a
#     submodule, re-exported through the package ``__init__``, and mounted via
#     the package import must NOT be flagged; an unmounted sibling still IS.
# =========================================================================== #
def test_barrel_reexported_mount_not_flagged_sibling_still_flagged(
    tmp_path: Path,
) -> None:
    root = tmp_path / "tree"
    root.mkdir()
    gate = _mirror_gate(root)
    api = root / "interfaces" / "x" / "api"

    # Router defined in a submodule.
    _write(
        api / "widget_routes.py",
        'from fastapi import APIRouter\n\nrouter = APIRouter(prefix="/widget")\n',
    )
    # An unmounted sibling router in another submodule.
    _write(
        api / "sibling_routes.py",
        'from fastapi import APIRouter\n\nrouter = APIRouter(prefix="/sibling")\n',
    )
    # Package barrel re-exports the widget router (but NOT the sibling).
    _write(api / "__init__.py", "from .widget_routes import router\n")
    # App mounts via the PACKAGE import (the barrel), not the submodule.
    _write(
        root / "app.py",
        "from fastapi import FastAPI\n"
        "from interfaces.x.api import router\n\n\n"
        "def create_app() -> FastAPI:\n"
        "    app = FastAPI()\n"
        "    app.include_router(router)\n"
        "    return app\n\n\n"
        "app = create_app()\n",
    )
    res = _run([sys.executable, str(gate)], cwd=root)  # no baseline -> NEW
    assert res.returncode == 1, (
        f"the unmounted sibling must red, got {res.returncode}\n"
        f"{res.stdout}\n{res.stderr}"
    )
    combined = res.stdout + res.stderr
    # The barrel-mounted widget router must be resolved through __init__ -> NOT flagged.
    assert "widget_routes.py:" not in combined, (
        f"barrel-re-exported + mounted router must NOT be flagged:\n{combined}"
    )
    # The unmounted sibling must still be flagged.
    assert "sibling_routes.py:" in combined, (
        f"the unmounted sibling router must still be flagged:\n{combined}"
    )


# =========================================================================== #
# (j) FIX #3r — fail-safe bias. An app that imports `router` from a package
#     whose __init__ does NOT CONFIRM a module-level re-export of it (here: the
#     re-export is function-scoped, so at runtime `from x.api import router`
#     would fail) must NOT credit the mount. The defining router stays FLAGGED —
#     Check A errs toward false-positive, never false-negative.
# =========================================================================== #
def test_unconfirmed_reexport_does_not_credit_mount(tmp_path: Path) -> None:
    root = tmp_path / "tree"
    root.mkdir()
    gate = _mirror_gate(root)
    api = root / "interfaces" / "x" / "api"

    _write(
        api / "widget_routes.py",
        'from fastapi import APIRouter\n\nrouter = APIRouter(prefix="/widget")\n',
    )
    # Package __init__ does NOT re-export `router` at module level — the import
    # is buried inside a function, so `from x.api import router` is NOT satisfied
    # at import time. The gate must NOT trust this as a re-export edge.
    _write(
        api / "__init__.py",
        "def _lazy() -> None:\n    from .widget_routes import router  # noqa: F401\n",
    )
    # App mounts via the package import (which would ImportError at runtime).
    _write(
        root / "app.py",
        "from fastapi import FastAPI\n"
        "from interfaces.x.api import router\n\n\n"
        "def create_app() -> FastAPI:\n"
        "    app = FastAPI()\n"
        "    app.include_router(router)\n"
        "    return app\n\n\n"
        "app = create_app()\n",
    )
    res = _run([sys.executable, str(gate)], cwd=root)  # no baseline -> NEW
    assert res.returncode == 1, (
        f"unconfirmed (function-scoped) re-export must NOT credit the mount, got "
        f"{res.returncode}\n{res.stdout}\n{res.stderr}"
    )
    combined = res.stdout + res.stderr
    assert "widget_routes.py:" in combined, (
        f"router must stay FLAGGED when no confirmed module-level re-export "
        f"edge exists (fail-safe):\n{combined}"
    )

    # Contrast: promote the re-export to MODULE LEVEL (a real barrel) -> credited.
    _write(api / "__init__.py", "from .widget_routes import router\n")
    green = _run([sys.executable, str(gate)], cwd=root)
    assert green.returncode == 0, (
        f"a confirmed module-level re-export must clear the mount, got "
        f"{green.returncode}\n{green.stdout}\n{green.stderr}"
    )


def test_include_router_inside_dormant_helper_does_not_mount(tmp_path: Path) -> None:
    """An uncalled ordinary helper must not credit router mounting."""
    root = tmp_path / "tree"
    root.mkdir()
    gate = _mirror_gate(root)

    _write(
        root / "interfaces" / "research" / "api" / "helper_routes.py",
        "from fastapi import APIRouter, FastAPI\n\n"
        "router = APIRouter(prefix='/helper')\n\n\n"
        "def dormant_helper(app: FastAPI) -> None:\n"
        "    app.include_router(router)\n",
    )
    res = _run([sys.executable, str(gate)], cwd=root)
    assert res.returncode == 1, res.stdout + res.stderr
    combined = res.stdout + res.stderr
    assert "helper_routes.py:" in combined
    assert "router product 'router'" in combined


def test_dormant_helper_enforcement_reference_does_not_credit_symbol(
    tmp_path: Path,
) -> None:
    """Calls inside arbitrary uncalled helpers and if False do not clear reachability."""
    root = tmp_path / "tree"
    root.mkdir()
    gate = _mirror_gate(root)

    _write(
        root / "substrate" / "authz" / "execution.py",
        '__all__ = ["execute_authorized_call"]\n\n\n'
        "def execute_authorized_call(x: int) -> int:\n    return x\n",
    )
    _write(
        root / "interfaces" / "research" / "api" / "dead_refs.py",
        "from substrate.authz.execution import execute_authorized_call\n\n\n"
        "def dormant_helper() -> None:\n"
        "    execute_authorized_call(1)\n\n\n"
        "if False:\n"
        "    execute_authorized_call(2)\n",
    )
    red = _run([sys.executable, str(gate)], cwd=root)
    assert red.returncode == 1, red.stdout + red.stderr
    assert "execute_authorized_call" in red.stdout + red.stderr

    _write(
        root / "interfaces" / "research" / "api" / "live_ref.py",
        "from fastapi import FastAPI\n"
        "from substrate.authz.execution import execute_authorized_call\n\n\n"
        "def create_app() -> FastAPI:\n"
        "    app = FastAPI()\n"
        "    _ = execute_authorized_call(1)\n"
        "    return app\n\n\n"
        "app = create_app()\n",
    )
    green = _run([sys.executable, str(gate)], cwd=root)
    assert green.returncode == 0, green.stdout + green.stderr


def test_sidecar_create_app_does_not_credit_enforcement_until_real_entrypoint(
    tmp_path: Path,
) -> None:
    """A never-loaded sidecar FastAPI factory is not a product root."""
    root = tmp_path / "tree"
    root.mkdir()
    gate = _mirror_gate(root)

    _write(
        root / "substrate" / "authz" / "execution.py",
        '__all__ = ["execute_authorized_call"]\n\n\n'
        "def execute_authorized_call(x: int) -> int:\n"
        "    return x\n",
    )
    _write(
        root / "interfaces" / "research" / "api" / "sidecar.py",
        "from fastapi import FastAPI\n"
        "from substrate.authz.execution import execute_authorized_call as run_authz\n\n\n"
        "def create_app() -> FastAPI:\n"
        "    app = FastAPI()\n"
        "    _ = run_authz(1)\n"
        "    return app\n",
    )

    red = _run([sys.executable, str(gate)], cwd=root)
    assert red.returncode == 1, red.stdout + red.stderr
    combined = red.stdout + red.stderr
    assert "execute_authorized_call" in combined

    _write(
        root / "interfaces" / "research" / "api" / "app.py",
        "from fastapi import FastAPI\n"
        "from substrate.authz.execution import execute_authorized_call as run_authz\n\n\n"
        "def create_app() -> FastAPI:\n"
        "    app = FastAPI()\n"
        "    _ = run_authz(1)\n"
        "    return app\n\n\n"
        "app = create_app()\n",
    )
    green = _run([sys.executable, str(gate)], cwd=root)
    assert green.returncode == 0, green.stdout + green.stderr


def test_type_checking_and_main_guards_do_not_credit_calls_or_mounts(
    tmp_path: Path,
) -> None:
    """Static non-product guards cannot clear enforcement or router findings."""
    root = tmp_path / "tree"
    root.mkdir()
    gate = _mirror_gate(root)

    _write(
        root / "substrate" / "authz" / "execution.py",
        '__all__ = ["execute_authorized_call"]\n\n\n'
        "def execute_authorized_call(x: int) -> int:\n"
        "    return x\n",
    )
    _write(
        root / "interfaces" / "research" / "api" / "guarded_refs.py",
        "import typing as typing_mod\n"
        "from typing import TYPE_CHECKING as TC\n"
        "from fastapi import APIRouter, FastAPI\n"
        "from substrate.authz.execution import execute_authorized_call\n\n\n"
        "router = APIRouter(prefix='/guarded')\n\n\n"
        "if TC:\n"
        "    execute_authorized_call(1)\n"
        "    app = FastAPI()\n"
        "    app.include_router(router)\n\n\n"
        "if typing_mod.TYPE_CHECKING:\n"
        "    execute_authorized_call(2)\n\n\n"
        "if __name__ == '__main__':\n"
        "    execute_authorized_call(3)\n"
        "    app = FastAPI()\n"
        "    app.include_router(router)\n",
    )

    red = _run([sys.executable, str(gate)], cwd=root)
    assert red.returncode == 1, red.stdout + red.stderr
    combined = red.stdout + red.stderr
    assert "execute_authorized_call" in combined
    assert "guarded_refs.py:" in combined
    assert "router product 'router'" in combined


def test_exported_uncalled_helper_body_does_not_credit_enforcement_export(
    tmp_path: Path,
) -> None:
    """An arbitrary exported helper is not a reachability root."""
    root = tmp_path / "tree"
    root.mkdir()
    gate = _mirror_gate(root)

    _write(
        root / "substrate" / "policies" / "review_tools.py",
        '__all__ = ["format_status_report", "guard_released_payload"]\n\n\n'
        "def format_status_report(payload: dict) -> dict:\n"
        "    return guard_released_payload(payload)\n\n\n"
        "def guard_released_payload(payload: dict) -> dict:\n"
        "    return payload\n",
    )
    red = _run([sys.executable, str(gate)], cwd=root)
    assert red.returncode == 1, red.stdout + red.stderr
    combined = red.stdout + red.stderr
    assert "guard_released_payload" in combined
    assert "format_status_report" not in combined

    _write(
        root / "interfaces" / "research" / "api" / "live_gate.py",
        "from fastapi import FastAPI\n"
        "from substrate.policies.review_tools import guard_released_payload\n\n\n"
        "def create_app() -> FastAPI:\n"
        "    app = FastAPI()\n"
        "    _ = guard_released_payload({})\n"
        "    return app\n\n\n"
        "app = create_app()\n",
    )
    green = _run([sys.executable, str(gate)], cwd=root)
    assert green.returncode == 0, green.stdout + green.stderr


def test_exported_uninstantiated_class_method_does_not_credit_enforcement_export(
    tmp_path: Path,
) -> None:
    """Methods on an arbitrary exported class are not reachability roots."""
    root = tmp_path / "tree"
    root.mkdir()
    gate = _mirror_gate(root)

    _write(
        root / "substrate" / "safety" / "approval_gate.py",
        '__all__ = ["ApprovalNotebook", "enforce_release_approval"]\n\n\n'
        "class ApprovalNotebook:\n"
        "    def write_note(self, payload: dict) -> dict:\n"
        "        return enforce_release_approval(payload)\n\n\n"
        "def enforce_release_approval(payload: dict) -> dict:\n"
        "    return payload\n",
    )
    red = _run([sys.executable, str(gate)], cwd=root)
    assert red.returncode == 1, red.stdout + red.stderr
    combined = red.stdout + red.stderr
    assert "enforce_release_approval" in combined
    assert "ApprovalNotebook" not in combined

    _write(
        root / "interfaces" / "research" / "api" / "live_approval.py",
        "from fastapi import FastAPI\n"
        "from substrate.safety.approval_gate import enforce_release_approval\n\n\n"
        "def create_app() -> FastAPI:\n"
        "    app = FastAPI()\n"
        "    _ = enforce_release_approval({})\n"
        "    return app\n\n\n"
        "app = create_app()\n",
    )
    green = _run([sys.executable, str(gate)], cwd=root)
    assert green.returncode == 0, green.stdout + green.stderr


def test_dormant_helper_call_does_not_credit_registration_wrapper(
    tmp_path: Path,
) -> None:
    """A register_*_routes call from an uncalled helper is not product wiring."""
    root = tmp_path / "tree"
    root.mkdir()
    gate = _mirror_gate(root)

    _write(
        root / "interfaces" / "research" / "api" / "wrapped_routes.py",
        "from fastapi import APIRouter, FastAPI\n\n"
        "router = APIRouter(prefix='/wrapped')\n\n\n"
        "def register_wrapped_routes(app: FastAPI) -> None:\n"
        "    app.include_router(router)\n",
    )
    _write(
        root / "interfaces" / "research" / "api" / "dead_caller.py",
        "from fastapi import FastAPI\n"
        "from .wrapped_routes import register_wrapped_routes\n\n\n"
        "def dormant_helper(app: FastAPI) -> None:\n"
        "    register_wrapped_routes(app)\n",
    )

    red = _run([sys.executable, str(gate)], cwd=root)
    assert red.returncode == 1, red.stdout + red.stderr
    combined = red.stdout + red.stderr
    assert "register_wrapped_routes" in combined
    assert "registration wrapper" in combined

    _write(
        root / "interfaces" / "research" / "api" / "live_caller.py",
        "from fastapi import FastAPI\n"
        "from .wrapped_routes import register_wrapped_routes\n\n\n"
        "def create_app() -> FastAPI:\n"
        "    app = FastAPI()\n"
        "    register_wrapped_routes(app)\n"
        "    return app\n\n\n"
        "app = create_app()\n",
    )
    green = _run([sys.executable, str(gate)], cwd=root)
    assert green.returncode == 0, green.stdout + green.stderr


def test_api_py_register_wrapper_scanned_even_without_routes_suffix(
    tmp_path: Path,
) -> None:
    """interfaces/**/api/*.py wrappers are in scope, not only *_routes.py."""
    root = tmp_path / "tree"
    root.mkdir()
    gate = _mirror_gate(root)

    _write(
        root / "interfaces" / "research" / "api" / "campaigns.py",
        "from fastapi import APIRouter, FastAPI\n\n"
        "campaign_router = APIRouter(prefix='/campaigns')\n\n\n"
        "def register_campaign_routes(app: FastAPI) -> None:\n"
        "    app.include_router(campaign_router)\n",
    )
    red = _run([sys.executable, str(gate)], cwd=root)
    assert red.returncode == 1, red.stdout + red.stderr
    combined = red.stdout + red.stderr
    assert "campaigns.py:" in combined
    assert "register_campaign_routes" in combined

    _write(
        root / "interfaces" / "research" / "api" / "app.py",
        "from fastapi import FastAPI\n"
        "from .campaigns import register_campaign_routes\n\n\n"
        "def create_app() -> FastAPI:\n"
        "    app = FastAPI()\n"
        "    register_campaign_routes(app)\n"
        "    return app\n\n\n"
        "app = create_app()\n",
    )
    green = _run([sys.executable, str(gate)], cwd=root)
    assert green.returncode == 0, green.stdout + green.stderr


def test_direct_app_route_module_is_not_false_positive(tmp_path: Path) -> None:
    """Direct @app route modules are scanned but not forced through include_router."""
    root = tmp_path / "tree"
    root.mkdir()
    gate = _mirror_gate(root)

    _write(
        root / "interfaces" / "research" / "api" / "direct.py",
        "from fastapi import FastAPI\n\n"
        "app = FastAPI()\n\n\n"
        "@app.get('/direct')\n"
        "def direct() -> dict[str, bool]:\n"
        "    return {'ok': True}\n",
    )
    res = _run([sys.executable, str(gate)], cwd=root)
    assert res.returncode == 0, res.stdout + res.stderr


def test_direct_app_route_does_not_hide_unmounted_router_product(
    tmp_path: Path,
) -> None:
    """A mixed module can have direct @app routes and a separate orphan router."""
    root = tmp_path / "tree"
    root.mkdir()
    gate = _mirror_gate(root)

    _write(
        root / "interfaces" / "research" / "api" / "mixed.py",
        "from fastapi import APIRouter, FastAPI\n\n"
        "app = FastAPI()\n"
        "router = APIRouter(prefix='/orphan')\n\n\n"
        "@app.get('/direct')\n"
        "def direct() -> dict[str, bool]:\n"
        "    return {'ok': True}\n\n\n"
        "@router.get('/router')\n"
        "def router_handler() -> dict[str, bool]:\n"
        "    return {'ok': True}\n",
    )
    red = _run([sys.executable, str(gate)], cwd=root)
    assert red.returncode == 1, red.stdout + red.stderr
    combined = red.stdout + red.stderr
    assert "mixed.py:" in combined
    assert "router product 'router'" in combined

    _write(
        root / "interfaces" / "research" / "api" / "app.py",
        "from fastapi import FastAPI\n"
        "from .mixed import router\n\n\n"
        "def create_app() -> FastAPI:\n"
        "    app = FastAPI()\n"
        "    app.include_router(router)\n"
        "    return app\n\n\n"
        "app = create_app()\n",
    )
    green = _run([sys.executable, str(gate)], cwd=root)
    assert green.returncode == 0, green.stdout + green.stderr


def test_nested_mounted_router_handler_credits_enforcement_alias_unmounted_does_not(
    tmp_path: Path,
) -> None:
    """Nested APIRouter handlers are reachable only when their router is mounted."""
    root = tmp_path / "tree"
    root.mkdir()
    gate = _mirror_gate(root)

    _write(
        root / "substrate" / "authz" / "execution.py",
        '__all__ = ["execute_authorized_call"]\n\n\n'
        "def execute_authorized_call(x: int) -> int:\n"
        "    return x\n",
    )
    _write(
        root / "interfaces" / "research" / "api" / "mounted_nested.py",
        "from fastapi import APIRouter, FastAPI\n"
        "from substrate.authz.execution import execute_authorized_call as run_authz\n\n\n"
        "def create_app() -> FastAPI:\n"
        "    app = FastAPI()\n"
        "    router = APIRouter(prefix='/mounted')\n\n"
        "    @router.get('/run')\n"
        "    def run() -> dict[str, int]:\n"
        "        return {'value': run_authz(1)}\n\n"
        "    app.include_router(router)\n"
        "    return app\n\n\n"
        "app = create_app()\n",
    )

    mounted = _run([sys.executable, str(gate)], cwd=root)
    assert mounted.returncode == 0, (
        f"mounted nested router handler must credit the aliased enforcement call, "
        f"got {mounted.returncode}\n{mounted.stdout}\n{mounted.stderr}"
    )

    _write(
        root / "interfaces" / "research" / "api" / "mounted_nested.py",
        "from fastapi import APIRouter, FastAPI\n"
        "from substrate.authz.execution import execute_authorized_call as run_authz\n\n\n"
        "def create_app() -> FastAPI:\n"
        "    app = FastAPI()\n"
        "    router = APIRouter(prefix='/unmounted')\n\n"
        "    @router.get('/run')\n"
        "    def run() -> dict[str, int]:\n"
        "        return {'value': run_authz(1)}\n\n"
        "    return app\n\n\n"
        "app = create_app()\n",
    )
    unmounted = _run([sys.executable, str(gate)], cwd=root)
    assert unmounted.returncode == 1, (
        f"unmounted nested router handler must not credit the enforcement call, "
        f"got {unmounted.returncode}\n{unmounted.stdout}\n{unmounted.stderr}"
    )
    combined = unmounted.stdout + unmounted.stderr
    assert "execute_authorized_call" in combined, combined
