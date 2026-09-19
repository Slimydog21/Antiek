from __future__ import annotations

import hashlib
import json

import duckdb
import pytest
from fastapi.testclient import TestClient

from runtime.db_lock import connect_write
from substrate.graph.schema import init_database_at_path
from substrate.interviews.authority import (
    InterviewAccountAuthority,
    operator_interview_account_authority,
)
from substrate.interviews.capability import issue_invite, resolve_invite, revoke_invite
from substrate.interviews.claims import (
    ClaimConflict,
)
from substrate.interviews.claims import (
    get_claim as get_canonical_claim,
)
from substrate.interviews.claims import (
    list_claims as list_canonical_claims,
)
from substrate.interviews.claims import (
    record_claim as record_canonical_claim,
)
from substrate.interviews.composition import (
    CompositionConflict,
    create_private_draft,
    get_private_draft,
)
from substrate.interviews.composition_execution import (
    CompositionExecutionConflict,
    ProviderCompositionResult,
    execute_proposal,
    get_execution,
    reconcile_checkpointed,
)
from substrate.interviews.composition_proposals import (
    CompositionProposalConflict,
    create_proposal,
    get_proposal,
)
from substrate.interviews.consent import record_consent_events
from substrate.interviews.contributor import (
    ContributorAttributionConflict,
    get_active_attribution,
    record_attribution,
    revoke_attribution,
)
from substrate.interviews.corroboration import (
    CorroborationMember,
    record_corroboration,
)
from substrate.interviews.derivation import DerivationConflict, bind_project, stage_answer_if_bound
from substrate.interviews.evidence_bundle_synthesis import (
    EvidenceBundleSynthesisConflict,
    assert_evidence_bundle_synthesis_custody,
    create_evidence_bundle_synthesis_proposal,
    get_evidence_bundle_synthesis_proposal,
)
from substrate.interviews.evidence_synthesis_acceptance import (
    apply_evidence_synthesis_acceptance,
    preview_evidence_synthesis_acceptance,
)
from substrate.interviews.migration import migrate_interview_authority_schema
from substrate.interviews.reconcile import reconcile_answer_derivations
from substrate.interviews.store import (
    InterviewStateConflict,
    append_turn,
    complete,
    create_interview,
    create_project,
    record_consent,
)
from substrate.interviews.write_acceptance import (
    EvidenceBundleItem,
    EvidenceInsertionSource,
    WriteAcceptanceConflict,
    apply_native_evidence_bundle,
    apply_native_evidence_insertion,
    create_native_private_write,
    edit_private_write,
    get_private_write_document,
    get_private_write_revision,
    list_private_write_documents,
    list_private_write_revisions,
    preview_native_evidence_bundle,
    preview_native_evidence_insertion,
    restore_private_write_revision,
    review_result,
    undo_acceptance,
)
from substrate.investigation_streams import resolve_writable_investigation_stream
from substrate.investigation_tenancy import InvestigationAuthority
from substrate.midnight_oil.budget_ledger import BudgetLedger, CallNotDispatched


def test_authority_is_account_bound_and_recovery_scopes_do_not_collide() -> None:
    alice = InterviewAccountAuthority("alice")
    bob = InterviewAccountAuthority("bob")

    assert alice.account_digest != bob.account_digest
    assert alice.project("shared").account_digest == alice.account_digest
    assert alice.interview("shared").recovery_scope != bob.interview("shared").recovery_scope
    assert operator_interview_account_authority().local_operator_compatibility is True
    with pytest.raises(ValueError):
        InterviewAccountAuthority(" alice ")
    with pytest.raises(ValueError):
        InterviewAccountAuthority("alice", local_operator_compatibility=True)


def test_owner_native_write_has_truthful_independent_revision_lineage(tmp_path) -> None:
    path = str(tmp_path / "owner-native.duckdb")
    init_database_at_path(path)
    alice = InterviewAccountAuthority("alice")
    created = create_native_private_write(
        path, alice, title="Native analysis", mutation_key="native-create-1",
    )
    assert created.revision == 1
    assert created.replayed is False
    assert create_native_private_write(
        path, alice, title="Native analysis", mutation_key="native-create-1",
    ).replayed is True
    with pytest.raises(WriteAcceptanceConflict, match="different input"):
        create_native_private_write(
            path, alice, title="Changed", mutation_key="native-create-1",
        )
    for invalid_title in ("", " padded", "padded ", "x" * 301):
        with pytest.raises(ValueError):
            create_native_private_write(
                path, alice, title=invalid_title, mutation_key="invalid-" + str(len(invalid_title)),
            )
    current = get_private_write_document(
        path, alice, write_document_id=created.write_document_id,
    )
    assert current.origin_kind == "owner_native"
    assert current.body_html == "<article></article>"
    with pytest.raises(ValueError, match="not found"):
        get_private_write_document(
            path, InterviewAccountAuthority("bob"),
            write_document_id=created.write_document_id,
        )
    assert list_private_write_documents(path, alice)[0].origin_kind == "owner_native"
    edited = edit_private_write(
        path, alice, write_document_id=created.write_document_id,
        mutation_key="native-edit-1", base_revision=1,
        base_body_sha256=created.body_sha256,
        body_html="<article><h1>Owner thesis</h1></article>", summary="First argument.",
    )
    assert edited.revision == 2
    history = list_private_write_revisions(
        path, alice, write_document_id=created.write_document_id,
    )
    assert [item.operation for item in history] == ["create", "edit"]
    assert all(item.origin_kind == "owner_native" for item in history)
    assert all(item.root_acceptance_event_id is None and item.proposal_id is None for item in history)
    assert get_private_write_revision(
        path, alice, write_document_id=created.write_document_id, revision=2,
    ).body_html == "<article><h1>Owner thesis</h1></article>"
    restored = restore_private_write_revision(
        path, alice, write_document_id=created.write_document_id,
        mutation_key="native-restore-1", base_revision=2,
        base_body_sha256=edited.body_sha256, target_revision=1,
    )
    assert restored.revision == 3
    assert get_private_write_document(
        path, alice, write_document_id=created.write_document_id,
    ).body_html == "<article></article>"
    with connect_write(path, purpose="test/native-ledger-counts", log_on_close=False) as con:
        assert con.execute("SELECT count(*) FROM interview_write_review_events_authority").fetchone() == (0,)
        assert con.execute("SELECT count(*) FROM interview_write_edit_events_authority").fetchone() == (0,)
        con.execute(
            "UPDATE interview_write_native_events_authority SET summary = 'tampered' "
            "WHERE event_id = ?", [edited.event_id],
        )
    with pytest.raises(WriteAcceptanceConflict, match="native receipt is corrupt"):
        get_private_write_document(
            path, alice, write_document_id=created.write_document_id,
        )


def test_owner_native_evidence_insertion_previews_then_appends_exact_receipt(tmp_path) -> None:
    path = str(tmp_path / "evidence-insert.duckdb")
    init_database_at_path(path)
    alice = InterviewAccountAuthority("alice")
    created = create_native_private_write(
        path, alice, title="Research synthesis", mutation_key="create",
    )
    source = EvidenceInsertionSource(
        citation_receipt_sha256="a" * 64, source_asset_id="research-1",
        claim_id="claim-1", source_document_id="document-1",
        chunk_ids=("chunk-2", "chunk-4"), source_title="Source <Study>",
        source_content_sha256="b" * 64,
        excerpt_text='Evidence <cannot> become markup & "quotes".',
    )
    preview = preview_native_evidence_insertion(
        path, alice, write_document_id=created.write_document_id,
        base_revision=1, base_body_sha256=created.body_sha256, source=source,
        preview_secret="test-preview-secret-" + "x" * 32,
    )
    assert get_private_write_document(
        path, alice, write_document_id=created.write_document_id,
    ).revision == 1
    assert "Evidence &lt;cannot&gt; become markup &amp; &quot;quotes&quot;." in preview.proposed_html
    assert "Source &lt;Study&gt;" in preview.proposed_html
    with pytest.raises(WriteAcceptanceConflict, match="preview is stale"):
        apply_native_evidence_insertion(
            path, alice, write_document_id=created.write_document_id,
            mutation_key="wrong-preview-secret", base_revision=1,
            base_body_sha256=created.body_sha256, source=source,
            preview_sha256=preview.preview_sha256,
            proposed_html_sha256=preview.proposed_html_sha256,
            preview_secret="wrong-preview-secret-" + "y" * 32,
        )
    inserted = apply_native_evidence_insertion(
        path, alice, write_document_id=created.write_document_id,
        mutation_key="insert-1", base_revision=1,
        base_body_sha256=created.body_sha256, source=source,
        preview_sha256=preview.preview_sha256,
        proposed_html_sha256=preview.proposed_html_sha256,
        preview_secret="test-preview-secret-" + "x" * 32,
    )
    assert inserted.revision == 2
    assert apply_native_evidence_insertion(
        path, alice, write_document_id=created.write_document_id,
        mutation_key="insert-1", base_revision=1,
        base_body_sha256=created.body_sha256, source=source,
        preview_sha256=preview.preview_sha256,
        proposed_html_sha256=preview.proposed_html_sha256,
        preview_secret="test-preview-secret-" + "x" * 32,
    ).replayed is True
    history = list_private_write_revisions(
        path, alice, write_document_id=created.write_document_id,
    )
    assert [item.operation for item in history] == ["create", "evidence_insert"]
    with connect_write(path, purpose="test/evidence-corruption", log_on_close=False) as con:
        con.execute(
            "UPDATE interview_write_evidence_insertions_authority "
            "SET source_title = 'tampered' WHERE native_event_id = ?", [inserted.event_id],
        )
    with pytest.raises(WriteAcceptanceConflict, match="evidence receipt is corrupt"):
        get_private_write_document(
            path, alice, write_document_id=created.write_document_id,
        )


def test_owner_native_evidence_bundle_preserves_order_relationships_and_one_revision(
    tmp_path,
) -> None:
    path = str(tmp_path / "evidence-bundle.duckdb")
    init_database_at_path(path)
    alice = InterviewAccountAuthority("alice")
    created = create_native_private_write(
        path, alice, title="Bundle analysis", mutation_key="bundle-create",
    )
    def source(receipt: str, suffix: str, text: str) -> EvidenceInsertionSource:
        return EvidenceInsertionSource(
            citation_receipt_sha256=receipt * 64,
            source_asset_id=f"research-{suffix}", claim_id=f"claim-{suffix}",
            source_document_id=f"document-{suffix}", chunk_ids=(f"chunk-{suffix}",),
            source_title=f"Source {suffix}", source_content_sha256=suffix * 64,
            excerpt_text=text,
        )
    items = (
        EvidenceBundleItem(source("a", "b", "First evidence"), "supports", "Baseline"),
        EvidenceBundleItem(source("c", "d", "Conflicting evidence"), "contradicts", None),
    )
    secret = "bundle-preview-secret-" + "x" * 32
    preview = preview_native_evidence_bundle(
        path, alice, write_document_id=created.write_document_id,
        base_revision=1, base_body_sha256=created.body_sha256,
        items=items, preview_secret=secret,
    )
    assert [item["relationship"] for item in preview.items] == ["supports", "contradicts"]
    assert preview.proposed_html.index("First evidence") < preview.proposed_html.index(
        "Conflicting evidence"
    )
    assert get_private_write_document(
        path, alice, write_document_id=created.write_document_id,
    ).revision == 1
    decision = apply_native_evidence_bundle(
        path, alice, write_document_id=created.write_document_id,
        mutation_key="bundle-apply", base_revision=1,
        base_body_sha256=created.body_sha256, items=items,
        preview_sha256=preview.preview_sha256,
        manifest_sha256=preview.manifest_sha256,
        proposed_html_sha256=preview.proposed_html_sha256, preview_secret=secret,
    )
    assert (decision.revision, decision.operation) == (2, "evidence_bundle")
    assert apply_native_evidence_bundle(
        path, alice, write_document_id=created.write_document_id,
        mutation_key="bundle-apply", base_revision=1,
        base_body_sha256=created.body_sha256, items=items,
        preview_sha256=preview.preview_sha256,
        manifest_sha256=preview.manifest_sha256,
        proposed_html_sha256=preview.proposed_html_sha256, preview_secret=secret,
    ).replayed is True
    with pytest.raises(WriteAcceptanceConflict, match="manifest is stale"):
        apply_native_evidence_bundle(
            path, alice, write_document_id=created.write_document_id,
            mutation_key="bundle-apply", base_revision=1,
            base_body_sha256=created.body_sha256, items=tuple(reversed(items)),
            preview_sha256=preview.preview_sha256,
            manifest_sha256=preview.manifest_sha256,
            proposed_html_sha256=preview.proposed_html_sha256, preview_secret=secret,
        )
    assert [item.operation for item in list_private_write_revisions(
        path, alice, write_document_id=created.write_document_id,
    )] == ["create", "evidence_bundle"]
    with connect_write(path, purpose="test/bundle-synthesis", log_on_close=False) as con:
        bundle_id = str(con.execute(
            "SELECT bundle_id FROM interview_write_evidence_bundles_authority"
        ).fetchone()[0])
        proposal = create_evidence_bundle_synthesis_proposal(
            con, alice, bundle_id=bundle_id, write_document_id=created.write_document_id,
            project_id=created.project_id, mutation_key="bundle-synthesis-1",
            base_revision=0, instruction="Preserve and analyze the disagreement.",
            provider_id="openai", model_id="gpt-test", projected_max_cents=25,
            approved_ceiling_cents=30,
            allowed_model_pairs=frozenset({("openai", "gpt-test")}),
            hydrated_items=items,
        )
        assert (proposal.state, proposal.revision, len(proposal.inputs)) == ("staged", 1, 2)
        assert proposal.inputs[1]["relationship"] == "contradicts"
        assert create_evidence_bundle_synthesis_proposal(
            con, alice, bundle_id=bundle_id, write_document_id=created.write_document_id,
            project_id=created.project_id, mutation_key="bundle-synthesis-1",
            base_revision=0, instruction="Preserve and analyze the disagreement.",
            provider_id="openai", model_id="gpt-test", projected_max_cents=25,
            approved_ceiling_cents=30,
            allowed_model_pairs=frozenset({("openai", "gpt-test")}),
            hydrated_items=items,
        ).proposal_id == proposal.proposal_id
        with pytest.raises(EvidenceBundleSynthesisConflict, match="different input"):
            create_evidence_bundle_synthesis_proposal(
                con, alice, bundle_id=bundle_id,
                write_document_id=created.write_document_id,
                project_id=created.project_id, mutation_key="bundle-synthesis-1",
                base_revision=1, instruction="Preserve and analyze the disagreement.",
                provider_id="openai", model_id="gpt-test", projected_max_cents=25,
                approved_ceiling_cents=30,
                allowed_model_pairs=frozenset({("openai", "gpt-test")}),
                hydrated_items=items,
            )
        with pytest.raises(ValueError, match="not found"):
            get_evidence_bundle_synthesis_proposal(
                con, InterviewAccountAuthority("bob"), proposal_id=proposal.proposal_id,
            )
        con.execute(
            "UPDATE interview_evidence_bundle_synthesis_inputs_authority "
            "SET excerpt_text = 'tampered' WHERE proposal_id = ? AND ordinal = 0",
            [proposal.proposal_id],
        )
        with pytest.raises(EvidenceBundleSynthesisConflict, match="input is corrupt"):
            get_evidence_bundle_synthesis_proposal(
                con, alice, proposal_id=proposal.proposal_id,
            )
        con.execute(
            "UPDATE interview_evidence_bundle_synthesis_inputs_authority "
            "SET excerpt_text = 'First evidence' WHERE proposal_id = ? AND ordinal = 0",
            [proposal.proposal_id],
        )
    class BundleExecutor:
        route_sha256 = "7" * 64
        calls = 0

        def execute(self, *, prompt, provider, model, idempotency_key):
            self.calls += 1
            return ProviderCompositionResult(
                raw_json=json.dumps({
                    "schema_version": 1, "title": "Disagreement analysis",
                    "lead": "The evidence remains contested.",
                    "units": [{
                        "evidence_unit_ids": ["evidence-1", "evidence-2"],
                        "prose": "Compare <script>alert(1)</script> both accounts.",
                    }],
                }),
                provider=provider, model=model, actual_cents=5,
                dispatch_event_id="bundle-dispatch-1",
                prompt_sha256=hashlib.sha256(prompt.encode()).hexdigest(),
            )

    executor = BundleExecutor()
    def revalidate(_con, current_proposal):
        assert_evidence_bundle_synthesis_custody(current_proposal, items)

    executed = execute_proposal(
        path, alice, proposal_id=proposal.proposal_id,
        attempt_id="bundle-execute-1", route_sha256=executor.route_sha256,
        executor=executor, source_revalidator=revalidate,
    )
    assert (executed.state, executed.actual_cents, executor.calls) == (
        "ready_for_review", 5, 1,
    )
    assert "Operator relationship: supports" in executed.result_html
    assert "Operator relationship: contradicts" in executed.result_html
    assert "&lt;script&gt;alert(1)&lt;/script&gt;" in executed.result_html
    assert "data-citation-receipt-sha256" in executed.result_html
    assert get_private_write_document(
        path, alice, write_document_id=created.write_document_id,
    ).revision == 2
    assert execute_proposal(
        path, alice, proposal_id=proposal.proposal_id,
        attempt_id="bundle-execute-1", route_sha256=executor.route_sha256,
        executor=executor, source_revalidator=revalidate,
    ).result_html_sha256 == executed.result_html_sha256
    assert executor.calls == 1
    acceptance_secret = "synthesis-acceptance-secret-" + "z" * 32
    acceptance_preview = preview_evidence_synthesis_acceptance(
        path, alice, proposal_id=proposal.proposal_id,
        write_document_id=created.write_document_id, base_revision=2,
        base_html_sha256=decision.body_sha256, preview_secret=acceptance_secret,
        source_revalidator=revalidate,
    )
    assert "Evidence synthesis" in acceptance_preview.proposed_html
    assert get_private_write_document(
        path, alice, write_document_id=created.write_document_id,
    ).revision == 2
    accepted = apply_evidence_synthesis_acceptance(
        path, alice, proposal_id=proposal.proposal_id,
        write_document_id=created.write_document_id,
        mutation_key="bundle-synthesis-accept-1", base_revision=2,
        base_html_sha256=decision.body_sha256,
        preview_sha256=acceptance_preview.preview_sha256,
        proposed_html_sha256=acceptance_preview.proposed_html_sha256,
        preview_secret=acceptance_secret, source_revalidator=revalidate,
    )
    assert (accepted.edit.revision, accepted.edit.operation) == (3, "synthesis_accept")
    assert apply_evidence_synthesis_acceptance(
        path, alice, proposal_id=proposal.proposal_id,
        write_document_id=created.write_document_id,
        mutation_key="bundle-synthesis-accept-1", base_revision=2,
        base_html_sha256=decision.body_sha256,
        preview_sha256=acceptance_preview.preview_sha256,
        proposed_html_sha256=acceptance_preview.proposed_html_sha256,
        preview_secret=acceptance_secret, source_revalidator=revalidate,
    ).edit.replayed is True
    assert [item.operation for item in list_private_write_revisions(
        path, alice, write_document_id=created.write_document_id,
    )] == ["create", "evidence_bundle", "synthesis_accept"]
    with connect_write(path, purpose="test/synthesis-accept-corruption", log_on_close=False) as con:
        con.execute(
            "UPDATE interview_write_synthesis_acceptances_authority SET route_sha256 = ? "
            "WHERE acceptance_id = ?", ["f" * 64, accepted.acceptance_id],
        )
    with pytest.raises(WriteAcceptanceConflict, match="synthesis acceptance is corrupt"):
        get_private_write_document(
            path, alice, write_document_id=created.write_document_id,
        )
    with connect_write(path, purpose="test/synthesis-accept-repair", log_on_close=False) as con:
        con.execute(
            "UPDATE interview_write_synthesis_acceptances_authority SET route_sha256 = ? "
            "WHERE acceptance_id = ?", [executor.route_sha256, accepted.acceptance_id],
        )
    with connect_write(path, purpose="test/bundle-counts", log_on_close=False) as con:
        assert con.execute(
            "SELECT count(*) FROM interview_write_evidence_bundles_authority"
        ).fetchone() == (1,)
        assert con.execute(
            "SELECT count(*) FROM interview_write_evidence_bundle_units_authority"
        ).fetchone() == (2,)
        con.execute(
            "UPDATE interview_write_evidence_bundle_units_authority SET ordinal = 2 "
            "WHERE ordinal = 1"
        )
    with pytest.raises(WriteAcceptanceConflict, match="bundle unit is corrupt"):
        get_private_write_document(
            path, alice, write_document_id=created.write_document_id,
        )
    with connect_write(path, purpose="test/bundle-missing", log_on_close=False) as con:
        con.execute(
            "UPDATE interview_write_evidence_bundle_units_authority SET ordinal = 1 "
            "WHERE ordinal = 2"
        )
        con.execute("DELETE FROM interview_write_evidence_bundles_authority")
    with pytest.raises(WriteAcceptanceConflict, match="bundle ledger is incomplete"):
        get_private_write_document(
            path, alice, write_document_id=created.write_document_id,
        )


