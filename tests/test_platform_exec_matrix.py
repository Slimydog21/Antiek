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
    script = CANONICAL_VERIFY.read_text(encoding="utf-8")
    fixture = (ROOT / _HANDOFF_FIXTURE).read_text(encoding="utf-8")

    assert "| P-46 | Agent handoff schema |" in matrix
    assert "| P-47 | Session theater grep |" in matrix
    assert f"./scripts/canonical_verify.sh handoff {_HANDOFF_FIXTURE}" in workflow
    assert (ROOT / _HANDOFF_FIXTURE).is_file()

    assert '"${TSX}" tools/agent/verify_handoff.ts "$f"' in script
    assert "bash scripts/audit_agent_session.sh \"$f\"" in script
    assert "CANONICAL_VERIFY_OK: handoff ($f)" in script
    assert "tools/agent/verify_handoff.ts" in workflow
    assert "scripts/audit_agent_session.sh" in workflow
    assert "tests/fixtures/agent_execution/**" in workflow
    assert "### Not proved" in fixture
    assert "### Status" in fixture
    assert re.search(r"^#{2,3} Scope Map$", fixture, re.MULTILINE)
    assert "pytest[^|]*\\|[[:space:]]*tail" not in fixture


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


def test_cascade_profile_rows_name_current_scope() -> None:
    """P-03..P-09 must track the concrete tests bundled by cascade."""
    script = CANONICAL_VERIFY.read_text(encoding="utf-8")
    matrix = MATRIX.read_text(encoding="utf-8")

    expected = {
        "03": {
            "body": ("`tests/test_cascade_create_plan_light.py`",),
            "script": ("tests/test_cascade_create_plan_light.py",),
        },
        "04": {
            "body": ("`scripts/audit_decomposer_call_sites.sh`",),
            "script": ("bash scripts/audit_decomposer_call_sites.sh",),
        },
        "05": {
            "body": ("`PlanTree`", "`/research/plans/{root_id}/edit`"),
            "script": (
                "test_invalid_edits_do_not_mutate_or_reopen_gate",
                "test_invalid_question_edits_are_refused_without_mutating_plan",
            ),
        },
        "06": {
            "body": ("`CascadeSession`", "`/research/sessions/{id}`"),
            "script": (
                "tests/test_parallel_orchestration.py::test_steer_routes_to_one_research",
                "tests/test_cascade_api.py::test_session_reconstructs_after_eviction",
            ),
        },
        "07": {
            "body": ("`substrate/gap_detection/`", "Speak `DRWGapSource`"),
            "script": ("tests/test_gap_detection.py", "tests/test_speak_drw_gap_source.py"),
        },
        "08": {
            "body": ("`substrate/research_bridge/ingest_file.py`",),
            "script": ("tests/test_universal_ingest.py",),
        },
        "09": {
            "body": ("`apps/reading/src/modes/DeepResearchWorkspace/`",),
            "script": ("src/modes/DeepResearchWorkspace/DeepResearchWorkspace.test.tsx",),
        },
    }

    for row_id, markers in expected.items():
        row = re.search(rf"^\| P-{row_id} \|(?P<body>.*)\|$", matrix, re.MULTILINE)
        assert row is not None, f"P-{row_id} row missing"
        body = row.group("body")

        assert "included in `canonical_verify.sh cascade`" in body
        missing_body = [marker for marker in markers["body"] if marker not in body]
        missing_script = [marker for marker in markers["script"] if marker not in script]

        assert not missing_body, f"P-{row_id} row missing marker(s): {missing_body}"
        assert not missing_script, (
            f"canonical cascade missing P-{row_id} marker(s): {missing_script}"
        )


