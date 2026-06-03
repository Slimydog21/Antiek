"""Substrate exerciser — drive every load-bearing master-spec chain
end-to-end against an isolated DuckDB. No external APIs called.

Run:
  python scripts/exercise_substrate.py [--db PATH] [--reset]

Prints a summary of what landed in each table + which audit events
fired. Safe to run repeatedly — the script is idempotent on
content-addressed identifiers and resets only when ``--reset`` is set.

Chains exercised (each maps to a master-spec section):
  §13.2 + §13.9 Phase 2  — skill accumulator → writer → audit
  §13.5 + §13.7 + §9.10  — attribution → payout → Stripe Connect transfer (mock)
  §13.9 + §13.7 audit    — quality gate → notebook promotion → audit
  §13.8                  — outcomes recording + backtest read
  §13.9 Phase 3          — federation config + cross-graph citation
  §14.2 + §13.7          — Loop 3 checklist transitions + rubric verifier
  §13.6 + autoresearch   — GEPA → Phase 8 → prompt applier (filesystem)
  §16.2                  — DP preference observation → dispatch hint
  §13.3                  — deletion request lifecycle
  §11.5                  — interview project + invite
"""

from __future__ import annotations

import argparse
import json
import os
import shutil
import sys
import uuid
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))


def reset_db(db_path: str) -> None:
    """Delete the DuckDB file if it exists. Re-create the schema fresh."""
    if os.path.exists(db_path):
        os.remove(db_path)
    parent = os.path.dirname(db_path)
    if parent:
        os.makedirs(parent, exist_ok=True)


def line(msg: str) -> None:
    print(f"  · {msg}")


def header(msg: str) -> None:
    print(f"\n── {msg} ─────────────────────────────────────")


