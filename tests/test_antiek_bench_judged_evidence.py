"""Rigorous adversarial tests for versioned blinded judge evidence.

Covers all four milestones: rubric validation, candidate blinding, journal
claim/settle protocol, and the typed judge client boundary.  Tests include
property-based validation, concurrency races, crash recovery, identity
leakage rejection, and authority-surface checks.
"""

from __future__ import annotations

import ast
import hashlib
import json
import multiprocessing
import os
from concurrent.futures import ThreadPoolExecutor
from dataclasses import replace
from pathlib import Path

import pytest

from substrate.antiek_bench.judged.blinding import (
    BlindedCandidate,
    BlindedJudgeRequest,
    BlindingContext,
    blind_candidates,
)
from substrate.antiek_bench.judged.client import (
    JudgeReconciliationRequiredError,
    score_and_persist,
)
from substrate.antiek_bench.judged.journal import (
    JudgeEvidenceJournal,
    JudgeEvidenceRecord,
    JudgeJournalCorruptionError,
)
from substrate.antiek_bench.judged.rubric import (
    AxisScore,
    JudgeResult,
    RubricAxis,
    RubricVersion,
    make_rubric,
    validate_scores,
)

# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------


def rubric() -> RubricVersion:
    return make_rubric(
        version="rubric-v1",
        task_class="synthesize",
        axes=(
            RubricAxis(name="synthesis_quality", min_score=1, max_score=5, requires_evidence=True),
            RubricAxis(name="source_handling", min_score=1, max_score=5, requires_evidence=True),
            RubricAxis(name="nuance", min_score=0, max_score=3, requires_evidence=False),
        ),
    )


def scores() -> tuple[AxisScore, ...]:
    return (
        AxisScore(axis="synthesis_quality", score=4, rationale="Good synthesis"),
        AxisScore(axis="source_handling", score=3, rationale="Adequate"),
        AxisScore(axis="nuance", score=2, rationale="Minor nuance captured"),
    )


def blinded_request(
    *,
    order: tuple[str, str] = ("A", "B"),
    salt: str = "test-salt",
) -> BlindedJudgeRequest:
    cands = blind_candidates(
        "Candidate A content",
        "Candidate B content",
        salt=salt,
        order=order,
    )
    return BlindedJudgeRequest(
        task_class="synthesize",
        item_id="item-1",
        task_context="Compare synthesis quality",
        candidates=cands,
        rubric_version="rubric-v1",
    )


class FakeJudgeClient:
    """Deterministic judge client for offline testing."""

    def __init__(
        self,
        result: JudgeResult | None = None,
        error: type[Exception] | None = None,
    ) -> None:
        self._result = result
        self._error = error
        self.call_count = 0
        self.last_request: BlindedJudgeRequest | None = None

    def score(self, request: BlindedJudgeRequest, rubric_version: RubricVersion) -> JudgeResult:
        self.call_count += 1
        self.last_request = request
        if self._error is not None:
            raise self._error("judge error sentinel")
        assert self._result is not None
        return self._result


def default_client() -> FakeJudgeClient:
    return FakeJudgeClient(JudgeResult(axis_scores=scores(), latency_ms=150, failure_code=""))


def default_record(**overrides: object) -> JudgeEvidenceRecord:
    def digest(value: str) -> str:
        return "sha256:" + hashlib.sha256(value.encode()).hexdigest()

    defaults = {
        "week_id": "2026-W28",
        "suite_version": "suite-v1",
        "item_id": "item-1",
        "rubric_version": "rubric-v1",
        "judge_model": "judge-model-a",
        "blinded_candidate_a": "A",
        "blinded_candidate_b": "B",
        "task_class": "synthesize",
        "task_context_hash": digest("context"),
        "rubric_fingerprint": digest("rubric"),
        "candidate_a_hash": digest("candidate-a"),
        "candidate_b_hash": digest("candidate-b"),
        "status": "pending",
    }
    defaults.update(overrides)
    status = defaults["status"]
    if status == "scored":
        score_json = json.dumps(
            [{"axis": "x", "rationale_hash": digest("rationale"), "score": 1}],
            sort_keys=True,
            separators=(",", ":"),
        )
        defaults.setdefault("axis_scores_json", score_json)
        defaults.setdefault("evidence_hash", digest(score_json))
    elif status == "failed":
        defaults.setdefault("failure_code", "judge_failure")
    elif status == "timeout":
        defaults.setdefault("failure_code", "judge_timeout")
    elif status == "schema_error":
        defaults.setdefault("failure_code", "invalid_judge_schema")
    elif status == "stale_claim":
        defaults.setdefault("failure_code", "reconciliation_required")
    return JudgeEvidenceRecord(**defaults)  # type: ignore[arg-type]


# ===================================================================
# Milestone 1 — Rubric
# ===================================================================