def test_read_profile_rows_name_current_scope() -> None:
    """P-10..P-18 must track the concrete tests bundled by Read profiles."""
    script = CANONICAL_VERIFY.read_text(encoding="utf-8")
    matrix = MATRIX.read_text(encoding="utf-8")

    expected = {
        "10": {
            "command": "read-foundation",
            "body": ("`substrate/books/`", "`interfaces/research/api/books.py`"),
            "script": ("tests/test_book_corpus_gate.py", "tests/test_contracts_read_lock.py"),
        },
        "11": {
            "command": "read-library",
            "body": ("`/library`", "`apps/reading/src/modes/Library/`"),
            "script": (
                "tests/test_library_api.py",
                "tests/test_servability_drift_guard.py",
                "src/components/library/LibraryView.test.tsx",
            ),
        },
        "12": {
            "command": "read-reader",
            "body": ("`/read/:documentId`", "`apps/reading/src/modes/Reading/`"),
            "script": (
                "tests/test_serve_structured_blocks.py",
                "tests/test_read_activation_dogfood.py",
                "src/modes/Reading/TalkToBook.test.tsx",
            ),
        },
        "13": {
            "command": "read-curate",
            "body": ("`substrate/books/curate.py`", "`/books/curate`"),
            "script": ("tests/test_book_curate.py", "src/modes/Library/Library.test.tsx"),
        },
        "14": {
            "command": "read-ad-border",
            "body": ("`substrate/ad_inventory/`", "reader ad rails/impressions"),
            "script": ("tests/test_reader_ad_slots.py", "src/modes/Reading/HouseSlot.test.tsx"),
        },
        "15": {
            "command": "read-voice-notes",
            "body": ("`interfaces/research/api/read_voice.py`", "reader voice-note UI"),
            "script": ("tests/test_voice_notes.py", "src/modes/Reading/VoiceNote.test.tsx"),
        },
        "16": {
            "command": "read-rabbit-hole",
            "body": ("`AISidecar`", "`TalkToBook` book Q&A"),
            "script": (
                "tests/test_tts_voice_reply.py",
                "test_talk_to_book_answer_cites_pages",
                "src/components/AISidecar.test.tsx",
            ),
        },
        "17": {
            "command": "read-passage-research",
            "body": ("`substrate/books/passage_research.py`", "`ResearchThis` handoff"),
            "script": ("tests/test_passage_research.py", "src/modes/Reading/ResearchThis.test.tsx"),
        },
        "18": {
            "command": "read-ad-escrow",
            "body": ("`substrate/marketplace_metrics/book_escrow.py`", "reader impression flush"),
            "script": ("tests/test_read_ad_escrow.py", "src/api/books.test.ts"),
        },
    }

    for row_id, markers in expected.items():
        row = re.search(rf"^\| P-{row_id} \|(?P<body>.*)\|$", matrix, re.MULTILINE)
        assert row is not None, f"P-{row_id} row missing"
        body = row.group("body")

        assert f"`./scripts/canonical_verify.sh {markers['command']}`" in body
        missing_body = [marker for marker in markers["body"] if marker not in body]
        missing_script = [marker for marker in markers["script"] if marker not in script]

        assert not missing_body, f"P-{row_id} row missing marker(s): {missing_body}"
        assert not missing_script, (
            f"canonical Read profile missing P-{row_id} marker(s): {missing_script}"
        )


def test_write_profile_rows_name_current_scope() -> None:
    """P-19..P-27 must track the concrete tests bundled by Write profiles."""
    script = CANONICAL_VERIFY.read_text(encoding="utf-8")
    matrix = MATRIX.read_text(encoding="utf-8")

    expected = {
        "19": {
            "command": "write-outline-block",
            "body": ("`substrate/write/outline_block.py`", "`/write/blocks` routes"),
            "script": ("tests/test_outline_block.py", "tests/test_speak_write_composer.py"),
        },
        "20": {
            "command": "write-edit-capture",
            "body": ("`substrate/edit/`", "Write editor edit payload mapping"),
            "script": ("tests/test_edit_capture.py", "src/modes/Write/Editor/editCapture.test.ts"),
        },
        "21": {
            "command": "write-block-repository",
            "body": ("`substrate/write/folders.py`", "`substrate/write/block_search.py`"),
            "script": ("tests/test_block_repository.py", "src/modes/Write/Repository/Repository.test.tsx"),
        },
        "22": {
            "command": "write-structured-editor",
            "body": ("`apps/reading/src/modes/Write/Editor/`", "generated draft mount"),
            "script": ("src/modes/Write/Editor/tiptapAdapter.test.ts", "src/modes/Write/Outline.test.tsx"),
        },
        "23": {
            "command": "write-brainstorm-interview",
            "body": ("`substrate/write/brainstorm_blocks.py`", "`IdeaDump` section emission"),
            "script": ("tests/test_brainstorm_interview.py", "src/modes/Write/Brainstorm/IdeaDump.test.tsx"),
        },
        "24": {
            "command": "write-draft-generation-style",
            "body": ("`substrate/write/draft_generation.py`", "`creative_writer` route/UI"),
            "script": ("tests/test_draft_generation.py", "tests/test_role_creative_writer.py"),
        },
        "25": {
            "command": "write-trace-to-source",
            "body": ("`substrate/write/trace.py`", "Write editor/X-ray open path"),
            "script": ("tests/test_trace_to_source.py", "src/modes/Write/Xray.test.tsx"),
        },
        "26": {
            "command": "write-pre-outline-freeform",
            "body": ("`substrate/write/promote_context.py`", "`ContextWindow`"),
            "script": ("tests/test_promote_context.py", "src/modes/Write/ContextWindow/ContextWindow.test.tsx"),
        },
        "27": {
            "command": "write-style-conditioning",
            "body": ("`substrate/write/style_profile.py`", "`creative_writer.style_guide` conditioning"),
            "script": ("tests/test_style_conditioning.py", "tests/test_draft_generation.py"),
        },
    }

    for row_id, markers in expected.items():
        row = re.search(rf"^\| P-{row_id} \|(?P<body>.*)\|$", matrix, re.MULTILINE)
        assert row is not None, f"P-{row_id} row missing"
        body = row.group("body")

        assert f"`./scripts/canonical_verify.sh {markers['command']}`" in body
        missing_body = [marker for marker in markers["body"] if marker not in body]
        missing_script = [marker for marker in markers["script"] if marker not in script]

        assert not missing_body, f"P-{row_id} row missing marker(s): {missing_body}"
        assert not missing_script, (
            f"canonical Write profile missing P-{row_id} marker(s): {missing_script}"
        )


