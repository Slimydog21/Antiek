"""Audio accounting admission with real private SQLite transactions.

These synthetic facts exercise accounting; they do not authorize provider sends
or establish the provenance of a real audio price or transcript.
"""

from __future__ import annotations

import hashlib
import sqlite3
from concurrent.futures import ThreadPoolExecutor
from dataclasses import replace
from pathlib import Path
from threading import Barrier

import pytest

from substrate.byot_usage.actions import (
    ApprovedOwnerRoute,
    AttemptProposal,
    CanonicalInputBinding,
    FinalSendFacts,
    OwnerActionDecision,
    RlmWorkflow,
    VerifiedAttemptFacts,
)
from substrate.byot_usage.ledger import (
    ByotUsageLedger,
    OperationConflict,
    SettlementEvidenceError,
)

AUDIO_VERSION = "owned-canonical-audio-http.v1"
RLM_KINDS: tuple[RlmWorkflow, ...] = (
    "long_document_wrestling",
    "long_corpus_synthesis",
    "investigation",
    "repl_query",
    "repl_batch",
    "dag_planning",
    "dag_execution",
    "equipped_batch",
)


def audio_decision(owner: str = "owner", budget: int = 100) -> OwnerActionDecision:
    return OwnerActionDecision(
        owner,
        "action",
        "audio_transcription",
        budget,
        "b" * 64,
        "d" * 64,
        (ApprovedOwnerRoute("record", "provider", "model", "a" * 64),),
    )


def proposal(operation: str = "attempt", reserved: int = 30) -> AttemptProposal:
    return AttemptProposal(
        operation, "record", "provider", "model", "a" * 64, "c" * 64, "e" * 64, reserved, 0
    )


def audio_binding() -> CanonicalInputBinding:
    return CanonicalInputBinding("1" * 64, "2" * 64, AUDIO_VERSION)


def send_facts(attempt: AttemptProposal, owner: str = "owner") -> FinalSendFacts:
    return FinalSendFacts(
        "f" * 64,
        attempt.authority_digest,
        attempt.route_digest,
        attempt.rate_limit_digest,
        "b" * 64,
        hashlib.sha256(f"{owner}/{attempt.operation_id}".encode()).hexdigest(),
        attempt.action_epoch,
        audio_binding(),
    )


def result(attempt: AttemptProposal, micro_usd: int = 100_000) -> VerifiedAttemptFacts:
    return VerifiedAttemptFacts(
        attempt.provider_id,
        attempt.model_id,
        f"event-{attempt.operation_id}",
        "3" * 64,
        "f" * 64,
        micro_usd,
        result_reference=f"external/{attempt.operation_id}",
    )


def ledger_at(tmp_path: Path, cap: int | None = 100) -> ByotUsageLedger:
    ledger = ByotUsageLedger(tmp_path / "usage.sqlite3")
    ledger.set_limit("record", "owner", cap)
    ledger.begin_action(audio_decision())
    return ledger


def allocate(ledger: ByotUsageLedger, attempt: AttemptProposal) -> None:
    ledger.allocate_action_attempt("owner", "action", attempt, canonical_input=audio_binding())


def claim(ledger: ByotUsageLedger, attempt: AttemptProposal) -> None:
    allocate(ledger, attempt)
    assert ledger.claim_action_attempt("owner", attempt.operation_id, send_facts(attempt)).won


def assert_unallocated(
    ledger: ByotUsageLedger, operation: str = "attempt", *, owner_held: int = 100
) -> None:
    assert ledger.operation("owner", operation) is None
    assert ledger.canonical_input_binding("owner", operation) is None
    action = ledger.action("owner", "action")
    assert action is not None
    assert action.reserved_cents == 0
    assert ledger.owner_usage("owner").held_cents == owner_held