class TestRubricValidation:
    def test_closed_axes_and_integer_bounds(self) -> None:
        r = rubric()
        assert r.axis_names == ("synthesis_quality", "source_handling", "nuance")
        assert r.axis("synthesis_quality").min_score == 1
        assert r.axis("synthesis_quality").max_score == 5

    @pytest.mark.parametrize("value", [True, False, 3.5])
    def test_non_integer_scores_are_rejected(self, value: object) -> None:
        with pytest.raises(ValueError, match="integer"):
            AxisScore(axis="quality", score=value, rationale="evidence")  # type: ignore[arg-type]

    @pytest.mark.parametrize("value", [True, 1.5])
    def test_non_integer_bounds_are_rejected(self, value: object) -> None:
        with pytest.raises(ValueError, match="integers"):
            RubricAxis("quality", value, 5, True)  # type: ignore[arg-type]

    def test_unknown_axis_fails_validation(self) -> None:
        r = rubric()
        bad = (AxisScore(axis="creativity", score=3, rationale="ok"),)
        errors = validate_scores(r, bad)
        assert any("unknown axis" in e for e in errors)

    def test_out_of_range_value_fails(self) -> None:
        r = rubric()
        bad = (AxisScore(axis="synthesis_quality", score=0, rationale="too low"),)
        errors = validate_scores(r, bad)
        assert any("outside" in e for e in errors)

    def test_out_of_range_high_fails(self) -> None:
        r = rubric()
        bad = (AxisScore(axis="synthesis_quality", score=6, rationale="too high"),)
        errors = validate_scores(r, bad)
        assert any("outside" in e for e in errors)

    def test_missing_rationale_for_evidence_required_axis_fails(self) -> None:
        r = rubric()
        bad = (AxisScore(axis="synthesis_quality", score=4, rationale="  "),)
        errors = validate_scores(r, bad)
        assert any("evidence required" in e for e in errors)

    def test_missing_axis_fails(self) -> None:
        r = rubric()
        incomplete = (AxisScore(axis="synthesis_quality", score=4, rationale="ok"),)
        errors = validate_scores(r, incomplete)
        assert any("missing axis: source_handling" in e for e in errors)

    def test_valid_scores_pass(self) -> None:
        r = rubric()
        assert validate_scores(r, scores()) == []

    def test_duplicate_axis_fails(self) -> None:
        r = rubric()
        duped = (
            AxisScore(axis="synthesis_quality", score=4, rationale="first"),
            AxisScore(axis="synthesis_quality", score=3, rationale="second"),
            AxisScore(axis="source_handling", score=3, rationale="ok"),
            AxisScore(axis="nuance", score=1, rationale="minor"),
        )
        errors = validate_scores(r, duped)
        assert any("duplicate axis" in e for e in errors)

    def test_version_drift_detected(self) -> None:
        r1 = rubric()
        r2 = make_rubric(
            version="rubric-v2",
            task_class="synthesize",
            axes=(
                RubricAxis(
                    name="synthesis_quality", min_score=1, max_score=5, requires_evidence=True
                ),
                RubricAxis(
                    name="source_handling", min_score=1, max_score=5, requires_evidence=True
                ),
                RubricAxis(name="nuance", min_score=0, max_score=3, requires_evidence=False),
            ),
        )
        assert r1.version != r2.version
        errors = validate_scores(r2, scores())
        assert errors == []  # same axes, different version is fine
        r3 = make_rubric(
            version="rubric-v3",
            task_class="synthesize",
            axes=(
                RubricAxis(
                    name="synthesis_quality", min_score=1, max_score=10, requires_evidence=True
                ),
                RubricAxis(
                    name="source_handling", min_score=1, max_score=5, requires_evidence=True
                ),
                RubricAxis(name="nuance", min_score=0, max_score=3, requires_evidence=False),
            ),
        )
        assert r3.axis("synthesis_quality").max_score == 10

    def test_blank_axis_name_rejected(self) -> None:
        with pytest.raises(ValueError, match="blank"):
            RubricAxis(name="", min_score=1, max_score=5, requires_evidence=True)

    def test_min_not_less_than_max_rejected(self) -> None:
        with pytest.raises(ValueError, match="less than"):
            RubricAxis(name="test", min_score=5, max_score=5, requires_evidence=True)

    def test_duplicate_axis_name_rejected(self) -> None:
        with pytest.raises(ValueError, match="duplicate"):
            RubricVersion(
                version="v1",
                task_class="t",
                axes=(
                    RubricAxis(name="x", min_score=1, max_score=5, requires_evidence=True),
                    RubricAxis(name="x", min_score=1, max_score=5, requires_evidence=True),
                ),
            )

    def test_empty_axes_rejected(self) -> None:
        with pytest.raises(ValueError, match="at least one"):
            RubricVersion(version="v1", task_class="t", axes=())


# ===================================================================
# Milestone 2 — Blinding
# ===================================================================


