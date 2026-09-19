"""Build ResearchArtifactBody from graph + trajectory."""

from __future__ import annotations

from pathlib import Path

from roles.note_taker.distill_query import (
    distillation_for,
    distillation_for_authorized,
)
from substrate.investigation_tenancy import InvestigationAuthority

from .authority import ArtifactAuthority
from .context import (
    problem_question_from_events,
    problem_question_from_events_authorized,
    synthesis_from_events,
    synthesis_from_events_authorized,
)
from .import_notes import load_persisted_agent_notes
from .schema import (
    ArtifactClaimInheritedSupport,
    ArtifactClaimSupport,
    ArtifactInsight,
    ArtifactQuestion,
    ResearchArtifactBody,
)


def _archived_terminal_provenance(authority: InvestigationAuthority, *, db_path: str | None):
    """Load canonical coverage only through the authorized synthesis reader."""
    from middleware.archive import authorized_synthesis_id, load_synthesis_authorized
    from runtime.db_lock import connect_read
    from substrate.graph import default_db_path
    from substrate.source_coverage import (
        ArchivedSourceCoverageEnvelope,
        validate_archived_claim_support,
    )

    con = connect_read(db_path or default_db_path())
    try:
        archived = load_synthesis_authorized(
            con,
            authority,
            authorized_synthesis_id(authority, "terminal"),
        )
        if archived is not None:
            from substrate.legal_gate.read import archive_chunk_ids_compatibility

            manifest_chunks = set(archived.substrate_manifest.get("chunk", []))
            authorized_chunks = archive_chunk_ids_compatibility(
                con,
                tuple(sorted(manifest_chunks)),
                authority=authority,
                enforce=True,
            )
            if authorized_chunks != manifest_chunks:
                raise ValueError("archive chunk manifest is no longer authorized")
    finally:
        con.close()
    if archived is None or archived.substrate is None:
        return None, None, []
    envelope = ArchivedSourceCoverageEnvelope.model_validate(archived.substrate)
    validate_archived_claim_support(
        envelope,
        archived.thesis,
        manifest_chunk_ids=set(archived.substrate_manifest.get("chunk", [])),
    )
    qualifications = (
        {
            (leaf.investigation_id, unit.unit_id): ArtifactClaimInheritedSupport(
                unit_id=unit.unit_id,
                qualification_state=unit.state,
                source_investigation_id=unit.source_investigation_id,
                supporting_leaf_investigation_id=leaf.investigation_id,
            )
            for leaf in envelope.inherited_reuse.leaves
            for unit in leaf.qualifications
        }
        if envelope.inherited_reuse is not None
        else {}
    )
    if envelope.inherited_reuse is not None:
        for leaf in envelope.inherited_reuse.leaves:
            if leaf.state == "legacy_unqualified":
                qualifications.update(
                    {
                        (leaf.investigation_id, unit_id): ArtifactClaimInheritedSupport(
                            unit_id=unit_id,
                            qualification_state="legacy_unqualified",
                            supporting_leaf_investigation_id=leaf.investigation_id,
                        )
                        for unit_id in leaf.injected_unit_ids
                    }
                )
    claim_support: list[ArtifactClaimSupport] = []
    if isinstance(archived.thesis, dict):
        for component in archived.thesis.get("thesis_components", []):
            if not isinstance(component, dict) or not str(component.get("claim", "")).strip():
                continue
            inherited_ids = component.get("supporting_inherited_unit_ids", [])
            chunk_ids = component.get("supporting_chunk_ids", [])
            path_indices = component.get("supporting_path_indices", [])
            if (
                not isinstance(inherited_ids, list)
                or not isinstance(chunk_ids, list)
                or not isinstance(path_indices, list)
            ):
                continue
            if not chunk_ids and not path_indices:
                continue
            inherited_support = []
            for unit_id in inherited_ids:
                supporting_leaves = dict.fromkeys(
                    envelope.claim_support_leaf_by_chunk[chunk_id]
                    for chunk_id in chunk_ids
                    if unit_id in envelope.claim_support_by_chunk.get(chunk_id, ())
                )
                resolved = [qualifications.get((leaf_id, unit_id)) for leaf_id in supporting_leaves]
                if not resolved or any(item is None for item in resolved):
                    inherited_support = []
                    break
                inherited_support.extend(item for item in resolved if item is not None)
            if inherited_ids and not inherited_support:
                continue
            claim_support.append(
                ArtifactClaimSupport(
                    claim=str(component["claim"]).strip(),
                    supporting_chunk_ids=tuple(dict.fromkeys(chunk_ids)),
                    supporting_path_indices=tuple(dict.fromkeys(path_indices)),
                    inherited_support=tuple(inherited_support),
                )
            )
    return envelope.coverage, envelope.inherited_reuse, claim_support


def _operator_compatibility_sources(
    investigation_id: str,
    *,
    db_path: str | None,
    events_dir: str | None,
):
    """Read historic globally keyed sources for the named local operator only."""
    view = distillation_for(investigation_id, db_path=db_path)
    question = problem_question_from_events(investigation_id, events_dir=events_dir)
    excerpt, withheld, event_ids, synthesis_event_id = synthesis_from_events(
        investigation_id, events_dir=events_dir
    )
    return view, question, excerpt, withheld, event_ids, synthesis_event_id


def build_body(
    investigation_id: str,
    *,
    authority: ArtifactAuthority,
    db_path: str | None = None,
    events_dir: str | None = None,
) -> ResearchArtifactBody:
    if authority.investigation_id != investigation_id:
        raise ValueError("artifact authority investigation mismatch")
    if authority.local_operator_compatibility:
        # Named compatibility lane for historic single-operator artifacts.
        view, question, excerpt, withheld, event_ids, synthesis_event_id = (
            _operator_compatibility_sources(
                investigation_id, db_path=db_path, events_dir=events_dir
            )
        )
        source_coverage = None
        inherited_reuse = None
        claim_support = []
    else:
        investigation_authority = (
            InvestigationAuthority(
                authority.account_id,
                investigation_id,
                root=Path(events_dir) if events_dir is not None else None,
            )
            if events_dir is not None
            else InvestigationAuthority(authority.account_id, investigation_id)
        )
        view = distillation_for_authorized(investigation_authority, db_path=db_path)
        question = problem_question_from_events_authorized(investigation_authority)
        excerpt, withheld, event_ids, synthesis_event_id = synthesis_from_events_authorized(
            investigation_authority
        )
        source_coverage, inherited_reuse, claim_support = _archived_terminal_provenance(
            investigation_authority, db_path=db_path
        )
    if not question:
        question = f"Investigation {investigation_id}"

    insights = [
        ArtifactInsight(
            node_id=n.node_id,
            text=n.text,
            source_document_id=n.source_document_id,
            confidence=n.confidence,
        )
        for n in view.insights
    ]
    questions = [
        ArtifactQuestion(
            node_id=n.node_id,
            text=n.text,
            escalated=n.escalated,
            reserved_child_investigation_id=n.reserved_child_investigation_id,
        )
        for n in view.questions
    ]
    agent_notes = load_persisted_agent_notes(investigation_id, authority=authority)
    return ResearchArtifactBody(
        investigation_id=investigation_id,
        problem_question=question,
        insights=insights,
        open_questions=questions,
        synthesis_excerpt=excerpt if not withheld else None,
        synthesis_withheld=withheld,
        synthesis_event_id=synthesis_event_id,
        source_event_ids=event_ids,
        source_coverage=source_coverage,
        inherited_reuse=inherited_reuse,
        claim_support=claim_support,
        agent_notes=agent_notes,
    )
