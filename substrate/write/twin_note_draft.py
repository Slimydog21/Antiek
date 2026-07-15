"""Import exact, fully verified V21/V22 twin-note bytes into a Write scaffold."""
from __future__ import annotations
import hashlib, json
from dataclasses import dataclass
from typing import Sequence
from runtime.db_lock import LockedConnection
from substrate.graph.ops import insert_deliverable, insert_section, new_random_id
from substrate.twin_note_taker.serving import VerifiedRevision
from .provenance_validity import invalidate_structural_provenance

def _canonical(value: object) -> str: return json.dumps(value,sort_keys=True,separators=(",",":"))
def _sha(value: str) -> str: return hashlib.sha256(value.encode()).hexdigest()

def _place_machine_note(con: LockedConnection, *, section_id: str, block_index: int,
                        content: str, metadata: dict) -> str:
    """Persist private import provenance; this path never emits a public block event."""
    block_id = new_random_id("oblk")
    con.execute(
        "INSERT INTO outline_blocks (outline_block_id,section_id,block_kind,provenance_kind,"
        "node_id,source_block_kind,source_block_id,content,block_index,cluster_id,metadata) "
        "VALUES (?,?,'machine_note','machine_note',NULL,NULL,NULL,?,?,NULL,?)",
        [block_id, section_id, content, block_index, _canonical(metadata)],
    )
    invalidate_structural_provenance(con, section_id, reason="block_placed")
    return block_id

@dataclass(frozen=True)
class TwinNoteDraft:
    deliverable_id: str
    source_kind: str
    source_id: str
    analysis_section_id: str
    source_section_ids: list[str]
    replayed: bool

def _metadata(source_kind: str, source_id: str, revision: VerifiedRevision,
              source_ordinal: int, note_ordinal: int, text: str) -> dict:
    return {"source_profile": "twin_note_revision_v1" if source_kind == "revision" else "twin_note_composition_member_v1",
            "source_kind":source_kind,"source_id":source_id,"source_ordinal":source_ordinal,
            "note_ordinal":note_ordinal,"revision_id":revision.revision_id,"asset_id":revision.asset_id,
            "body_sha256":revision.body_sha256,"html_sha256":revision.html_sha256,
            "snapshot_text":text,"snapshot_sha256":_sha(text)}

