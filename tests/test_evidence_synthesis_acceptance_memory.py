from __future__ import annotations

import hashlib
import json
import os
from contextlib import contextmanager

import duckdb
import pytest

import substrate.interviews.evidence_synthesis_acceptance as synthesis_acceptance
import substrate.interviews.synthesis_knowledge_admission as knowledge_admission
import substrate.interviews.write_acceptance as write_acceptance
from runtime.db_lock import LockedConnection
from substrate.graph.schema import init_database
from substrate.interviews.authority import InterviewAccountAuthority
from substrate.interviews.composition_execution import _prompt, _render, _validated_result
from substrate.interviews.evidence_bundle_synthesis import (
    assert_evidence_bundle_synthesis_custody,
    create_evidence_bundle_synthesis_proposal,
)
from substrate.interviews.evidence_synthesis_acceptance import (
    apply_evidence_synthesis_acceptance,
    preview_evidence_synthesis_acceptance,
)
from substrate.interviews.synthesis_knowledge_admission import (
    SynthesisKnowledgeAdmissionConflict,
    SynthesisKnowledgeCandidate,
    apply_synthesis_knowledge_admission,
    preview_synthesis_knowledge_admission,
)
from substrate.interviews.write_acceptance import (
    EvidenceBundleItem,
    EvidenceInsertionSource,
    WriteAcceptanceConflict,
    apply_native_evidence_bundle,
    create_native_private_write,
    get_private_write_document,
    list_private_write_revisions,
    preview_native_evidence_bundle,
)
from substrate.investigation_streams import resolve_writable_investigation_stream
from substrate.investigation_tenancy import InvestigationAuthority