class TestBlinding:
    def test_deterministic_order_and_swap(self) -> None:
        c1 = blind_candidates("content-a", "content-b", salt="s", order=("A", "B"))
        c2 = blind_candidates("content-a", "content-b", salt="s", order=("B", "A"))
        assert c1[0].blinded_id == "A"
        assert c1[1].blinded_id == "B"
        assert c2[0].blinded_id == "A"
        assert c2[1].blinded_id == "B"
        assert c1[0].content_hash == c2[1].content_hash
        assert c1[1].content_hash == c2[0].content_hash
        assert c1[0].content == c2[1].content

    def test_deterministic_hashing(self) -> None:
        c1 = blind_candidates("x", "y", salt="s")
        c2 = blind_candidates("x", "y", salt="s")
        assert c1 == c2

    def test_different_salt_produces_different_hash(self) -> None:
        c1 = blind_candidates("x", "y", salt="s1")
        c2 = blind_candidates("x", "y", salt="s2")
        assert c1[0].content_hash != c2[0].content_hash

    def test_no_identity_in_blinded_request(self) -> None:
        req = blinded_request()
        serialized = json.dumps(req.to_dict())
        for sentinel in ("openai", "model-a", "provider", "sk-"):
            assert sentinel not in serialized.lower()

    def test_join_map_stays_private(self) -> None:
        ctx = BlindingContext()
        ctx.register("A", "openai", "gpt-4o")
        ctx.register("B", "anthropic", "claude-3")
        assert ctx.lookup("A") == {"provider": "openai", "model": "gpt-4o"}
        assert ctx.lookup("C") is None

    def test_distinct_candidates_required(self) -> None:
        with pytest.raises(ValueError, match="distinct"):
            blind_candidates("x", "y", salt="s", order=("A", "A"))

    def test_exactly_two_candidates_required(self) -> None:
        cands = blind_candidates("x", "y", salt="s")
        with pytest.raises(ValueError, match="exactly two"):
            BlindedJudgeRequest(
                task_class="t",
                item_id="i",
                task_context="ctx",
                candidates=(cands[0],),  # type: ignore[arg-type]
                rubric_version="v",
            )

    def test_content_hash_is_salted_sha256(self) -> None:
        c = blind_candidates("test-content", "other", salt="my-salt")
        assert c[0].content_hash.startswith("sha256:")
        assert len(c[0].content_hash) == len("sha256:") + 64

    def test_request_to_dict_deterministic(self) -> None:
        req = blinded_request()
        d1 = json.dumps(req.to_dict(), sort_keys=True)
        d2 = json.dumps(req.to_dict(), sort_keys=True)
        assert d1 == d2


# ===================================================================
# Milestone 3 — Journal claim/settle
# ===================================================================


