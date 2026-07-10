from __future__ import annotations

import json
import os
import threading
from dataclasses import replace
from pathlib import Path

import pytest

from substrate.antiek_bench.judged import (
    AxisJudgment,
    CandidateArtifact,
    EvidenceJournal,
    EvidenceJournalCorruptionError,
    EvidenceRecord,
    JudgeResponse,
    ReconciliationRequiredError,
    blind_candidates,
    collect_judge_evidence,
    rubric_for,
    validate_judgments,
)


def judgments(task: str = "distill") -> dict[str, AxisJudgment]:
    rubric = rubric_for(task)  # type: ignore[arg-type]
    return {axis: AxisJudgment(4, f"reason for {axis}", ("A:line-1",)) for axis in rubric.axes}


class StubJudge:
    def __init__(self) -> None:
        self.calls = 0
        self.request = None

    def judge(self, request):  # type: ignore[no-untyped-def]
        self.calls += 1
        self.request = request
        return JudgeResponse(request.rubric.version, judgments(request.task_class))


def candidates() -> tuple[CandidateArtifact, CandidateArtifact]:
    return (
        CandidateArtifact(
            "first answer", "sentinel-model-a", "sentinel-provider", "evt-secret", "sk-api-key"
        ),
        CandidateArtifact("second answer", "model-b", "other-provider", "evt-other"),
    )


def test_rubric_is_closed_bounded_and_versioned() -> None:
    rubric = rubric_for("distill")
    validate_judgments(rubric, rubric.version, judgments())
    bad = judgments()
    bad["unknown"] = AxisJudgment(3, "why", ("A:1",))
    with pytest.raises(ValueError, match="axis"):
        validate_judgments(rubric, rubric.version, bad)
    for value in (0, 6):
        bad = judgments()
        bad[rubric.axes[0]] = AxisJudgment(value, "why", ("A:1",))
        with pytest.raises(ValueError, match="range"):
            validate_judgments(rubric, rubric.version, bad)
    with pytest.raises(ValueError, match="version"):
        validate_judgments(rubric, "old", judgments())
    bad = judgments()
    bad[rubric.axes[0]] = AxisJudgment(3, "", ("A:1",))
    with pytest.raises(ValueError, match="rationale"):
        validate_judgments(rubric, rubric.version, bad)


def test_blinding_is_deterministic_and_identity_private() -> None:
    request, private = blind_candidates(
        item_id="private prompt text", task_class="distill", candidates=candidates(), salt="salt"
    )
    repeated, _ = blind_candidates(
        item_id="private prompt text", task_class="distill", candidates=candidates(), salt="salt"
    )
    assert request == repeated
    public = json.dumps(request, default=lambda value: value.__dict__)
    for secret in (
        "private prompt text",
        "sentinel-model-a",
        "sentinel-provider",
        "evt-secret",
        "sk-api-key",
    ):
        assert secret not in public
    assert "first answer" in public and "second answer" in public
    assert "sentinel-model-a" in repr(private)
    assert "sentinel-provider" in repr(private)


def test_success_persists_evidence_but_no_raw_artifacts(tmp_path: Path) -> None:
    client = StubJudge()
    journal = EvidenceJournal(tmp_path / "evidence.jsonl")
    result = collect_judge_evidence(
        enabled=True,
        week_id="2026-W28",
        suite_version="suite-v3",
        item_id="raw prompt",
        task_context="Assess concise fidelity without using routing metadata.",
        task_class="distill",
        candidates=candidates(),
        judge_model="judge-model",
        salt="salt",
        client=client,
        journal=journal,
        now_ms=100,
    )
    assert result is not None and result.evidence.status == "ok" and client.calls == 1
    stored = journal.path.read_text()
    for secret in (
        "raw prompt",
        "first answer",
        "second answer",
        "sentinel-model-a",
        "sentinel-provider",
        "evt-secret",
    ):
        assert secret not in stored
    assert result.evidence.scores
    assert "reason for" not in stored and "rationales" not in stored


def test_float_score_is_rejected_even_when_numerically_integral() -> None:
    rubric = rubric_for("distill")
    bad = judgments()
    bad[rubric.axes[0]] = AxisJudgment(4.0, "reason", ("A:1",))  # type: ignore[arg-type]
    with pytest.raises(ValueError, match="range"):
        validate_judgments(rubric, rubric.version, bad)