def exercise(db_path: str) -> dict:
    """Run every chain. Returns a summary dict for the operator."""
    os.environ["ANTIEK_DUCKDB_PATH"] = db_path

    # ── Schema bootstrap ────────────────────────────────────────────
    header("Schema bootstrap")
    from substrate.graph import ensure_initialized
    ensure_initialized(db_path)
    line(f"DB at {db_path}")

    summary: dict = {}

    # ── Loop 3 checklist transitions (§14.2) ────────────────────────
    header("Loop 3 checklist (§14.2)")
    from runtime.db_lock import connect_write
    from substrate.loop_3.checklist_store import set_criterion, snapshot
    from substrate.loop_3.unlock_gate import Loop3UnlockCriterion

    with connect_write(db_path, purpose="exercise:loop3") as con:
        for criterion in Loop3UnlockCriterion:
            set_criterion(
                con, criterion=criterion, met=True,
                note=f"exerciser: {criterion.value} ratified",
            )
        snap = snapshot(con)
    line(f"all_criteria_met={snap.all_criteria_met} (env_unlocked={snap.env_unlocked})")
    summary["loop_3_criteria_met"] = snap.all_criteria_met

    # ── Federation config (§13.9 Phase 3) ──────────────────────────
    header("Federation config (§13.9 Phase 3)")
    from substrate.cross_graph.federation import FederationConfig
    from substrate.cross_graph.federation_config_store import (
        load_config,
        save_config,
    )
    with connect_write(db_path, purpose="exercise:fed") as con:
        save_config(con, FederationConfig(
            allowed_partner_substrates=("partner-research-coop",),
            require_opt_in_for_outbound_citations=True,
            require_attribution_for_outbound_citations=True,
        ))
        cfg = load_config(con)
    line(f"partners={list(cfg.allowed_partner_substrates)}")
    summary["federation_partners"] = list(cfg.allowed_partner_substrates)

    # ── Cross-graph citation (§13.9) ──────────────────────────────
    header("Cross-graph citation")
    from substrate.cross_graph.federation import record_cross_graph_citation
    refs = []
    for i in range(3):
        ref = record_cross_graph_citation(
            referencing_user_id="__operator__",
            referencing_investigation_id=f"inv-demo-{i}",
            referenced_user_id="user-A",
            referenced_note_id=f"note-{i}",
        )
        refs.append(ref.reference_id)
    line(f"recorded {len(refs)} citations")
    summary["citations_recorded"] = len(refs)

    # ── Notebook quality-gate promotion (§13.9) ───────────────────
    header("Notebook quality-gate promotion (§13.9)")
    # Seed a tier-1 document + chunk so the source-tier rubric can pass.
    tier1_doc_id = f"doc-tier1-{uuid.uuid4().hex[:8]}"
    tier1_chunk_id = f"chunk-{uuid.uuid4().hex[:8]}"
    with connect_write(db_path, purpose="exercise:nb_seed") as con:
        con.execute(
            "INSERT INTO documents ("
            "document_id, source_tier, document_type, source_uri, title"
            ") VALUES (?, 1, 'pdf', 'file:///tier1.pdf', "
            "'Lukin lab neutral-atom error rate analysis')",
            [tier1_doc_id],
        )
        con.execute(
            "INSERT INTO chunks ("
            "chunk_id, document_id, chunk_index, text, token_count"
            ") VALUES (?, ?, 0, 'tier-1 reference text', 12)",
            [tier1_chunk_id, tier1_doc_id],
        )

    from compounding.quality_gate import evaluate_notebook_for_public
    from substrate.notebooks import (
        append_block,
        create_notebook,
        gather_quality_gate_inputs,
        get_notebook,
        promote_to_public,
    )

    with connect_write(db_path, purpose="exercise:nb_create") as con:
        nb_id = create_notebook(
            con,
            title="Neutral-atom platforms: 100-qubit error rate snapshot",
            investigation_id="inv-demo-0",
        )
        append_block(
            con, nb_id, block_type="prose",
            content={
                "text": (
                    "Neutral-atom platforms have reached gate error rates "
                    "below 10⁻³ at 100-qubit scale. The cross-comparison "
                    "with trapped-ion systems shows similar performance "
                    "in the regime measured, with neutral-atom cycle "
                    "times longer but parallelism higher. The pattern "
                    "holds across all three independent measurements."
                ),
            },
        )
        append_block(
            con, nb_id, block_type="region_embed",
            content={"caption": "Tier-1 reference: Lukin lab"},
            ref_id=tier1_chunk_id,
        )
        nb = get_notebook(con, nb_id)
        inputs = gather_quality_gate_inputs(con, nb)
    verdict = evaluate_notebook_for_public(
        text_content=inputs.text_content,
        cited_chunk_tiers=inputs.cited_chunk_tiers,
        corpus_sector_terms=inputs.corpus_sector_terms,
        rubric_score=0.95,
    )
    line(f"gate verdict: accepted={verdict.accepted}")
    if verdict.accepted:
        with connect_write(db_path, purpose="exercise:nb_promote") as con:
            promote_to_public(con, nb_id)
        line(f"notebook {nb_id} promoted to user_public_contribution")
    summary["notebook_promoted"] = verdict.accepted

    # ── Skill accumulator → writer → audit (§13.2) ────────────────
    header("Skill accumulator → writer → audit (§13.2)")
    from substrate.multi_user.skill_accumulator import (
        MIN_USERS_FOR_PROMOTION,
        SkillRuleAccumulator,
    )
    from substrate.multi_user.skill_propagation import (
        extract_discovered_rule,
    )
    from substrate.multi_user.skill_writer import (
        drain_promotable_to_substrate,
    )
    acc = SkillRuleAccumulator()
    for u in range(MIN_USERS_FOR_PROMOTION + 2):  # high confidence
        digest = extract_discovered_rule(
            observation_text="Lukin lab papers in neutral-atom physics are Tier 1",
            rule_kind="source_tier_rule",
            domain="quantum",
            epsilon_budget_consumed=0.01,
        )
        acc.contribute(digest=digest, contributor_user_id=f"user-{u}")
    audit_events = []
    with connect_write(db_path, purpose="exercise:skill_drain") as con:
        outcomes = drain_promotable_to_substrate(
            accumulator=acc, con=con, broadcast=audit_events.append,
        )
    promoted = [o for o in outcomes if o.written]
    line(f"promoted rules: {len(promoted)} (audit events: {len(audit_events)})")
    summary["skill_rules_promoted"] = len(promoted)
    summary["skill_rule_audit_events"] = len(audit_events)

    # ── Payout pipeline (§13.5 + §9.10) ───────────────────────────
    header("Payout pipeline (§13.5 + §9.10)")
    from substrate.ad_inventory.event_emit import (
        make_broadcasting_payout_hook,
    )
    from substrate.ad_inventory.event_subscription import (
        AttributionComputedEvent,
        make_subscription,
    )
    from substrate.ad_inventory.payout import PayoutRouter, RevShareKind
    from substrate.ad_inventory.transfer_initiator import (
        initiate_transfer,
    )
    from tools.stripe_connect.providers import MockStripeProvider

    payout_events: list = []
    router = PayoutRouter()
    hook = make_broadcasting_payout_hook(
        investigation_id="inv-demo-0",
        broadcast=payout_events.append,
    )
    sub = make_subscription(router, on_decisions=hook)
    sub.handle(AttributionComputedEvent(
        page_id="page-1",
        impression_id="imp-demo-1",
        ad_revenue_usd_cents=2_500,  # $25 impression
        attribution_shares={tier1_doc_id: 0.7, "doc-creator-X": 0.3},
        document_to_recipient={
            tier1_doc_id: (RevShareKind.PUBLISHER, "publisher-mit-press", True),
            "doc-creator-X": (RevShareKind.CREATOR, "user-X", False),
        },
    ))
    line(f"decisions emitted: {len(router.decisions)} · audit events: {len(payout_events)}")
    stripe = MockStripeProvider()
    transfers_landed = 0
    with connect_write(db_path, purpose="exercise:payout") as con:
        for d in router.decisions:
            if d.kind == RevShareKind.CREATOR:
                outcome = initiate_transfer(
                    con=con, provider=stripe, decision=d,
                    account_id_for_recipient="acct_mock_user_X",
                )
            elif d.kind == RevShareKind.PUBLISHER:
                outcome = initiate_transfer(
                    con=con, provider=stripe, decision=d,
                    account_id_for_recipient="acct_mit_press_pre_onboarded",
                )
            else:
                outcome = initiate_transfer(
                    con=con, provider=stripe, decision=d,
                    account_id_for_recipient=None,
                )
            if outcome.status == "transferred":
                transfers_landed += 1
    line(f"stripe transfers landed: {transfers_landed} (escrow held: publisher pre-onboarded)")
    summary["payout_transfers_landed"] = transfers_landed
    summary["payout_audit_events"] = len(payout_events)

    # ── Outcomes recording + backtest (§13.8) ─────────────────────
    header("Outcomes + backtest (§13.8)")
    synth_id = f"syn-demo-{uuid.uuid4().hex[:8]}"
    with connect_write(db_path, purpose="exercise:outcomes") as con:
        con.execute(
            "INSERT INTO syntheses ("
            "synthesis_id, target_question, synthesis_timestamp, "
            "status, implicit_recommendation, thesis_text"
            ") VALUES (?, ?, CURRENT_TIMESTAMP, 'passed', 'proceed', ?)",
            [
                synth_id,
                "Will neutral-atom platforms cross 1000-qubit scale by 2027?",
                "Conditional yes if error rates hold.",
            ],
        )
        for kind in ("confirmed", "partially_confirmed", "disconfirmed"):
            con.execute(
                "INSERT INTO outcomes ("
                "outcome_id, synthesis_id, observer, "
                "thesis_outcomes, falsification_outcomes, "
                "execution_risk_outcomes, decision_alignment, notes"
                ") VALUES (?, ?, ?, ?, ?, ?, ?, ?)",
                [
                    f"out-{uuid.uuid4().hex[:8]}",
                    synth_id, "__operator__",
                    json.dumps([{
                        "thesis_claim": "100-qubit scale", "outcome": kind,
                        "evidence": "", "evidence_chunk_ids": [],
                    }]),
                    "[]", "[]", None, f"verdict: {kind}",
                ],
            )
    from middleware.backtest.analysis import backtest
    from runtime.db_lock import connect_read
    with connect_read(db_path) as con:
        report = backtest(con, synth_id)
    line(
        f"backtest: outcomes_recorded={report.outcomes_recorded} "
        f"load_bearing_invalidated={report.load_bearing_edges_invalidated} "
        f"chunks_demoted={report.cited_chunks_demoted}"
    )
    summary["outcomes_recorded"] = report.outcomes_recorded

    # ── GEPA → Phase 8 → applier (§13.6 + autoresearch) ───────────
    header("GEPA → Phase 8 → applier (§13.6)")
    from compounding.skill_growth import (
        SkillPatchGate,
        apply_prompt_variant,
        bridge_gepa_result_to_phase8,
        load_active_variant,
    )
    from tools.gepa.optimizer import GEPAResult
    from tools.gepa.pareto_front import ScoreVector, Variant

    gate = SkillPatchGate(
        mode="enforcing", epsilon=0.02, minimum_cohort_size=5,
    )
    pareto = [
        Variant(
            variant_id=f"gepa-synthesizer-{i:04x}{i:04x}feed",
            prompt_text=f"SYSTEM: synthesizer variant {i}",
            score=ScoreVector(
                rubric_score=0.85 + 0.03 * i,
                verifier_pass_rate=0.92 + 0.02 * i,
                cost_penalty=-0.05 - 0.01 * i,
                grounding_preserved=0.95,
            ),
            rationale=f"GEPA proposal {i}",
        )
        for i in range(3)
    ]
    result = GEPAResult(
        pareto_front=pareto,
        total_iterations=1,
        total_variants_evaluated=3,
        rejected_dominated=0,
    )
    outcomes = bridge_gepa_result_to_phase8(
        gate=gate,
        result=result,
        baseline_score=0.6,
        cohort_size=50,
        backtest_fn=lambda v: 0.5 + v.score.rubric_score * 0.3,
    )
    accepted = [o for o in outcomes if o.patch_outcome.decision.value == "accept"]
    applied_dir = ROOT / "compounding" / "applied_prompts_demo"
    if accepted:
        record = apply_prompt_variant(
            role="synthesizer",
            bridge_outcome=accepted[0],
            base_dir=applied_dir,
        )
        active = load_active_variant("synthesizer", base_dir=applied_dir)
        line(f"applied variant: {record.variant_id}")
        line(f"active text length: {len(active or '')} chars")
    summary["gepa_accepted_count"] = len(accepted)

    # ── DP preference → dispatch hint (§16.2) ─────────────────────
    header("DP preferences → dispatch hint (§16.2)")
    import substrate.dp_shuffler.preference_learning as _pref_mod
    from substrate.dispatch.preference_hints import (
        category_for_role,
        recommend_tier,
    )
    from substrate.dp_shuffler.epsilon_registry import (
        EpsilonRegistry,
        register_surface,
    )
    from substrate.dp_shuffler.preference_learning import (
        PreferenceLearningStream,
        PreferenceObservation,
    )

    # Deterministic stub of the randomizer for repro; the local-DP
    # randomization itself is exhaustively tested elsewhere.
    _orig_rr = _pref_mod.randomized_response
    _pref_mod.randomized_response = lambda truth, eps: truth  # type: ignore
    try:
        reg = EpsilonRegistry()
        register_surface(
            reg,
            surface_name=category_for_role("synthesizer"),
            epsilon_per_day=4.0,
            sensitivity="low",
            description="exerciser per-role upgrade preference",
        )
        stream = PreferenceLearningStream(
            registry=reg, per_obs_epsilon=0.05,
        )
        for _ in range(40):  # ≥ MIN_SAMPLE_COUNT
            stream.record(PreferenceObservation(
                category=category_for_role("synthesizer"),
                true_value=True,
            ))
        rec = recommend_tier(
            role="synthesizer", fallback_tier="pro",
            upgrade_tier="synthesis", stream=stream,
        )
        line(
            f"recommendation: {rec.recommended_tier} "
            f"(estimate={rec.debiased_estimate:.2f}, n={rec.sample_count})"
        )
        summary["dispatch_recommendation"] = rec.recommended_tier
    finally:
        _pref_mod.randomized_response = _orig_rr  # type: ignore

    # ── Deletion request lifecycle (§13.3) ────────────────────────
    header("Deletion request lifecycle (§13.3)")
    request_id = f"del-{uuid.uuid4().hex[:8]}"
    with connect_write(db_path, purpose="exercise:del_req") as con:
        con.execute(
            "INSERT INTO deletion_requests "
            "(request_id, user_id, status, reason) "
            "VALUES (?, ?, 'pending', ?)",
            [request_id, "__operator__", "exerciser demo request"],
        )
        # Cancel it.
        con.execute(
            "UPDATE deletion_requests SET status = 'cancelled', "
            "updated_at = CURRENT_TIMESTAMP WHERE request_id = ?",
            [request_id],
        )
    line(f"created + cancelled request {request_id}")
    summary["deletion_request_round_trip"] = True

    # ── Interview project + invite (§11.5) ───────────────────────
    header("Interview project + invite (§11.5)")
    from substrate.graph.ops import insert_interview, insert_interview_project
    with connect_write(db_path, purpose="exercise:interview") as con:
        project_id = insert_interview_project(
            con,
            title="Neutral-atom physics deep dive",
            topic_description="Cross-platform comparison interviews",
            deliverable_id=None,
            interview_guide={
                "must_cover": [
                    "What's the current error-rate trajectory?",
                    "Where does the architecture hit its scaling wall?",
                ],
                "framing": "Compare neutral-atom + trapped-ion + superconducting",
            },
        )
        interview_id = insert_interview(
            con, project_id=project_id,
            informant_handle="dr_lukin",
            informant_email=None,
        )
    line(f"project: {project_id} · interview: {interview_id}")
    summary["interview_project_id"] = project_id
    summary["interview_id"] = interview_id

    # ── IP holder + escrow (§9.10) ───────────────────────────────
    header("IP holder pre-onboarding (§9.10)")
    from substrate.ip_holders import create_pre_onboarded, mark_invited
    with connect_write(db_path, purpose="exercise:ip_holder") as con:
        h1 = create_pre_onboarded(
            con,
            display_name="MIT Press",
            legal_contact_email="ip@mitpress.example",
        )
        create_pre_onboarded(
            con,
            display_name="Cambridge University Press",
            legal_contact_email="ip@cup.example",
        )
        mark_invited(con, h1)
    line("created 2 IP holders, invited 1")
    summary["ip_holders_created"] = 2
    summary["ip_holders_invited"] = 1

    return summary


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--db",
        default=str(ROOT / ".antiek_demo" / "demo_run.duckdb"),
        help="Path to the isolated demo DB",
    )
    parser.add_argument(
        "--reset", action="store_true",
        help="Delete the demo DB before running",
    )
    args = parser.parse_args()

    if args.reset:
        reset_db(args.db)
        if (ROOT / "compounding" / "applied_prompts_demo").exists():
            shutil.rmtree(ROOT / "compounding" / "applied_prompts_demo")

    summary = exercise(args.db)
    print("\n" + "=" * 60)
    print("SUMMARY")
    print("=" * 60)
    for k, v in summary.items():
        print(f"  {k} = {v}")


if __name__ == "__main__":
    main()
