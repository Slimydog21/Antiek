"""Guards for the platform execution matrix.

The matrix is the handoff scope map source. If CI starts running a canonical
verifier that the matrix does not name, agents can claim platform coverage while
the operator cannot map that command to a row.
"""

from __future__ import annotations

from fnmatch import fnmatchcase
import re
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
MATRIX = ROOT / "docs" / "agent-execution" / "PLATFORM_EXEC_MATRIX.md"
AGENT_GATES = ROOT / ".github" / "workflows" / "agent_execution_gates.yml"
CANONICAL_VERIFY = ROOT / "scripts" / "canonical_verify.sh"
WERNER_ADAPTER = ROOT / "docs" / "agent-execution" / "WERNER_EXEC_ADAPTER.md"

_META_COMMANDS = {"agent-gates", "handoff"}
_PROVENANCE_INVARIANT_TRIGGER_PATHS = {
    "roles/*/parser.py",
    "substrate/provenance/**",
    "tools/lint/provenance_ref_check.py",
    "tests/test_invariant_registry_meta.py",
    "tests/test_provenance_ref_lint.py",
}
_READ_ACTIVATION_TRIGGER_PATHS = {
    "specs/activation/**",
    "tools/activation/read_dogfood.py",
    "tests/test_read_activation_dogfood.py",
}


def _workflow_canonical_commands() -> set[str]:
    text = AGENT_GATES.read_text(encoding="utf-8")
    commands = set(re.findall(r"canonical_verify\.sh ([a-z0-9-]+)", text))
    return commands - _META_COMMANDS


def _matrix_canonical_commands() -> set[str]:
    text = MATRIX.read_text(encoding="utf-8")
    return set(re.findall(r"canonical_verify\.sh ([a-z0-9-]+)", text))


def _matrix_literal_file_refs() -> set[str]:
    text = MATRIX.read_text(encoding="utf-8")
    refs = set(re.findall(r"`([^`]+\.(?:md|py|ts|tsx))`", text))
    return {
        ref
        for ref in refs
        if not ref.startswith(("./", "pytest ", "canonical_verify.sh "))
        and " " not in ref
        and "<" not in ref
    }


def _matrix_literal_dir_refs() -> set[str]:
    text = MATRIX.read_text(encoding="utf-8")
    refs = set(re.findall(r"`([^`]+/)`", text))
    return {
        ref
        for ref in refs
        if not ref.startswith(("/", "./", "canonical_verify.sh "))
        and " " not in ref
        and "<" not in ref
    }


def _script_canonical_commands() -> set[str]:
    text = CANONICAL_VERIFY.read_text(encoding="utf-8")
    return set(re.findall(r"^\s*([a-z0-9-]+)\)\s+cmd_", text, re.MULTILINE))


def _canonical_verify_test_inputs() -> set[str]:
    text = CANONICAL_VERIFY.read_text(encoding="utf-8")
    return set(re.findall(r"tests/[A-Za-z0-9_./-]+\.py", text))


def _workflow_event_paths(event_name: str) -> set[str]:
    text = AGENT_GATES.read_text(encoding="utf-8")
    match = re.search(
        rf"^  {event_name}:\n    branches: \[main\]\n    paths:\n(?P<body>(?:      - .*\n)+)",
        text,
        re.MULTILINE,
    )
    assert match is not None, f"{event_name} paths block not found"
    return set(re.findall(r"      - '([^']+)'", match.group("body")))


def _path_is_covered(path: str, patterns: set[str]) -> bool:
    return any(fnmatchcase(path, pattern) for pattern in patterns)


def _dir_is_covered(path: str, patterns: set[str]) -> bool:
    probe = f"{path.rstrip('/')}/__matrix_probe__"
    return _path_is_covered(path, patterns) or _path_is_covered(probe, patterns)


def test_platform_matrix_names_every_ci_canonical_command() -> None:
    matrix = MATRIX.read_text(encoding="utf-8")
    missing = sorted(cmd for cmd in _workflow_canonical_commands() if cmd not in matrix)

    assert not missing, (
        "agent_execution_gates.yml runs canonical verifier(s) not named in "
        f"PLATFORM_EXEC_MATRIX.md: {missing}"
    )