def prime_input(attempt: AttemptProposal, field: str, value: str) -> AttemptProposal:
    if field == "attempt_kind":
        if value == "prime_root":
            return replace(attempt, attempt_kind="prime_root")
        assert value == "prime_child"
        return replace(attempt, attempt_kind="prime_child")
    if field == "parent_operation_id":
        return replace(attempt, parent_operation_id=value)
    assert field == "native_session_id"
    return replace(attempt, native_session_id=value)


def proposal_guard_input(attempt: AttemptProposal, field: str, value: str | int) -> AttemptProposal:
    if field == "action_epoch":
        assert type(value) is int
        return replace(attempt, action_epoch=value)
    assert type(value) is str
    if field == "provider_id":
        return replace(attempt, provider_id=value)
    if field == "model_id":
        return replace(attempt, model_id=value)
    assert field == "route_digest"
    return replace(attempt, route_digest=value)


def final_guard_input(facts: FinalSendFacts, field: str, value: str | int) -> FinalSendFacts:
    if field == "action_epoch":
        assert type(value) is int
        return replace(facts, action_epoch=value)
    assert type(value) is str
    if field == "authority_digest":
        return replace(facts, authority_digest=value)
    if field == "route_digest":
        return replace(facts, route_digest=value)
    if field == "rate_limit_digest":
        return replace(facts, rate_limit_digest=value)
    if field == "body_authority_digest":
        return replace(facts, body_authority_digest=value)
    if field == "request_digest":
        return replace(facts, request_digest=value)
    assert field == "claim_nonce_digest"
    return replace(facts, claim_nonce_digest=value)


@pytest.mark.parametrize(
    "kind", ["audio", "Audio_transcription", "audio_transcription.v1", None, 1]
)
def test_only_named_audio_action_is_admitted(kind: object) -> None:
    candidate = audio_decision()
    object.__setattr__(candidate, "action_kind", kind)
    with pytest.raises(ValueError, match="workflow"):
        candidate.__post_init__()


@pytest.mark.parametrize("version", ["audio", "owned-canonical-audio-http.v2", "", None, 1])
def test_only_supported_binding_versions_are_admitted(version: object) -> None:
    candidate = audio_binding()
    object.__setattr__(candidate, "version", version)
    with pytest.raises(ValueError, match="version"):
        candidate.__post_init__()


@pytest.mark.parametrize("field", ["logical_digest", "policy_digest"])
def test_audio_binding_retains_digest_validation(field: str) -> None:
    with pytest.raises(ValueError, match="digest"):
        replace(audio_binding(), **{field: "not-a-digest"})


@pytest.mark.parametrize("binding", [None, CanonicalInputBinding("1" * 64, "2" * 64)])
def test_audio_refuses_absent_or_text_binding(
    tmp_path: Path, binding: CanonicalInputBinding | None
) -> None:
    ledger = ledger_at(tmp_path)
    with pytest.raises(OperationConflict, match="audio requires"):
        ledger.allocate_action_attempt("owner", "action", proposal(), canonical_input=binding)
    assert_unallocated(ledger)


@pytest.mark.parametrize("kind", RLM_KINDS)
def test_every_rlm_kind_refuses_audio_binding(tmp_path: Path, kind: RlmWorkflow) -> None:
    ledger = ByotUsageLedger(tmp_path / "usage.sqlite3")
    ledger.begin_action(replace(audio_decision(), action_kind=kind))
    with pytest.raises(OperationConflict, match="audio action"):
        ledger.allocate_action_attempt(
            "owner", "action", proposal(), canonical_input=audio_binding()
        )
    assert_unallocated(ledger)


