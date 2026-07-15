from __future__ import annotations
import pytest
from runtime.db_lock import connect_read,connect_write
from substrate.twin_note_taker.workflow import (TwinNoteWorkflow,TwinNoteWorkflowConflict,
    TwinNoteWorkflowIntegrity)
from tests.test_twin_note_compression import setup

def test_preview_apply_and_immutable_command_replay(setup):
    db,published,events,resolver=setup
    service=TwinNoteWorkflow(resolver,db_path=db,publication_root=str(published),events_dir=str(events))
    preview=service.preview(account_id="acct",asset_id="asset",window_ids=["w-b","w-a"])
    assert [m["window_id"] for m in preview.members]==["w-b","w-a"]
    assert preview.expected_predecessor is None and preview.note_count==2 and preview.source_count==2
    request=dict(account_id="acct",asset_id="asset",window_ids=["w-b","w-a"],
        expected_predecessor=None,preview_digest=preview.preview_digest,idempotency_key="cycle49-command-0001")
    first=service.apply(**request); second=service.apply(**request)
    assert first["revision_id"]==second["revision_id"] and second["replayed"] is True
    with connect_read(db) as con:
        assert con.execute("SELECT count(*) FROM twin_note_revision_commands").fetchone()==(1,)
    with pytest.raises(TwinNoteWorkflowConflict): service.apply(**{**request,"window_ids":["w-a","w-b"]})

def test_preview_is_pure_and_stale_digest_fails(setup):
    db,published,events,resolver=setup
    service=TwinNoteWorkflow(resolver,db_path=db,publication_root=str(published),events_dir=str(events))
    preview=service.preview(account_id="acct",asset_id="asset",window_ids=["w-a"])
    with connect_read(db) as con:
        assert con.execute("SELECT count(*) FROM twin_note_revisions").fetchone()==(0,)
    with pytest.raises(TwinNoteWorkflowConflict):
        service.apply(account_id="acct",asset_id="asset",window_ids=["w-a"],expected_predecessor=None,
            preview_digest="0"*64,idempotency_key="cycle49-command-0002")

@pytest.mark.parametrize("ledger",["effect-delete","effect-drift","outbox-delete","outbox-drift",
    "receipt-time-drift"])
def test_full_apply_replay_rejects_missing_or_drifted_effect_and_outbox(setup,ledger):
    db,published,events,resolver=setup
    service=TwinNoteWorkflow(resolver,db_path=db,publication_root=str(published),events_dir=str(events))
    preview=service.preview(account_id="acct",asset_id="asset",window_ids=["w-a"])
    request=dict(account_id="acct",asset_id="asset",window_ids=["w-a"],expected_predecessor=None,
        preview_digest=preview.preview_digest,idempotency_key="cycle49-command-ledger")
    made=service.apply(**request)
    with connect_write(db,purpose="test/c49-replay-drift") as con:
        if ledger=="effect-delete": con.execute("DELETE FROM twin_note_publication_effects WHERE revision_id=?",[made["revision_id"]])
        elif ledger=="effect-drift": con.execute("UPDATE twin_note_publication_effects SET expected_sha256=? WHERE revision_id=?",["0"*64,made["revision_id"]])
        elif ledger=="outbox-delete": con.execute("DELETE FROM write_event_outbox WHERE aggregate_id=?",[made["revision_id"]])
        elif ledger=="outbox-drift": con.execute("UPDATE write_event_outbox SET event_sha256=? WHERE aggregate_id=?",["0"*64,made["revision_id"]])
        else: con.execute("UPDATE twin_note_revision_commands SET created_at=created_at + INTERVAL 1 SECOND WHERE revision_id=?",[made["revision_id"]])
    with pytest.raises(TwinNoteWorkflowIntegrity): service.apply(**request)