def test_composition_execution_is_budget_guarded_checkpointed_and_reconcilable(
    tmp_path, monkeypatch
) -> None:
    from types import SimpleNamespace

    import substrate.interviews.composition_execution as execution_module
    import substrate.interviews.write_acceptance as acceptance_module

    path = str(tmp_path / "composition-execution.duckdb")
    init_database_at_path(path)
    authority = InterviewAccountAuthority("alice")
    draft = SimpleNamespace(
        draft_id="draft-1", project_id="project-1", title="Private evidence",
        manifest_sha256="1" * 64,
        body_sha256="2" * 64,
        manifest={"claims": [{"claim_id": "claim-1", "text": "Grounded fact",
                               "verification": "unverified"}]},
        body_html=(
            '<!doctype html><html><body><article><header><h1>Evidence</h1></header>'
            '<section class="antiek-claim" data-claim-id="claim-1">Grounded fact'
            '</section></article></body></html>'
        ),
    )

    def proposal(proposal_id: str):
        return SimpleNamespace(
            proposal_id=proposal_id, draft_id=draft.draft_id, project_id=draft.project_id,
            instruction="Connect evidence without changing its status.",
            provider_id="openai", model_id="gpt-test", projected_max_cents=40,
            approved_ceiling_cents=50,
            source_manifest_sha256=draft.manifest_sha256,
            source_body_sha256=draft.body_sha256,
        )

    monkeypatch.setattr(
        execution_module, "get_proposal",
        lambda con, auth, *, proposal_id: proposal(proposal_id),
    )
    revoke_on_dispatch = {"enabled": False, "all": False}

    def current_draft(con, auth, *, draft_id):
        if revoke_on_dispatch["all"] or (
            revoke_on_dispatch["enabled"] and con.execute(
                "SELECT 1 FROM interview_composition_execution_authority "
                "WHERE state = 'dispatching'"
            ).fetchone() is not None
        ):
            raise CompositionConflict("record consent is not currently granted")
        return draft

    monkeypatch.setattr(execution_module, "get_private_draft", current_draft)
    monkeypatch.setattr(
        acceptance_module, "get_proposal",
        lambda con, auth, *, proposal_id: proposal(proposal_id),
    )
    monkeypatch.setattr(acceptance_module, "get_private_draft", current_draft)

    class FakeCompositionExecutor:
        def __init__(
            self, route_sha256: str, actual_cents: int = 17,
            result_provider: str | None = None,
        ) -> None:
            self.calls = 0
            self.actual_cents = actual_cents
            self.route_sha256 = route_sha256
            self.result_provider = result_provider

        def execute(self, *, prompt, provider, model, idempotency_key):
            self.calls += 1
            return ProviderCompositionResult(
                raw_json=json.dumps({
                    "schema_version": 1, "title": "AI <draft>",
                    "lead": "A careful synthesis & review.",
                    "units": [{"claim_ids": ["claim-1"],
                               "prose": "Connect <without> inventing."}],
                }),
                provider=self.result_provider or provider, model=model,
                actual_cents=self.actual_cents,
                dispatch_event_id="dispatch-test-1",
                prompt_sha256=hashlib.sha256(prompt.encode()).hexdigest(),
            )

    executor = FakeCompositionExecutor("a" * 64)
    executed = execute_proposal(
        path, authority, proposal_id="proposal-1", attempt_id="attempt-1",
        route_sha256="a" * 64, executor=executor,
    )
    assert executed.state == "ready_for_review"
    assert executed.actual_cents == 17
    assert executor.calls == 1

    rejected_review = review_result(
        path, authority, proposal_id="proposal-1", mutation_key="review-reject-1",
        action="reject", base_revision=0, rationale="Needs a different structure.",
    )
    assert rejected_review.action == "reject"
    accepted_review = review_result(
        path, authority, proposal_id="proposal-1", mutation_key="review-accept-1",
        action="accept", base_revision=0, rationale="Evidence remains visible.",
    )
    assert accepted_review.revision == 1
    assert review_result(
        path, authority, proposal_id="proposal-1", mutation_key="review-accept-1",
        action="accept", base_revision=0, rationale="Evidence remains visible.",
    ).replayed is True
    with pytest.raises(WriteAcceptanceConflict, match="already accepted"):
        review_result(
            path, authority, proposal_id="proposal-1", mutation_key="review-accept-2",
            action="accept", base_revision=1,
        )
    private_write = get_private_write_document(
        path, authority, write_document_id=accepted_review.write_document_id
    )
    assert private_write.revision == 1
    assert private_write.body_html == executed.result_html
    with pytest.raises(ValueError, match="not found"):
        get_private_write_document(
            path, InterviewAccountAuthority("bob"),
            write_document_id=accepted_review.write_document_id,
        )
    undone = undo_acceptance(
        path, authority, target_event_id=accepted_review.event_id,
        mutation_key="review-undo-1", base_revision=1,
    )
    assert undone.revision == 2
    restored = get_private_write_document(
        path, authority, write_document_id=accepted_review.write_document_id
    )
    assert restored.revision == 2
    assert restored.body_html == ""
    assert undo_acceptance(
        path, authority, target_event_id=accepted_review.event_id,
        mutation_key="review-undo-1", base_revision=1,
    ).replayed is True
    empty_sha = hashlib.sha256(b"").hexdigest()
    owner_html = "<!doctype html><html><body><main><h1>Owner revision</h1></main></body></html>"
    edited = edit_private_write(
        path, authority, write_document_id=accepted_review.write_document_id,
        mutation_key="write-edit-1", base_revision=2, base_body_sha256=empty_sha,
        body_html=owner_html, summary="Owner-authored structure.",
    )
    assert edited.revision == 3
    assert edit_private_write(
        path, authority, write_document_id=accepted_review.write_document_id,
        mutation_key="write-edit-1", base_revision=2, base_body_sha256=empty_sha,
        body_html=owner_html, summary="Owner-authored structure.",
    ).replayed is True
    current_edit = get_private_write_document(
        path, authority, write_document_id=accepted_review.write_document_id
    )
    assert current_edit.body_html == owner_html
    with pytest.raises(WriteAcceptanceConflict, match="different input"):
        edit_private_write(
            path, authority, write_document_id=accepted_review.write_document_id,
            mutation_key="write-edit-1", base_revision=2, base_body_sha256=empty_sha,
            body_html="<p>changed</p>", summary="Owner-authored structure.",
        )
    with pytest.raises(WriteAcceptanceConflict, match="stale"):
        edit_private_write(
            path, authority, write_document_id=accepted_review.write_document_id,
            mutation_key="write-edit-stale", base_revision=2, base_body_sha256=empty_sha,
            body_html="<p>stale</p>",
        )
    for unsafe in (
        '<p onclick="alert(1)">x</p>', '<a href="jav&#97;script:alert(1)">x</a>',
        '<img src="/same-origin-fetch">', '<p><strong>broken</p>',
        '<style>body{background:url(/private-endpoint)}</style><p>x</p>',
        '<style>@import "/private-endpoint";</style><p>x</p>',
    ):
        with pytest.raises(ValueError, match="private Write HTML"):
            edit_private_write(
                path, authority, write_document_id=accepted_review.write_document_id,
                mutation_key="unsafe-" + hashlib.sha256(unsafe.encode()).hexdigest(),
                base_revision=3, base_body_sha256=edited.body_sha256, body_html=unsafe,
            )
    restored_edit = edit_private_write(
        path, authority, write_document_id=accepted_review.write_document_id,
        mutation_key="write-edit-restore", base_revision=3,
        base_body_sha256=edited.body_sha256, body_html="",
        summary="Restore historical empty body.",
    )
    assert restored_edit.revision == 4
    assert edit_private_write(
        path, authority, write_document_id=accepted_review.write_document_id,
        mutation_key="write-edit-1", base_revision=2, base_body_sha256=empty_sha,
        body_html=owner_html, summary="Owner-authored structure.",
    ).replayed is True
    assert get_private_write_document(
        path, authority, write_document_id=accepted_review.write_document_id
    ).body_html == ""
    with connect_write(path, purpose="test/edit-event-corruption", log_on_close=False) as con:
        con.execute(
            "UPDATE interview_write_edit_events_authority SET summary = 'tampered' "
            "WHERE event_id = ?", [edited.event_id],
        )
    with pytest.raises(WriteAcceptanceConflict, match="edit receipt is corrupt"):
        get_private_write_document(
            path, authority, write_document_id=accepted_review.write_document_id
        )
    with connect_write(path, purpose="test/edit-event-restore", log_on_close=False) as con:
        con.execute(
            "UPDATE interview_write_edit_events_authority "
            "SET summary = 'Owner-authored structure.' WHERE event_id = ?", [edited.event_id],
        )
        con.execute(
            "UPDATE interview_write_edit_revisions_authority SET body_html = 'tampered' "
            "WHERE event_id = ?", [edited.event_id],
        )
    with pytest.raises(WriteAcceptanceConflict, match="revision integrity failed"):
        get_private_write_document(
            path, authority, write_document_id=accepted_review.write_document_id
        )
    with connect_write(path, purpose="test/edit-body-restore", log_on_close=False) as con:
        con.execute(
            "UPDATE interview_write_edit_revisions_authority SET body_html = ? "
            "WHERE event_id = ?", [owner_html, edited.event_id],
        )
    with pytest.raises(WriteAcceptanceConflict, match="different input"):
        review_result(
            path, authority, proposal_id="proposal-1", mutation_key="review-reject-1",
            action="reject", base_revision=0, rationale="Changed rationale.",
        )
    with pytest.raises(WriteAcceptanceConflict, match="stale"):
        review_result(
            path, authority, proposal_id="proposal-1", mutation_key="review-stale",
            action="reject", base_revision=1,
        )
    con = duckdb.connect(path, read_only=True)
    try:
        assert con.execute("SELECT count(*) FROM deliverables").fetchone() == (0,)
        assert con.execute("SELECT count(*) FROM deliverable_sections").fetchone() == (0,)
        assert con.execute("SELECT count(*) FROM outline_blocks").fetchone() == (0,)
    finally:
        con.close()

    with connect_write(path, purpose="test/write-receipt-corruption", log_on_close=False) as con:
        con.execute(
            "UPDATE interview_write_review_events_authority "
            "SET source_manifest_sha256 = ? WHERE event_id = ?",
            ["f" * 64, accepted_review.event_id],
        )
    with pytest.raises(WriteAcceptanceConflict, match="receipt is corrupt"):
        get_private_write_document(
            path, authority, write_document_id=accepted_review.write_document_id
        )
    with pytest.raises(WriteAcceptanceConflict, match="receipt is corrupt"):
        list_private_write_documents(path, authority)
    with connect_write(path, purpose="test/write-receipt-restore", log_on_close=False) as con:
        con.execute(
            "UPDATE interview_write_review_events_authority "
            "SET source_manifest_sha256 = ? WHERE event_id = ?",
            [draft.manifest_sha256, accepted_review.event_id],
        )
    revoke_on_dispatch["all"] = True
    with pytest.raises(CompositionConflict, match="consent"):
        get_private_write_document(
            path, authority, write_document_id=accepted_review.write_document_id
        )
    with pytest.raises(CompositionConflict, match="consent"):
        list_private_write_documents(path, authority)
    with pytest.raises(CompositionConflict, match="consent"):
        list_private_write_revisions(
            path, authority, write_document_id=accepted_review.write_document_id
        )
    with pytest.raises(CompositionConflict, match="consent"):
        get_private_write_revision(
            path, authority, write_document_id=accepted_review.write_document_id,
            revision=1,
        )
    with pytest.raises(CompositionConflict, match="consent"):
        restore_private_write_revision(
            path, authority, write_document_id=accepted_review.write_document_id,
            mutation_key="withdrawn-restore", base_revision=4,
            base_body_sha256=empty_sha, target_revision=3,
        )
    revoke_on_dispatch["all"] = False
    assert "AI &lt;draft&gt;" in executed.result_html
    assert "Connect &lt;without&gt; inventing." in executed.result_html
    assert "Grounded fact" in executed.result_html
    replay = execute_proposal(
        path, authority, proposal_id="proposal-1", attempt_id="attempt-1",
        route_sha256="a" * 64, executor=executor,
    )
    assert replay.result_html_sha256 == executed.result_html_sha256
    assert executor.calls == 1

    crash_executor = FakeCompositionExecutor("b" * 64)
    with pytest.raises(CompositionExecutionConflict, match="reconciliation"):
        execute_proposal(
            path, authority, proposal_id="proposal-2", attempt_id="attempt-2",
            route_sha256="b" * 64, executor=crash_executor,
            crash_after_checkpoint=True,
        )
    assert crash_executor.calls == 1
    assert get_execution(path, authority, proposal_id="proposal-2").state == "provider_returned"
    recovered = reconcile_checkpointed(path, authority, proposal_id="proposal-2")
    assert recovered.state == "ready_for_review"
    assert crash_executor.calls == 1

    accepted_second = review_result(
        path, authority, proposal_id="proposal-2", mutation_key="review-accept-2",
        action="accept", base_revision=4,
    )
    fourth_executor = FakeCompositionExecutor("8" * 64)
    execute_proposal(
        path, authority, proposal_id="proposal-8", attempt_id="attempt-8",
        route_sha256="8" * 64, executor=fourth_executor,
    )
    accepted_fourth = review_result(
        path, authority, proposal_id="proposal-8", mutation_key="review-accept-8",
        action="accept", base_revision=5,
    )
    undone_fourth = undo_acceptance(
        path, authority, target_event_id=accepted_fourth.event_id,
        mutation_key="review-undo-4", base_revision=6,
    )
    restored_second = get_private_write_document(
        path, authority, write_document_id=accepted_review.write_document_id
    )
    lineage_edit = edit_private_write(
        path, authority, write_document_id=accepted_review.write_document_id,
        mutation_key="write-edit-restored-lineage", base_revision=undone_fourth.revision,
        base_body_sha256=restored_second.body_sha256,
        body_html=restored_second.body_html.replace("Grounded fact", "Grounded fact edited", 1),
    )
    with connect_write(path, purpose="test/restored-lineage-proof", log_on_close=False) as con:
        assert con.execute(
            "SELECT root_acceptance_event_id FROM interview_write_edit_events_authority "
            "WHERE event_id = ?", [lineage_edit.event_id],
        ).fetchone() == (accepted_second.event_id,)
    history = list_private_write_revisions(
        path, authority, write_document_id=accepted_review.write_document_id
    )
    assert [item.revision for item in history] == list(range(1, 9))
    assert all(item.body_html is None for item in history)
    historical_owner_edit = get_private_write_revision(
        path, authority, write_document_id=accepted_review.write_document_id, revision=3
    )
    assert historical_owner_edit.body_html == owner_html
    assert historical_owner_edit.operation == "edit"
    current_before_restore = get_private_write_document(
        path, authority, write_document_id=accepted_review.write_document_id
    )
    restored_history = restore_private_write_revision(
        path, authority, write_document_id=accepted_review.write_document_id,
        mutation_key="write-restore-history-3", base_revision=8,
        base_body_sha256=current_before_restore.body_sha256, target_revision=3,
    )
    assert restored_history.revision == 9
    restored_metadata = get_private_write_revision(
        path, authority, write_document_id=accepted_review.write_document_id, revision=9
    )
    assert restored_metadata.operation == "restore"
    assert restored_metadata.target_revision == 3
    assert restored_metadata.target_body_sha256 == historical_owner_edit.body_sha256
    assert restored_metadata.root_acceptance_event_id == accepted_review.event_id
    assert restored_metadata.body_html == owner_html
    with connect_write(path, purpose="test/restore-target-corruption", log_on_close=False) as con:
        con.execute(
            "UPDATE interview_write_edit_events_authority SET target_body_sha256 = ? "
            "WHERE event_id = ?", ["f" * 64, restored_history.event_id],
        )
    with pytest.raises(WriteAcceptanceConflict, match="edit receipt is corrupt"):
        get_private_write_revision(
            path, authority, write_document_id=accepted_review.write_document_id,
            revision=9,
        )
    with connect_write(path, purpose="test/restore-target-repair", log_on_close=False) as con:
        con.execute(
            "UPDATE interview_write_edit_events_authority SET target_body_sha256 = ? "
            "WHERE event_id = ?",
            [historical_owner_edit.body_sha256, restored_history.event_id],
        )
    successor = edit_private_write(
        path, authority, write_document_id=accepted_review.write_document_id,
        mutation_key="write-after-restore", base_revision=9,
        base_body_sha256=restored_history.body_sha256,
        body_html=owner_html.replace("</main>", "<p>Successor</p></main>"),
    )
    assert successor.revision == 10
    assert restore_private_write_revision(
        path, authority, write_document_id=accepted_review.write_document_id,
        mutation_key="write-restore-history-3", base_revision=8,
        base_body_sha256=current_before_restore.body_sha256, target_revision=3,
    ).replayed is True
    with pytest.raises(WriteAcceptanceConflict, match="different input"):
        restore_private_write_revision(
            path, authority, write_document_id=accepted_review.write_document_id,
            mutation_key="write-restore-history-3", base_revision=8,
            base_body_sha256=current_before_restore.body_sha256, target_revision=2,
        )

    overshoot_executor = FakeCompositionExecutor("c" * 64, actual_cents=41)
    overshoot = execute_proposal(
        path, authority, proposal_id="proposal-3", attempt_id="attempt-3",
        route_sha256="c" * 64, executor=overshoot_executor,
    )
    assert overshoot.state == "rejected"
    assert overshoot.result_html is None
    assert overshoot.rejection_reason == "provider composition exceeded projected maximum"
    con = duckdb.connect(path, read_only=True)
    try:
        assert con.execute(
            "SELECT spent_cents, held_cents FROM midnight_oil_reservations "
            "WHERE run_id = ?", [overshoot.run_id],
        ).fetchone() == (41, 0)
    finally:
        con.close()

    revoke_on_dispatch["enabled"] = True
    withdrawn_executor = FakeCompositionExecutor("7" * 64)
    with pytest.raises(CallNotDispatched):
        execute_proposal(
            path, authority, proposal_id="proposal-7", attempt_id="attempt-7",
            route_sha256="7" * 64, executor=withdrawn_executor,
        )
    revoke_on_dispatch["enabled"] = False
    assert withdrawn_executor.calls == 0
    withdrawn = get_execution(path, authority, proposal_id="proposal-7")
    assert withdrawn.state == "call_not_dispatched"
    con = duckdb.connect(path, read_only=True)
    try:
        assert con.execute(
            "SELECT state FROM midnight_oil_call_holds WHERE hold_id = ?",
            [withdrawn.hold_id],
        ).fetchone() == ("released",)
    finally:
        con.close()

    orphan_run_id = "ivrun-" + hashlib.sha256(
        (authority.account_digest + "\0proposal-6").encode()
    ).hexdigest()[:32]
    orphan_ledger = BudgetLedger(path)
    orphan_ledger.reserve(orphan_run_id, 50, {"composition_writer": 50})
    orphan_hold = orphan_ledger.reserve_call(orphan_run_id, "composition_writer", 40)
    recovered_executor = FakeCompositionExecutor("6" * 64)
    orphan_recovered = execute_proposal(
        path, authority, proposal_id="proposal-6", attempt_id="attempt-6",
        route_sha256="6" * 64, executor=recovered_executor,
    )
    assert orphan_recovered.state == "ready_for_review"
    assert recovered_executor.calls == 1
    con = duckdb.connect(path, read_only=True)
    try:
        assert con.execute(
            "SELECT state FROM midnight_oil_call_holds WHERE hold_id = ?",
            [orphan_hold.hold_id],
        ).fetchone() == ("released",)
    finally:
        con.close()

    wrong_route_executor = FakeCompositionExecutor(
        "d" * 64, result_provider="foreign-provider"
    )
    wrong_route = execute_proposal(
        path, authority, proposal_id="proposal-4", attempt_id="attempt-4",
        route_sha256="d" * 64, executor=wrong_route_executor,
    )
    assert wrong_route.state == "rejected"
    assert wrong_route.rejection_reason == "composition provider route is outside approval"
    assert wrong_route_executor.calls == 1

    unattested_executor = FakeCompositionExecutor("e" * 64)
    with pytest.raises(ValueError, match="boot-attested"):
        execute_proposal(
            path, authority, proposal_id="proposal-5", attempt_id="attempt-5",
            route_sha256="f" * 64, executor=unattested_executor,
        )
    assert unattested_executor.calls == 0
    con = duckdb.connect(path, read_only=True)
    try:
        assert con.execute(
            "SELECT count(*) FROM interview_composition_execution_authority "
            "WHERE proposal_id = 'proposal-5'"
        ).fetchone() == (0,)
        assert con.execute(
            "SELECT count(*) FROM midnight_oil_reservations "
            "WHERE run_id LIKE 'ivrun-%'"
        ).fetchone()[0] == 7
    finally:
        con.close()