@pytest.mark.parametrize("binding", [None, CanonicalInputBinding("1" * 64, "2" * 64)])
def test_original_rlm_absent_cap_and_input_contract_remains_valid(
    tmp_path: Path, binding: CanonicalInputBinding | None
) -> None:
    ledger = ByotUsageLedger(tmp_path / "usage.sqlite3")
    ledger.begin_action(replace(audio_decision(), action_kind="long_document_wrestling"))
    attempt = proposal()
    ledger.allocate_action_attempt("owner", "action", attempt, canonical_input=binding)
    facts = replace(send_facts(attempt), canonical_input=binding)
    assert ledger.claim_action_attempt("owner", "attempt", facts).won
    recorded = ledger.record_action_attempt_result(
        "owner", "attempt", replace(result(attempt), result_text="original stored answer")
    )
    assert recorded.operation.result_text == "original stored answer"


@pytest.mark.parametrize(
    ("field", "value"),
    [
        ("attempt_kind", "prime_root"),
        ("attempt_kind", "prime_child"),
        ("parent_operation_id", "parent"),
        ("native_session_id", "session"),
    ],
)
def test_audio_never_enters_prime_or_parent_admission(
    tmp_path: Path, field: str, value: str
) -> None:
    ledger = ledger_at(tmp_path)
    with pytest.raises(OperationConflict, match="independent canonical"):
        allocate(ledger, prime_input(proposal(), field, value))
    assert_unallocated(ledger)


@pytest.mark.parametrize("create_null_row", [False, True])
def test_missing_and_null_cap_refuse_without_operation_insert(
    tmp_path: Path, create_null_row: bool
) -> None:
    ledger = ByotUsageLedger(tmp_path / "usage.sqlite3")
    if create_null_row:
        ledger.set_limit("record", "owner", None)
    ledger.begin_action(audio_decision())
    with pytest.raises(OperationConflict, match="explicit local record limit"):
        allocate(ledger, proposal())
    assert_unallocated(ledger)
    row = ledger.key_usage("record", "owner")
    assert (row is not None) == create_null_row


def test_zero_cap_is_zero_not_unlimited(tmp_path: Path) -> None:
    ledger = ledger_at(tmp_path, 0)
    with pytest.raises(OperationConflict, match="local record limit"):
        allocate(ledger, proposal(reserved=1))
    assert_unallocated(ledger)
    attempt = proposal(reserved=0)
    allocate(ledger, attempt)
    assert ledger.claim_action_attempt("owner", "attempt", send_facts(attempt)).won
    usage = ledger.key_usage("record", "owner")
    assert usage is not None
    assert (usage.limit_cents, usage.used_cents, usage.held_cents) == (0, 0, 0)


def test_real_used_and_held_exposure_is_rechecked_at_claim(tmp_path: Path) -> None:
    ledger = ledger_at(tmp_path, 64)
    ledger.record_settlement("record", "owner", 15, "4" * 64)
    ledger.prepare_operation("record", "owner", "legacy-held", 20, "5" * 64)
    attempt = proposal()
    with pytest.raises(OperationConflict, match="local record limit"):
        allocate(ledger, attempt)
    assert_unallocated(ledger, owner_held=120)
    ledger.set_limit("record", "owner", 65)
    allocate(ledger, attempt)
    row = ledger.key_usage("record", "owner")
    assert row is not None
    assert (row.used_cents, row.held_cents) == (15, 50)
    ledger.set_limit("record", "owner", 64)
    with pytest.raises(OperationConflict, match="current local record limit"):
        ledger.claim_action_attempt("owner", "attempt", send_facts(attempt))
    current_attempt = ledger.action_attempt("owner", "attempt")
    assert current_attempt is not None
    assert current_attempt.operation.state == "allocated"
    ledger.set_limit("record", "owner", 65)
    assert ledger.claim_action_attempt("owner", "attempt", send_facts(attempt)).won
    assert not ledger.claim_action_attempt("owner", "attempt", send_facts(attempt)).won
    current = ledger.key_usage("record", "owner")
    assert current is not None
    assert (current.used_cents, current.held_cents, current.limit_cents) == (15, 50, 65)