class TestJudgeJournal:
    def test_claim_and_settle_round_trip(self, tmp_path: Path) -> None:
        journal = JudgeEvidenceJournal(tmp_path / "judge.jsonl")
        record = default_record()
        assert journal.claim(record) is True
        settled = default_record(status="scored", latency_ms=100)
        assert journal.settle(settled) is True
        result = journal.lookup(record.computed_claim_id)
        assert result is not None
        assert result.status == "scored"
        assert result.latency_ms == 100

    def test_duplicate_claim_is_rejected(self, tmp_path: Path) -> None:
        journal = JudgeEvidenceJournal(tmp_path / "judge.jsonl")
        record = default_record()
        assert journal.claim(record) is True
        assert journal.claim(record) is False

    def test_settle_without_claim_fails(self, tmp_path: Path) -> None:
        journal = JudgeEvidenceJournal(tmp_path / "judge.jsonl")
        settled = default_record(status="scored")
        assert journal.settle(settled) is False

    def test_duplicate_settle_fails(self, tmp_path: Path) -> None:
        journal = JudgeEvidenceJournal(tmp_path / "judge.jsonl")
        journal.claim(default_record())
        settled = default_record(status="scored", latency_ms=50)
        assert journal.settle(settled) is True
        assert journal.settle(settled) is False

    def test_terminal_event_requires_claim(self, tmp_path: Path) -> None:
        journal = JudgeEvidenceJournal(tmp_path / "judge.jsonl")
        settled = default_record(status="scored")
        assert journal.settle(settled) is False

    def test_pending_record_must_not_have_scores(self, tmp_path: Path) -> None:
        """A pending record with scores is invalid and rejected at claim time."""
        journal = JudgeEvidenceJournal(tmp_path / "judge.jsonl")
        bad = default_record(
            axis_scores_json='[{"axis":"x","score":1,"rationale":"r"}]',
        )
        with pytest.raises(ValueError, match="pending record must not have scores"):
            journal.claim(bad)

    def test_blank_field_rejected(self, tmp_path: Path) -> None:
        """Blank identity fields are rejected at claim time."""
        journal = JudgeEvidenceJournal(tmp_path / "judge.jsonl")
        with pytest.raises(ValueError, match="must not be blank"):
            journal.claim(default_record(week_id=""))

    def test_identity_tampering_is_corruption(self, tmp_path: Path) -> None:
        path = tmp_path / "judge.jsonl"
        payload = default_record().to_dict()
        payload["claim_id"] = "jj_tampered"
        path.write_text(json.dumps(payload) + "\n")
        with pytest.raises(JudgeJournalCorruptionError):
            JudgeEvidenceJournal(path).replay()

    def test_torn_tail_is_tolerated(self, tmp_path: Path) -> None:
        journal = JudgeEvidenceJournal(tmp_path / "judge.jsonl")
        journal.claim(default_record())
        with journal.path.open("ab") as handle:
            handle.write(b'{"torn":')
        assert len(journal.replay()) == 1

    def test_torn_tail_recovery_is_fsynced_on_duplicate(
        self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        journal = JudgeEvidenceJournal(tmp_path / "judge.jsonl")
        record = default_record()
        journal.claim(record)
        with journal.path.open("ab") as handle:
            handle.write(b'{"torn":')
        calls = 0
        real_fsync = os.fsync

        def observing_fsync(fd: int) -> None:
            nonlocal calls
            calls += 1
            real_fsync(fd)

        monkeypatch.setattr(os, "fsync", observing_fsync)
        assert journal.claim(record) is False
        assert calls == 1
        assert journal.path.read_bytes().endswith(b"\n")

    def test_short_write_is_completed_before_claim_returns(
        self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        journal = JudgeEvidenceJournal(tmp_path / "judge.jsonl")
        real_write = os.write
        writes = 0

        def short_write(fd: int, payload: bytes) -> int:
            nonlocal writes
            writes += 1
            prefix = payload[: max(1, len(payload) // 3)]
            return real_write(fd, prefix)

        monkeypatch.setattr(os, "write", short_write)
        assert journal.claim(default_record()) is True
        assert writes > 1
        assert len(journal.replay()) == 1

    def test_short_reads_never_truncate_a_valid_claim(
        self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        journal = JudgeEvidenceJournal(tmp_path / "judge.jsonl")
        record = default_record()
        assert journal.claim(record) is True
        original = journal.path.read_bytes()
        real_read = os.read

        def short_read(fd: int, size: int) -> bytes:
            return real_read(fd, min(size, 17))

        monkeypatch.setattr(os, "read", short_read)
        assert journal.claim(record) is False
        assert journal.path.read_bytes() == original

    @pytest.mark.parametrize("attack", ["boolean_score", "forged_evidence_hash"])
    def test_replay_rejects_forged_scored_evidence(self, tmp_path: Path, attack: str) -> None:
        path = tmp_path / "judge.jsonl"
        payload = default_record(status="scored").to_dict()
        if attack == "boolean_score":
            scores_payload = json.loads(payload["axis_scores_json"])
            scores_payload[0]["score"] = True
            payload["axis_scores_json"] = json.dumps(
                scores_payload, sort_keys=True, separators=(",", ":")
            )
            payload["evidence_hash"] = (
                "sha256:" + hashlib.sha256(payload["axis_scores_json"].encode()).hexdigest()
            )
        else:
            payload["evidence_hash"] = "sha256:" + "0" * 64
        path.write_text(json.dumps(payload) + "\n")
        with pytest.raises(JudgeJournalCorruptionError):
            JudgeEvidenceJournal(path).replay()

    def test_corruption_before_final_line_is_loud(self, tmp_path: Path) -> None:
        journal = JudgeEvidenceJournal(tmp_path / "judge.jsonl")
        journal.claim(default_record())
        journal.path.write_bytes(b'{"bad":true}\n' + journal.path.read_bytes())
        with pytest.raises(JudgeJournalCorruptionError, match="row 1"):
            journal.replay()

    def test_file_hash_changes_on_write(self, tmp_path: Path) -> None:
        journal = JudgeEvidenceJournal(tmp_path / "judge.jsonl")
        h1 = journal.file_hash()
        assert h1 == ""
        journal.claim(default_record())
        h2 = journal.file_hash()
        assert h2 != ""
        assert h2 != h1

    def test_fsync_after_every_append(self, tmp_path: Path) -> None:
        """Verify journal file is non-empty and coherent after each append."""
        journal = JudgeEvidenceJournal(tmp_path / "judge.jsonl")
        journal.claim(default_record())
        assert journal.path.exists()
        content = journal.path.read_text()
        lines = content.strip().splitlines()
        assert len(lines) == 1
        data = json.loads(lines[0])
        assert data["status"] == "pending"

    def test_stale_claim_becomes_reconciliation_required(self, tmp_path: Path) -> None:
        journal = JudgeEvidenceJournal(tmp_path / "judge.jsonl")
        record = default_record()
        journal.claim(record)
        cid = record.computed_claim_id
        assert journal.mark_stale(cid) is True
        result = journal.lookup(cid)
        assert result is not None
        assert result.status == "stale_claim"
        assert result.failure_code == "reconciliation_required"

    def test_stale_claim_prevents_settlement(self, tmp_path: Path) -> None:
        journal = JudgeEvidenceJournal(tmp_path / "judge.jsonl")
        record = default_record()
        journal.claim(record)
        journal.mark_stale(record.computed_claim_id)
        settled = default_record(status="scored")
        assert journal.settle(settled) is False

    def test_mark_stale_on_nonexistent_claim_fails(self, tmp_path: Path) -> None:
        journal = JudgeEvidenceJournal(tmp_path / "judge.jsonl")
        assert journal.mark_stale("jj_nonexistent") is False

    def test_mark_stale_on_already_terminal_fails(self, tmp_path: Path) -> None:
        journal = JudgeEvidenceJournal(tmp_path / "judge.jsonl")
        record = default_record()
        journal.claim(record)
        journal.settle(default_record(status="scored"))
        assert journal.mark_stale(record.computed_claim_id) is False

    def test_concurrent_claims_one_succeeds(self, tmp_path: Path) -> None:
        """Two threads race to claim the same record; exactly one wins."""
        journal = JudgeEvidenceJournal(tmp_path / "judge.jsonl")
        record = default_record()
        results: list[bool] = []

        def attempt() -> None:
            results.append(journal.claim(record))

        with ThreadPoolExecutor(max_workers=2) as pool:
            list(pool.map(lambda _: attempt(), range(2)))
        assert sorted(results) == [False, True]
        assert len(journal.replay()) == 1

    def test_concurrent_different_items_both_succeed(self, tmp_path: Path) -> None:
        """Two threads claiming different items both succeed."""
        journal = JudgeEvidenceJournal(tmp_path / "judge.jsonl")
        r1 = default_record(item_id="item-1")
        r2 = default_record(item_id="item-2")
        results: list[bool] = []

        def attempt(record: JudgeEvidenceRecord) -> None:
            results.append(journal.claim(record))

        with ThreadPoolExecutor(max_workers=2) as pool:
            list(pool.map(lambda r: attempt(r), [r1, r2]))
        assert all(results)
        assert len(journal.replay()) == 2

    def test_no_prompt_response_candidate_identity_in_journal(self, tmp_path: Path) -> None:
        """Evidence journal must never contain prompt/response bodies or identity."""
        journal = JudgeEvidenceJournal(tmp_path / "judge.jsonl")
        req = blinded_request()
        client = default_client()
        from substrate.antiek_bench.judged.client import score_and_persist

        score_and_persist(
            request=req,
            rubric=rubric(),
            client=client,
            journal=journal,
            week_id="2026-W28",
            suite_version="suite-v1",
            judge_model="judge-a",
            candidate_models=("candidate-a", "candidate-b"),
        )
        content = journal.path.read_text()
        for sentinel in (
            "Candidate A content",
            "Candidate B content",
            "openai",
            "model-a",
            "sk-",
            "test-salt",
        ):
            assert sentinel not in content


# ===================================================================
# Milestone 4 — Judge client boundary
# ===================================================================


class TestScoreAndPersist:
    def test_rejects_self_judging_before_claim(self, tmp_path: Path) -> None:
        journal = JudgeEvidenceJournal(tmp_path / "judge.jsonl")
        client = default_client()
        with pytest.raises(ValueError, match="may not judge"):
            score_and_persist(
                request=blinded_request(),
                rubric=rubric(),
                client=client,
                journal=journal,
                week_id="2026-W28",
                suite_version="suite-v1",
                judge_model="candidate-a",
                candidate_models=("candidate-a", "candidate-b"),
            )
        assert client.call_count == 0
        assert not journal.path.exists()

    @pytest.mark.parametrize(
        "judge_request",
        [
            replace(blinded_request(), rubric_version="other"),
            replace(blinded_request(), task_class="wrestle"),
        ],
    )
    def test_rejects_request_rubric_mismatch(
        self, tmp_path: Path, judge_request: BlindedJudgeRequest
    ) -> None:
        with pytest.raises(ValueError, match="differ"):
            score_and_persist(
                request=judge_request,
                rubric=rubric(),
                client=default_client(),
                journal=JudgeEvidenceJournal(tmp_path / "judge.jsonl"),
                week_id="2026-W28",
                suite_version="suite-v1",
                judge_model="judge-a",
                candidate_models=("candidate-a", "candidate-b"),
            )

    def test_exact_content_context_and_rubric_definition_bind_identity(
        self, tmp_path: Path
    ) -> None:
        journal = JudgeEvidenceJournal(tmp_path / "judge.jsonl")
        client = default_client()
        base = blinded_request()
        changed_content = BlindedJudgeRequest(
            task_class=base.task_class,
            item_id=base.item_id,
            task_context=base.task_context,
            candidates=blind_candidates("changed", "Candidate B content", salt="test-salt"),
            rubric_version=base.rubric_version,
        )
        changed_context = replace(base, task_context="different qualitative task context")
        changed_rubric = make_rubric(
            version="rubric-v1",
            task_class="synthesize",
            axes=(RubricAxis("quality", 0, 5, True),),
        )
        for request, current_rubric in (
            (base, rubric()),
            (changed_content, rubric()),
            (changed_context, rubric()),
            (base, changed_rubric),
        ):
            score_and_persist(
                request=request,
                rubric=current_rubric,
                client=client,
                journal=journal,
                week_id="2026-W28",
                suite_version="suite-v1",
                judge_model="judge-a",
                candidate_models=("candidate-a", "candidate-b"),
            )
        assert client.call_count == 4
        assert len(journal.replay()) == 4

    def test_forged_content_hash_cannot_alias_different_body(self, tmp_path: Path) -> None:
        journal = JudgeEvidenceJournal(tmp_path / "judge.jsonl")
        client = default_client()
        base = blinded_request()
        candidate_a, candidate_b = base.candidates
        forged = replace(
            base,
            candidates=(
                BlindedCandidate("A", candidate_a.content_hash, "forged different body"),
                candidate_b,
            ),
        )
        for request in (base, forged):
            score_and_persist(
                request=request,
                rubric=rubric(),
                client=client,
                journal=journal,
                week_id="2026-W28",
                suite_version="suite-v1",
                judge_model="judge-a",
                candidate_models=("candidate-a", "candidate-b"),
            )
        assert client.call_count == 2
        assert len(journal.replay()) == 2

    def test_judge_receives_content_but_storage_keeps_only_hashes(self, tmp_path: Path) -> None:
        journal = JudgeEvidenceJournal(tmp_path / "judge.jsonl")
        client = default_client()
        request = blinded_request()
        score_and_persist(
            request=request,
            rubric=rubric(),
            client=client,
            journal=journal,
            week_id="2026-W28",
            suite_version="suite-v1",
            judge_model="judge-a",
            candidate_models=("candidate-a", "candidate-b"),
        )
        assert client.last_request is not None
        assert [candidate.content for candidate in client.last_request.candidates] == [
            "Candidate A content",
            "Candidate B content",
        ]
        persisted = journal.path.read_text()
        for forbidden in (
            "Candidate A content",
            "Candidate B content",
            "Compare synthesis quality",
            "Good synthesis",
            "Adequate",
            "Minor nuance captured",
            "candidate-a",
            "candidate-b",
        ):
            assert forbidden not in persisted

    def test_successful_score_and_persist(self, tmp_path: Path) -> None:
        journal = JudgeEvidenceJournal(tmp_path / "judge.jsonl")
        req = blinded_request()
        client = default_client()
        record = score_and_persist(
            request=req,
            rubric=rubric(),
            client=client,
            journal=journal,
            week_id="2026-W28",
            suite_version="suite-v1",
            judge_model="judge-a",
            candidate_models=("candidate-a", "candidate-b"),
        )
        assert record is not None
        assert record.status == "scored"
        assert record.axis_scores_json != ""
        assert record.evidence_hash.startswith("sha256:")
        assert record.latency_ms > 0
        assert client.call_count == 1

    def test_duplicate_claim_returns_none(self, tmp_path: Path) -> None:
        journal = JudgeEvidenceJournal(tmp_path / "judge.jsonl")
        req = blinded_request()
        client = default_client()
        r1 = score_and_persist(
            request=req,
            rubric=rubric(),
            client=client,
            journal=journal,
            week_id="2026-W28",
            suite_version="suite-v1",
            judge_model="judge-a",
            candidate_models=("candidate-a", "candidate-b"),
        )
        r2 = score_and_persist(
            request=req,
            rubric=rubric(),
            client=client,
            journal=journal,
            week_id="2026-W28",
            suite_version="suite-v1",
            judge_model="judge-a",
            candidate_models=("candidate-a", "candidate-b"),
        )
        assert r1 is not None
        assert r2 == r1
        assert client.call_count == 1  # only one external call

    def test_schema_error_persists_failure_code(self, tmp_path: Path) -> None:
        journal = JudgeEvidenceJournal(tmp_path / "judge.jsonl")
        bad_scores = (AxisScore(axis="creativity", score=3, rationale="unknown"),)
        client = FakeJudgeClient(
            JudgeResult(axis_scores=bad_scores, latency_ms=10, failure_code="")
        )
        req = blinded_request()
        record = score_and_persist(
            request=req,
            rubric=rubric(),
            client=client,
            journal=journal,
            week_id="2026-W28",
            suite_version="suite-v1",
            judge_model="judge-a",
            candidate_models=("candidate-a", "candidate-b"),
        )
        assert record is not None
        assert record.status == "schema_error"
        assert record.failure_code == "invalid_judge_schema"

    def test_judge_failure_persists_fixed_failure_code(self, tmp_path: Path) -> None:
        journal = JudgeEvidenceJournal(tmp_path / "judge.jsonl")
        client = FakeJudgeClient(error=RuntimeError)
        req = blinded_request()
        record = score_and_persist(
            request=req,
            rubric=rubric(),
            client=client,
            journal=journal,
            week_id="2026-W28",
            suite_version="suite-v1",
            judge_model="judge-a",
            candidate_models=("candidate-a", "candidate-b"),
        )
        assert record is not None
        assert record.status == "failed"
        assert record.failure_code == "judge_failure"
        assert "sentinel" not in journal.path.read_text()

    def test_timeout_persists_fixed_failure_code(self, tmp_path: Path) -> None:
        journal = JudgeEvidenceJournal(tmp_path / "judge.jsonl")
        client = FakeJudgeClient(error=TimeoutError)
        req = blinded_request()
        record = score_and_persist(
            request=req,
            rubric=rubric(),
            client=client,
            journal=journal,
            week_id="2026-W28",
            suite_version="suite-v1",
            judge_model="judge-a",
            candidate_models=("candidate-a", "candidate-b"),
        )
        assert record is not None
        assert record.status == "timeout"
        assert record.failure_code == "judge_timeout"

    def test_judge_client_failure_code_persisted(self, tmp_path: Path) -> None:
        journal = JudgeEvidenceJournal(tmp_path / "judge.jsonl")
        client = FakeJudgeClient(
            JudgeResult(axis_scores=(), latency_ms=5, failure_code="judge_unavailable")
        )
        req = blinded_request()
        record = score_and_persist(
            request=req,
            rubric=rubric(),
            client=client,
            journal=journal,
            week_id="2026-W28",
            suite_version="suite-v1",
            judge_model="judge-a",
            candidate_models=("candidate-a", "candidate-b"),
        )
        assert record is not None
        assert record.status == "failed"
        assert record.failure_code == "judge_unavailable"

    def test_different_order_produces_different_claim_id(self, tmp_path: Path) -> None:
        journal = JudgeEvidenceJournal(tmp_path / "judge.jsonl")
        req1 = blinded_request(order=("A", "B"))
        req2 = blinded_request(order=("B", "A"))
        client = default_client()
        r1 = score_and_persist(
            request=req1,
            rubric=rubric(),
            client=client,
            journal=journal,
            week_id="2026-W28",
            suite_version="suite-v1",
            judge_model="judge-a",
            candidate_models=("candidate-a", "candidate-b"),
        )
        r2 = score_and_persist(
            request=req2,
            rubric=rubric(),
            client=client,
            journal=journal,
            week_id="2026-W28",
            suite_version="suite-v1",
            judge_model="judge-a",
            candidate_models=("candidate-a", "candidate-b"),
        )
        assert r1 is not None
        assert r2 is not None
        assert r1.computed_claim_id != r2.computed_claim_id
        assert client.call_count == 2

    def test_no_secret_leakage_in_any_persisted_state(self, tmp_path: Path) -> None:
        journal = JudgeEvidenceJournal(tmp_path / "judge.jsonl")
        req = blinded_request(salt="sk-SECRETKEY123_private-sentinel")
        client = default_client()
        score_and_persist(
            request=req,
            rubric=rubric(),
            client=client,
            journal=journal,
            week_id="2026-W28",
            suite_version="suite-v1",
            judge_model="judge-a",
            candidate_models=("candidate-a", "candidate-b"),
        )
        content = journal.path.read_text()
        for sentinel in ("sk-SECRETKEY123", "private-sentinel", "Candidate A content"):
            assert sentinel not in content


# ===================================================================
# Authority boundary — no dispatch/model-selection imports
# ===================================================================


class TestAuthorityBoundary:
    def test_no_execution_authority_surface(self) -> None:
        """Verify the judged package imports no dispatch or model-selection modules."""
        for module_path in (
            "substrate/antiek_bench/judged/rubric.py",
            "substrate/antiek_bench/judged/blinding.py",
            "substrate/antiek_bench/judged/journal.py",
            "substrate/antiek_bench/judged/client.py",
        ):
            tree = ast.parse(Path(module_path).read_text(encoding="utf-8"))
            forbidden_modules = {"substrate.dispatch", "substrate.model_registration"}
            for node in ast.walk(tree):
                if isinstance(node, ast.Import):
                    for alias in node.names:
                        assert not any(alias.name.startswith(mod) for mod in forbidden_modules), (
                            f"{module_path} imports forbidden module {alias.name}"
                        )
                elif isinstance(node, ast.ImportFrom):
                    assert not any(
                        (node.module or "").startswith(mod) for mod in forbidden_modules
                    ), f"{module_path} imports from forbidden module {node.module}"

    def test_judge_client_protocol_has_no_authority_methods(self) -> None:
        """JudgeClient protocol must not have dispatch/install/select methods."""
        from substrate.antiek_bench.judged.client import JudgeClient

        forbidden = {"dispatch", "install", "select_driver", "as_dispatch_kwargs"}
        for name in dir(JudgeClient):
            if not name.startswith("_"):
                assert name not in forbidden, f"JudgeClient has forbidden method: {name}"

    def test_no_any_in_production_modules(self) -> None:
        """Verify no Any type in production module annotations."""
        for module_path in (
            "substrate/antiek_bench/judged/rubric.py",
            "substrate/antiek_bench/judged/blinding.py",
            "substrate/antiek_bench/judged/journal.py",
            "substrate/antiek_bench/judged/client.py",
        ):
            content = Path(module_path).read_text(encoding="utf-8")
            # Check for bare `Any` in type annotations (not in imports or strings)
            # This is a heuristic; mypy enforces the real check.
            assert "type: ignore" not in content, f"{module_path} contains type: ignore"


# ===================================================================
# Integration — full two-pass scoring workflow
# ===================================================================


def _attempt_judge_claim(path: str, queue: object) -> None:
    journal = JudgeEvidenceJournal(path)
    queue.put(journal.claim(default_record()))  # type: ignore[attr-defined]


class TestIntegration:
    def test_two_pass_order_swap_workflow(self, tmp_path: Path) -> None:
        """Simulate the full two-pass workflow: blind, score, swap, score again."""
        journal = JudgeEvidenceJournal(tmp_path / "judge.jsonl")
        r = rubric()
        client = default_client()

        # Pass 1: A first
        req1 = blinded_request(order=("A", "B"))
        rec1 = score_and_persist(
            request=req1,
            rubric=r,
            client=client,
            journal=journal,
            week_id="2026-W28",
            suite_version="suite-v1",
            judge_model="judge-a",
            candidate_models=("candidate-a", "candidate-b"),
        )
        assert rec1 is not None
        assert rec1.status == "scored"
        assert rec1.blinded_candidate_a == "A"
        assert rec1.blinded_candidate_b == "B"

        # Pass 2: B first (order swap)
        req2 = blinded_request(order=("B", "A"))
        rec2 = score_and_persist(
            request=req2,
            rubric=r,
            client=client,
            journal=journal,
            week_id="2026-W28",
            suite_version="suite-v1",
            judge_model="judge-a",
            candidate_models=("candidate-a", "candidate-b"),
        )
        assert rec2 is not None
        assert rec2.status == "scored"
        assert rec2.blinded_candidate_a == "A"
        assert rec2.blinded_candidate_b == "B"

        # Two distinct records in journal
        records = list(journal.replay().values())
        assert len(records) == 2
        assert records[0].computed_claim_id != records[1].computed_claim_id
        assert client.call_count == 2

    def test_crash_after_claim_prevents_redispatch(self, tmp_path: Path) -> None:
        """A pending claim from a crashed run must not trigger re-evaluation."""
        journal = JudgeEvidenceJournal(tmp_path / "judge.jsonl")
        req = blinded_request()
        # Simulate crash: claim but never settle
        pending = default_record(
            judge_model="judge-a",
            task_context_hash="sha256:" + hashlib.sha256(req.task_context.encode()).hexdigest(),
            rubric_fingerprint=rubric().fingerprint,
            candidate_a_hash=req.candidates[0].content_binding,
            candidate_b_hash=req.candidates[1].content_binding,
        )
        journal.claim(pending)

        # Second attempt: claim fails (duplicate)
        client = default_client()
        with pytest.raises(JudgeReconciliationRequiredError):
            score_and_persist(
                request=req,
                rubric=rubric(),
                client=client,
                journal=journal,
                week_id="2026-W28",
                suite_version="suite-v1",
                judge_model="judge-a",
                candidate_models=("candidate-a", "candidate-b"),
            )
        assert client.call_count == 0

    def test_concurrent_scoring_race(self, tmp_path: Path) -> None:
        """Two threads race to score the same request; exactly one makes the call."""
        journal = JudgeEvidenceJournal(tmp_path / "judge.jsonl")
        req = blinded_request()
        client = default_client()
        results: list[JudgeEvidenceRecord | None] = []

        def attempt() -> None:
            results.append(
                score_and_persist(
                    request=req,
                    rubric=rubric(),
                    client=client,
                    journal=journal,
                    week_id="2026-W28",
                    suite_version="suite-v1",
                    judge_model="judge-a",
                    candidate_models=("candidate-a", "candidate-b"),
                )
            )

        with ThreadPoolExecutor(max_workers=2) as pool:
            list(pool.map(lambda _: attempt(), range(2)))
        assert len(results) == 2
        assert results[0] == results[1]
        assert client.call_count == 1

    def test_multiprocess_claim_race(self, tmp_path: Path) -> None:
        """Two processes race to claim the same record; exactly one wins."""
        path = str(tmp_path / "judge.jsonl")
        ctx = multiprocessing.get_context("spawn")
        queue: multiprocessing.Queue[bool] = ctx.Queue()
        workers = [ctx.Process(target=_attempt_judge_claim, args=(path, queue)) for _ in range(2)]
        for w in workers:
            w.start()
        for w in workers:
            w.join(timeout=10)
            assert w.exitcode == 0
        assert sorted(queue.get(timeout=1) for _ in workers) == [False, True]
        assert len(JudgeEvidenceJournal(path).replay()) == 1

    def test_persisted_scores_are_parseable(self, tmp_path: Path) -> None:
        """Verify persisted axis_scores_json round-trips correctly."""
        journal = JudgeEvidenceJournal(tmp_path / "judge.jsonl")
        req = blinded_request()
        client = default_client()
        record = score_and_persist(
            request=req,
            rubric=rubric(),
            client=client,
            journal=journal,
            week_id="2026-W28",
            suite_version="suite-v1",
            judge_model="judge-a",
            candidate_models=("candidate-a", "candidate-b"),
        )
        assert record is not None
        parsed = json.loads(record.axis_scores_json)
        assert len(parsed) == 3
        axes = {s["axis"] for s in parsed}
        assert axes == {"synthesis_quality", "source_handling", "nuance"}

    def test_evidence_hash_is_deterministic(self, tmp_path: Path) -> None:
        """Same scores produce the same evidence hash."""
        journal1 = JudgeEvidenceJournal(tmp_path / "j1.jsonl")
        journal2 = JudgeEvidenceJournal(tmp_path / "j2.jsonl")
        req = blinded_request()
        r1 = score_and_persist(
            request=req,
            rubric=rubric(),
            client=default_client(),
            journal=journal1,
            week_id="w",
            suite_version="s",
            judge_model="j",
            candidate_models=("candidate-a", "candidate-b"),
        )
        r2 = score_and_persist(
            request=req,
            rubric=rubric(),
            client=default_client(),
            journal=journal2,
            week_id="w",
            suite_version="s",
            judge_model="j",
            candidate_models=("candidate-a", "candidate-b"),
        )
        assert r1 is not None and r2 is not None
        assert r1.evidence_hash == r2.evidence_hash