def test_init_installs_composite_canonical_interview_tables(tmp_path) -> None:
    path = str(tmp_path / "antiek.duckdb")
    init_database_at_path(path)
    con = duckdb.connect(path)
    try:
        project_info = con.execute(
            "PRAGMA table_info('interview_projects_authority')"
        ).fetchall()
        columns = {
            row[1] for row in con.execute("PRAGMA table_info('interviews_authority')").fetchall()
        }
        assert {row[1] for row in project_info if row[5]} == {"account_digest", "project_id"}
        assert {"informant_email", "consent_recorded", "transcript_turns"} <= columns
        assert con.execute(
            "SELECT schema_version FROM interview_authority_migration_manifest"
        ).fetchone() == (22,)
    finally:
        con.close()


def test_migration_copies_explicit_owner_content_and_is_idempotent(tmp_path) -> None:
    path = str(tmp_path / "legacy.duckdb")
    init_database_at_path(path)
    con = duckdb.connect(path)
    try:
        con.execute(
            "INSERT INTO interview_projects "
            "(project_id, title, topic_description, owner_user_id) VALUES "
            "('project-1', 'Title', 'Topic', 'alice')"
        )
        con.execute(
            "INSERT INTO interviews "
            "(interview_id, project_id, informant_handle, informant_email, "
            "consent_recorded, status, transcript_turns) VALUES "
            "('interview-1', 'project-1', 'Ada', 'ada@example.test', true, "
            "'completed', '[{\"role\":\"informant\",\"text\":\"answer\"}]')"
        )
        migrate_interview_authority_schema(con)
        migrate_interview_authority_schema(con)

        assert con.execute(
            "SELECT owner_user_id, title, topic_description FROM interview_projects_authority"
        ).fetchall() == [("alice", "Title", "Topic")]
        assert con.execute(
            "SELECT owner_user_id, informant_email, consent_recorded, status "
            "FROM interviews_authority"
        ).fetchall() == [("alice", "ada@example.test", True, "completed")]
    finally:
        con.close()


def test_missing_explicit_owner_is_quarantined_not_claimed(tmp_path) -> None:
    con = duckdb.connect(str(tmp_path / "minimal.duckdb"))
    try:
        con.execute(
            "CREATE TABLE interview_projects (project_id TEXT, title TEXT, "
            "topic_description TEXT, deliverable_id TEXT, interview_guide TEXT, "
            "owner_user_id TEXT, created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP)"
        )
        con.execute("INSERT INTO interview_projects (project_id, title, owner_user_id) VALUES ('p', 'T', '')")
        migrate_interview_authority_schema(con)
        assert con.execute("SELECT count(*) FROM interview_projects_authority").fetchone()[0] == 0
        assert con.execute(
            "SELECT entity_kind, entity_id, reason FROM interview_authority_quarantine"
        ).fetchall() == [("project", "p", "missing_explicit_owner")]
    finally:
        con.close()


def test_absent_owner_column_is_quarantined_not_claimed(tmp_path) -> None:
    con = duckdb.connect(str(tmp_path / "ownerless.duckdb"))
    try:
        con.execute(
            "CREATE TABLE interview_projects (project_id TEXT, title TEXT, "
            "topic_description TEXT, deliverable_id TEXT, interview_guide TEXT, "
            "created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP)"
        )
        con.execute("INSERT INTO interview_projects (project_id, title) VALUES ('p', 'T')")
        migrate_interview_authority_schema(con)
        assert con.execute("SELECT count(*) FROM interview_projects_authority").fetchone()[0] == 0
        assert con.execute("SELECT reason FROM interview_authority_quarantine").fetchone()[0] == "missing_explicit_owner"
    finally:
        con.close()


def test_sparse_explicit_owner_legacy_schema_migrates_with_safe_defaults(tmp_path) -> None:
    con = duckdb.connect(str(tmp_path / "sparse.duckdb"))
    try:
        con.execute(
            "CREATE TABLE interview_projects (project_id TEXT, title TEXT, owner_user_id TEXT)"
        )
        con.execute("CREATE TABLE interviews (interview_id TEXT, project_id TEXT)")
        con.execute("INSERT INTO interview_projects VALUES ('p', 'Title', 'alice')")
        con.execute("INSERT INTO interviews VALUES ('i', 'p')")
        migrate_interview_authority_schema(con)
        assert con.execute(
            "SELECT title, topic_description FROM interview_projects_authority"
        ).fetchall() == [("Title", None)]
        assert con.execute(
            "SELECT status, consent_recorded FROM interviews_authority"
        ).fetchall() == [("invited", False)]
    finally:
        con.close()