@pytest.mark.parametrize("remove_row", [False, True])
def test_winning_claim_requires_current_nonnull_cap(tmp_path: Path, remove_row: bool) -> None:
    ledger = ledger_at(tmp_path)
    attempt = proposal()
    allocate(ledger, attempt)
    if remove_row:
        with sqlite3.connect(tmp_path / "usage.sqlite3") as con:
            con.execute(
                "DELETE FROM byot_key_usage WHERE owner_user_id='owner' AND api_key_id='record'"
            )
    else:
        ledger.set_limit("record", "owner", None)
    with pytest.raises(OperationConflict, match="explicit local record limit"):
        ledger.claim_action_attempt("owner", "attempt", send_facts(attempt))
    current_attempt = ledger.action_attempt("owner", "attempt")
    assert current_attempt is not None
    assert current_attempt.operation.state == "allocated"
    ledger.set_limit("record", "owner", 30)
    assert ledger.claim_action_attempt("owner", "attempt", send_facts(attempt)).won
    ledger.set_limit("record", "owner", None)
    assert not ledger.claim_action_attempt("owner", "attempt", send_facts(attempt)).won
    assert ledger.owner_usage("owner").held_cents == 100


def test_audio_allocation_idempotence_never_duplicates_hold(tmp_path: Path) -> None:
    ledger = ledger_at(tmp_path)
    attempt = proposal()
    allocate(ledger, attempt)
    before = ledger.action_attempt("owner", "attempt")
    allocate(ledger, attempt)
    assert ledger.action_attempt("owner", "attempt") == before
    assert ledger.owner_usage("owner").held_cents == 100
    row = ledger.key_usage("record", "owner")
    assert row is not None and row.held_cents == 30
    with pytest.raises(OperationConflict, match="cannot be rebound"):
        allocate(ledger, replace(attempt, reserved_cents=31))
    with pytest.raises(OperationConflict, match="cannot be rebound"):
        ledger.allocate_action_attempt(
            "owner",
            "action",
            attempt,
            canonical_input=replace(audio_binding(), logical_digest="6" * 64),
        )
    ledger.set_limit("record", "owner", None)
    with pytest.raises(OperationConflict, match="explicit local record limit"):
        allocate(ledger, attempt)
    assert ledger.action_attempt("owner", "attempt") == before


@pytest.mark.parametrize("field", ["provider_id", "model_id", "route_digest", "action_epoch"])
def test_audio_allocation_preserves_route_and_action_guards(tmp_path: Path, field: str) -> None:
    ledger = ledger_at(tmp_path)
    value: str | int = 1 if field == "action_epoch" else "6" * 64
    with pytest.raises(OperationConflict):
        allocate(ledger, proposal_guard_input(proposal(), field, value))
    assert_unallocated(ledger)


@pytest.mark.parametrize(
    "field",
    [
        "authority_digest",
        "route_digest",
        "rate_limit_digest",
        "body_authority_digest",
        "action_epoch",
    ],
)
def test_claim_refuses_changed_final_authority(tmp_path: Path, field: str) -> None:
    ledger = ledger_at(tmp_path)
    attempt = proposal()
    allocate(ledger, attempt)
    value: str | int = 1 if field == "action_epoch" else "6" * 64
    with pytest.raises(OperationConflict, match="binding changed"):
        ledger.claim_action_attempt(
            "owner", "attempt", final_guard_input(send_facts(attempt), field, value)
        )
    current_attempt = ledger.action_attempt("owner", "attempt")
    assert current_attempt is not None
    assert current_attempt.operation.state == "allocated"


@pytest.mark.parametrize("field", ["logical_digest", "policy_digest"])
def test_claim_refuses_changed_logical_audio_input(tmp_path: Path, field: str) -> None:
    ledger = ledger_at(tmp_path)
    attempt = proposal()
    allocate(ledger, attempt)
    changed = replace(audio_binding(), **{field: "6" * 64})
    with pytest.raises(OperationConflict, match="differs from allocation"):
        ledger.claim_action_attempt(
            "owner", "attempt", replace(send_facts(attempt), canonical_input=changed)
        )
    current_attempt = ledger.action_attempt("owner", "attempt")
    assert current_attempt is not None
    assert current_attempt.operation.state == "allocated"