def test_failure_is_fixed_code_and_exception_text_never_persists(tmp_path: Path) -> None:
    class Failing:
        def judge(self, request):  # type: ignore[no-untyped-def]
            raise RuntimeError("API_KEY=super-secret")

    journal = EvidenceJournal(tmp_path / "evidence.jsonl")
    result = collect_judge_evidence(
        enabled=True,
        week_id="2026-W28",
        suite_version="v",
        item_id="i",
        task_context="Assess concise fidelity.",
        task_class="distill",
        candidates=candidates(),
        judge_model="judge",
        salt="salt",
        client=Failing(),
        journal=journal,
    )
    assert result is not None and result.evidence.failure_code == "invalid_or_failed_response"
    assert "super-secret" not in journal.path.read_text()


def test_secret_bearing_evidence_reference_becomes_private_fixed_failure(tmp_path: Path) -> None:
    secret = "API_KEY=super-secret\nleak"

    class MalformedReferenceJudge:
        def judge(self, request):  # type: ignore[no-untyped-def]
            rows = judgments(request.task_class)
            axis = request.rubric.axes[0]
            rows[axis] = AxisJudgment(4, "valid rationale", (f"A:{secret}",))
            return JudgeResponse(request.rubric.version, rows)

    journal = EvidenceJournal(tmp_path / "malformed-ref.jsonl")
    result = collect_judge_evidence(
        enabled=True,
        week_id="w",
        suite_version="v",
        item_id="i",
        task_context="Assess concise fidelity.",
        task_class="distill",
        candidates=candidates(),
        judge_model="judge",
        salt="s",
        client=MalformedReferenceJudge(),
        journal=journal,
    )
    assert result is not None
    assert result.evidence.status == "failed"
    assert result.evidence.failure_code == "invalid_or_failed_response"
    persisted = journal.path.read_text()
    assert secret not in persisted
    assert "super-secret" not in persisted


def test_crash_claim_requires_reconciliation_and_never_recalls(tmp_path: Path) -> None:
    client = StubJudge()
    journal = EvidenceJournal(tmp_path / "evidence.jsonl")
    request, _ = blind_candidates(
        item_id="i", task_class="distill", candidates=candidates(), salt="s"
    )
    from substrate.antiek_bench.judged.journal import EvidenceRecord

    pending = EvidenceRecord(
        "w",
        "v",
        request.item_id_hash,
        "distill",
        request.rubric.version,
        "judge",
        tuple(row.content_hash for row in request.candidates),
        ("A", "B"),
        "pending",
        0,
    )
    assert journal.claim(pending)
    with pytest.raises(ReconciliationRequiredError):
        collect_judge_evidence(
            enabled=True,
            week_id="w",
            suite_version="v",
            item_id="i",
            task_context="Assess concise fidelity.",
            task_class="distill",
            candidates=candidates(),
            judge_model="judge",
            salt="s",
            client=client,
            journal=journal,
            now_ms=999_999,
        )
    assert client.calls == 0


def test_torn_tail_recovers_but_interior_corruption_fails(tmp_path: Path) -> None:
    journal = EvidenceJournal(tmp_path / "evidence.jsonl")
    client = StubJudge()
    collect_judge_evidence(
        enabled=True,
        week_id="w",
        suite_version="v",
        item_id="i",
        task_context="Assess concise fidelity.",
        task_class="distill",
        candidates=candidates(),
        judge_model="judge",
        salt="s",
        client=client,
        journal=journal,
    )
    with journal.path.open("ab") as handle:
        handle.write(b'{"torn":')
    assert len(journal.replay()) == 1
    journal.path.write_bytes(b'{"bad":true}\n' + journal.path.read_bytes())
    with pytest.raises(EvidenceJournalCorruptionError, match="row 1"):
        journal.replay()


def test_disabled_and_self_judging_do_not_call_client(tmp_path: Path) -> None:
    client = StubJudge()
    journal = EvidenceJournal(tmp_path / "evidence.jsonl")
    assert (
        collect_judge_evidence(
            enabled=False,
            week_id="w",
            suite_version="v",
            item_id="i",
            task_context="Assess concise fidelity.",
            task_class="distill",
            candidates=candidates(),
            judge_model="judge",
            salt="s",
            client=client,
            journal=journal,
        )
        is None
    )
    with pytest.raises(ValueError, match="own output"):
        collect_judge_evidence(
            enabled=True,
            week_id="w",
            suite_version="v",
            item_id="i",
            task_context="Assess concise fidelity.",
            task_class="distill",
            candidates=candidates(),
            judge_model="sentinel-model-a",
            salt="s",
            client=client,
            journal=journal,
        )
    assert client.calls == 0 and not journal.path.exists()