def test_agent_workflow_runs_every_matrix_canonical_command() -> None:
    missing = sorted(
        (_matrix_canonical_commands() - _META_COMMANDS)
        - _workflow_canonical_commands()
    )

    assert not missing, (
        "PLATFORM_EXEC_MATRIX.md names canonical verifier(s) not run by "
        f"agent_execution_gates.yml: {missing}"
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


def test_platform_matrix_literal_file_refs_exist() -> None:
    missing = sorted(
        ref for ref in _matrix_literal_file_refs() if not (ROOT / ref).exists()
    )

    assert not missing, (
        "PLATFORM_EXEC_MATRIX.md names literal file ref(s) that do not exist "
        f"from repo root: {missing}"
    )


def test_platform_matrix_literal_dir_refs_exist() -> None:
    missing = sorted(
        ref for ref in _matrix_literal_dir_refs() if not (ROOT / ref).is_dir()
    )

    assert not missing, (
        "PLATFORM_EXEC_MATRIX.md names literal directory ref(s) that do not exist "
        f"from repo root: {missing}"
    )


def test_unified_substrate_lock_row_names_invariant_registry_when_verified() -> None:
    script = CANONICAL_VERIFY.read_text(encoding="utf-8")
    matrix = MATRIX.read_text(encoding="utf-8")

    if "tests/test_invariant_registry_meta.py" not in script:
        return

    row = re.search(r"^\| P-38 \|(?P<body>.*)\|$", matrix, re.MULTILINE)
    assert row is not None
    assert "substrate/invariants/" in row.group("body")


def test_agent_gates_trigger_on_provenance_invariant_inputs() -> None:
    """P-38 now runs the invariant registry, including parser provenance checks."""
    for event_name in ("push", "pull_request"):
        paths = _workflow_event_paths(event_name)
        missing = sorted(_PROVENANCE_INVARIANT_TRIGGER_PATHS - paths)
        assert not missing, (
            f"agent_execution_gates.yml {event_name} does not trigger on "
            f"provenance invariant input(s): {missing}"
        )


def test_agent_gates_trigger_on_read_activation_dogfood_inputs() -> None:
    """P-12 read-reader runs the dogfood closure guard."""
    for event_name in ("push", "pull_request"):
        paths = _workflow_event_paths(event_name)
        missing = sorted(_READ_ACTIVATION_TRIGGER_PATHS - paths)
        assert not missing, (
            f"agent_execution_gates.yml {event_name} does not trigger on "
            f"Read activation dogfood input(s): {missing}"
        )


def test_agent_gates_trigger_on_canonical_verify_test_inputs() -> None:
    """A verifier test change must schedule the workflow that consumes it."""
    canonical_tests = _canonical_verify_test_inputs()
    assert canonical_tests, "canonical_verify.sh references no test inputs"

    for event_name in ("push", "pull_request"):
        paths = _workflow_event_paths(event_name)
        missing = sorted(
            path for path in canonical_tests if not _path_is_covered(path, paths)
        )
        assert not missing, (
            f"agent_execution_gates.yml {event_name} does not trigger on "
            f"canonical verifier test input(s): {missing}"
        )


def test_agent_gates_trigger_on_matrix_entrypoint_files() -> None:
    """A matrix entry-point edit must schedule the workflow guarding its row."""
    matrix_files = {
        ref for ref in _matrix_literal_file_refs() if (ROOT / ref).is_file()
    }
    assert matrix_files, "PLATFORM_EXEC_MATRIX.md names no literal entry files"

    for event_name in ("push", "pull_request"):
        paths = _workflow_event_paths(event_name)
        missing = sorted(
            path for path in matrix_files if not _path_is_covered(path, paths)
        )
        assert not missing, (
            f"agent_execution_gates.yml {event_name} does not trigger on "
            f"platform matrix entry-point file(s): {missing}"
        )


def test_agent_gates_trigger_on_matrix_entrypoint_dirs() -> None:
    """A matrix entry-point directory edit must schedule its guarding workflow."""
    matrix_dirs = {
        ref for ref in _matrix_literal_dir_refs() if (ROOT / ref).is_dir()
    }
    assert matrix_dirs, "PLATFORM_EXEC_MATRIX.md names no literal entry directories"

    for event_name in ("push", "pull_request"):
        paths = _workflow_event_paths(event_name)
        missing = sorted(path for path in matrix_dirs if not _dir_is_covered(path, paths))
        assert not missing, (
            f"agent_execution_gates.yml {event_name} does not trigger on "
            f"platform matrix entry-point dir(s): {missing}"
        )


def test_werner_adapter_names_agent_gate_and_measured_live_boundary() -> None:
    """P-50 agent-gates are hermetic; live mascot p95/fps needs operator proof."""
    text = WERNER_ADAPTER.read_text(encoding="utf-8")

    assert "./scripts/canonical_verify.sh agent-gates" in text
    assert "p95/fps" in text
    assert "not proved by agent-gates" in text