@pytest.mark.parametrize("field", ["request_digest", "claim_nonce_digest"])
def test_bound_wire_or_nonce_cannot_be_reclaimed(tmp_path: Path, field: str) -> None:
    ledger = ledger_at(tmp_path)
    attempt = proposal()
    claim(ledger, attempt)
    with pytest.raises(OperationConflict, match="not claimable"):
        ledger.claim_action_attempt(
            "owner", "attempt", final_guard_input(send_facts(attempt), field, "6" * 64)
        )
    assert not ledger.claim_action_attempt("owner", "attempt", send_facts(attempt)).won
    current_attempt = ledger.action_attempt("owner", "attempt")
    assert current_attempt is not None
    assert current_attempt.operation.state == "sent"


@pytest.mark.parametrize(
    ("column", "value"),
    [
        ("attempt_kind", "prime_root"),
        ("parent_operation_id", "parent"),
        ("native_session_id", "session"),
    ],
)
def test_claim_independently_validates_persisted_audio_proposal(
    tmp_path: Path, column: str, value: str
) -> None:
    ledger = ledger_at(tmp_path)
    attempt = proposal()
    allocate(ledger, attempt)
    with sqlite3.connect(tmp_path / "usage.sqlite3") as con:
        con.execute(
            f"UPDATE byot_operation_journal SET {column}=? WHERE operation_id='attempt'", (value,)
        )
    with pytest.raises(OperationConflict, match="independent canonical"):
        ledger.claim_action_attempt("owner", "attempt", send_facts(attempt))
    assert ledger.operation("owner", "attempt") is not None
    current_attempt = ledger.action_attempt("owner", "attempt")
    assert current_attempt is not None
    assert current_attempt.operation.state == "allocated"


def test_claim_refuses_persisted_text_binding_even_when_facts_match(tmp_path: Path) -> None:
    ledger = ledger_at(tmp_path)
    attempt = proposal()
    allocate(ledger, attempt)
    with sqlite3.connect(tmp_path / "usage.sqlite3") as con:
        con.execute("UPDATE byot_canonical_input SET version='owned-canonical-http.v1'")
    text_binding = CanonicalInputBinding("1" * 64, "2" * 64)
    with pytest.raises(OperationConflict, match="audio requires"):
        ledger.claim_action_attempt(
            "owner", "attempt", replace(send_facts(attempt), canonical_input=text_binding)
        )
    current_attempt = ledger.action_attempt("owner", "attempt")
    assert current_attempt is not None
    assert current_attempt.operation.state == "allocated"


def test_canonical_insert_failure_rolls_back_operation_and_hold(tmp_path: Path) -> None:
    ledger = ledger_at(tmp_path)
    with sqlite3.connect(tmp_path / "usage.sqlite3") as con:
        con.execute(
            "CREATE TRIGGER reject_audio BEFORE INSERT ON byot_canonical_input "
            "BEGIN SELECT RAISE(ABORT,'private audio insert failure'); END"
        )
    with pytest.raises(sqlite3.IntegrityError, match="audio insert failure"):
        allocate(ledger, proposal())
    assert_unallocated(ledger)
    usage = ledger.key_usage("record", "owner")
    assert usage is not None and usage.held_cents == 0


