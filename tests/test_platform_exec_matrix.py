"""Guards for the platform execution matrix.

The matrix is the handoff scope map source. If CI starts running a canonical
verifier that the matrix does not name, agents can claim platform coverage while
the operator cannot map that command to a row.
"""

from __future__ import annotations

import re
from fnmatch import fnmatchcase
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
    "antiek/cli.py",
    "apps/reading/e2e/_ams/read_activation_evidence.test.ts",
    "apps/reading/e2e/_ams/read_activation_evidence.ts",
    "apps/reading/e2e/read-golden-path.spec.ts",
    "specs/activation/**",
    "tests/test_antiek_read_activation_cli.py",
    "tools/activation/read_dogfood.py",
    "tests/test_read_activation_dogfood.py",
}
_PROMPT_AUTORESEARCH_TRIGGER_PATHS = {
    "docs/OPERATOR_ACTIONS.md",
    "docs/operator_gate_actions.md",
    "tools/prompt_autoresearch/**",
    "tests/test_autoresearch_wedge1_probe.py",
    "tests/test_prompt_autoresearch.py",
    "tests/test_prompt_autoresearch_calibration.py",
    "tests/test_prompt_autoresearch_docs.py",
    "tests/test_prompt_autoresearch_readiness.py",
    "tests/test_prompt_autoresearch_verdict.py",
}
_AMS_REF_LINT_TRIGGER_PATHS = {
    "docs/agent-execution/**",
    "docs/htmlspec/antiek-hard-to-vary-execution/sprint-05-ams-bridge.html",
    "scripts/agent_ams_ref_lint.sh",
    "tests/fixtures/agent_execution/**",
    "tests/test_agent_ams_ref_lint.py",
    "tools/ams-v2/ref-lint.sh",
    "tools/specs/verify_spec_refs.ts",
}
_CI_PYTEST_TRIGGER_PATHS = {
    ".github/workflows/ci.yml",
    "docs/decisions/ci-pytest-timeout.md",
    "tests/test_ci_pytest_timeout_docs.py",
}
_READING_COPY_LINT_TRIGGER_PATHS = {
    "apps/reading/src/components/**",
    "apps/reading/src/modes/**",
    "apps/reading/src/shared/copyLint.test.ts",
    "apps/reading/src/shared/copy_lint_baseline.json",
    "apps/reading/src/shared/language.ts",
    "apps/reading/src/shell/**",
}
_RESEARCH_BRIDGE_DOGFOOD_TRIGGER_PATHS = {
    "antiek/cli.py",
    "substrate/research_bridge/**",
}
_OPERATOR_COORDINATION_TRIGGER_PATHS = {
    "apps/reading/src/modes/OperatorDashboard/**",
}
_HANDOFF_FIXTURE = "tests/fixtures/agent_execution/handoff_pass.md"


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


def test_agent_workflow_runs_handoff_fixture_gate_for_schema_rows() -> None:
    workflow = AGENT_GATES.read_text(encoding="utf-8")
    matrix = MATRIX.read_text(encoding="utf-8")

    assert "| P-46 | Agent handoff schema |" in matrix
    assert "| P-47 | Session theater grep |" in matrix
    assert f"./scripts/canonical_verify.sh handoff {_HANDOFF_FIXTURE}" in workflow
    assert (ROOT / _HANDOFF_FIXTURE).is_file()


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


def test_cascade_adapter_row_names_canonical_bundle() -> None:
    """P-02 is part of the cascade profile, not an orphan raw pytest command."""
    script = CANONICAL_VERIFY.read_text(encoding="utf-8")
    matrix = MATRIX.read_text(encoding="utf-8")

    row = re.search(r"^\| P-02 \|(?P<body>.*)\|$", matrix, re.MULTILINE)
    assert row is not None
    body = row.group("body")

    assert "tests/test_cascade_planner.py::test_dispatch_decomposer_maps_stub_response" in script
    assert "`roles/cascade_planner/planner.py`" in body
    assert "`tests/test_cascade_planner.py`" in body
    assert "included in `canonical_verify.sh cascade`" in body
    assert "pytest tests/test_cascade_planner.py::test_dispatch_decomposer_maps_stub_response -q" not in body


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


def test_agent_gates_trigger_on_prompt_autoresearch_inputs() -> None:
    """P-53 runs the Prompt Autoresearch Wedge 1 closure bundle."""
    for event_name in ("push", "pull_request"):
        paths = _workflow_event_paths(event_name)
        missing = sorted(_PROMPT_AUTORESEARCH_TRIGGER_PATHS - paths)
        assert not missing, (
            f"agent_execution_gates.yml {event_name} does not trigger on "
            f"Prompt Autoresearch input(s): {missing}"
        )