def test_speak_profile_rows_name_current_scope() -> None:
    """P-28..P-36 must track the concrete tests bundled by Speak profiles."""
    script = CANONICAL_VERIFY.read_text(encoding="utf-8")
    matrix = MATRIX.read_text(encoding="utf-8")

    expected = {
        "28": {
            "command": "speak-consent-rights-gate",
            "body": ("`substrate/speak/consent.py`", "`substrate/speak/publish_gate.py`"),
            "script": ("tests/test_speak_consent.py", "tests/test_speak_publish.py"),
        },
        "29": {
            "command": "speak-async-voice-interview",
            "body": ("`substrate/speak/async_interview.py`", "invitee voice route/UI"),
            "script": ("tests/test_async_interview.py", "src/modes/SpeakInvite/SpeakInvite.test.tsx"),
        },
        "30": {
            "command": "speak-project-invitations",
            "body": ("`substrate/speak/project.py`", "`substrate/speak/invitations.py`"),
            "script": ("tests/test_speak_project.py", "src/modes/SpeakIndex/SpeakIndex.test.tsx"),
        },
        "31": {
            "command": "speak-compounding-interviewer",
            "body": ("`substrate/speak/interviewer_context.py`", "DRW gap source"),
            "script": ("tests/test_compounding_interviewer.py", "tests/test_speak_drw_gap_source.py"),
        },
        "32": {
            "command": "speak-cross-interviewee-verification",
            "body": ("`substrate/speak/corroboration.py`", "Speak agreement surface"),
            "script": ("tests/test_cross_interviewee.py", "src/modes/Speak/Speak.test.tsx"),
        },
        "33": {
            "command": "speak-contributor-economics",
            "body": ("`substrate/speak/contributor.py`", "Speak settings owed-not-paid surface"),
            "script": ("tests/test_contributor_economics.py", "test_release_payout_accrues_to_escrow_no_disbursement"),
        },
        "34": {
            "command": "speak-economics-matrix",
            "body": ("`substrate/speak/economics_mode.py`", "Speak settings matrix"),
            "script": ("tests/test_economics_matrix.py", "src/modes/Speak/SpeakSettings.test.tsx"),
        },
        "35": {
            "command": "speak-biography-authoring",
            "body": ("`substrate/speak/biography.py`", "Write outline bridge"),
            "script": ("tests/test_biography_authoring.py", "src/lib/speakApi.biography.test.ts"),
        },
        "36": {
            "command": "speak-publishing-physical",
            "body": ("`substrate/speak/publish.py`", "`substrate/speak/physical_book.py`"),
            "script": ("tests/test_speak_publish.py", "src/modes/Speak/Speak.test.tsx"),
        },
    }

    for row_id, markers in expected.items():
        row = re.search(rf"^\| P-{row_id} \|(?P<body>.*)\|$", matrix, re.MULTILINE)
        assert row is not None, f"P-{row_id} row missing"
        body = row.group("body")

        assert f"`./scripts/canonical_verify.sh {markers['command']}`" in body
        missing_body = [marker for marker in markers["body"] if marker not in body]
        missing_script = [marker for marker in markers["script"] if marker not in script]

        assert not missing_body, f"P-{row_id} row missing marker(s): {missing_body}"
        assert not missing_script, (
            f"canonical Speak profile missing P-{row_id} marker(s): {missing_script}"
        )


