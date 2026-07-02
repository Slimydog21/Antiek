"""Guards for the platform execution matrix.

The matrix is the handoff scope map source. If CI starts running a canonical
verifier that the matrix does not name, agents can claim platform coverage while
the operator cannot map that command to a row.
"""

from __future__ import annotations

import re
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
MATRIX = ROOT / "docs" / "agent-execution" / "PLATFORM_EXEC_MATRIX.md"
AGENT_GATES = ROOT / ".github" / "workflows" / "agent_execution_gates.yml"
CANONICAL_VERIFY = ROOT / "scripts" / "canonical_verify.sh"

_META_COMMANDS = {"agent-gates", "handoff"}


def _workflow_canonical_commands() -> set[str]:
    text = AGENT_GATES.read_text(encoding="utf-8")
    commands = set(re.findall(r"canonical_verify\.sh ([a-z0-9-]+)", text))
    return commands - _META_COMMANDS


def _matrix_canonical_commands() -> set[str]:
    text = MATRIX.read_text(encoding="utf-8")
    return set(re.findall(r"canonical_verify\.sh ([a-z0-9-]+)", text))


def _script_canonical_commands() -> set[str]:
    text = CANONICAL_VERIFY.read_text(encoding="utf-8")
    return set(re.findall(r"^\s*([a-z0-9-]+)\)\s+cmd_", text, re.MULTILINE))


def test_platform_matrix_names_every_ci_canonical_command() -> None:
    matrix = MATRIX.read_text(encoding="utf-8")
    missing = sorted(cmd for cmd in _workflow_canonical_commands() if cmd not in matrix)

    assert not missing, (
        "agent_execution_gates.yml runs canonical verifier(s) not named in "
        f"PLATFORM_EXEC_MATRIX.md: {missing}"
    )


def test_platform_matrix_canonical_commands_exist_in_script() -> None:
    missing = sorted(_matrix_canonical_commands() - _script_canonical_commands())

    assert not missing, (
        "PLATFORM_EXEC_MATRIX.md names canonical verifier(s) missing from "
        f"scripts/canonical_verify.sh: {missing}"
    )


def test_platform_matrix_row_ids_are_contiguous() -> None:
    text = MATRIX.read_text(encoding="utf-8")
    row_numbers = [int(n) for n in re.findall(r"^\| P-(\d{2}) \|", text, re.MULTILINE)]

    assert row_numbers == list(range(1, len(row_numbers) + 1))


def test_unified_substrate_lock_row_names_invariant_registry_when_verified() -> None:
    script = CANONICAL_VERIFY.read_text(encoding="utf-8")
    matrix = MATRIX.read_text(encoding="utf-8")

    if "tests/test_invariant_registry_meta.py" not in script:
        return

    row = re.search(r"^\| P-38 \|(?P<body>.*)\|$", matrix, re.MULTILINE)
    assert row is not None
    assert "substrate/invariants/" in row.group("body")