def test_migration_downgrades_unproved_delivery_states_to_failed(tmp_path) -> None:
    path = str(tmp_path / "delivery-upgrade.duckdb")
    init_database_at_path(path)
    authority = InterviewAccountAuthority("alice")
    with connect_write(path, purpose="test/interview-delivery-upgrade") as con:
        create_project(
            con, authority, project_id="p", title="P", topic_description=None,
            deliverable_id=None, interview_guide={},
        )
        create_interview(
            con, authority, project_id="p", interview_id="i",
            informant_handle=None, informant_email=None,
        )
        con.execute(
            "INSERT INTO interview_answer_derivations "
            "(account_digest, interview_id, question_id, project_id, owner_user_id, "
            "answer_sha256, investigation_id, investigation_digest, stream_key, "
            "binding_revision, delivery_state) VALUES (?, 'i', 'q', 'p', 'alice', ?, "
            "'research', ?, ?, 1, 'processing')",
            [authority.account_digest, "a" * 64, "b" * 64, "c" * 64],
        )
        migrate_interview_authority_schema(con)
        assert con.execute(
            "SELECT delivery_state, last_error_code FROM interview_answer_derivations"
        ).fetchone() == ("failed", "migration_missing_delivery_evidence")


def test_same_display_ids_and_mutations_are_account_isolated(tmp_path) -> None:
    path = str(tmp_path / "isolated.duckdb")
    init_database_at_path(path)
    alice = InterviewAccountAuthority("alice")
    bob = InterviewAccountAuthority("bob")
    with connect_write(path, purpose="test/interview-isolation") as con:
        for authority, title in ((alice, "Alice"), (bob, "Bob")):
            create_project(
                con, authority, project_id="shared-project", title=title,
                topic_description=None, deliverable_id=None, interview_guide={},
            )
            create_interview(
                con, authority, project_id="shared-project", interview_id="shared-interview",
                informant_handle=title, informant_email=None,
            )
        record_consent(con, alice, interview_id="shared-interview", granted=True)
        append_turn(
            con, alice, interview_id="shared-interview", role="informant", text="Alice answer"
        )
        rows = con.execute(
            "SELECT owner_user_id, transcript_turns FROM interviews_authority "
            "WHERE interview_id = 'shared-interview' ORDER BY owner_user_id"
        ).fetchall()
    assert "Alice answer" in rows[0][1]
    assert rows[1] == ("bob", None)


def test_consent_terminal_state_and_corrupt_transcript_are_fail_closed(tmp_path) -> None:
    path = str(tmp_path / "lifecycle.duckdb")
    init_database_at_path(path)
    authority = InterviewAccountAuthority("alice")
    with connect_write(path, purpose="test/interview-lifecycle") as con:
        create_project(
            con, authority, project_id="p", title="P", topic_description=None,
            deliverable_id=None, interview_guide={},
        )
        create_interview(
            con, authority, project_id="p", interview_id="i",
            informant_handle=None, informant_email=None,
        )
        with pytest.raises(InterviewStateConflict, match="consent"):
            append_turn(con, authority, interview_id="i", role="informant", text="answer")
        with pytest.raises(InterviewStateConflict, match="consent"):
            complete(con, authority, interview_id="i", transcript_document_id=None)
        assert record_consent(con, authority, interview_id="i", granted=True)
        append_turn(con, authority, interview_id="i", role="informant", text="answer")
        assert complete(con, authority, interview_id="i", transcript_document_id=None)
        with pytest.raises(InterviewStateConflict, match="completed"):
            append_turn(con, authority, interview_id="i", role="interviewer", text="late")

        create_interview(
            con, authority, project_id="p", interview_id="corrupt",
            informant_handle=None, informant_email=None,
        )
        con.execute(
            "UPDATE interviews_authority SET transcript_turns = 'not-json' "
            "WHERE account_digest = ? AND interview_id = 'corrupt'",
            [authority.account_digest],
        )
        with pytest.raises(InterviewStateConflict, match="corrupt"):
            append_turn(
                con, authority, interview_id="corrupt", role="interviewer", text="safe"
            )


def test_invite_capability_is_hashed_account_bound_and_revocable(tmp_path) -> None:
    path = str(tmp_path / "capability.duckdb")
    init_database_at_path(path)
    alice = InterviewAccountAuthority("alice")
    bob = InterviewAccountAuthority("bob")
    with connect_write(path, purpose="test/interview-capability") as con:
        for authority in (alice, bob):
            create_project(
                con, authority, project_id="shared", title=authority.account_id,
                topic_description=None, deliverable_id=None, interview_guide={},
            )
            create_interview(
                con, authority, project_id="shared", interview_id="shared",
                informant_handle=None, informant_email=None,
            )
        issued = issue_invite(con, alice, interview_id="shared")
        stored = con.execute(
            "SELECT token_digest, owner_user_id FROM interview_invite_capabilities"
        ).fetchone()
        assert issued.token not in stored
        capability = resolve_invite(con, issued.token)
        assert capability is not None
        assert capability.authority.account_id == "alice"
        assert capability.interview_id == "shared"
        assert not revoke_invite(con, bob, invite_id=issued.invite_id)
        assert resolve_invite(con, issued.token) is not None
        assert revoke_invite(con, alice, invite_id=issued.invite_id)
        assert resolve_invite(con, issued.token) is None


def test_answer_derivation_requires_explicit_account_bound_target(tmp_path) -> None:
    path = str(tmp_path / "derivation.duckdb")
    init_database_at_path(path)
    alice = InterviewAccountAuthority("alice")
    target = InvestigationAuthority("alice", "research-one", root=tmp_path / "events")
    with connect_write(path, purpose="test/interview-derivation") as con:
        create_project(
            con, alice, project_id="p", title="P", topic_description=None,
            deliverable_id=None, interview_guide={},
        )
        create_interview(
            con, alice, project_id="p", interview_id="i",
            informant_handle=None, informant_email=None,
        )
        record_consent(con, alice, interview_id="i", granted=True)
        assert stage_answer_if_bound(
            con, alice, interview_id="i", question_id="q0", answer_text="not committed"
        ) is None
        append_turn(
            con, alice, interview_id="i", role="informant", text="Earlier answer",
            question_id="q0",
        )
        assert con.execute("SELECT count(*) FROM interview_answer_derivations").fetchone()[0] == 0
        with pytest.raises(ValueError, match="crosses account"):
            bind_project(
                con, alice, project_id="p",
                investigation=InvestigationAuthority("bob", "research-one", root=tmp_path / "events"),
            )
        assert bind_project(con, alice, project_id="p", investigation=target) == 1
        append_turn(
            con, alice, interview_id="i", role="informant", text="Answer",
            question_id="q1",
        )
        rows = con.execute(
            "SELECT answer_sha256, investigation_id, investigation_digest, stream_key, "
            "delivery_state FROM interview_answer_derivations ORDER BY question_id"
        ).fetchall()
        assert len(rows) == 2
        row = rows[1]
        assert row[1:] == (
            "research-one", target.investigation_digest, target.stream_key, "pending"
        )
        assert "Answer" not in row
        # Exact answer retry is idempotent and does not duplicate the outbox row.
        append_turn(
            con, alice, interview_id="i", role="informant", text="Answer",
            question_id="q1",
        )
        assert con.execute("SELECT count(*) FROM interview_answer_derivations").fetchone()[0] == 2
        with pytest.raises(DerivationConflict, match="pending"):
            bind_project(
                con, alice, project_id="p",
                investigation=InvestigationAuthority("alice", "research-two", root=tmp_path / "events"),
            )


def test_answer_and_derivation_intent_rollback_together(tmp_path, monkeypatch) -> None:
    path = str(tmp_path / "rollback.duckdb")
    init_database_at_path(path)
    authority = InterviewAccountAuthority("alice")
    target = InvestigationAuthority("alice", "research", root=tmp_path / "events")
    with connect_write(path, purpose="test/interview-derivation-rollback") as con:
        create_project(
            con, authority, project_id="p", title="P", topic_description=None,
            deliverable_id=None, interview_guide={},
        )
        create_interview(
            con, authority, project_id="p", interview_id="i",
            informant_handle=None, informant_email=None,
        )
        record_consent(con, authority, interview_id="i", granted=True)
        bind_project(con, authority, project_id="p", investigation=target)

        def fail_stage(*args, **kwargs):
            raise KeyboardInterrupt("simulated process interruption")

        monkeypatch.setattr("substrate.interviews.derivation.stage_answer_if_bound", fail_stage)
        with pytest.raises(KeyboardInterrupt, match="simulated"):
            append_turn(
                con, authority, interview_id="i", role="informant",
                text="must roll back", question_id="q1",
            )
        assert con.execute(
            "SELECT transcript_turns FROM interviews_authority WHERE account_digest = ? "
            "AND interview_id = 'i'", [authority.account_digest],
        ).fetchone()[0] is None
        assert con.execute("SELECT count(*) FROM interview_answer_derivations").fetchone()[0] == 0