def create_twin_note_draft(con: LockedConnection, *, owner_user_id: str, source_kind: str,
        source_id: str, source_digest: str, revisions: Sequence[VerifiedRevision], title: str,
        deliverable_kind: str, idempotency_key: str, transaction_owner: bool = True) -> TwinNoteDraft:
    request_sha = _sha(_canonical({"source":{"kind":source_kind,"id":source_id},
        "idempotency_key":idempotency_key,"title":title,"deliverable_kind":deliverable_kind}))
    if transaction_owner: con.execute("BEGIN TRANSACTION")
    try:
        replay = con.execute("SELECT deliverable_id,request_sha256,source_digest,analysis_section_id "
            "FROM deliverable_twin_note_imports WHERE owner_user_id=? AND idempotency_key=?",
            [owner_user_id,idempotency_key]).fetchone()
        if replay:
            if replay[1] != request_sha or replay[2] != source_digest: raise ValueError("twin-note import receipt conflicts")
            did, analysis = replay[0], replay[3]
            sources = con.execute("SELECT source_ordinal,composition_member_ordinal,revision_id,body_sha256,html_sha256,source_section_id,note_count "
                "FROM deliverable_twin_note_sources WHERE deliverable_id=? ORDER BY source_ordinal",[did]).fetchall()
            expected = [(i,None if source_kind=="revision" else i,r.revision_id,r.body_sha256,
                         r.html_sha256,len(r.body.agent_notes)) for i,r in enumerate(revisions)]
            actual = [row[:5]+row[6:] for row in sources]
            if len(sources)!=len(revisions) or actual != expected:
                raise ValueError("stored twin-note scaffold disagrees with source")
            deliverable = con.execute("SELECT title,deliverable_kind,owner_user_id,metadata FROM deliverables WHERE deliverable_id=?",[did]).fetchone()
            sections = con.execute("SELECT section_id,section_index,title,prose_text,prose_provenance FROM deliverable_sections WHERE deliverable_id=? ORDER BY section_index",[did]).fetchall()
            if deliverable is None or deliverable[:3] != (title,deliverable_kind,owner_user_id) or json.loads(deliverable[3]) != {"review_state":"source_scaffold","generated":False}:
                raise ValueError("stored twin-note scaffold disagrees with request")
            expected_sections=[(analysis,0,"Analysis",None,None)]+[(s[5],i+1,f"Twin notes — {r.asset_id}"[:300],None,None) for i,(r,s) in enumerate(zip(revisions,sources,strict=True))]
            if sections != expected_sections: raise ValueError("stored twin-note scaffold sections disagree")
            blocks = con.execute("SELECT b.occurrence_kind,b.source_ordinal,b.note_ordinal,b.snapshot_sha256,o.outline_block_id,o.section_id,o.block_index,o.content,o.block_kind,o.provenance_kind,o.metadata "
                "FROM deliverable_twin_note_blocks b JOIN outline_blocks o USING(outline_block_id) "
                "WHERE b.deliverable_id=? ORDER BY b.source_ordinal,b.note_ordinal,b.occurrence_kind DESC",[did]).fetchall()
            wanted=[]
            analysis_index=0
            for i,r in enumerate(revisions):
                for j,text in enumerate(r.body.agent_notes):
                    meta=_canonical(_metadata(source_kind,source_id,r,i,j,text))
                    wanted.extend([("source",i,j,_sha(text),sources[i][5],j,text,"machine_note","machine_note",meta),
                                   ("analysis",i,j,_sha(text),analysis,analysis_index,text,"machine_note","machine_note",meta)])
                    analysis_index += 1
            actual=[r[:4]+r[5:10]+(_canonical(json.loads(r[10])),) for r in blocks]
            all_block_count=con.execute("SELECT count(*) FROM outline_blocks o JOIN deliverable_sections s USING(section_id) WHERE s.deliverable_id=?",[did]).fetchone()[0]
            if actual != wanted or all_block_count != len(blocks):
                raise ValueError("stored twin-note scaffold disagrees with source")
            if transaction_owner: con.execute("COMMIT")
            return TwinNoteDraft(did,source_kind,source_id,analysis,[s[5] for s in sources],True)
        did=insert_deliverable(con,title=title,deliverable_kind=deliverable_kind,owner_user_id=owner_user_id,
                               metadata={"review_state":"source_scaffold","generated":False})
        analysis=insert_section(con,deliverable_id=did,section_index=0,title="Analysis")
        con.execute("INSERT INTO deliverable_twin_note_imports VALUES (?,?,?,?,?,?,?,?,CURRENT_TIMESTAMP)",
            [did,owner_user_id,idempotency_key,request_sha,source_kind,source_id,source_digest,analysis])
        section_ids=[]; analysis_index=0
        for i,r in enumerate(revisions):
            sid=insert_section(con,deliverable_id=did,section_index=i+1,title=f"Twin notes — {r.asset_id}"[:300])
            section_ids.append(sid)
            con.execute("INSERT INTO deliverable_twin_note_sources VALUES (?,?,?,?,?,?,?,?,?)",
                [did,i,None if source_kind=="revision" else i,r.revision_id,r.asset_id,r.body_sha256,r.html_sha256,sid,len(r.body.agent_notes)])
            for j,text in enumerate(r.body.agent_notes):
                metadata=_metadata(source_kind,source_id,r,i,j,text)
                obid=_place_machine_note(con,section_id=sid,block_index=j,content=text,metadata=metadata)
                con.execute("INSERT INTO deliverable_twin_note_blocks VALUES (?,?,?,?,?,?)",[obid,did,"source",i,j,_sha(text)])
                analysis_obid=_place_machine_note(con,section_id=analysis,block_index=analysis_index,
                    content=text,metadata=metadata)
                analysis_index += 1
                con.execute("INSERT INTO deliverable_twin_note_blocks VALUES (?,?,?,?,?,?)",[analysis_obid,did,"analysis",i,j,_sha(text)])
        if transaction_owner: con.execute("COMMIT")
        return TwinNoteDraft(did,source_kind,source_id,analysis,section_ids,False)
    except BaseException:
        if transaction_owner: con.execute("ROLLBACK")
        raise
