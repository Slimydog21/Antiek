"""ANT-EXEC-H2V SPR-08 — subprocess tests for scripts/canonical_verify.sh."""

from __future__ import annotations

import subprocess
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
SCRIPT = ROOT / "scripts" / "canonical_verify.sh"
PY = ROOT / ".venv" / "bin" / "python"
PASS_FIXTURE = ROOT / "tests" / "fixtures" / "agent_execution" / "handoff_pass.md"


def _run(*args: str) -> subprocess.CompletedProcess[str]:
    return subprocess.run(
        [str(SCRIPT), *args],
        cwd=ROOT,
        capture_output=True,
        text=True,
        check=False,
    )


def test_canonical_verify_profile_exit_zero() -> None:
    proc = _run("profile")
    assert proc.returncode == 0, proc.stderr or proc.stdout
    assert "CANONICAL_VERIFY_OK: profile" in proc.stdout


def test_canonical_verify_handoff_pass_fixture() -> None:
    proc = _run("handoff", str(PASS_FIXTURE))
    assert proc.returncode == 0, proc.stderr or proc.stdout
    assert "HANDOFF_OK" in proc.stdout or "HANDOFF_OK" in proc.stderr
    assert "AUDIT_OK" in proc.stdout


def test_canonical_verify_cascade_hermetic() -> None:
    if not PY.is_file():
        return
    proc = _run("cascade")
    assert proc.returncode == 0, proc.stderr or proc.stdout
    assert "CANONICAL_VERIFY_OK: cascade" in proc.stdout


def test_canonical_verify_read_foundation_hermetic() -> None:
    if not PY.is_file():
        return
    proc = _run("read-foundation")
    assert proc.returncode == 0, proc.stderr or proc.stdout
    assert "CANONICAL_VERIFY_OK: read-foundation" in proc.stdout


def test_canonical_verify_read_library_hermetic() -> None:
    if not PY.is_file():
        return
    proc = _run("read-library")
    assert proc.returncode == 0, proc.stderr or proc.stdout
    assert "CANONICAL_VERIFY_OK: read-library" in proc.stdout


def test_canonical_verify_read_reader_hermetic() -> None:
    if not PY.is_file():
        return
    proc = _run("read-reader")
    assert proc.returncode == 0, proc.stderr or proc.stdout
    assert "CANONICAL_VERIFY_OK: read-reader" in proc.stdout


def test_canonical_verify_read_curate_hermetic() -> None:
    if not PY.is_file():
        return
    proc = _run("read-curate")
    assert proc.returncode == 0, proc.stderr or proc.stdout
    assert "CANONICAL_VERIFY_OK: read-curate" in proc.stdout


def test_canonical_verify_read_ad_border_hermetic() -> None:
    if not PY.is_file():
        return
    proc = _run("read-ad-border")
    assert proc.returncode == 0, proc.stderr or proc.stdout
    assert "CANONICAL_VERIFY_OK: read-ad-border" in proc.stdout


def test_canonical_verify_read_voice_notes_hermetic() -> None:
    if not PY.is_file():
        return
    proc = _run("read-voice-notes")
    assert proc.returncode == 0, proc.stderr or proc.stdout
    assert "CANONICAL_VERIFY_OK: read-voice-notes" in proc.stdout


def test_canonical_verify_read_rabbit_hole_hermetic() -> None:
    if not PY.is_file():
        return
    proc = _run("read-rabbit-hole")
    assert proc.returncode == 0, proc.stderr or proc.stdout
    assert "CANONICAL_VERIFY_OK: read-rabbit-hole" in proc.stdout


def test_canonical_verify_read_passage_research_hermetic() -> None:
    if not PY.is_file():
        return
    proc = _run("read-passage-research")
    assert proc.returncode == 0, proc.stderr or proc.stdout
    assert "CANONICAL_VERIFY_OK: read-passage-research" in proc.stdout


def test_canonical_verify_read_ad_escrow_hermetic() -> None:
    if not PY.is_file():
        return
    proc = _run("read-ad-escrow")
    assert proc.returncode == 0, proc.stderr or proc.stdout
    assert "CANONICAL_VERIFY_OK: read-ad-escrow" in proc.stdout


def test_canonical_verify_write_outline_block_hermetic() -> None:
    if not PY.is_file():
        return
    proc = _run("write-outline-block")
    assert proc.returncode == 0, proc.stderr or proc.stdout
    assert "CANONICAL_VERIFY_OK: write-outline-block" in proc.stdout


def test_canonical_verify_write_edit_capture_hermetic() -> None:
    if not PY.is_file():
        return
    proc = _run("write-edit-capture")
    assert proc.returncode == 0, proc.stderr or proc.stdout
    assert "CANONICAL_VERIFY_OK: write-edit-capture" in proc.stdout


def test_canonical_verify_write_block_repository_hermetic() -> None:
    if not PY.is_file():
        return
    proc = _run("write-block-repository")
    assert proc.returncode == 0, proc.stderr or proc.stdout
    assert "CANONICAL_VERIFY_OK: write-block-repository" in proc.stdout