def test_reconciler_delivers_owner_admitted_document_and_event_once(tmp_path, monkeypatch) -> None:
    from substrate.event_log import trajectory_authorized
    from substrate.legal_gate.read import read_document

    monkeypatch.setenv("ANTIEK_RESEARCH_EVENTS_DIR", str(tmp_path / "events"))
    monkeypatch.setenv("ANTIEK_EMBEDDING_PROVIDER", "hash")
    path = str(tmp_path / "reconcile.duckdb")
    init_database_at_path(path)
    alice = InterviewAccountAuthority("alice")
    bob = InterviewAccountAuthority("bob")
    target = InvestigationAuthority("alice", "research")
    resolve_writable_investigation_stream(target)
    with connect_write(path, purpose="test/interview-reconcile") as con:
        create_project(
            con, alice, project_id="p", title="P", topic_description=None,
            deliverable_id=None, interview_guide={},
        )
        create_interview(
            con, alice, project_id="p", interview_id="i",
            informant_handle=None, informant_email=None,
        )
        record_consent(con, alice, interview_id="i", granted=True)
        bind_project(con, alice, project_id="p", investigation=target)
        append_turn(
            con, alice, interview_id="i", role="informant", text="Grounded answer",
            question_id="q1",
        )
        with pytest.raises(ValueError, match="not found"):
            reconcile_answer_derivations(con, bob, interview_id="i")
        result = reconcile_answer_derivations(con, alice, interview_id="i")
        assert (result.attempted, result.completed, result.pending, result.failed) == (1, 1, 0, 0)
        state = con.execute(
            "SELECT delivery_state, document_id, admission_receipt_id, event_id "
            "FROM interview_answer_derivations"
        ).fetchone()
        assert state[0] == "completed"
        assert all(isinstance(value, str) and value for value in state[1:])
        document = read_document(con, target, state[1])
        assert document["raw_text"] == "Grounded answer"
        assert document["owner_user_id"] == "alice"
        assert con.execute(
            "SELECT text FROM chunks WHERE document_id = ?", [state[1]]
        ).fetchone() == ("Grounded answer",)
        with pytest.raises(ClaimConflict, match="attribute consent"):
            record_canonical_claim(
                con, alice, interview_id="i", question_id="q1",
                source_document_id=state[1], text="Subject founded the laboratory",
                about_subject=True, subject_ref="person:subject-1",
                speaker_is_subject=False, confidence=0.7,
            )
        record_consent_events(
            con, alice, interview_id="i", scopes={"attribute"}, granted=True,
            actor_kind="operator_witness",
        )
        claim = record_canonical_claim(
            con, alice, interview_id="i", question_id="q1",
            source_document_id=state[1], text="Subject founded the laboratory",
            about_subject=True, subject_ref="person:subject-1",
            speaker_is_subject=False, confidence=0.7,
        )
        assert claim.is_third_party is True
        assert claim.source_document_id == state[1]
        assert record_canonical_claim(
            con, alice, interview_id="i", question_id="q1",
            source_document_id=state[1], text="Subject founded the laboratory",
            about_subject=True, subject_ref="person:subject-1",
            speaker_is_subject=False, confidence=0.7,
        ).claim_id == claim.claim_id
        con.execute("BEGIN TRANSACTION")
        nested = record_canonical_claim(
            con, alice, interview_id="i", question_id="q1",
            source_document_id=state[1], text="Nested transaction claim",
            about_subject=True, subject_ref="person:subject-1",
            speaker_is_subject=False, confidence=0.5,
        )
        con.execute("ROLLBACK")
        with pytest.raises(ValueError, match="not found"):
            get_canonical_claim(con, alice, claim_id=nested.claim_id)
        unknown_peer = record_canonical_claim(
            con, alice, interview_id="i", question_id="q1",
            source_document_id=state[1], text="The laboratory was founded by the subject",
            about_subject=True, subject_ref="person:subject-1",
            speaker_is_subject=False, confidence=0.6,
        )
        unknown_cluster = record_corroboration(
            con, alice, project_id="p", canonical_claim_id=claim.claim_id,
            members=[
                CorroborationMember(claim.claim_id, "attests"),
                CorroborationMember(unknown_peer.claim_id, "attests"),
            ],
        )
        assert unknown_cluster.label == "single_sourced"
        assert unknown_cluster.independent_attesters == 1
        create_interview(
            con, alice, project_id="p", interview_id="i2",
            informant_handle=None, informant_email=None,
        )
        record_consent(con, alice, interview_id="i2", granted=True)
        record_consent_events(
            con, alice, interview_id="i2", scopes={"attribute"}, granted=True,
            actor_kind="operator_witness",
        )
        append_turn(
            con, alice, interview_id="i2", role="informant",
            text="Independent grounded answer", question_id="q1",
        )
        assert reconcile_answer_derivations(con, alice, interview_id="i2").completed == 1
        second_document_id = con.execute(
            "SELECT document_id FROM interview_answer_derivations "
            "WHERE account_digest = ? AND interview_id = 'i2' AND question_id = 'q1'",
            [alice.account_digest],
        ).fetchone()[0]
        origin_a = record_canonical_claim(
            con, alice, interview_id="i", question_id="q1",
            source_document_id=state[1], text="Direct witness A confirmed the founding",
            about_subject=True, subject_ref="person:subject-1",
            speaker_is_subject=False, independence_key="origin:witness-a", confidence=0.6,
        )
        origin_b = record_canonical_claim(
            con, alice, interview_id="i2", question_id="q1",
            source_document_id=second_document_id,
            text="Direct witness B confirmed the founding",
            about_subject=True, subject_ref="person:subject-1",
            speaker_is_subject=False, independence_key="origin:witness-b", confidence=0.6,
        )
        confirmed = record_corroboration(
            con, alice, project_id="p", canonical_claim_id=origin_a.claim_id,
            members=[
                CorroborationMember(origin_a.claim_id, "attests"),
                CorroborationMember(origin_b.claim_id, "attests"),
            ],
        )
        assert confirmed.label == "multiply_attested"
        assert confirmed.independent_attesters == 2
        credit_a = record_attribution(
            con, alice, project_id="p", interview_id="i", command_id="credit-a",
            contributor_ref="contributor:ada", display_label="Ada",
            evidence_basis="self_reported", evidence_ref="answer:q1",
        )
        assert record_attribution(
            con, alice, project_id="p", interview_id="i", command_id="credit-a",
            contributor_ref="contributor:ada", display_label="Ada",
            evidence_basis="self_reported", evidence_ref="answer:q1",
        ).event_id == credit_a.event_id
        with pytest.raises(ContributorAttributionConflict, match="active"):
            record_attribution(
                con, alice, project_id="p", interview_id="i", command_id="credit-conflict",
                contributor_ref="contributor:other", display_label="Other",
                evidence_basis="operator_verified", evidence_ref="operator:evidence",
            )
        credit_b = record_attribution(
            con, alice, project_id="p", interview_id="i2", command_id="credit-b",
            contributor_ref="contributor:grace", display_label="Grace",
            evidence_basis="operator_verified", evidence_ref="operator:witness-log",
        )
        con.execute("BEGIN TRANSACTION")
        nested_draft = create_private_draft(
            con, alice, project_id="p", command_id="draft-nested", title="Private evidence",
            claim_ids=[origin_a.claim_id, origin_b.claim_id],
        )
        con.execute("ROLLBACK")
        with pytest.raises(ValueError, match="not found"):
            get_private_draft(con, alice, draft_id=nested_draft.draft_id)
        durable_draft = create_private_draft(
            con, alice, project_id="p", command_id="draft-1", title="Private evidence",
            claim_ids=[origin_a.claim_id, origin_b.claim_id],
        )
        assert durable_draft.body_html.startswith("<!doctype html>")
        assert durable_draft.manifest["claims"][0]["claim_id"] == origin_a.claim_id
        assert durable_draft.manifest["claims"][0]["contributor"]["event_id"] == credit_a.event_id
        assert "Contributor credit Ada" in durable_draft.body_html
        assert durable_draft.manifest["claims"][0]["custody"]["source_receipt_id"]
        assert {event["scope"] for event in durable_draft.manifest["claims"][0][
            "consent_evidence"
        ]} == {"record", "attribute"}
        plain_credited_claim = record_canonical_claim(
            con, alice, interview_id="i", question_id="q1",
            source_document_id=state[1], text="The laboratory opened its archive",
            about_subject=False, subject_ref=None, speaker_is_subject=False, confidence=0.5,
        )
        plain_credited_draft = create_private_draft(
            con, alice, project_id="p", command_id="draft-plain-credit",
            title="Plain credited evidence", claim_ids=[plain_credited_claim.claim_id],
        )
        assert plain_credited_draft.manifest["claims"][0]["contributor"] is not None
        proposal = create_proposal(
            con, alice, project_id="p", draft_id=durable_draft.draft_id,
            mutation_key="proposal-1", base_revision=0,
            instruction="Create a concise narrative while retaining every evidence label.",
            provider_id="openai", model_id="gpt-test", projected_max_cents=40,
            approved_ceiling_cents=50,
            allowed_model_pairs=frozenset({("openai", "gpt-test")}),
        )
        assert (proposal.revision, proposal.state) == (1, "staged")

        assert create_proposal(
            con, alice, project_id="p", draft_id=durable_draft.draft_id,
            mutation_key="proposal-1", base_revision=0,
            instruction="Create a concise narrative while retaining every evidence label.",
            provider_id="openai", model_id="gpt-test", projected_max_cents=40,
            approved_ceiling_cents=50,
            allowed_model_pairs=frozenset({("openai", "gpt-test")}),
        ).proposal_id == proposal.proposal_id
        with pytest.raises(CompositionProposalConflict, match="different input"):
            create_proposal(
                con, alice, project_id="p", draft_id=durable_draft.draft_id,
                mutation_key="proposal-1", base_revision=0, instruction="Changed",
                provider_id="openai", model_id="gpt-test", projected_max_cents=40,
                approved_ceiling_cents=50,
                allowed_model_pairs=frozenset({("openai", "gpt-test")}),
            )
        with pytest.raises(CompositionProposalConflict, match="stale"):
            create_proposal(
                con, alice, project_id="p", draft_id=durable_draft.draft_id,
                mutation_key="proposal-stale", base_revision=0, instruction="Second",
                provider_id="openai", model_id="gpt-test", projected_max_cents=40,
                approved_ceiling_cents=50,
                allowed_model_pairs=frozenset({("openai", "gpt-test")}),
            )
        with pytest.raises(ValueError, match="ceiling"):
            create_proposal(
                con, alice, project_id="p", draft_id=durable_draft.draft_id,
                mutation_key="proposal-over", base_revision=1, instruction="Over budget",
                provider_id="openai", model_id="gpt-test", projected_max_cents=51,
                approved_ceiling_cents=50,
                allowed_model_pairs=frozenset({("openai", "gpt-test")}),
            )
        disputed = record_canonical_claim(
            con, alice, interview_id="i", question_id="q1",
            source_document_id=state[1], text="The laboratory opened in 1999",
            about_subject=True, subject_ref="person:subject-1",
            speaker_is_subject=False, confidence=0.5,
        )
        counterclaim = record_canonical_claim(
            con, alice, interview_id="i2", question_id="q1",
            source_document_id=second_document_id, text="The laboratory did not open in 1999",
            about_subject=True, subject_ref="person:subject-1",
            speaker_is_subject=False, confidence=0.5,
        )
        record_corroboration(
            con, alice, project_id="p", canonical_claim_id=disputed.claim_id,
            members=[
                CorroborationMember(disputed.claim_id, "attests"),
                CorroborationMember(counterclaim.claim_id, "contradicts"),
            ],
        )
        disputed_draft = create_private_draft(
            con, alice, project_id="p", command_id="draft-disputed", title="Disputed evidence",
            claim_ids=[disputed.claim_id, counterclaim.claim_id],
        )
        assert "Disputed" in disputed_draft.body_html
        revocation = revoke_attribution(
            con, alice, project_id="p", interview_id="i", command_id="revoke-credit-a",
            target_event_id=credit_a.event_id,
        )
        assert revoke_attribution(
            con, alice, project_id="p", interview_id="i", command_id="revoke-credit-a",
            target_event_id=credit_a.event_id,
        ) == revocation
        assert get_active_attribution(
            con, alice, project_id="p", interview_id="i"
        ) is None
        historical_replay = record_attribution(
            con, alice, project_id="p", interview_id="i", command_id="credit-a",
            contributor_ref="contributor:ada", display_label="Ada",
            evidence_basis="self_reported", evidence_ref="answer:q1",
        )
        assert historical_replay.event_id == credit_a.event_id
        assert historical_replay.active is False
        rebound = record_attribution(
            con, alice, project_id="p", interview_id="i", command_id="credit-a-v2",
            contributor_ref="contributor:ada", display_label="Ada Lovelace",
            evidence_basis="contractual_record", evidence_ref="contract:credit-v2",
        )
        assert rebound.event_id != credit_a.event_id
        assert credit_b.event_id
        assert con.execute(
            "SELECT count(*) FROM information_schema.tables WHERE table_schema = 'main' "
            "AND table_name IN ('speak_contributors','speak_accruals','speak_interview_grades')"
        ).fetchone() == (0,)
        record_consent_events(
            con, alice, interview_id="i", scopes={"attribute"}, granted=False,
            actor_kind="operator_witness",
        )
        with pytest.raises(CompositionConflict, match="attribute consent"):
            get_private_draft(con, alice, draft_id=durable_draft.draft_id)
        with pytest.raises(CompositionConflict, match="attribute consent"):
            get_private_draft(con, alice, draft_id=plain_credited_draft.draft_id)
        with pytest.raises(CompositionConflict, match="attribute consent"):
            get_proposal(con, alice, proposal_id=proposal.proposal_id)
        with pytest.raises(ContributorAttributionConflict, match="consent"):
            record_attribution(
                con, alice, project_id="p", interview_id="i", command_id="credit-a-v2",
                contributor_ref="contributor:ada", display_label="Ada Lovelace",
                evidence_basis="contractual_record", evidence_ref="contract:credit-v2",
            )
        assert list_canonical_claims(con, bob, project_id="p") == []
        assert reconcile_answer_derivations(con, alice, interview_id="i").attempted == 0
        # Simulate a crash after the event append but before its DB acknowledgement.
        con.execute(
            "UPDATE interview_answer_derivations SET delivery_state = 'processing'"
        )
        replayed_ack = reconcile_answer_derivations(con, alice, interview_id="i")
        assert (replayed_ack.attempted, replayed_ack.completed) == (1, 1)
    events = [row for row in trajectory_authorized(target) if row.get("event_id") == state[3]]
    assert len(events) == 1
    assert events[0]["document_id"] == state[1]


def test_reconciler_recovers_after_event_append_failure_without_duplicate_document(
    tmp_path, monkeypatch
) -> None:
    monkeypatch.setenv("ANTIEK_RESEARCH_EVENTS_DIR", str(tmp_path / "events"))
    path = str(tmp_path / "event-retry.duckdb")
    init_database_at_path(path)
    authority = InterviewAccountAuthority("alice")
    target = InvestigationAuthority("alice", "research")
    resolve_writable_investigation_stream(target)
    import substrate.interviews.reconcile as reconcile_module

    original_append = reconcile_module.append_event_once_authorized
    with connect_write(path, purpose="test/interview-event-retry") as con:
        create_project(
            con, authority, project_id="p", title="P", topic_description=None,
            deliverable_id=None, interview_guide={},
        )
        create_interview(
            con, authority, project_id="p", interview_id="i",
            informant_handle=None, informant_email=None,
        )
        record_consent(con, authority, interview_id="i", granted=True)
        bind_project(con, authority, project_id="p", investigation=target)
        append_turn(
            con, authority, interview_id="i", role="informant", text="Retry answer",
            question_id="q1",
        )

        def fail_append(*args, **kwargs):
            raise OSError("simulated event filesystem failure")

        monkeypatch.setattr(
            "substrate.interviews.reconcile.append_event_once_authorized", fail_append
        )
        first = reconcile_answer_derivations(con, authority, interview_id="i")
        assert (first.completed, first.pending) == (0, 1)
        row = con.execute(
            "SELECT delivery_state, document_id, event_json, last_error_code "
            "FROM interview_answer_derivations"
        ).fetchone()
        assert row[0] == "processing"
        assert row[1] and row[2]
        assert row[3] == "OSError"
        assert con.execute(
            "SELECT attempt_count FROM interview_answer_derivations"
        ).fetchone() == (1,)
        assert con.execute("SELECT count(*) FROM documents").fetchone()[0] == 1
        monkeypatch.setattr(
            "substrate.interviews.reconcile.append_event_once_authorized", original_append
        )
        second = reconcile_answer_derivations(con, authority, interview_id="i")
        assert (second.completed, second.pending) == (1, 0)
        assert con.execute("SELECT count(*) FROM documents").fetchone()[0] == 1
        assert con.execute(
            "SELECT attempt_count FROM interview_answer_derivations"
        ).fetchone() == (2,)


def test_reconciler_fails_closed_on_answer_hash_corruption(tmp_path, monkeypatch) -> None:
    monkeypatch.setenv("ANTIEK_RESEARCH_EVENTS_DIR", str(tmp_path / "events"))
    path = str(tmp_path / "corrupt-reconcile.duckdb")
    init_database_at_path(path)
    authority = InterviewAccountAuthority("alice")
    target = InvestigationAuthority("alice", "research")
    resolve_writable_investigation_stream(target)
    with connect_write(path, purpose="test/interview-reconcile-corrupt") as con:
        create_project(
            con, authority, project_id="p", title="P", topic_description=None,
            deliverable_id=None, interview_guide={},
        )
        create_interview(
            con, authority, project_id="p", interview_id="i",
            informant_handle=None, informant_email=None,
        )
        record_consent(con, authority, interview_id="i", granted=True)
        bind_project(con, authority, project_id="p", investigation=target)
        append_turn(
            con, authority, interview_id="i", role="informant", text="Original",
            question_id="q1",
        )
        con.execute(
            "UPDATE interview_answer_derivations SET answer_sha256 = ?",
            ["0" * 64],
        )
        result = reconcile_answer_derivations(con, authority, interview_id="i")
        assert (result.completed, result.failed) == (0, 1)
        assert con.execute("SELECT count(*) FROM documents").fetchone()[0] == 0
        assert reconcile_answer_derivations(
            con, authority, interview_id="i"
        ).failed == 0


def test_reconciler_does_not_write_when_event_persistence_is_disabled(
    tmp_path, monkeypatch
) -> None:
    monkeypatch.setenv("ANTIEK_RESEARCH_EVENTS_DIR", str(tmp_path / "events"))
    path = str(tmp_path / "events-disabled.duckdb")
    init_database_at_path(path)
    authority = InterviewAccountAuthority("alice")
    target = InvestigationAuthority("alice", "research")
    resolve_writable_investigation_stream(target)
    with connect_write(path, purpose="test/interview-events-disabled") as con:
        create_project(
            con, authority, project_id="p", title="P", topic_description=None,
            deliverable_id=None, interview_guide={},
        )
        create_interview(
            con, authority, project_id="p", interview_id="i",
            informant_handle=None, informant_email=None,
        )
        record_consent(con, authority, interview_id="i", granted=True)
        bind_project(con, authority, project_id="p", investigation=target)
        append_turn(
            con, authority, interview_id="i", role="informant", text="No event, no doc",
            question_id="q1",
        )
        monkeypatch.setenv("ANTIEK_EVENTS_DISABLED", "1")
        result = reconcile_answer_derivations(con, authority, interview_id="i")
        assert (result.completed, result.pending, result.failed) == (0, 1, 0)
        assert con.execute("SELECT count(*) FROM documents").fetchone()[0] == 0
        assert con.execute(
            "SELECT delivery_state, last_error_code FROM interview_answer_derivations"
        ).fetchone() == ("pending", "RuntimeError")


def test_reconciler_rechecks_current_consent_before_document_delivery(
    tmp_path, monkeypatch
) -> None:
    monkeypatch.setenv("ANTIEK_RESEARCH_EVENTS_DIR", str(tmp_path / "events"))
    path = str(tmp_path / "consent-recheck.duckdb")
    init_database_at_path(path)
    authority = InterviewAccountAuthority("alice")
    target = InvestigationAuthority("alice", "research")
    resolve_writable_investigation_stream(target)
    with connect_write(path, purpose="test/interview-consent-recheck") as con:
        create_project(
            con, authority, project_id="p", title="P", topic_description=None,
            deliverable_id=None, interview_guide={},
        )
        create_interview(
            con, authority, project_id="p", interview_id="i",
            informant_handle=None, informant_email=None,
        )
        record_consent(con, authority, interview_id="i", granted=True)
        bind_project(con, authority, project_id="p", investigation=target)
        append_turn(
            con, authority, interview_id="i", role="informant", text="Consent-bound",
            question_id="q1",
        )
        record_consent(con, authority, interview_id="i", granted=False)
        blocked = reconcile_answer_derivations(con, authority, interview_id="i")
        assert (blocked.completed, blocked.pending) == (0, 1)
        assert con.execute("SELECT count(*) FROM documents").fetchone()[0] == 0
        assert con.execute(
            "SELECT last_error_code FROM interview_answer_derivations"
        ).fetchone() == ("DerivationConsentBlocked",)
        record_consent(con, authority, interview_id="i", granted=True)
        assert reconcile_answer_derivations(
            con, authority, interview_id="i"
        ).completed == 1