def test_agent_gates_trigger_on_ams_ref_lint_inputs() -> None:
    """P-48 runs the canonical AMS spec reference anti-fiction gate."""
    for event_name in ("push", "pull_request"):
        paths = _workflow_event_paths(event_name)
        missing = sorted(_AMS_REF_LINT_TRIGGER_PATHS - paths)
        assert not missing, (
            f"agent_execution_gates.yml {event_name} does not trigger on "
            f"AMS ref-lint input(s): {missing}"
        )


def test_agent_gates_trigger_on_ci_pytest_contract_inputs() -> None:
    """P-49 must keep the full-suite pytest throughput contract visible."""
    for event_name in ("push", "pull_request"):
        paths = _workflow_event_paths(event_name)
        missing = sorted(_CI_PYTEST_TRIGGER_PATHS - paths)
        assert not missing, (
            f"agent_execution_gates.yml {event_name} does not trigger on "
            f"CI pytest contract input(s): {missing}"
        )


def test_agent_gates_trigger_on_reading_copy_lint_inputs() -> None:
    """The agent gate catches user-facing copy regressions on app surfaces."""
    for event_name in ("push", "pull_request"):
        paths = _workflow_event_paths(event_name)
        missing = sorted(_READING_COPY_LINT_TRIGGER_PATHS - paths)
        assert not missing, (
            f"agent_execution_gates.yml {event_name} does not trigger on "
            f"reading copy-lint input(s): {missing}"
        )


def test_agent_gates_trigger_on_research_bridge_dogfood_inputs() -> None:
    """The Deep Research Bridge dogfood gate runs on bridge substrate edits."""
    matrix = MATRIX.read_text(encoding="utf-8")
    assert "research-bridge-dogfood" in matrix

    for event_name in ("push", "pull_request"):
        paths = _workflow_event_paths(event_name)
        missing = sorted(_RESEARCH_BRIDGE_DOGFOOD_TRIGGER_PATHS - paths)
        assert not missing, (
            f"agent_execution_gates.yml {event_name} does not trigger on "
            f"research bridge dogfood input(s): {missing}"
        )


def test_agent_gates_trigger_on_operator_coordination_summary_inputs() -> None:
    """The Operator dashboard consumes the Coordination roadmap focus summary."""
    for event_name in ("push", "pull_request"):
        paths = _workflow_event_paths(event_name)
        missing = sorted(_OPERATOR_COORDINATION_TRIGGER_PATHS - paths)
        assert not missing, (
            f"agent_execution_gates.yml {event_name} does not trigger on "
            f"operator coordination summary input(s): {missing}"
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


def test_agent_gates_matrix_row_names_current_scope() -> None:
    """P-50 must track the bundled agent-gates checks, not only Werner."""
    script = CANONICAL_VERIFY.read_text(encoding="utf-8")
    matrix = MATRIX.read_text(encoding="utf-8")

    row = re.search(r"^\| P-50 \|(?P<body>.*)\|$", matrix, re.MULTILINE)
    assert row is not None
    body = row.group("body")

    expected_scope_markers = {
        "tools/agent/verify_handoff.ts": "verify_handoff.ts",
        "scripts/audit_agent_session.sh": "audit_agent_session.sh",
        "src/modes/Settings/Settings.test.tsx": "Settings.test.tsx",
        "src/shared/copyLint.test.ts": "copyLint.test.ts",
        "tests/test_provenance_ref_lint.py": "test_provenance_ref_lint.py",
        "tests/test_prompt_autoresearch_readiness.py": (
            "test_prompt_autoresearch_readiness.py"
        ),
        "test_read_activation_dogfood.py": "read activation",
    }
    missing = sorted(
        marker
        for script_marker, marker in expected_scope_markers.items()
        if script_marker in script and marker not in body
    )

    assert not missing, (
        "P-50 agent-gates row does not name current gate scope marker(s): "
        f"{missing}"
    )


def test_serve_rights_legal_row_names_operator_proof_artifacts() -> None:
    """P-51 must stay operator-proof-bound, not a fake informational CI closure."""
    matrix = MATRIX.read_text(encoding="utf-8")
    row = re.search(r"^\| P-51 \|(?P<body>.*)\|$", matrix, re.MULTILINE)
    assert row is not None
    body = row.group("body")

    assert "`docs/OPERATOR_ACTIONS.md`" in body
    assert "`infrastructure/runbooks/first-deploy.md`" in body
    assert "**No** informational CI job alone (F7)" in body
    assert "Jurisdiction-specific legal review" in body


def test_reading_substrate_pytest_row_names_throughput_contract() -> None:
    """P-49's full-suite CI claim must name the doc/test guarding xdist scope."""
    matrix = MATRIX.read_text(encoding="utf-8")
    row = re.search(r"^\| P-49 \|(?P<body>.*)\|$", matrix, re.MULTILINE)
    assert row is not None
    body = row.group("body")

    assert "`.github/workflows/ci.yml`" in body
    assert "`docs/decisions/ci-pytest-timeout.md`" in body
    assert "`tests/test_ci_pytest_timeout_docs.py`" in body
    assert "CI on `main` (full suite)" in body
    assert "Local hardware parity" in body