def test_unified_profile_rows_name_current_scope() -> None:
    """P-37..P-45 must track the concrete tests bundled by Unified profiles."""
    script = CANONICAL_VERIFY.read_text(encoding="utf-8")
    matrix = MATRIX.read_text(encoding="utf-8")

    expected = {
        "37": {
            "command": "drw-reading-surface-transfer",
            "body": ("`substrate/contracts/drw_sprint_lock.py`", "`substrate/contracts/reading_surface.py`"),
            "script": ("tests/test_contracts_drw_lock.py", "src/modes/Coordination/Roadmap.test.tsx"),
        },
        "38": {
            "command": "unified-substrate-contract-lock",
            "body": ("`substrate/contracts/`", "`substrate/invariants/`"),
            "script": ("tests/test_contracts_unified_lock.py", "tests/test_invariant_registry_meta.py"),
        },
        "39": {
            "command": "unified-remote-exec-fanout",
            "body": ("`runtime/remote_exec/`", "`runtime/research_runner/` factory seam"),
            "script": ("tests/test_remote_exec_runner.py", "tests/test_remote_exec_fallback.py"),
        },
        "40": {
            "command": "unified-seams-and-collisions",
            "body": ("`substrate/seams/`", "seam/collision guards"),
            "script": ("tests/test_seam_conformance.py", "tests/e2e/test_flywheel.py"),
        },
        "41": {
            "command": "unified-navigation-ia-taxonomy",
            "body": ("`apps/reading/src/shell/workflowTaxonomy.ts`", "`NavRail`"),
            "script": ("src/shell/taxonomy.test.ts", "src/shell/navrail.panel.test.tsx"),
        },
        "42": {
            "command": "unified-coordination-gate-ledger",
            "body": ("`substrate/coordination/gate_ledger.py`", "Coordination mode"),
            "script": ("tests/test_coordination_no_fork.py", "src/modes/Coordination/Coordination.test.tsx"),
        },
        "43": {
            "command": "unified-thread-navigation",
            "body": ("`substrate/seams/thread.py`", "`ThreadBreadcrumb`"),
            "script": ("tests/test_thread_reconstruct.py", "src/shell/ThreadBreadcrumb.test.tsx"),
        },
        "44": {
            "command": "unified-cost-consent-surface",
            "body": ("`substrate/coordination/cost_view.py`", "`substrate/coordination/consent_view.py`"),
            "script": ("tests/test_cost_consent_no_disbursement.py", "src/modes/Coordination/CostConsent.test.tsx"),
        },
        "45": {
            "command": "unified-flywheel-conformance",
            "body": ("`tests/e2e/test_flywheel.py`", "`tools/codegen/check_conformance.py`"),
            "script": ("tests/e2e/test_flywheel.py", "tools/codegen/check_conformance.py"),
        },
    }

    for row_id, markers in expected.items():
        row = re.search(rf"^\| P-{row_id} \|(?P<body>.*)\|$", matrix, re.MULTILINE)
        assert row is not None, f"P-{row_id} row missing"
        body = row.group("body")

        assert f"`./scripts/canonical_verify.sh {markers['command']}`" in body
        missing_body = [marker for marker in markers["body"] if marker not in body]
        missing_script = [marker for marker in markers["script"] if marker not in script]

        assert not missing_body, f"P-{row_id} row missing marker(s): {missing_body}"
        assert not missing_script, (
            f"canonical Unified profile missing P-{row_id} marker(s): {missing_script}"
        )


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


def test_operator_closure_rows_name_canonical_bundle_scope() -> None:
    """P-52/P-53 must name the canonical dogfood/autoresearch closure bundles."""
    script = CANONICAL_VERIFY.read_text(encoding="utf-8")
    matrix = MATRIX.read_text(encoding="utf-8")

    p52 = re.search(r"^\| P-52 \|(?P<body>.*)\|$", matrix, re.MULTILINE)
    assert p52 is not None
    p52_body = p52.group("body")

    assert "`substrate/research_bridge/`" in p52_body
    assert "`antiek/cli.py`" in p52_body
    assert "`./scripts/canonical_verify.sh research-bridge-dogfood`" in p52_body
    assert "Operator ADRB log under runs/adrb plus verdict document" in p52_body
    assert "Five real operator projects" in p52_body
    for marker in (
        "tests/test_antiek_research_bridge_cli.py",
        "tests/test_research_bridge_dogfood_log.py",
        "tests/test_research_bridge_dogfood_readiness.py",
        "tests/test_research_bridge_dogfood_verdict.py",
        "tests/test_research_bridge_draft_export.py",
    ):
        assert marker in script

    p53 = re.search(r"^\| P-53 \|(?P<body>.*)\|$", matrix, re.MULTILINE)
    assert p53 is not None
    p53_body = p53.group("body")

    assert "`tools/prompt_autoresearch/`" in p53_body
    assert "`tests/test_prompt_autoresearch.py`" in p53_body
    assert "`tests/test_autoresearch_wedge1_probe.py`" in p53_body
    assert "`./scripts/canonical_verify.sh prompt-autoresearch-wedge1`" in p53_body
    assert "Operator outcomes/calibration artifacts" in p53_body
    assert "Real >=20 mutation dogfood" in p53_body
    for marker in (
        "tests/test_prompt_autoresearch.py",
        "tests/test_prompt_autoresearch_calibration.py",
        "tests/test_prompt_autoresearch_readiness.py",
        "tests/test_prompt_autoresearch_verdict.py",
        "tests/test_autoresearch_wedge1_probe.py",
        "tests/test_prompt_autoresearch_docs.py",
    ):
        assert marker in script
