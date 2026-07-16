from __future__ import annotations

import base64
import json
import sqlite3
from concurrent.futures import ThreadPoolExecutor
from dataclasses import replace

import pytest
from nacl.signing import SigningKey

from substrate.twin_note_taker import (
    AUTHORITY_VERIFY_KEY_ENV,
    AssetContent,
    ProposedInsight,
    ProposedQuestion,
    TwinGenerationReceipt,
    TwinProposal,
    proposal_receipt_hash,
    source_asset_receipt_hash,
)
from substrate.twin_recursion import (
    FailureCode,
    SourceRevision,
    TwinConflictError,
    TwinIntegrityError,
    TwinRecursionLedger,
)
from substrate.twin_recursion.ledger import TRIGGERS


@pytest.fixture
def signing_key(monkeypatch: pytest.MonkeyPatch) -> SigningKey:
    key = SigningKey.generate()
    monkeypatch.setenv(AUTHORITY_VERIFY_KEY_ENV, base64.b64encode(bytes(key.verify_key)).decode())
    return key


@pytest.fixture
def revision() -> SourceRevision:
    return SourceRevision("acct", AssetContent(
        "asset", "Title", "Substantive exact source bytes for the twin.",
        source_event_ids=("evt-source",),
    ))


def _proposal(text: str = "An advisory insight") -> TwinProposal:
    return TwinProposal((ProposedInsight(text, ""),),
                        (ProposedQuestion("What next?"),), "Summary")


def _receipt(revision: SourceRevision, proposal: TwinProposal, key: SigningKey,
             receipt_id: str = "receipt-1", expires: int = 4_000_000_000) -> TwinGenerationReceipt:
    asset = revision.asset
    claims: dict[str, object] = {
        "receipt_id": receipt_id,
        "account_id": revision.account_id,
        "asset_id": asset.asset_id,
        "model_id": "model",
        "budget_authority_id": "grant",
        "source_content_hash": revision.content_hash,
        "source_asset_hash": source_asset_receipt_hash(asset),
        "source_event_ids": asset.source_event_ids,
        "proposal_payload_hash": proposal_receipt_hash(asset, proposal),
        "expires_at_unix": expires,
    }
    payload = dict(claims)
    payload["source_event_ids"] = list(asset.source_event_ids)
    signature = key.sign(json.dumps(payload, sort_keys=True, separators=(",", ":")).encode()).signature
    return TwinGenerationReceipt(**claims, signature=base64.b64encode(signature).decode())  # type: ignore[arg-type]


def _complete(ledger: TwinRecursionLedger, revision: SourceRevision, key: SigningKey):
    proposal = _proposal()
    return ledger.apply_completion(revision, model_id="model", proposal=proposal,
                                   receipt=_receipt(revision, proposal, key))


def test_registration_is_idempotent_and_complete_asset_is_revision_identity(tmp_path, revision):
    path = tmp_path / "twins.sqlite"
    first = TwinRecursionLedger(path).register_source(revision)
    assert TwinRecursionLedger(path).register_source(revision) == first
    assert first.state == "pending_authorization" and first.body is None and first.job_id
    changed_title = SourceRevision("acct", replace(revision.asset, title="Changed"))
    assert changed_title.source_hash != revision.source_hash


def test_callers_cannot_fabricate_non_recursive_twin(tmp_path, revision):
    ledger = TwinRecursionLedger(tmp_path / "db")
    ledger.register_source(revision)
    with pytest.raises(TwinConflictError, match="does not exist"):
        ledger.register_materialized_twin("binding_fake")


