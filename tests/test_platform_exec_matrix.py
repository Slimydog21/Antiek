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

_META_COMMANDS = {"agent-gates", "handoff"}


def _workflow_canonical_commands() -> set[str]:
    text = AGENT_GATES.read_text(encoding="utf-8")
    commands = set(re.findall(r"canonical_verify\.sh ([a-z0-9-]+)", text))
    return commands - _META_COMMANDS


def test_platform_matrix_names_every_ci_canonical_command() -> None:
    matrix = MATRIX.read_text(encoding="utf-8")
    missing = sorted(cmd for cmd in _workflow_canonical_commands() if cmd not in matrix)

    assert not missing, (
        "agent_execution_gates.yml runs canonical verifier(s) not named in "
        f"PLATFORM_EXEC_MATRIX.md: {missing}"
    )


def test_platform_matrix_row_ids_are_contiguous() -> None:
    text = MATRIX.read_text(encoding="utf-8")
    row_numbers = [int(n) for n in re.findall(r"^\| P-(\d{2}) \|", text, re.MULTILINE)]

    assert row_numbers == list(range(1, len(row_numbers) + 1))