def test_synthesis_acceptance_real_sql_in_memory(monkeypatch, tmp_path) -> None:
    """Exercise the real transaction/DDL without relying on saturated file-backed I/O."""
    raw = duckdb.connect(":memory:")
    fd = os.open("/dev/null", os.O_RDONLY)
    locked = LockedConnection(raw, fd, "/dev/null", log_on_close=False)
    init_database(locked)

    @contextmanager
    def shared_connection(*_args, **_kwargs):
        yield locked

    monkeypatch.setattr(write_acceptance, "connect_read", shared_connection)
    monkeypatch.setattr(write_acceptance, "connect_write", shared_connection)
    monkeypatch.setattr(synthesis_acceptance, "connect_read", shared_connection)
    monkeypatch.setattr(synthesis_acceptance, "connect_write", shared_connection)
    monkeypatch.setattr(knowledge_admission, "connect_read", shared_connection)
    monkeypatch.setattr(knowledge_admission, "connect_write", shared_connection)

    authority = InterviewAccountAuthority("memory-owner")
    created = create_native_private_write(
        "ignored", authority, title="Memory manuscript", mutation_key="create",
    )

    def source(receipt: str, content: str, suffix: str) -> EvidenceInsertionSource:
        return EvidenceInsertionSource(
            citation_receipt_sha256=receipt * 64, source_asset_id=f"asset-{suffix}",
            claim_id=f"claim-{suffix}", source_document_id=f"document-{suffix}",
            chunk_ids=(f"chunk-{suffix}",), source_title=f"Source {suffix}",
            source_content_sha256=content * 64, excerpt_text=f"Evidence {suffix}",
        )

    items = (
        EvidenceBundleItem(source("a", "b", "one"), "supports", "Baseline"),
        EvidenceBundleItem(source("c", "d", "two"), "contradicts", None),
    )
    secret = "memory-preview-secret-" + "x" * 40
    bundle_preview = preview_native_evidence_bundle(
        "ignored", authority, write_document_id=created.write_document_id,
        base_revision=1, base_body_sha256=created.body_sha256,
        items=items, preview_secret=secret,
    )
    bundle = apply_native_evidence_bundle(
        "ignored", authority, write_document_id=created.write_document_id,
        mutation_key="bundle", base_revision=1, base_body_sha256=created.body_sha256,
        items=items, preview_sha256=bundle_preview.preview_sha256,
        manifest_sha256=bundle_preview.manifest_sha256,
        proposed_html_sha256=bundle_preview.proposed_html_sha256, preview_secret=secret,
    )
    bundle_id = str(raw.execute(
        "SELECT bundle_id FROM interview_write_evidence_bundles_authority"
    ).fetchone()[0])
    proposal = create_evidence_bundle_synthesis_proposal(
        locked, authority, bundle_id=bundle_id,
        write_document_id=created.write_document_id, project_id=created.project_id,
        mutation_key="proposal", base_revision=0, instruction="Compare exactly.",
        provider_id="openai", model_id="gpt-test", projected_max_cents=20,
        approved_ceiling_cents=25,
        allowed_model_pairs=frozenset({("openai", "gpt-test")}),
        hydrated_items=items,
    )
    raw_json = json.dumps({
        "schema_version": 1, "title": "Comparison", "lead": "Evidence differs.",
        "units": [{"evidence_unit_ids": ["evidence-1", "evidence-2"],
                   "prose": "The accounts remain in tension."}],
    })
    prompt_sha = hashlib.sha256(_prompt(proposal, proposal.inputs).encode()).hexdigest()
    result_html = _render(
        _validated_result(raw_json, proposal, proposal.inputs), proposal, proposal.inputs,
    )
    result_sha = hashlib.sha256(result_html.encode()).hexdigest()
    raw.execute(
        "INSERT INTO interview_composition_execution_authority "
        "(account_digest, proposal_id, owner_user_id, attempt_id, run_id, state, "
        "prompt_sha256, route_sha256, hold_id, provider, model, actual_cents, "
        "dispatch_event_id, raw_result_json, raw_result_sha256, receipt_prompt_sha256, "
        "result_html, result_html_sha256) VALUES (?, ?, ?, 'attempt', 'run', "
        "'ready_for_review', ?, ?, 'hold', 'openai', 'gpt-test', 3, 'dispatch', ?, ?, ?, ?, ?)",
        [authority.account_digest, proposal.proposal_id, authority.account_id,
         prompt_sha, "7" * 64, raw_json, hashlib.sha256(raw_json.encode()).hexdigest(),
         prompt_sha, result_html, result_sha],
    )

    def revalidate(_con, current):
        assert_evidence_bundle_synthesis_custody(current, items)

    preview = preview_evidence_synthesis_acceptance(
        "ignored", authority, proposal_id=proposal.proposal_id,
        write_document_id=created.write_document_id, base_revision=2,
        base_html_sha256=bundle.body_sha256, preview_secret=secret,
        source_revalidator=revalidate,
    )
    assert get_private_write_document(
        "ignored", authority, write_document_id=created.write_document_id,
    ).revision == 2
    accepted = apply_evidence_synthesis_acceptance(
        "ignored", authority, proposal_id=proposal.proposal_id,
        write_document_id=created.write_document_id, mutation_key="accept",
        base_revision=2, base_html_sha256=bundle.body_sha256,
        preview_sha256=preview.preview_sha256,
        proposed_html_sha256=preview.proposed_html_sha256, preview_secret=secret,
        source_revalidator=revalidate,
    )
    assert accepted.edit.revision == 3
    assert apply_evidence_synthesis_acceptance(
        "ignored", authority, proposal_id=proposal.proposal_id,
        write_document_id=created.write_document_id, mutation_key="accept",
        base_revision=2, base_html_sha256=bundle.body_sha256,
        preview_sha256=preview.preview_sha256,
        proposed_html_sha256=preview.proposed_html_sha256, preview_secret=secret,
        source_revalidator=revalidate,
    ).edit.replayed is True
    assert [row.operation for row in list_private_write_revisions(
        "ignored", authority, write_document_id=created.write_document_id,
    )] == ["create", "evidence_bundle", "synthesis_accept"]

    target = InvestigationAuthority("memory-owner", "research", root=tmp_path / "events")
    resolve_writable_investigation_stream(target)

    class Embedding:
        def encode(self, text: str) -> list[float]:
            return [float(byte) / 255 for byte in hashlib.sha256(text.encode()).digest()[:8]]

    candidates = (
        SynthesisKnowledgeCandidate(
            unit_index=0, kind="insight", text="The accounts remain in tension."
        ),
    )
    before = raw.execute(
        "SELECT (SELECT count(*) FROM nodes), "
        "(SELECT count(*) FROM interview_synthesis_knowledge_admissions_authority)"
    ).fetchone()
    knowledge_preview = preview_synthesis_knowledge_admission(
        "ignored", authority, acceptance_id=accepted.acceptance_id,
        proposal_id=proposal.proposal_id, write_document_id=created.write_document_id,
        target=target, candidates=candidates, preview_secret=secret,
        source_revalidator=revalidate,
    )
    assert knowledge_preview.items[0].disposition == "created"
    assert raw.execute(
        "SELECT (SELECT count(*) FROM nodes), "
        "(SELECT count(*) FROM interview_synthesis_knowledge_admissions_authority)"
    ).fetchone() == before
    admitted = apply_synthesis_knowledge_admission(
        "ignored", authority, acceptance_id=accepted.acceptance_id,
        proposal_id=proposal.proposal_id, write_document_id=created.write_document_id,
        target=target, candidates=candidates,
        preview_sha256=knowledge_preview.preview_sha256, mutation_key="admit",
        preview_secret=secret, source_revalidator=revalidate,
        embedding_provider=Embedding(),
    )
    assert admitted.replayed is False
    assert raw.execute(
        "SELECT count(*) FROM investigation_node_memberships WHERE account_digest = ? "
        "AND investigation_digest = ?",
        [target.account_digest, target.investigation_digest],
    ).fetchone() == (1,)
    replay = apply_synthesis_knowledge_admission(
        "ignored", authority, acceptance_id=accepted.acceptance_id,
        proposal_id=proposal.proposal_id, write_document_id=created.write_document_id,
        target=target, candidates=candidates,
        preview_sha256=knowledge_preview.preview_sha256, mutation_key="admit",
        preview_secret=secret, source_revalidator=revalidate,
        embedding_provider=Embedding(),
    )
    assert replay.replayed is True
    assert replay.admission_id == admitted.admission_id
    with pytest.raises(SynthesisKnowledgeAdmissionConflict, match="already admitted"):
        apply_synthesis_knowledge_admission(
            "ignored", authority, acceptance_id=accepted.acceptance_id,
            proposal_id=proposal.proposal_id, write_document_id=created.write_document_id,
            target=target, candidates=candidates,
            preview_sha256=knowledge_preview.preview_sha256, mutation_key="admit-again",
            preview_secret=secret, source_revalidator=revalidate,
            embedding_provider=Embedding(),
        )
    original_evidence_sha = raw.execute(
        "SELECT evidence_sha256 FROM "
        "interview_synthesis_knowledge_admission_items_authority"
    ).fetchone()[0]
    raw.execute(
        "UPDATE interview_synthesis_knowledge_admission_items_authority "
        "SET evidence_sha256 = ?", ["f" * 64],
    )
    with pytest.raises(SynthesisKnowledgeAdmissionConflict, match="item receipt is corrupt"):
        apply_synthesis_knowledge_admission(
            "ignored", authority, acceptance_id=accepted.acceptance_id,
            proposal_id=proposal.proposal_id, write_document_id=created.write_document_id,
            target=target, candidates=candidates,
            preview_sha256=knowledge_preview.preview_sha256, mutation_key="admit",
            preview_secret=secret, source_revalidator=revalidate,
            embedding_provider=Embedding(),
        )
    raw.execute(
        "UPDATE interview_synthesis_knowledge_admission_items_authority "
        "SET evidence_sha256 = ?", [original_evidence_sha],
    )
    raw.execute(
        "UPDATE interview_write_synthesis_acceptances_authority SET route_sha256 = ?",
        ["f" * 64],
    )
    with pytest.raises(WriteAcceptanceConflict, match="synthesis acceptance is corrupt"):
        get_private_write_document(
            "ignored", authority, write_document_id=created.write_document_id,
        )

    raw.close()
    os.close(fd)
