from __future__ import annotations

import json
import os
import sqlite3
from concurrent.futures import ThreadPoolExecutor

import pytest

from substrate.multimedia.research_intent import ResearchIntentError, ResearchIntentLedger
from substrate.multimedia.verified_audio_playback import (
    AudioEvidenceSourceMetadata,
    AudioLearnedClaimMetadata,
)


def _claim(text: str = "Lift changes with airflow.") -> AudioLearnedClaimMetadata:
    return AudioLearnedClaimMetadata(
        chapter_id="chapter-1",
        line_id="chapter-1-line-0",
        claim_text=text,
        source_count=1,
        follow_up_prompt="How does airflow change lift?",
        source_chunk_ids=("chunk-1",),
        evidence_status="verified_exact",
        evidence_sources=(AudioEvidenceSourceMetadata(
            chunk_id="chunk-1", document_id="doc-1", locator="p. 4",
            authority_kind="canonical_graph", chunk_sha256="a" * 64,
            start_utf8_byte=0, end_utf8_byte=len(text.encode()),
            span_sha256="b" * 64, exact_text=text,
        ),),
    )


def _create(ledger: ResearchIntentLedger, owner: str = "a" * 64, key: str = "key-123456789012"):
    return ledger.create(
        owner_identity_digest=owner, idempotency_key=key,
        asset_id="asset-1", revision_id="rev-1", receipt_sha256="c" * 64,
        audio_sha256="d" * 64, question="What changes lift?", claim=_claim(),
    )


def test_ledger_is_private_persistent_owner_scoped_and_exactly_idempotent(tmp_path) -> None:
    ledger = ResearchIntentLedger(tmp_path)
    created, first = _create(ledger)
    replayed, second = _create(ResearchIntentLedger(tmp_path))
    assert first is True and second is False and replayed == created
    assert oct(os.stat(ledger.path).st_mode & 0o777) == "0o600"
    with pytest.raises(ResearchIntentError, match="unavailable"):
        ledger.get(owner_identity_digest="b" * 64, intent_id=created.intent_id)
    assert ledger.get(owner_identity_digest="a" * 64, intent_id=created.intent_id) == created


def test_ledger_rejects_idempotency_drift_but_allows_another_owner(tmp_path) -> None:
    ledger = ResearchIntentLedger(tmp_path)
    _create(ledger)
    with pytest.raises(ResearchIntentError, match="idempotency conflict"):
        ledger.create(
            owner_identity_digest="a" * 64, idempotency_key="key-123456789012",
            asset_id="asset-1", revision_id="rev-1", receipt_sha256="c" * 64,
            audio_sha256="d" * 64, question="A different question", claim=_claim(),
        )
    other, created = _create(ledger, owner="b" * 64)
    assert created is True and other.intent_id


def test_concurrent_same_request_returns_one_intent(tmp_path) -> None:
    ledger = ResearchIntentLedger(tmp_path)
    with ThreadPoolExecutor(max_workers=8) as pool:
        results = list(pool.map(lambda _: _create(ledger), range(8)))
    assert len({intent.intent_id for intent, _created in results}) == 1
    assert sum(created for _intent, created in results) == 1


def test_corrupt_schema_refuses_to_operate(tmp_path) -> None:
    path = tmp_path / "research-intents.sqlite3"
    with sqlite3.connect(path) as connection:
        connection.execute("CREATE TABLE multimedia_research_intents (intent_id TEXT)")
    os.chmod(path, 0o600)
    with pytest.raises(ResearchIntentError, match="schema conflicts"):
        _create(ResearchIntentLedger(tmp_path))


def test_ledger_rejects_permissive_file_and_tampered_record(tmp_path) -> None:
    ledger = ResearchIntentLedger(tmp_path)
    intent, _created = _create(ledger)
    os.chmod(ledger.path, 0o644)
    with pytest.raises(ResearchIntentError, match="path is unsafe"):
        ledger.get(owner_identity_digest="a" * 64, intent_id=intent.intent_id)
    os.chmod(ledger.path, 0o600)
    with sqlite3.connect(ledger.path) as connection:
        raw = connection.execute(
            "SELECT record_json FROM multimedia_research_intents WHERE intent_id=?",
            (intent.intent_id,),
        ).fetchone()[0]
        record = json.loads(raw)
        record["intent"]["claim_text"] = "Substituted claim."
        connection.execute(
            "UPDATE multimedia_research_intents SET record_json=? WHERE intent_id=?",
            (json.dumps(record), intent.intent_id),
        )
    with pytest.raises(ResearchIntentError, match="integrity conflicts"):
        ledger.get(owner_identity_digest="a" * 64, intent_id=intent.intent_id)


def test_ledger_detects_owner_and_idempotency_row_rebinding(tmp_path) -> None:
    ledger = ResearchIntentLedger(tmp_path)
    intent, _created = _create(ledger)
    with sqlite3.connect(ledger.path) as connection:
        connection.execute(
            "UPDATE multimedia_research_intents SET owner_identity_digest=?, idempotency_key=? "
            "WHERE intent_id=?",
            ("b" * 64, "replacement-key-1234", intent.intent_id),
        )
    with pytest.raises(ResearchIntentError, match="binding conflicts"):
        ledger.get(owner_identity_digest="b" * 64, intent_id=intent.intent_id)


@pytest.mark.parametrize(
    ("field", "value"),
    [
        ("evidence_digest", "f" * 64),
        ("plan_handoff_status", "ready"),
        ("provider_launch_authorized", True),
        ("spend_authority_digest", "f" * 64),
    ],
)
def test_ledger_rejects_mutated_evidence_or_execution_authority(tmp_path, field, value) -> None:
    ledger = ResearchIntentLedger(tmp_path)
    intent, _created = _create(ledger)
    with sqlite3.connect(ledger.path) as connection:
        row = connection.execute(
            "SELECT record_json FROM multimedia_research_intents WHERE intent_id=?",
            (intent.intent_id,),
        ).fetchone()
        record = json.loads(row[0])
        record["intent"][field] = value
        if field == "evidence_digest":
            connection.execute(
                "UPDATE multimedia_research_intents SET evidence_digest=? WHERE intent_id=?",
                (value, intent.intent_id),
            )
        connection.execute(
            "UPDATE multimedia_research_intents SET record_json=? WHERE intent_id=?",
            (json.dumps(record), intent.intent_id),
        )
    with pytest.raises(ResearchIntentError, match="integrity conflicts"):
        ledger.get(owner_identity_digest="a" * 64, intent_id=intent.intent_id)


def test_ledger_requires_a_privately_controlled_root(tmp_path) -> None:
    os.chmod(tmp_path, 0o777)
    with pytest.raises(ValueError, match="privately controlled"):
        ResearchIntentLedger(tmp_path)


def test_ledger_never_follows_a_database_symlink(tmp_path) -> None:
    ledger = ResearchIntentLedger(tmp_path)
    target = tmp_path / "target.sqlite3"
    target.touch(mode=0o600)
    ledger.path.symlink_to(target)
    with pytest.raises(ResearchIntentError, match="path is unsafe"):
        _create(ledger)