def test_materialized_twin_is_derived_from_real_binding_and_cannot_complete(
        tmp_path, signing_key, revision):
    ledger = TwinRecursionLedger(tmp_path / "db")
    ledger.register_source(revision)
    parent = _complete(ledger, revision, signing_key)
    child = ledger.register_materialized_twin(parent.binding_id)
    assert child.state == "ready" and not child.twinnable and child.job_id is None
    assert child.asset_id == parent.twin_id
    assert ledger.register_materialized_twin(parent.binding_id) == child
    child_revision = SourceRevision("acct", AssetContent(
        child.asset_id, "Twin notes: Title", parent.body_json, "twin",
        ("evt-twin-" + __import__("hashlib").sha256(parent.binding_id.encode()).hexdigest()[:32],),
    ))
    with pytest.raises(TwinConflictError, match="cannot recursively"):
        ledger.apply_completion(
            child_revision,
            model_id="model", proposal=_proposal(), receipt=_receipt(revision, _proposal(), signing_key),
        )


def test_invalid_receipt_rolls_back_and_leaves_pending(tmp_path, signing_key, revision):
    ledger = TwinRecursionLedger(tmp_path / "db")
    ledger.register_source(revision)
    receipt = replace(_receipt(revision, _proposal(), signing_key), signature="invalid")
    with pytest.raises(ValueError, match="signature"):
        ledger.apply_completion(revision, model_id="model", proposal=_proposal(), receipt=receipt)
    assert ledger.get("acct", "asset", revision.source_hash).state == "pending_authorization"


def test_exact_replay_is_spend_free_and_any_signed_byte_substitution_conflicts(
        tmp_path, monkeypatch, signing_key, revision):
    ledger = TwinRecursionLedger(tmp_path / "db")
    ledger.register_source(revision)
    proposal = _proposal()
    receipt = _receipt(revision, proposal, signing_key)
    first = ledger.apply_completion(revision, model_id="model", proposal=proposal, receipt=receipt)
    monkeypatch.delenv(AUTHORITY_VERIFY_KEY_ENV)
    assert ledger.apply_completion(revision, model_id="model", proposal=proposal, receipt=receipt) == first
    changed_receipt = _receipt(revision, proposal, signing_key, expires=4_000_000_001)
    with pytest.raises(TwinConflictError, match="substitution"):
        ledger.apply_completion(revision, model_id="model", proposal=proposal,
                                receipt=changed_receipt)


def test_rollback_injection_is_atomic_including_audit_event(tmp_path, signing_key, revision):
    def explode() -> None:
        raise RuntimeError("injected")
    path = tmp_path / "db"
    ledger = TwinRecursionLedger(path, before_commit=explode)
    ledger.register_source(revision)
    with pytest.raises(RuntimeError, match="injected"):
        _complete(ledger, revision, signing_key)
    snap = TwinRecursionLedger(path).get("acct", "asset", revision.source_hash)
    assert snap.state == "pending_authorization" and snap.binding_id is None
    with sqlite3.connect(path) as con:
        assert con.execute("SELECT count(*) FROM twin_events").fetchone()[0] == 1


def test_concurrent_exact_completions_converge(tmp_path, signing_key, revision):
    path = tmp_path / "db"
    TwinRecursionLedger(path).register_source(revision)
    proposal, receipt = _proposal(), _receipt(revision, _proposal(), signing_key)
    def complete(_unused: int):
        return TwinRecursionLedger(path).apply_completion(
            revision, model_id="model", proposal=proposal, receipt=receipt)
    with ThreadPoolExecutor(max_workers=2) as pool:
        snapshots = list(pool.map(complete, range(2)))
    assert snapshots[0] == snapshots[1]


def test_failures_are_bounded_and_reset_preserves_hash_chained_audit(tmp_path, revision):
    path = tmp_path / "db"
    ledger = TwinRecursionLedger(path)
    pending = ledger.register_source(revision)
    with pytest.raises(ValueError, match="bounded"):
        ledger.mark_failed(revision, "secret-bearing arbitrary reason")  # type: ignore[arg-type]
    failed = ledger.mark_failed(revision, FailureCode.DISPATCH_UNKNOWN)
    assert failed.state == "failed" and failed.failure == "dispatch_unknown"
    reset = ledger.reset_failed(revision)
    assert reset.state == "pending_authorization" and reset.job_id == pending.job_id
    with sqlite3.connect(path) as con:
        events = con.execute("SELECT event_type,event_data FROM twin_events ORDER BY sequence").fetchall()
    assert [event[0] for event in events] == ["source_registered", "failure_recorded", "failure_reset"]
    assert json.loads(events[2][1]) == {"previous_failure_code": "dispatch_unknown"}
    ledger.verify_integrity()