def test_owner_record_caps_and_claims_are_isolated(tmp_path: Path) -> None:
    ledger = ledger_at(tmp_path)
    ledger.set_limit("record", "other", 0)
    ledger.begin_action(audio_decision("other"))
    attempt = proposal()
    allocate(ledger, attempt)
    with pytest.raises(OperationConflict, match="local record limit"):
        ledger.allocate_action_attempt("other", "action", attempt, canonical_input=audio_binding())
    assert ledger.operation("other", "attempt") is None
    with pytest.raises(OperationConflict):
        ledger.claim_action_attempt("other", "attempt", send_facts(attempt, "other"))
    ledger.set_limit("record", "other", 30)
    ledger.allocate_action_attempt("other", "action", attempt, canonical_input=audio_binding())
    assert ledger.claim_action_attempt("other", "attempt", send_facts(attempt, "other")).won
    assert ledger.claim_action_attempt("owner", "attempt", send_facts(attempt)).won
    assert ledger.owner_usage("owner").held_cents == ledger.owner_usage("other").held_cents == 100


def test_two_real_claimers_have_one_winner_and_one_hold(tmp_path: Path) -> None:
    ledger = ledger_at(tmp_path)
    attempt = proposal()
    allocate(ledger, attempt)
    barrier = Barrier(2, timeout=5)

    def compete(_: int) -> bool:
        barrier.wait()
        return ledger.claim_action_attempt("owner", "attempt", send_facts(attempt)).won

    with ThreadPoolExecutor(max_workers=2) as pool:
        assert sorted(pool.map(compete, range(2))) == [False, True]
    row = ledger.key_usage("record", "owner")
    assert row is not None and row.held_cents == 30
    assert ledger.owner_usage("owner").held_cents == 100


def test_close_and_claim_race_never_erases_possible_send(tmp_path: Path) -> None:
    ledger = ledger_at(tmp_path)
    attempt = proposal()
    allocate(ledger, attempt)
    barrier = Barrier(2, timeout=5)

    def try_claim() -> bool:
        barrier.wait()
        try:
            return ledger.claim_action_attempt("owner", "attempt", send_facts(attempt)).won
        except OperationConflict:
            return False

    def close() -> None:
        barrier.wait()
        ledger.close_action("owner", "action", expected_epoch=0)

    with ThreadPoolExecutor(max_workers=2) as pool:
        claimant = pool.submit(try_claim)
        closer = pool.submit(close)
        won = claimant.result(timeout=10)
        closer.result(timeout=10)
    stored = ledger.action_attempt("owner", "attempt")
    assert stored is not None
    assert stored.operation.state == ("sent" if won else "cancelled")
    assert ledger.owner_usage("owner").held_cents == (30 if won else 0)
    with pytest.raises(OperationConflict):
        ledger.claim_action_attempt(
            "owner", "attempt", replace(send_facts(attempt), claim_nonce_digest="7" * 64)
        )


def test_unknown_restart_preserves_liability_and_refuses_reissue(tmp_path: Path) -> None:
    ledger = ledger_at(tmp_path)
    attempt = proposal()
    claim(ledger, attempt)
    ledger.mark_action_attempt_unknown("owner", "attempt")
    ledger.close_action("owner", "action", expected_epoch=0)
    reopened = ByotUsageLedger(tmp_path / "usage.sqlite3")
    current_attempt = reopened.action_attempt("owner", "attempt")
    assert current_attempt is not None
    assert current_attempt.operation.state == "unknown"
    assert reopened.owner_usage("owner").held_cents == 30
    assert not reopened.claim_action_attempt("owner", "attempt", send_facts(attempt)).won
    with pytest.raises(OperationConflict):
        reopened.claim_action_attempt(
            "owner", "attempt", replace(send_facts(attempt), claim_nonce_digest="7" * 64)
        )
    with pytest.raises(OperationConflict, match="not provably unsent"):
        reopened.cancel_action_attempt("owner", "attempt", expected_epoch=1)


