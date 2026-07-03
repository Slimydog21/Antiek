"""Contracts for operator-action support probes documented in OPERATOR_ACTIONS."""

from __future__ import annotations

import re
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
OPERATOR_ACTIONS = ROOT / "docs" / "OPERATOR_ACTIONS.md"
AGENT_GATES = ROOT / ".github" / "workflows" / "agent_execution_gates.yml"
CANONICAL_VERIFY = ROOT / "scripts" / "canonical_verify.sh"

PROBE_RE = re.compile(
    r"(?:-m\s+tools\.ops\.([A-Za-z0-9_]+)|python\s+tools/ops/([A-Za-z0-9_]+)\.py)"
)


def _operator_probe_modules() -> list[str]:
    text = OPERATOR_ACTIONS.read_text(encoding="utf-8")
    modules = [match.group(1) or match.group(2) for match in PROBE_RE.finditer(text)]
    assert modules, "OPERATOR_ACTIONS.md does not document any tools.ops probes"
    return sorted(set(modules))


def _operator_action_section_for(module: str) -> str:
    text = OPERATOR_ACTIONS.read_text(encoding="utf-8")
    probe_match = next(
        (
            match
            for match in PROBE_RE.finditer(text)
            if (match.group(1) or match.group(2)) == module
        ),
        None,
    )
    assert probe_match is not None, f"probe command not found for {module}"
    section_start = text.rfind("\n### OA-", 0, probe_match.start())
    assert section_start >= 0, f"OA section start not found for {module}"
    section_start += 1
    section_end = text.find("\n### OA-", probe_match.end())
    if section_end < 0:
        section_end = len(text)
    return text[section_start:section_end]


def test_operator_actions_documented_probes_have_modules_and_tests() -> None:
    """Every documented support probe must have an implementation and test file."""
    missing: list[str] = []
    for module in _operator_probe_modules():
        module_path = ROOT / "tools" / "ops" / f"{module}.py"
        test_path = ROOT / "tests" / f"test_{module}.py"
        if not module_path.is_file():
            missing.append(str(module_path.relative_to(ROOT)))
        if not test_path.is_file():
            missing.append(str(test_path.relative_to(ROOT)))

    assert not missing


def test_operator_actions_probes_do_not_claim_to_close_operator_gates() -> None:
    """Support probes can validate evidence, but closure remains operator-owned."""
    missing_boundary: list[str] = []
    for module in _operator_probe_modules():
        section = _operator_action_section_for(module)
        compact = " ".join(section.split()).lower()
        has_boundary = (
            re.search(r"does\s+\W*not\W*\s+close", compact) is not None
            or "support evidence only" in compact
        )
        if not has_boundary:
            missing_boundary.append(module)

    assert not missing_boundary


def test_agent_gates_runs_documented_operator_probe_tests() -> None:
    """Agent gates should fail if a documented operator probe regresses."""
    script = CANONICAL_VERIFY.read_text(encoding="utf-8")
    workflow = AGENT_GATES.read_text(encoding="utf-8")

    missing = [
        f"tests/test_{module}.py"
        for module in _operator_probe_modules()
        if f"tests/test_{module}.py" not in script
    ]

    assert not missing
    assert "tools/ops/**" in workflow
    assert "docs/OPERATOR_ACTIONS.md" in workflow