def test_schema_and_event_corruption_fail_closed(tmp_path, revision):
    path = tmp_path / "db"
    ledger = TwinRecursionLedger(path)
    ledger.register_source(revision)
    with sqlite3.connect(path) as con:
        con.execute("DROP TRIGGER twin_event_immutable")
        con.execute("UPDATE twin_events SET event_hash=?", ("0" * 64,))
    with pytest.raises(TwinIntegrityError, match="schema object"):
        ledger.verify_integrity()
    with pytest.raises(TwinIntegrityError, match="schema object"):
        TwinRecursionLedger(path)


def test_integrity_replays_events_and_rederives_body(tmp_path, signing_key, revision):
    path = tmp_path / "db"
    ledger = TwinRecursionLedger(path)
    ledger.register_source(revision)
    snapshot = _complete(ledger, revision, signing_key)
    forged = snapshot.body.model_copy(update={"problem_question": "Forged but valid body"})
    forged_json = json.dumps(forged.model_dump(mode="json"), sort_keys=True,
                             separators=(",", ":"))
    with sqlite3.connect(path) as con:
        con.execute("DROP TRIGGER twin_binding_immutable")
        con.execute("UPDATE twin_bindings SET body_json=?,body_hash=?",
                    (forged_json, __import__("hashlib").sha256(forged_json.encode()).hexdigest()))
        con.execute(TRIGGERS["twin_binding_immutable"])
    with pytest.raises(TwinIntegrityError, match="proposal and canonical body"):
        ledger.verify_integrity()


def test_integrity_rejects_auditable_state_with_missing_event(tmp_path, revision):
    path = tmp_path / "db"
    ledger = TwinRecursionLedger(path)
    ledger.register_source(revision)
    ledger.mark_failed(revision, FailureCode.DISPATCH_UNKNOWN)
    ledger.reset_failed(revision)
    with sqlite3.connect(path) as con:
        con.execute("DROP TRIGGER twin_event_no_delete")
        con.execute("DELETE FROM twin_events WHERE event_type='failure_recorded'")
        con.execute(TRIGGERS["twin_event_no_delete"])
    with pytest.raises(TwinIntegrityError, match="sequence|chain|lifecycle"):
        ledger.verify_integrity()


def test_universality_is_account_scoped_and_empty_is_unknown(tmp_path, signing_key, revision):
    ledger = TwinRecursionLedger(tmp_path / "db")
    assert ledger.universality_report("acct").verdict == "unknown"
    ledger.register_source(revision)
    assert ledger.universality_report("acct").verdict == "partial"
    _complete(ledger, revision, signing_key)
    report = ledger.universality_report("acct")
    assert report.verdict == "universal" and report.bound_revisions == 1
    other = SourceRevision("other", replace(revision.asset, asset_id="other-asset"))
    ledger.register_source(other)
    assert ledger.universality_report("acct").verdict == "universal"
    assert ledger.universality_report("other").verdict == "partial"


def test_html_is_derived_from_canonical_body(tmp_path, signing_key, revision):
    ledger = TwinRecursionLedger(tmp_path / "db")
    ledger.register_source(revision)
    snapshot = _complete(ledger, revision, signing_key)
    rendered = ledger.render_twin_html(snapshot.binding_id)
    assert rendered.startswith("<!doctype html>")
    assert snapshot.body.problem_question in rendered
    ledger.verify_integrity()
