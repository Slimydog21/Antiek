from __future__ import annotations
import pytest
from runtime.db_lock import connect_read,connect_write
from substrate.write.twin_note_draft import create_twin_note_draft
from tests.test_twin_note_serving import served

def test_exact_revision_import_is_snapshot_only_and_replays(served):
    db,service,a,_=served
    revision=service.revision("__operator__",a.revision_id)
    args=dict(owner_user_id="__operator__",source_kind="revision",source_id=a.revision_id,
        source_digest=revision.body_sha256,revisions=[revision],title="Frozen notes",
        deliverable_kind="research_memo",idempotency_key="cycle49-import-0001")
    with connect_write(db,purpose="test/c49-import") as con: first=create_twin_note_draft(con,**args)
    with connect_write(db,purpose="test/c49-replay") as con: second=create_twin_note_draft(con,**args)
    assert second.replayed and second.deliverable_id==first.deliverable_id
    with connect_read(db) as con:
        assert con.execute("SELECT prose_text FROM deliverable_sections WHERE section_id=?",[first.analysis_section_id]).fetchone()==(None,)
        assert con.execute("SELECT count(*) FROM nodes").fetchone()==(0,)
        assert con.execute("SELECT occurrence_kind,count(*) FROM deliverable_twin_note_blocks GROUP BY occurrence_kind ORDER BY occurrence_kind").fetchall()==[("analysis",1),("source",1)]
        assert con.execute("SELECT DISTINCT block_kind,provenance_kind FROM outline_blocks WHERE section_id IN (?,?)",[first.analysis_section_id,first.source_section_ids[0]]).fetchall()==[("machine_note","machine_note")]

def test_composition_import_preserves_member_order(served):
    db,service,a,b=served
    made=service.compose("__operator__",[b.revision_id,a.revision_id])
    verified=service.verified_composition("__operator__",made["composition_id"])
    with connect_write(db,purpose="test/c49-composition-import") as con:
        draft=create_twin_note_draft(con,owner_user_id="__operator__",source_kind="composition",
            source_id=verified.composition_id,source_digest=verified.ordered_members_sha256,
            revisions=verified.members,title="Ordered",deliverable_kind="research_memo",
            idempotency_key="cycle49-import-0002")
    with connect_read(db) as con:
        rows=con.execute("SELECT revision_id FROM deliverable_twin_note_sources WHERE deliverable_id=? ORDER BY source_ordinal",[draft.deliverable_id]).fetchall()
    assert rows==[(b.revision_id,),(a.revision_id,)]

@pytest.mark.parametrize("source_kind,bad_ordinal",[("revision",0),("composition",None)])
def test_replay_verifies_composition_member_ordinal(served,source_kind,bad_ordinal):
    db,service,a,b=served
    if source_kind=="revision": source_id,digest,revisions=a.revision_id,a.body_sha256,[service.revision("__operator__",a.revision_id)]
    else:
        made=service.compose("__operator__",[a.revision_id,b.revision_id]); verified=service.verified_composition("__operator__",made["composition_id"])
        source_id,digest,revisions=verified.composition_id,verified.ordered_members_sha256,verified.members
    args=dict(owner_user_id="__operator__",source_kind=source_kind,source_id=source_id,
        source_digest=digest,revisions=revisions,title="Ordinal",deliverable_kind="research_memo",
        idempotency_key="cycle49-import-ordinal")
    with connect_write(db,purpose="test/c49-ordinal-create") as con: draft=create_twin_note_draft(con,**args)
    with connect_write(db,purpose="test/c49-ordinal-drift") as con:
        con.execute("UPDATE deliverable_twin_note_sources SET composition_member_ordinal=? "
                    "WHERE deliverable_id=? AND source_ordinal=0",[bad_ordinal,draft.deliverable_id])
    with connect_write(db,purpose="test/c49-ordinal-replay") as con:
        with pytest.raises(ValueError): create_twin_note_draft(con,**args)