def test_reconciler_rejects_resealed_event_that_crosses_document_identity(
    tmp_path, monkeypatch
) -> None:
    import hashlib
    import json

    monkeypatch.setenv("ANTIEK_RESEARCH_EVENTS_DIR", str(tmp_path / "events"))
    path = str(tmp_path / "event-corrupt.duckdb")
    init_database_at_path(path)
    authority = InterviewAccountAuthority("alice")
    target = InvestigationAuthority("alice", "research")
    resolve_writable_investigation_stream(target)
    import substrate.interviews.reconcile as reconcile_module

    original_append = reconcile_module.append_event_once_authorized
    with connect_write(path, purpose="test/interview-event-corrupt") as con:
        create_project(
            con, authority, project_id="p", title="P", topic_description=None,
            deliverable_id=None, interview_guide={},
        )
        create_interview(
            con, authority, project_id="p", interview_id="i",
            informant_handle=None, informant_email=None,
        )
        record_consent(con, authority, interview_id="i", granted=True)
        bind_project(con, authority, project_id="p", investigation=target)
        append_turn(
            con, authority, interview_id="i", role="informant", text="Event-bound",
            question_id="q1",
        )
        monkeypatch.setattr(
            "substrate.interviews.reconcile.append_event_once_authorized",
            lambda *args, **kwargs: (_ for _ in ()).throw(OSError("hold")),
        )
        reconcile_answer_derivations(con, authority, interview_id="i")
        raw = con.execute(
            "SELECT event_json FROM interview_answer_derivations"
        ).fetchone()[0]
        envelope = json.loads(raw)
        envelope["document_id"] = "foreign-document"
        corrupt = json.dumps(envelope, sort_keys=True, separators=(",", ":"))
        con.execute(
            "UPDATE interview_answer_derivations SET event_json = ?, event_fingerprint = ?",
            [corrupt, hashlib.sha256(corrupt.encode()).hexdigest()],
        )
        monkeypatch.setattr(
            "substrate.interviews.reconcile.append_event_once_authorized", original_append
        )
        result = reconcile_answer_derivations(con, authority, interview_id="i")
        assert result.failed == 1
        assert con.execute(
            "SELECT delivery_state, last_error_code FROM interview_answer_derivations"
        ).fetchone() == ("failed", "DerivationConflict")