def test_concurrent_claimers_make_exactly_one_client_call(tmp_path: Path) -> None:
    client = StubJudge()
    journal = EvidenceJournal(tmp_path / "race.jsonl")
    barrier = threading.Barrier(2)
    outcomes: list[object] = []

    def run() -> None:
        barrier.wait()
        try:
            outcomes.append(
                collect_judge_evidence(
                    enabled=True,
                    week_id="w",
                    suite_version="v",
                    item_id="i",
                    task_context="Assess concise fidelity.",
                    task_class="distill",
                    candidates=candidates(),
                    judge_model="judge",
                    salt="s",
                    client=client,
                    journal=journal,
                )
            )
        except ReconciliationRequiredError as exc:
            outcomes.append(exc)

    threads = [threading.Thread(target=run) for _ in range(2)]
    for thread in threads:
        thread.start()
    for thread in threads:
        thread.join()
    assert client.calls == 1
    assert len(outcomes) == 2


def test_journal_rejects_invalid_terminal_and_claim_metadata_mismatch(tmp_path: Path) -> None:
    request, _ = blind_candidates(
        item_id="i", task_class="distill", candidates=candidates(), salt="s"
    )
    pending = EvidenceRecord(
        "w",
        "v",
        request.item_id_hash,
        "distill",
        request.rubric.version,
        "judge",
        tuple(row.content_hash for row in request.candidates),
        ("A", "B"),
        "pending",
        1,
    )
    journal = EvidenceJournal(tmp_path / "invalid.jsonl")
    assert journal.claim(pending)
    invalid = replace(pending, status="ok", scores=(("unknown", 99),))
    with pytest.raises(ValueError):
        journal.settle(invalid)
    failed = replace(pending, status="failed", failure_code="API_KEY=secret")
    with pytest.raises(ValueError, match="fixed"):
        journal.settle(failed)
    mismatch = replace(
        pending, status="failed", failure_code="invalid_or_failed_response", claimed_at_ms=2
    )
    with pytest.raises(ValueError, match="metadata"):
        journal.settle(mismatch)


def test_journal_completes_short_reads_and_writes(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    request, _ = blind_candidates(
        item_id="i", task_class="distill", candidates=candidates(), salt="s"
    )
    pending = EvidenceRecord(
        "w",
        "v",
        request.item_id_hash,
        "distill",
        request.rubric.version,
        "judge",
        tuple(row.content_hash for row in request.candidates),
        ("A", "B"),
        "pending",
        1,
    )
    journal = EvidenceJournal(tmp_path / "short-io.jsonl")
    real_write = os.write
    monkeypatch.setattr(
        os,
        "write",
        lambda fd, payload: real_write(fd, payload[: max(1, len(payload) // 3)]),
    )
    assert journal.claim(pending)
    monkeypatch.setattr(os, "write", real_write)
    original = journal.path.read_bytes()
    real_read = os.read
    monkeypatch.setattr(os, "read", lambda fd, size: real_read(fd, min(size, 13)))
    assert journal.claim(pending) is False
    assert journal.path.read_bytes() == original


def test_torn_tail_truncation_is_fsynced_on_duplicate(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    journal = EvidenceJournal(tmp_path / "torn-fsync.jsonl")
    request, _ = blind_candidates(
        item_id="i", task_class="distill", candidates=candidates(), salt="s"
    )
    pending = EvidenceRecord(
        "w",
        "v",
        request.item_id_hash,
        "distill",
        request.rubric.version,
        "judge",
        tuple(row.content_hash for row in request.candidates),
        ("A", "B"),
        "pending",
        1,
    )
    assert journal.claim(pending)
    with journal.path.open("ab") as handle:
        handle.write(b'{"torn":')
    calls = 0
    real_fsync = os.fsync

    def observe(fd: int) -> None:
        nonlocal calls
        calls += 1
        real_fsync(fd)

    monkeypatch.setattr(os, "fsync", observe)
    assert journal.claim(pending) is False
    assert calls == 1
    assert journal.path.read_bytes().endswith(b"\n")


def test_stored_identity_tampering_is_corruption(tmp_path: Path) -> None:
    journal = EvidenceJournal(tmp_path / "tamper.jsonl")
    client = StubJudge()
    collect_judge_evidence(
        enabled=True,
        week_id="w",
        suite_version="v",
        item_id="i",
        task_context="Assess concise fidelity.",
        task_class="distill",
        candidates=candidates(),
        judge_model="judge",
        salt="s",
        client=client,
        journal=journal,
    )
    lines = journal.path.read_text().splitlines()
    payload = json.loads(lines[0])
    payload["evidence_id"] = "je_tampered"
    journal.path.write_text(json.dumps(payload) + "\n" + "\n".join(lines[1:]) + "\n")
    with pytest.raises(EvidenceJournalCorruptionError):
        journal.replay()