def test_canonical_verify_write_structured_editor_hermetic() -> None:
    if not PY.is_file():
        return
    proc = _run("write-structured-editor")
    assert proc.returncode == 0, proc.stderr or proc.stdout
    assert "CANONICAL_VERIFY_OK: write-structured-editor" in proc.stdout


def test_canonical_verify_write_brainstorm_interview_hermetic() -> None:
    if not PY.is_file():
        return
    proc = _run("write-brainstorm-interview")
    assert proc.returncode == 0, proc.stderr or proc.stdout
    assert "CANONICAL_VERIFY_OK: write-brainstorm-interview" in proc.stdout


def test_canonical_verify_write_draft_generation_style_hermetic() -> None:
    if not PY.is_file():
        return
    proc = _run("write-draft-generation-style")
    assert proc.returncode == 0, proc.stderr or proc.stdout
    assert "CANONICAL_VERIFY_OK: write-draft-generation-style" in proc.stdout


def test_canonical_verify_write_trace_to_source_hermetic() -> None:
    if not PY.is_file():
        return
    proc = _run("write-trace-to-source")
    assert proc.returncode == 0, proc.stderr or proc.stdout
    assert "CANONICAL_VERIFY_OK: write-trace-to-source" in proc.stdout


def test_canonical_verify_write_pre_outline_freeform_hermetic() -> None:
    if not PY.is_file():
        return
    proc = _run("write-pre-outline-freeform")
    assert proc.returncode == 0, proc.stderr or proc.stdout
    assert "CANONICAL_VERIFY_OK: write-pre-outline-freeform" in proc.stdout


def test_canonical_verify_write_style_conditioning_hermetic() -> None:
    if not PY.is_file():
        return
    proc = _run("write-style-conditioning")
    assert proc.returncode == 0, proc.stderr or proc.stdout
    assert "CANONICAL_VERIFY_OK: write-style-conditioning" in proc.stdout


def test_canonical_verify_speak_consent_rights_gate_hermetic() -> None:
    if not PY.is_file():
        return
    proc = _run("speak-consent-rights-gate")
    assert proc.returncode == 0, proc.stderr or proc.stdout
    assert "CANONICAL_VERIFY_OK: speak-consent-rights-gate" in proc.stdout


def test_canonical_verify_speak_async_voice_interview_hermetic() -> None:
    if not PY.is_file():
        return
    proc = _run("speak-async-voice-interview")
    assert proc.returncode == 0, proc.stderr or proc.stdout
    assert "CANONICAL_VERIFY_OK: speak-async-voice-interview" in proc.stdout


def test_canonical_verify_speak_project_invitations_hermetic() -> None:
    if not PY.is_file():
        return
    proc = _run("speak-project-invitations")
    assert proc.returncode == 0, proc.stderr or proc.stdout
    assert "CANONICAL_VERIFY_OK: speak-project-invitations" in proc.stdout


def test_canonical_verify_speak_compounding_interviewer_hermetic() -> None:
    if not PY.is_file():
        return
    proc = _run("speak-compounding-interviewer")
    assert proc.returncode == 0, proc.stderr or proc.stdout
    assert "CANONICAL_VERIFY_OK: speak-compounding-interviewer" in proc.stdout


def test_canonical_verify_speak_cross_interviewee_verification_hermetic() -> None:
    if not PY.is_file():
        return
    proc = _run("speak-cross-interviewee-verification")
    assert proc.returncode == 0, proc.stderr or proc.stdout
    assert "CANONICAL_VERIFY_OK: speak-cross-interviewee-verification" in proc.stdout


def test_canonical_verify_speak_contributor_economics_hermetic() -> None:
    if not PY.is_file():
        return
    proc = _run("speak-contributor-economics")
    assert proc.returncode == 0, proc.stderr or proc.stdout
    assert "CANONICAL_VERIFY_OK: speak-contributor-economics" in proc.stdout


def test_canonical_verify_speak_economics_matrix_hermetic() -> None:
    if not PY.is_file():
        return
    proc = _run("speak-economics-matrix")
    assert proc.returncode == 0, proc.stderr or proc.stdout
    assert "CANONICAL_VERIFY_OK: speak-economics-matrix" in proc.stdout


def test_canonical_verify_speak_biography_authoring_hermetic() -> None:
    if not PY.is_file():
        return
    proc = _run("speak-biography-authoring")
    assert proc.returncode == 0, proc.stderr or proc.stdout
    assert "CANONICAL_VERIFY_OK: speak-biography-authoring" in proc.stdout


def test_canonical_verify_deep_research_hermetic() -> None:
    if not PY.is_file():
        return
    proc = _run("deep-research")
    assert proc.returncode == 0, proc.stderr or proc.stdout
    assert "CANONICAL_VERIFY_OK: deep-research" in proc.stdout


def test_canonical_verify_html_transport_hermetic() -> None:
    if not PY.is_file():
        return
    proc = _run("html-transport")
    assert proc.returncode == 0, proc.stderr or proc.stdout
    assert "CANONICAL_VERIFY_OK: html-transport" in proc.stdout