def test_authenticated_operator_routes_cannot_read_other_account_interview(tmp_path, monkeypatch) -> None:
    from interfaces.research.api.app import create_app
    from substrate.auth import mint_magic_link_token

    path = str(tmp_path / "http.duckdb")
    monkeypatch.setenv("ANTIEK_DB_PATH", path)
    monkeypatch.setenv("ANTIEK_DUCKDB_PATH", path)
    monkeypatch.setenv("ANTIEK_AUTH_SECRET", "interview-http-" + "x" * 48)
    monkeypatch.setenv("ANTIEK_COOKIE_INSECURE", "1")
    monkeypatch.setenv("ANTIEK_OPERATOR_EMAIL", "alice@example.test,bob@example.test")
    monkeypatch.setenv("ANTIEK_RESEARCH_EVENTS_DIR", str(tmp_path / "events"))
    app = create_app(register_wrestling=False, register_providers=False)
    alice, bob = TestClient(app), TestClient(app)
    for email, client in (("alice@example.test", alice), ("bob@example.test", bob)):
        assert client.get(
            f"/auth/callback?token={mint_magic_link_token(email)}", follow_redirects=False
        ).status_code == 302

    created = alice.post("/interview-projects", json={"title": "Private"})
    assert created.status_code == 201, created.text
    invited = alice.post(
        "/interviews", json={"project_id": created.json()["project_id"], "informant_handle": "Ada"}
    )
    assert invited.status_code == 201, invited.text
    interview_id = invited.json()["interview_id"]

    assert alice.get(f"/interviews/{interview_id}").status_code == 200
    assert bob.get(f"/interviews/{interview_id}").status_code == 404
    assert bob.post(
        f"/interviews/{interview_id}/turn", json={"role": "informant", "text": "intrusion"}
    ).status_code == 404
    assert bob.get(f"/speak/interviews/{interview_id}").status_code == 404
    assert bob.get("/speak/projects").status_code == 404

    empty_margin = alice.get(f"/interviews/{interview_id}/margin")
    assert empty_margin.status_code == 200
    assert empty_margin.headers["cache-control"] == "no-store"
    assert empty_margin.json()["body"] == ""
    assert empty_margin.json()["revision"] == 0
    saved = alice.put(
        f"/interviews/{interview_id}/margin",
        json={"schema_version": 1, "base_revision": 0,
              "mutation_key": "margin-1", "body": "Private observation"},
    )
    assert saved.status_code == 200, saved.text
    assert saved.json()["revision"] == 1
    replayed = alice.put(
        f"/interviews/{interview_id}/margin",
        json={"schema_version": 1, "base_revision": 0,
              "mutation_key": "margin-1", "body": "Private observation"},
    )
    assert replayed.status_code == 200
    assert replayed.json()["replayed"] is True
    stale = alice.put(
        f"/interviews/{interview_id}/margin",
        json={"schema_version": 1, "base_revision": 0,
              "mutation_key": "margin-2", "body": "Stale"},
    )
    assert stale.status_code == 409
    assert bob.get(f"/interviews/{interview_id}/margin").status_code == 404
    assert bob.put(
        f"/interviews/{interview_id}/margin",
        json={"schema_version": 1, "base_revision": 0,
              "mutation_key": "intrusion", "body": "Intrusion"},
    ).status_code == 404

    assert alice.post(
        f"/interviews/{interview_id}/turn",
        json={"role": "interviewer", "text": "Private first question"},
    ).status_code == 202
    issued = alice.post(
        f"/interviews/{interview_id}/invites",
        json={"required_scopes": ["record", "attribute"]},
    )
    assert issued.status_code == 201, issued.text
    invite_path = issued.json()["link"]
    landing = bob.get(invite_path)
    assert landing.status_code == 200
    assert landing.headers["cache-control"] == "no-store"
    assert landing.json()["interview_id"] == interview_id
    assert "informant_email" not in landing.json()
    assert landing.json()["transcript"] == []
    blocked = bob.post(
        f"{invite_path}/answer",
        json={"question_id": "q1", "transcript": "answer", "duration_seconds": 1},
    )
    assert blocked.status_code in {400, 403, 409}
    attribute = bob.post(f"{invite_path}/consent", json={"scopes": ["attribute"]})
    assert attribute.status_code == 200
    assert attribute.json()["granted"] == ["attribute"]
    assert bob.post(
        f"{invite_path}/answer",
        json={"question_id": "q1", "transcript": "answer", "duration_seconds": 1},
    ).status_code == 403
    consent = bob.post(f"{invite_path}/consent", json={"scopes": ["record"]})
    assert consent.status_code == 200, consent.text
    assert consent.json()["granted"] == ["attribute", "record"]
    after_consent = bob.get(invite_path).json()
    assert after_consent["granted_consent_scopes"] == ["attribute", "record"]
    assert after_consent["transcript"][0]["text"] == "Private first question"
    bound = alice.put(
        f"/interviews/{interview_id}/derivation-target",
        json={"investigation_id": "private-research"},
    )
    assert bound.status_code == 200, bound.text
    assert bound.json()["investigation_id"] == "private-research"
    assert bob.put(
        f"/interviews/{interview_id}/derivation-target",
        json={"investigation_id": "intrusion"},
    ).status_code == 404
    answer = bob.post(
        f"{invite_path}/answer",
        json={"question_id": "q1", "transcript": "answer", "duration_seconds": 1},
    )
    assert answer.status_code == 201, answer.text
    assert answer.json()["skipped_reason"] == "canonical_derivation_staged"
    pending_derivations = alice.get(f"/interviews/{interview_id}/derivations")
    assert pending_derivations.status_code == 200
    assert pending_derivations.json()[0]["delivery_state"] == "pending"
    assert bob.get(f"/interviews/{interview_id}/derivations").status_code == 404
    assert bob.post(
        f"/interviews/{interview_id}/derivations/reconcile"
    ).status_code == 404
    reconciled = alice.post(f"/interviews/{interview_id}/derivations/reconcile")
    assert reconciled.status_code == 200, reconciled.text
    assert reconciled.json()["completed"] == 1
    delivered = alice.get(f"/interviews/{interview_id}/derivations").json()[0]
    assert delivered["delivery_state"] == "completed"
    assert delivered["document_id"]
    missing_grounding = alice.post(
        f"/speak/interviews/{interview_id}/claims",
        json={"text": "Explicit claim"},
    )
    assert missing_grounding.status_code == 422
    claim_payload = {
        "text": "The subject founded the laboratory",
        "question_id": "q1",
        "source_document_id": delivered["document_id"],
        "about_subject": True,
        "subject_ref": "person:subject-1",
        "speaker_is_subject": False,
        "independence_key": "origin:direct-witness-ada",
        "confidence": 0.7,
    }
    canonical_claim = alice.post(
        f"/speak/interviews/{interview_id}/claims", json=claim_payload
    )
    assert canonical_claim.status_code == 201, canonical_claim.text
    assert canonical_claim.json()["is_third_party"] is True
    assert canonical_claim.json()["source_document_id"] == delivered["document_id"]
    assert canonical_claim.json()["independence_key"] == "origin:direct-witness-ada"
    assert alice.post(
        f"/speak/interviews/{interview_id}/claims", json=claim_payload
    ).json()["claim_id"] == canonical_claim.json()["claim_id"]
    assert bob.post(
        f"/speak/interviews/{interview_id}/claims", json=claim_payload
    ).status_code == 404
    listed = alice.get(f"/speak/projects/{created.json()['project_id']}/claims")
    assert listed.status_code == 200, listed.text
    assert listed.json()["claims"] == [
        {
            "claim_id": canonical_claim.json()["claim_id"],
            "interview_id": interview_id,
            "question_id": "q1",
            "source_document_id": delivered["document_id"],
            "text": "The subject founded the laboratory",
            "about_subject": True,
            "is_third_party": True,
            "subject_ref": "person:subject-1",
            "speaker_is_subject": False,
            "independence_key": "origin:direct-witness-ada",
            "verification": "unverified",
            "confidence": 0.7,
        }
    ]
    assert bob.get(
        f"/speak/projects/{created.json()['project_id']}/claims"
    ).status_code == 404
    cluster_payload = {
        "canonical_claim_id": canonical_claim.json()["claim_id"],
        "members": [{"claim_id": canonical_claim.json()["claim_id"], "stance": "attests"}],
    }
    cluster = alice.post(
        f"/speak/projects/{created.json()['project_id']}/claim-clusters",
        json=cluster_payload,
    )
    assert cluster.status_code == 201, cluster.text
    assert cluster.json()["label"] == "single_sourced"
    assert cluster.json()["independent_attesters"] == 1
    assert alice.post(
        f"/speak/projects/{created.json()['project_id']}/claim-clusters",
        json=cluster_payload,
    ).json()["cluster_id"] == cluster.json()["cluster_id"]
    assert bob.post(
        f"/speak/projects/{created.json()['project_id']}/claim-clusters",
        json=cluster_payload,
    ).status_code == 404
    contributor_path = (
        f"/speak/projects/{created.json()['project_id']}/interviews/{interview_id}/"
        "contributor-attribution"
    )
    contributor_payload = {
        "contributor_ref": "contributor:ada",
        "display_label": "Ada",
        "evidence_basis": "self_reported",
        "evidence_ref": "answer:q1",
    }
    contributor = alice.post(
        contributor_path, json=contributor_payload,
        headers={"Idempotency-Key": "credit-http-1"},
    )
    assert contributor.status_code == 201, contributor.text
    assert contributor.json()["display_label"] == "Ada"
    assert contributor.json()["active"] is True
    assert alice.post(
        contributor_path, json=contributor_payload,
        headers={"Idempotency-Key": "credit-http-1"},
    ).json()["event_id"] == contributor.json()["event_id"]
    assert alice.post(
        contributor_path, json={**contributor_payload, "display_label": "Changed"},
        headers={"Idempotency-Key": "credit-http-1"},
    ).status_code == 409
    assert bob.post(
        contributor_path, json=contributor_payload,
        headers={"Idempotency-Key": "foreign-credit"},
    ).status_code == 404
    current_contributor = alice.get(contributor_path)
    assert current_contributor.status_code == 200
    assert current_contributor.headers["cache-control"] == "no-store"
    injection_payload = {
        **claim_payload,
        "text": "Evidence <script>alert('unsafe')</script>",
        "independence_key": None,
    }
    injection_claim = alice.post(
        f"/speak/interviews/{interview_id}/claims", json=injection_payload
    )
    assert injection_claim.status_code == 201, injection_claim.text
    draft_payload = {
        "title": "Private <Evidence>",
        "claim_ids": [canonical_claim.json()["claim_id"], injection_claim.json()["claim_id"]],
    }
    draft = alice.post(
        f"/speak/projects/{created.json()['project_id']}/html-drafts",
        json=draft_payload, headers={"Idempotency-Key": "private-draft-1"},
    )
    assert draft.status_code == 201, draft.text
    assert draft.headers["cache-control"] == "no-store"
    assert draft.json()["visibility"] == "private"
    assert "<script>" not in draft.json()["html"]
    assert "&lt;script&gt;" in draft.json()["html"]
    assert "Unverified interview claim" in draft.json()["html"]
    assert canonical_claim.json()["claim_id"] in draft.json()["html"]
    assert "question q1" in draft.json()["html"]
    assert "Corroboration cluster" in draft.json()["html"]
    assert draft.json()["manifest"]["claims"][0]["custody"]["source_receipt_id"]
    assert draft.json()["manifest"]["claims"][0]["contributor"]["event_id"] == (
        contributor.json()["event_id"]
    )
    assert "Contributor credit Ada" in draft.json()["html"]
    replayed_draft = alice.post(
        f"/speak/projects/{created.json()['project_id']}/html-drafts",
        json=draft_payload, headers={"Idempotency-Key": "private-draft-1"},
    )
    assert replayed_draft.status_code == 201
    for frozen_field in (
        "draft_id", "manifest", "manifest_sha256", "html", "body_sha256", "visibility"
    ):
        assert replayed_draft.json()[frozen_field] == draft.json()[frozen_field]
    assert alice.post(
        f"/speak/projects/{created.json()['project_id']}/html-drafts",
        json={**draft_payload, "title": "Changed"},
        headers={"Idempotency-Key": "private-draft-1"},
    ).status_code == 409
    fetched_draft = alice.get(
        f"/speak/projects/{created.json()['project_id']}/html-drafts/"
        f"{draft.json()['draft_id']}"
    )
    assert fetched_draft.status_code == 200
    assert fetched_draft.headers["cache-control"] == "no-store"
    assert fetched_draft.json()["body_sha256"] == draft.json()["body_sha256"]
    proposal_path = (
        f"/speak/projects/{created.json()['project_id']}/html-drafts/"
        f"{draft.json()['draft_id']}/ai-proposals"
    )
    proposal_payload = {
        "base_revision": 0,
        "instruction": "Draft connective prose without changing evidence labels.",
        "provider_id": "openai", "model_id": "gpt-test",
        "projected_max_cents": 40, "approved_ceiling_cents": 50,
    }
    registered = alice.post(
        "/settings/models/register",
        json={"provider_id": "openai", "model_id": "gpt-test"},
    )
    assert registered.status_code == 200, registered.text
    staged = alice.post(
        proposal_path, json=proposal_payload,
        headers={"Idempotency-Key": "proposal-http-1"},
    )
    assert staged.status_code == 201, staged.text
    assert staged.headers["cache-control"] == "no-store"
    assert staged.json()["state"] == "staged"
    assert staged.json()["source_manifest_sha256"] == draft.json()["manifest_sha256"]
    assert alice.post(
        proposal_path, json=proposal_payload,
        headers={"Idempotency-Key": "proposal-http-1"},
    ).json()["proposal_id"] == staged.json()["proposal_id"]
    changed_proposal = alice.post(
        proposal_path, json={**proposal_payload, "instruction": "Changed"},
        headers={"Idempotency-Key": "proposal-http-1"},
    )
    assert changed_proposal.status_code == 409
    assert changed_proposal.headers["cache-control"] == "no-store"
    unknown_model = alice.post(
        proposal_path, json={**proposal_payload, "model_id": "unknown"},
        headers={"Idempotency-Key": "proposal-unknown"},
    )
    assert unknown_model.status_code == 400
    assert unknown_model.headers["cache-control"] == "no-store"
    oversized_cost = alice.post(
        proposal_path, json={**proposal_payload, "projected_max_cents": 1_000_000_001,
                             "approved_ceiling_cents": 1_000_000_001},
        headers={"Idempotency-Key": "proposal-overflow"},
    )
    assert oversized_cost.status_code == 400
    with connect_write(path, purpose="test/proposal-write-count", log_on_close=False) as con:
        writes_before_denial = con.execute("SELECT count(*) FROM write_log").fetchone()[0]
    foreign_proposal = bob.post(
        proposal_path, json=proposal_payload,
        headers={"Idempotency-Key": "foreign-proposal"},
    )
    assert foreign_proposal.status_code == 404
    assert foreign_proposal.headers["cache-control"] == "no-store"
    with connect_write(path, purpose="test/proposal-write-count", log_on_close=False) as con:
        assert con.execute("SELECT count(*) FROM write_log").fetchone()[0] == writes_before_denial
    fetched_proposal = alice.get(proposal_path + "/" + staged.json()["proposal_id"])
    assert fetched_proposal.status_code == 200
    assert fetched_proposal.headers["cache-control"] == "no-store"
    execution_path = proposal_path + "/" + staged.json()["proposal_id"] + "/execute"
    disabled_execution = alice.post(
        execution_path, headers={"Idempotency-Key": "execute-http-1"}
    )
    assert disabled_execution.status_code == 503
    assert disabled_execution.headers["cache-control"] == "no-store"

    class HttpCompositionExecutor:
        route_sha256 = "8" * 64

        def __init__(self) -> None:
            self.calls = 0

        def execute(self, *, prompt, provider, model, idempotency_key):
            self.calls += 1
            return ProviderCompositionResult(
                raw_json=json.dumps({
                    "schema_version": 1, "title": "Private synthesis",
                    "lead": "Evidence-bound draft for review.",
                    "units": [{"claim_ids": [canonical_claim.json()["claim_id"]],
                               "prose": "The evidence remains explicitly unverified."}],
                }),
                provider=provider, model=model, actual_cents=5,
                dispatch_event_id="dispatch-http-fake",
                prompt_sha256=hashlib.sha256(prompt.encode()).hexdigest(),
            )

    http_executor = HttpCompositionExecutor()
    app.state.composition_execution_enabled = True
    app.state.composition_executor = http_executor
    executed_http = alice.post(
        execution_path, headers={"Idempotency-Key": "execute-http-1"}
    )
    assert executed_http.status_code == 200, executed_http.text
    assert executed_http.headers["cache-control"] == "no-store"
    assert executed_http.json()["state"] == "ready_for_review"
    assert "Unverified interview claim" in executed_http.json()["html"]
    assert http_executor.calls == 1
    assert alice.post(
        execution_path, headers={"Idempotency-Key": "execute-http-1"}
    ).json()["html_sha256"] == executed_http.json()["html_sha256"]
    assert http_executor.calls == 1
    assert bob.post(
        execution_path, headers={"Idempotency-Key": "foreign-execute"}
    ).status_code == 404
    inspected_execution = alice.get(
        proposal_path + "/" + staged.json()["proposal_id"] + "/execution"
    )
    assert inspected_execution.status_code == 200
    assert inspected_execution.headers["cache-control"] == "no-store"
    review_path = proposal_path + "/" + staged.json()["proposal_id"] + "/review"
    accepted_http = alice.post(
        review_path,
        json={"action": "accept", "base_revision": 0,
              "rationale": "Evidence remains visible."},
        headers={"Idempotency-Key": "review-http-accept-1"},
    )
    assert accepted_http.status_code == 200, accepted_http.text
    assert accepted_http.headers["cache-control"] == "no-store"
    assert accepted_http.json()["revision"] == 1
    assert alice.post(
        review_path,
        json={"action": "accept", "base_revision": 0,
              "rationale": "Evidence remains visible."},
        headers={"Idempotency-Key": "review-http-accept-1"},
    ).json()["replayed"] is True
    private_write_path = (
        f"/speak/projects/{created.json()['project_id']}/private-write/"
        f"{accepted_http.json()['write_document_id']}"
    )
    private_write_collection = alice.get("/speak/private-write?limit=1")
    assert private_write_collection.status_code == 200, private_write_collection.text
    assert private_write_collection.headers["cache-control"] == "no-store"
    collection_body = private_write_collection.json()
    assert collection_body["documents"] == [{
        "write_document_id": accepted_http.json()["write_document_id"],
        "project_id": created.json()["project_id"],
        "title": "Private <Evidence>", "revision": 1,
        "html_sha256": executed_http.json()["html_sha256"],
        "visibility": "private",
        "updated_at": collection_body["documents"][0]["updated_at"],
        "origin_kind": "ai_composition",
    }]
    assert isinstance(collection_body["documents"][0]["updated_at"], str)
    assert collection_body["next_after_document_id"] == accepted_http.json()["write_document_id"]
    assert "Evidence-bound draft" not in private_write_collection.text
    assert "Evidence remains visible" not in private_write_collection.text
    assert bob.get("/speak/private-write").json() == {
        "documents": [], "next_after_document_id": None,
    }
    anonymous_collection = TestClient(app).get("/speak/private-write")
    assert anonymous_collection.status_code == 401
    assert anonymous_collection.headers["cache-control"] == "no-store"
    cursor = accepted_http.json()["write_document_id"]
    assert alice.get(
        "/speak/private-write", params={"after_document_id": cursor}
    ).json() == {"documents": [], "next_after_document_id": None}
    for invalid_query in ("limit=0", "limit=101", "limit=01"):
        invalid_collection = alice.get("/speak/private-write?" + invalid_query)
        assert invalid_collection.status_code == 400
        assert invalid_collection.headers["cache-control"] == "no-store"
    for bad_cursor in ("x" * 513, "not-a-write-id", "ivwd-" + "g" * 32, "line\nbreak"):
        invalid_cursor = alice.get(
            "/speak/private-write", params={"after_document_id": bad_cursor}
        )
        assert invalid_cursor.status_code == 400
        assert invalid_cursor.headers["cache-control"] == "no-store"
    native_http = alice.post(
        "/speak/private-write", json={"title": "Owner field notes"},
        headers={"Idempotency-Key": "native-http-create-1"},
    )
    assert native_http.status_code == 201, native_http.text
    assert native_http.headers["cache-control"] == "no-store"
    assert native_http.json()["origin_kind"] == "owner_native"
    assert "html" not in native_http.json()
    assert alice.post(
        "/speak/private-write", json={"title": "Owner field notes"},
        headers={"Idempotency-Key": "native-http-create-1"},
    ).json()["replayed"] is True
    assert alice.post(
        "/speak/private-write", json={"title": "Changed"},
        headers={"Idempotency-Key": "native-http-create-1"},
    ).status_code == 409
    assert alice.post(
        "/speak/private-write", json={"title": "Forged", "html": "<script>x</script>"},
        headers={"Idempotency-Key": "native-http-forged"},
    ).status_code == 422
    assert bob.post(
        "/speak/private-write", json={"title": "Bob"},
        headers={"Idempotency-Key": "native-http-bob"},
    ).status_code == 201
    native_path = (
        f"/speak/projects/{native_http.json()['project_id']}/private-write/"
        f"{native_http.json()['write_document_id']}"
    )
    native_current = alice.get(native_path)
    assert native_current.status_code == 200
    assert native_current.json()["origin_kind"] == "owner_native"
    assert native_current.json()["html"] == "<article></article>"
    assert bob.get(native_path).status_code == 404
    native_history = alice.get(native_path + "/history")
    assert native_history.json()["origin_kind"] == "owner_native"
    assert native_history.json()["revisions"][0]["operation"] == "create"
    assert native_history.json()["revisions"][0]["proposal_id"] is None
    assert native_history.json()["revisions"][0]["root_acceptance_event_id"] is None
    monkeypatch.setattr(
        "interfaces.research.api.hosted_document_routes.resolve_legal_citation_insertion_source",
        lambda document_id, chunk_ids, *, owner_id, con=None: (
            "Sealed source", "d" * 64, "Exact <sealed> evidence"
        ),
    )
    from substrate.engagement_spine.citation_evidence import parse_citation_evidence

    citation_authority = {
        "source_kind": "synthesis_claim", "source_asset_id": "research-1",
        "claim_id": "claim-1", "chunk_ids": ["chunk-1"],
        "document_id": "source-document-1",
    }
    citation = {**citation_authority,
                "receipt_sha256": parse_citation_evidence(citation_authority).receipt_sha256}
    preview_body = {
        "base_revision": 1, "base_html_sha256": native_http.json()["html_sha256"],
        "citation_evidence": citation,
    }
    preview_http = alice.post(
        native_path + "/evidence-insertions/preview", json=preview_body,
    )
    assert preview_http.status_code == 200, preview_http.text
    assert preview_http.headers["cache-control"] == "no-store"
    assert "Exact &lt;sealed&gt; evidence" in preview_http.json()["proposed_html"]
    assert alice.get(native_path).json()["revision"] == 1
    apply_body = {
        "base_revision": 1, "base_html_sha256": native_http.json()["html_sha256"],
        "citation_evidence": citation,
        "preview_sha256": preview_http.json()["preview_sha256"],
        "proposed_html_sha256": preview_http.json()["proposed_html_sha256"],
    }
    inserted_http = alice.post(
        native_path + "/evidence-insertions", json=apply_body,
        headers={"Idempotency-Key": "native-evidence-http-1"},
    )
    assert inserted_http.status_code == 200, inserted_http.text
    assert inserted_http.json()["operation"] == "evidence_insert"
    assert alice.post(
        native_path + "/evidence-insertions", json=apply_body,
        headers={"Idempotency-Key": "native-evidence-http-1"},
    ).json()["replayed"] is True
    assert bob.post(
        native_path + "/evidence-insertions/preview", json=preview_body,
    ).status_code in {404, 409}
    assert alice.get(native_path + "/history").json()["revisions"][-1][
        "operation"
    ] == "evidence_insert"
    second_authority = {
        "source_kind": "synthesis_claim", "source_asset_id": "research-2",
        "claim_id": "claim-2", "chunk_ids": ["chunk-2"],
        "document_id": "source-document-2",
    }
    second_citation = {
        **second_authority,
        "receipt_sha256": parse_citation_evidence(second_authority).receipt_sha256,
    }
    bundle_items = [
        {"citation_evidence": citation, "relationship": "supports",
         "operator_label": "Established baseline"},
        {"citation_evidence": second_citation, "relationship": "contradicts",
         "operator_label": None},
    ]
    inserted_current = alice.get(native_path).json()
    bundle_preview_body = {
        "base_revision": inserted_current["revision"],
        "base_html_sha256": inserted_current["html_sha256"], "items": bundle_items,
    }
    bundle_preview = alice.post(
        native_path + "/evidence-bundles/preview", json=bundle_preview_body,
    )
    assert bundle_preview.status_code == 200, bundle_preview.text
    assert bundle_preview.json()["operation"] == "evidence_bundle"
    assert [item["relationship"] for item in bundle_preview.json()["items"]] == [
        "supports", "contradicts",
    ]
    bundle_apply_body = {
        **bundle_preview_body,
        "preview_sha256": bundle_preview.json()["preview_sha256"],
        "manifest_sha256": bundle_preview.json()["manifest_sha256"],
        "proposed_html_sha256": bundle_preview.json()["proposed_html_sha256"],
    }
    bundle_applied = alice.post(
        native_path + "/evidence-bundles", json=bundle_apply_body,
        headers={"Idempotency-Key": "native-bundle-http-1"},
    )
    assert bundle_applied.status_code == 200, bundle_applied.text
    assert bundle_applied.json()["operation"] == "evidence_bundle"
    assert bundle_applied.json()["bundle_id"].startswith("ivwb-")
    assert alice.post(
        native_path + "/evidence-bundles", json=bundle_apply_body,
        headers={"Idempotency-Key": "native-bundle-http-1"},
    ).json()["replayed"] is True
    assert alice.get(native_path + "/history").json()["revisions"][-1][
        "operation"
    ] == "evidence_bundle"
    http_bundle_id = bundle_applied.json()["bundle_id"]
    monkeypatch.setattr(
        "interfaces.research.api.speak_routes._project_evidence_bundle_synthesis",
        lambda **_kwargs: 25,
    )
    synthesis_path = native_path + f"/evidence-bundles/{http_bundle_id}/ai-proposals"
    synthesis_payload = {
        "base_revision": 0,
        "instruction": "Preserve the explicit disagreement.",
        "provider_id": "openai", "model_id": "gpt-test",
        "approved_ceiling_cents": 30, "expected_output_tokens": 4000,
    }
    projected_http = alice.post(
        synthesis_path + "/projection",
        json={key: value for key, value in synthesis_payload.items()
              if key not in {"base_revision", "approved_ceiling_cents"}},
    )
    assert projected_http.status_code == 200, projected_http.text
    assert projected_http.json()["projected_max_cents"] == 25
    assert projected_http.json()["item_count"] == 2
    assert "spent_status" in projected_http.json()["budget"]
    synthesis_http = alice.post(
        synthesis_path, json=synthesis_payload,
        headers={"Idempotency-Key": "bundle-synthesis-http-1"},
    )
    assert synthesis_http.status_code == 201, synthesis_http.text
    assert synthesis_http.headers["cache-control"] == "no-store"
    assert synthesis_http.json()["source_kind"] == "evidence_bundle"
    assert synthesis_http.json()["projected_max_cents"] == 25
    assert synthesis_http.json()["item_count"] == 2
    assert "inputs" not in synthesis_http.json()
    assert alice.post(
        synthesis_path, json=synthesis_payload,
        headers={"Idempotency-Key": "bundle-synthesis-http-1"},
    ).json()["proposal_id"] == synthesis_http.json()["proposal_id"]
    assert bob.post(
        synthesis_path, json=synthesis_payload,
        headers={"Idempotency-Key": "bundle-synthesis-foreign"},
    ).status_code in {404, 409}
    class HttpBundleSynthesisExecutor:
        route_sha256 = "6" * 64
        calls = 0

        def execute(self, *, prompt, provider, model, idempotency_key):
            self.calls += 1
            return ProviderCompositionResult(
                raw_json=json.dumps({
                    "schema_version": 1, "title": "Bundle review",
                    "lead": "The sources disagree.",
                    "units": [{
                        "evidence_unit_ids": ["evidence-1", "evidence-2"],
                        "prose": "The contradiction remains unresolved.",
                    }],
                }),
                provider=provider, model=model, actual_cents=4,
                dispatch_event_id="bundle-http-dispatch",
                prompt_sha256=hashlib.sha256(prompt.encode()).hexdigest(),
            )

    bundle_executor = HttpBundleSynthesisExecutor()
    app.state.composition_executor = bundle_executor
    bundle_execution_path = (
        synthesis_path + f"/{synthesis_http.json()['proposal_id']}/execute"
    )
    bundle_execution = alice.post(
        bundle_execution_path,
        headers={"Idempotency-Key": "bundle-synthesis-execute-http-1"},
    )
    assert bundle_execution.status_code == 200, bundle_execution.text
    assert bundle_execution.json()["state"] == "ready_for_review"
    assert bundle_execution.json()["actual_cents"] == 4
    assert "Operator relationship: contradicts" in bundle_execution.json()["html"]
    assert bundle_executor.calls == 1
    assert alice.post(
        bundle_execution_path,
        headers={"Idempotency-Key": "bundle-synthesis-execute-http-1"},
    ).json()["html_sha256"] == bundle_execution.json()["html_sha256"]
    assert bundle_executor.calls == 1
    inspected_bundle = alice.get(
        synthesis_path + f"/{synthesis_http.json()['proposal_id']}/execution"
    )
    assert inspected_bundle.status_code == 200, inspected_bundle.text
    assert inspected_bundle.json()["html_sha256"] == bundle_execution.json()["html_sha256"]
    wrong_bundle_execution = alice.get(
        synthesis_path.replace(native_http.json()["project_id"], "ivwp-" + "f" * 32)
        + f"/{synthesis_http.json()['proposal_id']}/execution"
    )
    assert wrong_bundle_execution.status_code == 404
    already_final = alice.post(
        synthesis_path + f"/{synthesis_http.json()['proposal_id']}/reconcile"
    )
    assert already_final.status_code == 409
    assert already_final.headers["cache-control"] == "no-store"
    native_before_acceptance = alice.get(native_path).json()
    write_preview_path = (
        synthesis_path + f"/{synthesis_http.json()['proposal_id']}/write-preview"
    )
    write_preview_http = alice.post(write_preview_path, json={
        "base_revision": native_before_acceptance["revision"],
        "base_html_sha256": native_before_acceptance["html_sha256"],
    })
    assert write_preview_http.status_code == 200, write_preview_http.text
    assert write_preview_http.json()["operation"] == "synthesis_accept"
    assert "Evidence synthesis" in write_preview_http.json()["proposed_html"]
    assert alice.get(native_path).json()["revision"] == native_before_acceptance["revision"]
    write_accept_http = alice.post(
        synthesis_path + f"/{synthesis_http.json()['proposal_id']}/write-acceptance",
        json={
            "base_revision": native_before_acceptance["revision"],
            "base_html_sha256": native_before_acceptance["html_sha256"],
            "preview_sha256": write_preview_http.json()["preview_sha256"],
            "proposed_html_sha256": write_preview_http.json()["proposed_html_sha256"],
        }, headers={"Idempotency-Key": "bundle-synthesis-write-accept-http-1"},
    )
    assert write_accept_http.status_code == 200, write_accept_http.text
    assert write_accept_http.json()["operation"] == "synthesis_accept"
    assert write_accept_http.json()["revision"] == native_before_acceptance["revision"] + 1
    assert alice.post(
        synthesis_path + f"/{synthesis_http.json()['proposal_id']}/write-acceptance",
        json={
            "base_revision": native_before_acceptance["revision"],
            "base_html_sha256": native_before_acceptance["html_sha256"],
            "preview_sha256": write_preview_http.json()["preview_sha256"],
            "proposed_html_sha256": write_preview_http.json()["proposed_html_sha256"],
        }, headers={"Idempotency-Key": "bundle-synthesis-write-accept-http-1"},
    ).json()["replayed"] is True
    assert alice.get(native_path + "/history").json()["revisions"][-1][
        "operation"
    ] == "synthesis_accept"
    graph_target = InvestigationAuthority("alice@example.test", "knowledge-target")
    resolve_writable_investigation_stream(graph_target)
    knowledge_path = (
        synthesis_path + f"/{synthesis_http.json()['proposal_id']}/acceptances/"
        f"{write_accept_http.json()['acceptance_id']}"
    )
    knowledge_payload = {
        "target_investigation_id": "knowledge-target",
        "items": [{
            "unit_index": 0, "kind": "insight",
            "text": "The contradiction remains unresolved.",
        }],
    }
    candidates_http = alice.get(knowledge_path + "/knowledge-candidates")
    assert candidates_http.status_code == 200, candidates_http.text
    assert candidates_http.headers["cache-control"] == "no-store"
    assert candidates_http.json()["verification"] == "unverified"
    assert candidates_http.json()["units"][0]["text"] == (
        "The contradiction remains unresolved."
    )
    assert bob.get(knowledge_path + "/knowledge-candidates").status_code == 404
    with duckdb.connect(path, read_only=True) as con:
        graph_before = con.execute("SELECT count(*) FROM nodes").fetchone()[0]
        admissions_before = con.execute(
            "SELECT count(*) FROM interview_synthesis_knowledge_admissions_authority"
        ).fetchone()[0]
    knowledge_preview_http = alice.post(
        knowledge_path + "/knowledge-preview", json=knowledge_payload,
    )
    assert knowledge_preview_http.status_code == 200, knowledge_preview_http.text
    assert knowledge_preview_http.headers["cache-control"] == "no-store"
    assert knowledge_preview_http.json()["verification"] == "unverified"
    assert knowledge_preview_http.json()["items"][0]["disposition"] == "created"
    with duckdb.connect(path, read_only=True) as con:
        assert con.execute("SELECT count(*) FROM nodes").fetchone()[0] == graph_before
        assert con.execute(
            "SELECT count(*) FROM interview_synthesis_knowledge_admissions_authority"
        ).fetchone()[0] == admissions_before
    knowledge_apply_http = alice.post(
        knowledge_path + "/knowledge-admission",
        json={**knowledge_payload,
              "preview_sha256": knowledge_preview_http.json()["preview_sha256"]},
        headers={"Idempotency-Key": "knowledge-admit-http-1"},
    )
    assert knowledge_apply_http.status_code == 200, knowledge_apply_http.text
    assert knowledge_apply_http.json()["replayed"] is False
    assert knowledge_apply_http.json()["epistemic_status"] == (
        "model_proposed_operator_admitted"
    )
    assert alice.post(
        knowledge_path + "/knowledge-admission",
        json={**knowledge_payload,
              "preview_sha256": knowledge_preview_http.json()["preview_sha256"]},
        headers={"Idempotency-Key": "knowledge-admit-http-1"},
    ).json()["replayed"] is True
    assert bob.post(
        knowledge_path + "/knowledge-preview", json=knowledge_payload,
    ).status_code == 404
    assert bob.post(write_preview_path, json={
        "base_revision": native_before_acceptance["revision"],
        "base_html_sha256": native_before_acceptance["html_sha256"],
    }).status_code in {404, 409}
    assert bob.post(
        bundle_execution_path,
        headers={"Idempotency-Key": "bundle-synthesis-execute-foreign"},
    ).status_code in {404, 409}
    write_http = alice.get(private_write_path)
    assert write_http.status_code == 200, write_http.text
    assert write_http.headers["cache-control"] == "no-store"
    assert write_http.json()["html_sha256"] == executed_http.json()["html_sha256"]
    assert bob.get(private_write_path).status_code == 404
    undo_http = alice.post(
        private_write_path + "/undo",
        json={"target_event_id": accepted_http.json()["event_id"], "base_revision": 1},
        headers={"Idempotency-Key": "review-http-undo-1"},
    )
    assert undo_http.status_code == 200, undo_http.text
    assert undo_http.json()["revision"] == 2
    restored_http = alice.get(private_write_path)
    assert restored_http.status_code == 200
    assert restored_http.json()["html"] == ""
    edit_http = alice.post(
        private_write_path + "/edits",
        json={
            "base_revision": 2,
            "base_html_sha256": hashlib.sha256(b"").hexdigest(),
            "html": "<article><h1>Owner HTTP revision</h1></article>",
            "summary": "Direct owner edit.",
        },
        headers={"Idempotency-Key": "write-http-edit-1"},
    )
    assert edit_http.status_code == 200, edit_http.text
    assert edit_http.headers["cache-control"] == "no-store"
    assert edit_http.json()["revision"] == 3
    assert alice.post(
        private_write_path + "/edits",
        json={
            "base_revision": 2,
            "base_html_sha256": hashlib.sha256(b"").hexdigest(),
            "html": "<article><h1>Owner HTTP revision</h1></article>",
            "summary": "Direct owner edit.",
        },
        headers={"Idempotency-Key": "write-http-edit-1"},
    ).json()["replayed"] is True
    assert alice.get(private_write_path).json()["html"] == (
        "<article><h1>Owner HTTP revision</h1></article>"
    )
    assert bob.post(
        private_write_path + "/edits",
        json={"base_revision": 3, "base_html_sha256": edit_http.json()["html_sha256"],
              "html": "<p>foreign</p>"},
        headers={"Idempotency-Key": "foreign-write-edit"},
    ).status_code == 404
    unsafe_http = alice.post(
        private_write_path + "/edits",
        json={"base_revision": 3, "base_html_sha256": edit_http.json()["html_sha256"],
              "html": '<iframe src="data:text/html,bad"></iframe>'},
        headers={"Idempotency-Key": "unsafe-write-edit"},
    )
    assert unsafe_http.status_code == 400
    assert unsafe_http.headers["cache-control"] == "no-store"
    history_http = alice.get(private_write_path + "/history")
    assert history_http.status_code == 200, history_http.text
    assert history_http.headers["cache-control"] == "no-store"
    assert history_http.json()["current_revision"] == 3
    assert [item["operation"] for item in history_http.json()["revisions"]] == [
        "accept", "undo", "edit",
    ]
    assert all(
        "html" not in item and "summary" not in item and "rationale" not in item
        for item in history_http.json()["revisions"]
    )
    history_bytes = history_http.text
    assert "Owner HTTP revision" not in history_bytes
    assert "Direct owner edit" not in history_bytes
    assert "Evidence remains visible" not in history_bytes
    page_http = alice.get(private_write_path + "/history?after_revision=1&limit=1")
    assert [item["revision"] for item in page_http.json()["revisions"]] == [2]
    invalid_history_http = alice.get(private_write_path + "/history?limit=0")
    assert invalid_history_http.status_code == 400
    assert invalid_history_http.headers["cache-control"] == "no-store"
    historical_http = alice.get(private_write_path + "/revisions/3")
    assert historical_http.status_code == 200, historical_http.text
    assert historical_http.headers["cache-control"] == "no-store"
    assert historical_http.json()["html"] == (
        "<article><h1>Owner HTTP revision</h1></article>"
    )
    assert historical_http.json()["is_current"] is True
    invalid_revision_http = alice.get(private_write_path + "/revisions/not-a-number")
    assert invalid_revision_http.status_code == 404
    assert invalid_revision_http.headers["cache-control"] == "no-store"
    missing_restore_http = alice.post(private_write_path + "/restores", json={})
    assert missing_restore_http.status_code == 400
    assert missing_restore_http.headers["cache-control"] == "no-store"
    restore_http = alice.post(
        private_write_path + "/restores",
        json={"base_revision": 3, "base_html_sha256": edit_http.json()["html_sha256"],
              "target_revision": 2},
        headers={"Idempotency-Key": "write-http-restore-2"},
    )
    assert restore_http.status_code == 200, restore_http.text
    assert restore_http.headers["cache-control"] == "no-store"
    assert restore_http.json()["revision"] == 4
    assert restore_http.json()["operation"] == "restore"
    assert alice.get(private_write_path).json()["html"] == ""
    successor_http = alice.post(
        private_write_path + "/edits",
        json={"base_revision": 4, "base_html_sha256": hashlib.sha256(b"").hexdigest(),
              "html": "<p>After restore</p>"},
        headers={"Idempotency-Key": "write-http-after-restore"},
    )
    assert successor_http.status_code == 200, successor_http.text
    assert alice.post(
        private_write_path + "/restores",
        json={"base_revision": 3, "base_html_sha256": edit_http.json()["html_sha256"],
              "target_revision": 2},
        headers={"Idempotency-Key": "write-http-restore-2"},
    ).json()["replayed"] is True
    assert bob.get(private_write_path + "/history").status_code == 404
    assert bob.get(private_write_path + "/revisions/3").status_code == 404
    assert bob.post(
        private_write_path + "/restores",
        json={"base_revision": 5,
              "base_html_sha256": successor_http.json()["html_sha256"],
              "target_revision": 2},
        headers={"Idempotency-Key": "foreign-write-restore"},
    ).status_code == 404
    assert bob.get(
        f"/speak/projects/{created.json()['project_id']}/html-drafts/"
        f"{draft.json()['draft_id']}"
    ).status_code == 404
    assert bob.post(
        f"/speak/projects/{created.json()['project_id']}/html-drafts",
        json=draft_payload, headers={"Idempotency-Key": "foreign-claim-injection"},
    ).status_code == 404
    revoked_credit = alice.post(
        contributor_path + "/revoke",
        json={"target_event_id": contributor.json()["event_id"]},
        headers={"Idempotency-Key": "revoke-credit-http-1"},
    )
    assert revoked_credit.status_code == 200, revoked_credit.text
    assert alice.get(contributor_path).status_code == 404
    assert alice.post(
        contributor_path + "/revoke",
        json={"target_event_id": contributor.json()["event_id"]},
        headers={"Idempotency-Key": "revoke-credit-http-1"},
    ).json()["event_id"] == revoked_credit.json()["event_id"]
    with connect_write(path, purpose="test/contributor-economic-separation") as con:
        assert con.execute("SELECT count(*) FROM speak_contributors").fetchone() == (0,)
        assert con.execute("SELECT count(*) FROM speak_accruals").fetchone() == (0,)
        assert con.execute("SELECT count(*) FROM speak_interview_grades").fetchone() == (0,)
    replay = bob.post(
        f"{invite_path}/answer",
        json={"question_id": "q1", "transcript": "answer", "duration_seconds": 1},
    )
    assert replay.status_code == 201
    mismatch = bob.post(
        f"{invite_path}/answer",
        json={"question_id": "q1", "transcript": "changed", "duration_seconds": 1},
    )
    assert mismatch.status_code == 409
    assert bob.delete(f"/interview-invites/{issued.json()['invite_id']}").status_code == 404
    revoked = alice.delete(f"/interview-invites/{issued.json()['invite_id']}")
    assert revoked.status_code == 204
    assert bob.get(invite_path).status_code == 404

    second = alice.post(
        "/interviews", json={"project_id": created.json()["project_id"], "informant_handle": "Grace"}
    ).json()
    second_issue = alice.post(f"/interviews/{second['interview_id']}/invites", json={}).json()
    second_path = second_issue["link"]
    assert bob.post(f"{second_path}/consent", json={"scopes": ["record"]}).status_code == 200
    token = second_path.rsplit("/", 1)[1]

    class RevokingTranscriber:
        def transcribe(self, audio_bytes, *, filename, language=None):
            from substrate.interviews.capability import resolve_invite, revoke_invite

            with connect_write(path, purpose="test/revoke-during-transcription") as con:
                capability = resolve_invite(con, token)
                assert capability is not None
                assert revoke_invite(con, capability.authority, invite_id=capability.invite_id)

            class Result:
                text = "must not commit"

            return Result()

    import interfaces.research.api.speak_routes as speak_routes

    monkeypatch.setattr(speak_routes, "_INVITEE_TRANSCRIBER", RevokingTranscriber())
    voice = bob.post(
        f"{second_path}/voice?question_id=q-race",
        content=b"audio", headers={"Content-Type": "audio/webm"},
    )
    assert voice.status_code == 404, voice.text
    detail = alice.get(f"/interviews/{second['interview_id']}").json()
    assert all(turn["text"] != "must not commit" for turn in detail["transcript"])
