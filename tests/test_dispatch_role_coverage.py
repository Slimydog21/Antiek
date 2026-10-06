"""Every role a tracked caller hands to the dispatch router must exist in the real config.

This guards a defect class that has recurred in production and never once in CI:

  * ``skills/domain/extract.py`` dispatched ``role="knowledge_extractor"`` with no
    ``role_tiers`` entry, so every Phase 8 run produced an empty ``auto_patch_applied``
    event and the Phase 8 postcondition failed the whole investigation (fixed 2026-05-18).
  * the AGH SPR-01 ``thought_partner`` endpoint,
  * ``substrate/write/draft_generation.default_dispatch_fn`` dispatched
    ``role="creative_writer"``, so ``POST /write/sections/{id}/generate`` 503'd on every
    call and the whole writing-generate path was dead,
  * ``substrate/speak/async_interview.py`` dispatched ``role="interviewer"``,
  * and ``substrate/reformat/pipeline.py`` dispatches ``role="reformat"``.

Every one of those was found in production rather than by a test, and the reason is worth
naming. The callers all accept an injected generator (``generate_fn``); every test injects
a fake one; so the single function that reaches the real dispatch path has no coverage at
all. ``substrate/reformat/pipeline.py`` says so in its own comment - "the REAL one rides
the one dispatch path" - and the real one was the only one never run.

``router._dispatch_authoritative`` raises ``KeyError`` for a role that is not in
``config.role_tiers``, so the failure mode is total rather than degraded: the feature
cannot run once.
"""

from __future__ import annotations

import ast
from pathlib import Path

from substrate.dispatch.router import DispatchConfig

REPO_ROOT = Path(__file__).resolve().parents[1]
CONFIG_PATH = REPO_ROOT / "substrate" / "dispatch" / "config.yaml"
SCANNED_ROOTS = (
    "substrate",
    "interfaces",
    "skills",
    "tools",
    "services",
    "orchestration",
    "middleware",
    "acquisition",
    "processing",
    "runtime",
    "roles",
)


def _imports_router_dispatch(tree: ast.Module) -> bool:
    """True when the module pulls ``dispatch`` out of the dispatch router.

    Narrowing on the import is what keeps this honest: ``dispatch`` is a common name, and
    an unrelated function called ``dispatch`` must not be reported as a role caller.
    """
    for node in ast.walk(tree):
        if (
            isinstance(node, ast.ImportFrom)
            and node.module
            and "dispatch" in node.module
            and any(alias.name == "dispatch" for alias in node.names)
        ):
            return True
    return False


def _dispatched_role_literals(source: str) -> list[tuple[str, int]]:
    try:
        tree = ast.parse(source)
    except SyntaxError:  # pragma: no cover - a broken file fails elsewhere
        return []
    if not _imports_router_dispatch(tree):
        return []
    found: list[tuple[str, int]] = []
    for node in ast.walk(tree):
        if not isinstance(node, ast.Call):
            continue
        func = node.func
        name = func.attr if isinstance(func, ast.Attribute) else getattr(func, "id", None)
        if name != "dispatch":
            continue
        role: object = None
        if len(node.args) >= 2 and isinstance(node.args[1], ast.Constant):
            role = node.args[1].value
        else:
            for keyword in node.keywords:
                if keyword.arg == "role" and isinstance(keyword.value, ast.Constant):
                    role = keyword.value.value
        if isinstance(role, str):
            found.append((role, node.lineno))
    return found


def test_every_dispatched_role_is_declared_in_the_real_config() -> None:
    declared = DispatchConfig.from_yaml(CONFIG_PATH).role_tiers
    violations: list[str] = []
    scanned = 0
    for root in SCANNED_ROOTS:
        for path in sorted((REPO_ROOT / root).rglob("*.py")):
            text = path.read_text(errors="replace")
            if "dispatch(" not in text:
                continue
            scanned += 1
            for role, lineno in _dispatched_role_literals(text):
                if role not in declared:
                    violations.append(
                        f"{path.relative_to(REPO_ROOT)}:{lineno} dispatches role={role!r}"
                    )
    assert scanned > 0, "the scan found no file that calls dispatch - the guard is not working"
    assert not violations, (
        "these dispatch calls pass a role that has no entry in "
        f"{CONFIG_PATH.relative_to(REPO_ROOT)}:\n  "
        + "\n  ".join(violations)
        + f"\nrouter._dispatch_authoritative raises KeyError for an unknown role, so each of "
        f"these features cannot run at all.\nDeclared roles: {sorted(declared)}"
    )