@pytest.mark.parametrize("text", ["transcript", " ", "\n"])
def test_transcript_refusal_precedes_result_write(tmp_path: Path, text: str) -> None:
    ledger = ledger_at(tmp_path)
    attempt = proposal()
    claim(ledger, attempt)
    before = ledger.action_attempt("owner", "attempt")
    with pytest.raises(SettlementEvidenceError, match="transcript"):
        ledger.record_action_attempt_result(
            "owner", "attempt", replace(result(attempt), result_text=text)
        )
    assert ledger.action_attempt("owner", "attempt") == before
    assert ledger.owner_usage("owner").used_cents == 0
    assert ledger.pending_projection_events() == ()


@pytest.mark.parametrize("settled", [False, True])
def test_transcript_guard_precedes_matching_idempotent_result(
    tmp_path: Path, settled: bool
) -> None:
    ledger = ledger_at(tmp_path)
    attempt = proposal()
    claim(ledger, attempt)
    facts = result(attempt)
    ledger.record_action_attempt_result("owner", "attempt", facts)
    if settled:
        ledger.settle_action_attempt("owner", "attempt")
    with sqlite3.connect(tmp_path / "usage.sqlite3") as con:
        con.execute("UPDATE byot_operation_journal SET result_text='private injected transcript'")
    before = ledger.action_attempt("owner", "attempt")
    events = ledger.pending_projection_events()
    with pytest.raises(SettlementEvidenceError, match="transcript"):
        ledger.record_action_attempt_result(
            "owner", "attempt", replace(facts, result_text="private injected transcript")
        )
    assert ledger.action_attempt("owner", "attempt") == before
    assert ledger.pending_projection_events() == events


def test_unknown_transcript_refusal_preserves_hold(tmp_path: Path) -> None:
    ledger = ledger_at(tmp_path)
    attempt = proposal()
    claim(ledger, attempt)
    ledger.mark_action_attempt_unknown("owner", "attempt")
    ledger.close_action("owner", "action", expected_epoch=0)
    with pytest.raises(SettlementEvidenceError, match="transcript"):
        ledger.reconcile_action_attempt_usage(
            "owner", "attempt", replace(result(attempt), result_text="transcript")
        )
    current_attempt = ledger.action_attempt("owner", "attempt")
    assert current_attempt is not None
    assert current_attempt.operation.state == "unknown"
    assert ledger.owner_usage("owner").held_cents == 30
    assert ledger.owner_usage("owner").used_cents == 0


def test_empty_result_keeps_rounding_and_exactly_once_settlement(tmp_path: Path) -> None:
    ledger = ledger_at(tmp_path)
    attempt = proposal()
    claim(ledger, attempt)
    facts = result(attempt, micro_usd=1)
    pending = ledger.record_action_attempt_result("owner", "attempt", facts)
    assert pending.operation.actual_cents == 1
    assert pending.operation.result_text == ""
    assert pending.result_reference == "external/attempt"
    ledger.settle_action_attempt("owner", "attempt")
    ledger.record_action_attempt_result("owner", "attempt", facts)
    ledger.settle_action_attempt("owner", "attempt")
    assert ledger.owner_usage("owner").used_cents == 1
    assert len(ledger.pending_projection_events()) == 1
    row = ledger.key_usage("record", "owner")
    assert row is not None and (row.used_cents, row.held_cents) == (1, 0)


def test_audio_overrun_keeps_quarantine_and_actual_charge(tmp_path: Path) -> None:
    ledger = ledger_at(tmp_path)
    attempt = proposal(reserved=10)
    claim(ledger, attempt)
    allocate(ledger, proposal("sibling", reserved=10))
    ledger.record_action_attempt_result("owner", "attempt", result(attempt, micro_usd=150_000))
    action = ledger.action("owner", "action")
    assert action is not None and action.quarantined and action.epoch == 1
    current_attempt = ledger.action_attempt("owner", "sibling")
    assert current_attempt is not None
    assert current_attempt.operation.state == "cancelled"
    ledger.settle_action_attempt("owner", "attempt")
    assert ledger.owner_usage("owner").used_cents == 15
    assert len(ledger.pending_projection_events()) == 1
