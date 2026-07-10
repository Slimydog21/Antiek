from __future__ import annotations

import hashlib
import hmac
from dataclasses import asdict, replace
from decimal import Decimal
from pathlib import Path

import pytest

from substrate.antiek_bench.judged import (
    AxisJudgment,
    CandidateArtifact,
    EvidenceJournal,
    JudgeResponse,
    PrivateJoinEnvelope,
    collect_judge_evidence,
    seal_private_join,
    verify_private_join,
)
from substrate.antiek_bench.live import LiveCallRecord

KEY = b"operator-private-join-key-32bytes!!"
PROMPT = "sha256:" + hashlib.sha256(b"exact prompt").hexdigest()


class Judge:
    def judge(self, request):  # type: ignore[no-untyped-def]
        return JudgeResponse(
            request.rubric.version,
            {
                axis: AxisJudgment(4, f"reason for {axis}", ("A:line-1",))
                for axis in request.rubric.axes
            },
        )


def artifact(model: str) -> CandidateArtifact:
    return CandidateArtifact(
        content=f"answer from {model}",
        model_id=model,
        provider_id=f"provider-{model[-1]}",
        route_receipt_id=f"evt-{model}",
    )


def live_record(candidate: CandidateArtifact) -> LiveCallRecord:
    response_hash = hashlib.sha256(candidate.content.encode()).hexdigest()
    return LiveCallRecord(
        wedge_id="wedge",
        week_id="2026-W28",
        suite_version="suite-v1",
        requested_provider=candidate.provider_id,
        requested_model=candidate.model_id,
        task_class="distill",
        item_id="item-1",
        status="ok",
        reserved_usd=Decimal("0.01"),
        actual_provider=candidate.provider_id,
        actual_model=candidate.model_id,
        cost_usd=Decimal("0.001"),
        prompt_hash=PROMPT,
        response_hash=response_hash,
        route_receipt_id=candidate.route_receipt_id,
    )


def fixture(tmp_path: Path):  # type: ignore[no-untyped-def]
    candidates = (artifact("model-a"), artifact("model-b"))
    result = collect_judge_evidence(
        enabled=True,
        week_id="2026-W28",
        suite_version="suite-v1",
        item_id="item-1",
        task_context="Assess exact response quality.",
        task_class="distill",
        candidates=candidates,
        judge_model="judge-model",
        salt="private-salt",
        client=Judge(),
        journal=EvidenceJournal(tmp_path / "judge.jsonl"),
        now_ms=100,
    )
    assert result is not None
    live = (live_record(candidates[0]), live_record(candidates[1]))
    envelope = seal_private_join(
        evidence=result.evidence,
        private_join=result.private_join,
        live_records=live,
        item_id="item-1",
        prompt_hash=PROMPT,
        signing_key=KEY,
    )
    return result, live, envelope


def resign(envelope: PrivateJoinEnvelope) -> PrivateJoinEnvelope:
    unsigned = replace(envelope, signature="")
    signature = hmac.new(KEY, unsigned.signing_payload(), hashlib.sha256).hexdigest()
    return replace(unsigned, signature="hmac-sha256:" + signature)


def test_exact_private_join_verifies_to_public_safe_digest(tmp_path: Path) -> None:
    result, live, envelope = fixture(tmp_path)
    verified = verify_private_join(
        envelope=envelope,
        evidence=result.evidence,
        live_records=live,
        signing_key=KEY,
    )
    assert verified.envelope_digest.startswith("sha256:")
    assert verified.evidence_id == result.evidence.evidence_id
    public = repr(asdict(verified))
    for private in ("provider-a", "provider-b", "model-a", "model-b"):
        assert private not in public
    private = repr(asdict(envelope))
    assert "model-a" in private and "provider-b" in private


@pytest.mark.parametrize("field", ["item_id", "task_class", "prompt_hash"])
def test_signed_near_match_live_contract_fails_closed(tmp_path: Path, field: str) -> None:
    result, live, envelope = fixture(tmp_path)
    values = {
        "item_id": "forged-item",
        "task_class": "synthesize",
        "prompt_hash": "sha256:" + "0" * 64,
    }
    forged = resign(replace(envelope, **{field: values[field]}))
    with pytest.raises(ValueError, match="does not match"):
        verify_private_join(
            envelope=forged,
            evidence=result.evidence,
            live_records=live,
            signing_key=KEY,
        )


def test_model_response_and_order_variants_fail_closed(tmp_path: Path) -> None:
    result, live, envelope = fixture(tmp_path)
    first, second = envelope.bindings
    variants = (
        replace(envelope, bindings=(replace(first, model_id="forged-model"), second)),
        replace(envelope, bindings=(replace(first, live_response_hash="0" * 64), second)),
        replace(envelope, bindings=(second, first)),
    )
    for variant in variants:
        with pytest.raises(ValueError):
            verify_private_join(
                envelope=resign(variant),
                evidence=result.evidence,
                live_records=live,
                signing_key=KEY,
            )


def test_wrong_key_or_evidence_cannot_reuse_envelope(tmp_path: Path) -> None:
    result, live, envelope = fixture(tmp_path)
    with pytest.raises(ValueError, match="signature"):
        verify_private_join(
            envelope=envelope,
            evidence=result.evidence,
            live_records=live,
            signing_key=b"different-operator-private-key!!!",
        )
    forged_evidence = replace(result.evidence, judge_model="other-judge")
    with pytest.raises(ValueError, match="judged evidence"):
        verify_private_join(
            envelope=envelope,
            evidence=forged_evidence,
            live_records=live,
            signing_key=KEY,
        )


def test_short_key_and_forged_policy_fail_closed(tmp_path: Path) -> None:
    result, live, envelope = fixture(tmp_path)
    with pytest.raises(ValueError, match="at least 32 bytes"):
        verify_private_join(
            envelope=envelope,
            evidence=result.evidence,
            live_records=live,
            signing_key=b"too-short",
        )
    forged = resign(replace(envelope, judge_policy_version="forged-policy"))
    with pytest.raises(ValueError, match="judged evidence"):
        verify_private_join(
            envelope=forged,
            evidence=result.evidence,
            live_records=live,
            signing_key=KEY,
        )


def test_seal_rejects_live_response_not_produced_by_candidate(tmp_path: Path) -> None:
    result, live, _ = fixture(tmp_path)
    forged_live = replace(live[0], response_hash="0" * 64)
    with pytest.raises(ValueError, match="exact live response"):
        seal_private_join(
            evidence=result.evidence,
            private_join=result.private_join,
            live_records=(forged_live, live[1]),
            item_id="item-1",
            prompt_hash=PROMPT,
            signing_key=KEY,
        )
