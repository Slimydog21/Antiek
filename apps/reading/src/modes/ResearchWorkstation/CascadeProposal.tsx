import { useCallback, useEffect, useRef, useState } from "react";

import LemonButton from "../../components/lemon/LemonButton";
import AIActionFailure from "../../shared/AIActionFailure";
import {
  ApiError,
  classifyClientError,
  type ClientFailureClassification,
} from "../../lib/api";
import Thinking from "../../shared/Thinking";
import {
  approvePlan,
  approveSpend,
  createPlan,
  editPlan,
  getBudgetDefaults,
  getPlan,
  getSpendPreview,
  getSession,
  launchPlan,
  type PlanNode,
  type PlanTree,
  type SpendMode,
  type SpendPreview,
} from "../../api/research";
import { notifyResearchStarted } from "../../werner";

/**
 * CascadeProposal — the Research door's "break this into sub-questions" mode
 * (SPR-01 product-depth) → the OPTIONAL "plan it first" path (Living-Roadmap
 * SPR-05 M2).
 *
 * The one-shot Ask runs a single research. This is the second, OPTIONAL mode
 * (the operator decision: plan-mode is NOT forced on every Ask): the user
 * states a problem space, the AI proposes a small set of focused
 * sub-questions, the user trims/edits/rewords them, APPROVES, and on launch
 * each approved sub-question becomes its own parallel research. The user
 * watches them think on the next surface (SPR-02).
 *
 * ── WHAT THE PLAN RENDERS (honesty gate, rigor #1) ──────────────────────
 * The SPR-05 sprint page describes the plan as "known insights, open
 * questions, and sub-question sprints." The shipped cascade planner
 * (roles/cascade_planner/planner.py → POST /research/plans → PlanTree)
 * actually produces ONLY the sub-question sprints (the PlanTree leaves: each a
 * `question` + a `rationale` + a `focus_boundary`). It does NOT produce
 * "known insights" or "open questions" — those are DISTILLATION artifacts
 * (getDistillation) that exist only AFTER a research has run; a fresh problem
 * space has none. So this surface renders the planner's REAL output — the
 * sub-questions and, newly, each one's RATIONALE (also real planner output) —
 * and does NOT fabricate placeholder insight/question blocks the planner never
 * produced. That deliberate gap is named here and in the sprint handoff
 * rather than papered over with hand-faked content.
 *
 * It wires shipped machinery, it does not reinvent it: createPlan runs the
 * decomposer + cascade planner; editPlan applies one trim/reword through the
 * SPR-05 tree contract (which re-opens the approval gate on every edit);
 * approvePlan + launchPlan are the gated launch. The frontend never decides
 * launchability — it shows what the backend's glass-box gate reports.
 *
 * Vocabulary: the surface speaks human. "Sub-question", "research",
 * "researches running in parallel" — never "leaf", "investigation", "cascade
 * session", or any raw id. The substrate keeps its nouns; the door does not
 * leak them.
 *
 * Honesty: the propose call needs a model provider. Without keys it fails,
 * and we render the SAME <AIActionFailure> the one-shot path uses — an honest
 * "the AI isn't connected" with a retry, never a fake tree or a stuck
 * spinner.
 */

interface Props {
  /** The problem space the user typed in the composer. */
  problem: string;
  /** Launch landed: hand the session to the parent to navigate into the
   * live monitor. */
  onLaunched: (sessionId: string) => void;
  /** The user backed out of cascade mode (e.g. trimmed it down to nothing,
   * or hit "Ask one question instead"). The parent restores the one-shot
   * composer with the problem text intact. */
  onFallBackToAsk: () => void;
}

interface PlanState {
  rootNodeId: string;
  tree: PlanTree;
  launchable: boolean;
}

type FailureStage = "propose" | "edit" | "approval" | "launch";

/** The leaf sub-questions under the root — exactly the set the backend launches
 * (cascade_session spawns one research per tree leaf). We render and count the
 * leaves, not just root.children, so "what you see" equals "what runs": a
 * single-level proposal is unchanged, but if the planner ever nests, the door
 * can never silently understate the launch count. */
function subQuestions(tree: PlanTree): PlanNode[] {
  const leaves: PlanNode[] = [];
  const collect = (node: PlanNode) => {
    if (node.children.length === 0) leaves.push(node);
    else node.children.forEach(collect);
  };
  tree.root.children.forEach(collect);
  return leaves;
}

export default function CascadeProposal({ problem, onLaunched, onFallBackToAsk }: Props) {
  const [plan, setPlan] = useState<PlanState | null>(null);
  // Phase gates the human-in-the-loop: a plan block is editable ONLY once
  // phase === "ready" (after createPlan resolves), so an edit can NEVER race the
  // planner while it is still proposing (the spec's rigor-#3 edit-while-streaming
  // edge — handled by construction, not left as a free-for-all).
  const [phase, setPhase] = useState<"proposing" | "recovering" | "ready" | "launching">("proposing");
  const [failure, setFailure] = useState<ClientFailureClassification | null>(
    null,
  );
  const [failureStage, setFailureStage] = useState<FailureStage>("propose");
  const [editing, setEditing] = useState<string | null>(null);
  const [planMutationPending, setPlanMutationPending] = useState(false);
  const [draft, setDraft] = useState("");
  const [perResearchCost, setPerResearchCost] = useState<number | null>(null);
  const [priceCeiling, setPriceCeiling] = useState("");
  const [ceilingApproved, setCeilingApproved] = useState(false);
  const [spendMode, setSpendMode] = useState<SpendMode>("stop_limit");
  const [hardPreview, setHardPreview] = useState<SpendPreview | null>(null);
  const [previewPending, setPreviewPending] = useState(false);
  const [authorityDigest, setAuthorityDigest] = useState<string | null>(null);
  const [approvedSessionId, setApprovedSessionId] = useState<string | null>(null);
  const previewSequence = useRef(0);

  // Propose the tree once on mount (and on an explicit retry). A ref guards
  // React 18 StrictMode's double-invoke so we don't POST two plans.
  const proposedRef = useRef(false);

  const propose = useCallback(async () => {
    setPhase("proposing");
    setFailure(null);
    setFailureStage("propose");
    try {
      const r = await createPlan({ problem });
      setPlan({ rootNodeId: r.root_node_id, tree: r.tree, launchable: false });
      setPhase("ready");
    } catch (e) {
      // Classify the backend envelope (or network throw) — never collapse to
      // setFailed("") which masked every failure as "no provider configured".
      setFailure(classifyClientError(e));
      setPhase("ready");
    }
  }, [problem]);

  useEffect(() => {
    if (proposedRef.current) return;
    proposedRef.current = true;
    void propose();
    // Cost contract for the launch estimate — read from the backend's
    // BudgetCap default, never hardcoded. A failure here is non-fatal: we
    // just don't show the dollar estimate.
    void getBudgetDefaults()
      .then((b) => setPerResearchCost(b.per_research_cost_usd))
      .catch(() => setPerResearchCost(null));
  }, [propose]);

  useEffect(() => {
    const count = plan === null ? 0 : subQuestions(plan.tree).length;
    if (perResearchCost === null || count === 0) {
      setPriceCeiling("");
    } else {
      setPriceCeiling((perResearchCost * count).toFixed(2));
    }
    setCeilingApproved(false);
    setAuthorityDigest(null);
    setApprovedSessionId(null);
  }, [perResearchCost, plan]);

  useEffect(() => {
    const sequence = ++previewSequence.current;
    if (
      plan === null ||
      !/^\d+(?:\.\d{1,2})?$/.test(priceCeiling) ||
      Number(priceCeiling) <= 0
    ) {
      setHardPreview(null);
      setPreviewPending(false);
      return;
    }
    setPreviewPending(true);
    void getSpendPreview(plan.rootNodeId, "hard_ceiling", priceCeiling)
      .then((preview) => {
        if (previewSequence.current === sequence) setHardPreview(preview);
      })
      .catch(() => {
        if (previewSequence.current === sequence) setHardPreview(null);
      })
      .finally(() => {
        if (previewSequence.current === sequence) setPreviewPending(false);
      });
  }, [plan, priceCeiling]);

  const applyEdit = useCallback(
    async (edit: { op: "remove" | "reword"; target_local_id: string; question?: string }) => {
      if (!plan || planMutationPending || phase !== "ready") return;
      // Approval belongs to an exact tree version. Revoke it before the edit
      // request leaves the browser so the old tree cannot launch in the gap.
      setCeilingApproved(false);
      setAuthorityDigest(null);
      setApprovedSessionId(null);
      setPlanMutationPending(true);
      try {
        const r = await editPlan(plan.rootNodeId, edit);
        setPlan({ rootNodeId: r.root_node_id, tree: r.tree, launchable: r.launchable });
      } catch (e) {
        // The server may have committed the edit even if its response was
        // lost. Fail closed instead of letting the stale visible tree launch.
        setFailureStage("edit");
        setFailure(classifyClientError(e));
      } finally {
        setPlanMutationPending(false);
      }
    },
    [phase, plan, planMutationPending],
  );

  const onLaunch = useCallback(async () => {
    const parsedCeiling = Number(priceCeiling);
    const researchCount = plan === null ? 0 : subQuestions(plan.tree).length;
    if (
      !plan ||
      phase !== "ready" ||
      planMutationPending ||
      researchCount === 0 ||
      !ceilingApproved ||
      (spendMode === "hard_ceiling" && authorityDigest === null) ||
      !/^\d+(?:\.\d{1,2})?$/.test(priceCeiling) ||
      !Number.isFinite(parsedCeiling) ||
      parsedCeiling <= 0
    ) return;
    setPhase("launching");
    let approvalCompleted = false;
    try {
      // The glass-box gate: approve, then launch. approvePlan pins the
      // current (possibly trimmed) plan; launchPlan refuses anything not
      // approved. We approve-then-launch in one user action because the
      // door's affordance is a single "Start these researches" — the
      // human-in-the-loop trim already happened above.
      if (spendMode === "stop_limit") {
        await approvePlan(plan.rootNodeId);
      }
      approvalCompleted = true;
      const r = await launchPlan(
        plan.rootNodeId,
        spendMode === "hard_ceiling"
          ? {
              spend_mode: "hard_ceiling",
              hard_ceiling_usd: priceCeiling,
              authority_digest: authorityDigest!,
            }
           : { aggregate_budget_usd: parsedCeiling },
      );
      notifyResearchStarted(r.session_id);
      onLaunched(r.session_id);
    } catch (e) {
      setFailureStage(approvalCompleted ? "launch" : "approval");
      setFailure(classifyClientError(e));
      setPhase("ready");
    }
  }, [authorityDigest, ceilingApproved, onLaunched, phase, plan, planMutationPending, priceCeiling, spendMode]);

  const changeApproval = useCallback(
    async (checked: boolean) => {
      setCeilingApproved(false);
      setAuthorityDigest(null);
      setApprovedSessionId(null);
      if (!checked || !plan) return;
      if (spendMode === "stop_limit") {
        setCeilingApproved(true);
        return;
      }
      if (!hardPreview?.eligible) return;
      setPlanMutationPending(true);
      setFailure(null);
      try {
        await approvePlan(plan.rootNodeId);
        const approved = await approveSpend(plan.rootNodeId, priceCeiling);
        if (!approved.authority_digest) throw new Error("hard approval returned no authority");
        setAuthorityDigest(approved.authority_digest);
        setApprovedSessionId(approved.recovery_session_id ?? null);
        setHardPreview(approved);
        setCeilingApproved(true);
      } catch (error) {
        setFailureStage("approval");
        setFailure(classifyClientError(error));
      } finally {
        setPlanMutationPending(false);
      }
    },
    [hardPreview?.eligible, plan, priceCeiling, spendMode],
  );

  const retryFailure = useCallback(async () => {
    if (failureStage === "propose" || plan === null) {
      await propose();
      return;
    }
    setFailure(null);
    setPhase("recovering");
    try {
      if (failureStage === "edit" || failureStage === "approval") {
        const r = await getPlan(plan.rootNodeId);
        setPlan({ rootNodeId: r.root_node_id, tree: r.tree, launchable: r.launchable });
        setCeilingApproved(false);
        setAuthorityDigest(null);
        setApprovedSessionId(null);
        setPhase("ready");
        return;
      }
      if (
        spendMode === "hard_ceiling" &&
        approvedSessionId !== null &&
        authorityDigest !== null
      ) {
        const recovered = await launchPlan(plan.rootNodeId, {
          spend_mode: "hard_ceiling",
          hard_ceiling_usd: priceCeiling,
          authority_digest: authorityDigest,
        });
        onLaunched(recovered.session_id);
        return;
      }
      const sessionId =
        `session-${plan.rootNodeId}`;
      try {
        await getSession(sessionId);
        onLaunched(sessionId);
      } catch (e) {
        if (!(e instanceof ApiError) || e.status !== 404) throw e;
        const r = await getPlan(plan.rootNodeId);
        setPlan({ rootNodeId: r.root_node_id, tree: r.tree, launchable: r.launchable });
        setCeilingApproved(false);
        setAuthorityDigest(null);
        setApprovedSessionId(null);
        setPhase("ready");
      }
    } catch (e) {
      setFailure(classifyClientError(e));
      setPhase("ready");
    }
  }, [approvedSessionId, authorityDigest, failureStage, onLaunched, plan, priceCeiling, propose, spendMode]);

  // ── Proposing: the AI is breaking the problem down. ──
  if (phase === "proposing" || phase === "recovering") {
    return (
      <div className="flex flex-col items-center gap-3 py-8" role="status" aria-live="polite">
        <Thinking
          size={40}
          label={phase === "recovering" ? "Recovering authoritative research state" : "Breaking your question into sub-questions"}
        />
        <p className="text-sm font-serif text-ink-mute dark:text-moonlight">
          {phase === "recovering"
            ? "Checking what the research engine committed…"
            : "Working out the sub-questions to research in parallel…"}
        </p>
      </div>
    );
  }

  // ── Honest failure: no tree came back (most often: no provider keys). ──
  if (failure !== null) {
    return (
      <div className="flex flex-col gap-3 py-4">
        <AIActionFailure
          title={
            failureStage === "edit"
              ? "Couldn’t update the research plan"
              : failureStage === "approval"
                ? "Couldn’t approve the research plan"
              : failureStage === "launch"
                ? "Couldn’t start the research plan"
                : "Couldn’t break this into sub-questions"
          }
          code={failure.code}
          retryable={failure.retryable}
          reason={failure.message ?? null}
          onRetry={() => void retryFailure()}
          retryLabel={
            failureStage === "edit" || failureStage === "approval"
              ? "Reload plan"
              : failureStage === "launch"
                ? "Check launch status"
                : "Try again"
          }
        />
        <div>
          <LemonButton variant="tertiary" size="sm" onClick={onFallBackToAsk}>
            Ask it as one question instead
          </LemonButton>
        </div>
      </div>
    );
  }

  if (!plan) return null;

  const subs = subQuestions(plan.tree);
  const launchCount = subs.length;

  // The AI couldn't split it (an atomic question, or a thin result). Don't
  // pretend a cascade — offer the one-shot, which is exactly right for one
  // focused question.
  if (launchCount === 0) {
    return (
      <div className="flex flex-col gap-3 py-4">
        <p className="text-sm font-serif text-ink dark:text-bright">
          This looks like a single focused question — there’s nothing to break
          apart. Ask it directly.
        </p>
        <div className="flex gap-2">
          <LemonButton variant="primary" size="md" onClick={onFallBackToAsk}>
            Ask this question
          </LemonButton>
          <LemonButton variant="tertiary" size="sm" onClick={() => void propose()}>
            Try breaking it down again
          </LemonButton>
        </div>
      </div>
    );
  }

  const estimate =
    perResearchCost !== null
      ? `recommended $${(perResearchCost * launchCount).toFixed(2)} stop limit for ${launchCount} ${
          launchCount === 1 ? "research" : "researches"
        }`
      : null;
  const parsedCeiling = Number(priceCeiling);
  const ceilingValid =
    /^\d+(?:\.\d{1,2})?$/.test(priceCeiling) &&
    Number.isFinite(parsedCeiling) &&
    parsedCeiling > 0;
  const interactionLocked = planMutationPending || phase === "launching";

  // ── The proposed sub-questions: trim, edit, then launch. ──
  return (
    <div className="flex flex-col gap-4 py-2">
      <div>
        <p className="text-[11px] font-mono uppercase tracking-wider text-shadow-1 dark:text-moonlight mb-1">
          Proposed sub-questions
        </p>
        <p className="text-sm font-serif text-ink-mute dark:text-moonlight leading-relaxed">
          Each becomes its own research, running in parallel. Trim or reword
          anything before you start.
        </p>
      </div>

      <ul className="flex flex-col gap-1.5">
        {subs.map((sub) => (
          <li
            key={sub.local_id}
            className="group flex items-start gap-2 rounded-hog border border-rule dark:border-charcoal-1 bg-ice-0 dark:bg-charcoal-2 px-3 py-2"
          >
            {editing === sub.local_id ? (
              <form
                className="flex flex-1 gap-1.5"
                onSubmit={(e) => {
                  e.preventDefault();
                  const q = draft.trim();
                  if (q && q !== sub.question) {
                    void applyEdit({ op: "reword", target_local_id: sub.local_id, question: q });
                  }
                  setEditing(null);
                }}
              >
                <input
                  className="min-w-0 flex-1 rounded border border-rule dark:border-charcoal-1 bg-ice-1 dark:bg-charcoal-1 px-2 py-1 text-[13px] font-serif text-ink dark:text-bright"
                  value={draft}
                  onChange={(e) => setDraft(e.target.value)}
                  aria-label="Edit sub-question"
                  disabled={interactionLocked}
                  autoFocus
                />
                <LemonButton variant="primary" size="sm" type="submit" disabled={interactionLocked}>
                  Save
                </LemonButton>
              </form>
            ) : (
              <>
                <div className="flex-1 min-w-0">
                  <p className="text-[13px] font-serif text-ink dark:text-bright leading-relaxed">
                    {sub.question}
                  </p>
                  {/* The planner's REAL rationale for this sub-question — why it
                      chose to chase this thread. Rendered only when present
                      (the planner may omit it); never a placeholder. This is
                      the "why" half of the plan, sourced from planner output. */}
                  {sub.rationale?.trim() && (
                    <p className="mt-0.5 text-[11px] font-serif italic text-ink-mute dark:text-moonlight leading-snug">
                      {sub.rationale}
                    </p>
                  )}
                </div>
                <div className="flex shrink-0 gap-2 opacity-60 transition-opacity group-hover:opacity-100">
                  <button
                    type="button"
                    className="text-[11px] font-mono text-shadow-1 dark:text-moonlight hover:text-sun"
                    disabled={interactionLocked}
                    onClick={() => {
                      setDraft(sub.question);
                      setEditing(sub.local_id);
                    }}
                  >
                    edit
                  </button>
                  <button
                    type="button"
                    className="text-[11px] font-mono text-shadow-1 dark:text-moonlight hover:text-emperor"
                    disabled={interactionLocked}
                    onClick={() => void applyEdit({ op: "remove", target_local_id: sub.local_id })}
                  >
                    remove
                  </button>
                </div>
              </>
            )}
          </li>
        ))}
      </ul>

      <fieldset className="border-t border-rule pt-3 dark:border-charcoal-1">
        <legend className="text-[11px] font-mono uppercase text-shadow-1 dark:text-moonlight">
          Spend control
        </legend>
        <div
          aria-label="Spend control mode"
          className="mt-2 inline-grid grid-cols-2 border border-rule dark:border-charcoal-1"
          role="group"
        >
          <button
            aria-pressed={spendMode === "stop_limit"}
            className={`min-h-9 px-3 text-xs font-medium ${
              spendMode === "stop_limit"
                ? "bg-ink text-bright dark:bg-bright dark:text-ink"
                : "bg-ice-0 text-ink dark:bg-charcoal-2 dark:text-bright"
            }`}
            disabled={interactionLocked}
            onClick={() => {
              setSpendMode("stop_limit");
              setCeilingApproved(false);
              setAuthorityDigest(null);
              setApprovedSessionId(null);
            }}
            type="button"
          >
            Stop limit
          </button>
          <button
            aria-describedby="hard-ceiling-eligibility"
            aria-pressed={spendMode === "hard_ceiling"}
            className={`min-h-9 border-l border-rule px-3 text-xs font-medium dark:border-charcoal-1 ${
              spendMode === "hard_ceiling"
                ? "bg-ink text-bright dark:bg-bright dark:text-ink"
                : "bg-ice-0 text-ink disabled:text-ink-mute dark:bg-charcoal-2 dark:text-bright dark:disabled:text-moonlight"
            }`}
            disabled={interactionLocked || previewPending || hardPreview?.eligible !== true}
            onClick={() => {
              setSpendMode("hard_ceiling");
              setCeilingApproved(false);
              setAuthorityDigest(null);
              setApprovedSessionId(null);
            }}
            type="button"
          >
            Hard ceiling
          </button>
        </div>
        <p id="hard-ceiling-eligibility" className="mt-2 max-w-2xl text-xs text-ink-mute dark:text-moonlight">
          {previewPending
            ? "Checking whether every provider path can enforce a hard ceiling…"
            : hardPreview?.eligible
              ? "Available: every reachable paid request is bounded, send-once, and reconcilable in USD."
              : hardPreview?.reasons[0] ?? "Hard ceiling availability is determined by the research engine."}
        </p>
        <div className="mt-2 flex flex-wrap items-end gap-3">
          <label className="flex flex-col gap-1 text-xs font-medium text-ink dark:text-bright">
            {spendMode === "hard_ceiling" ? "Maximum Antiek may authorize" : "Stop after reported spend"}
            <span className="flex h-9 items-center border border-rule bg-ice-0 px-2 dark:border-charcoal-1 dark:bg-charcoal-2">
              <span aria-hidden="true" className="mr-1 text-ink-mute dark:text-moonlight">$</span>
              <input
                aria-describedby="aggregate-stop-limit-note"
                aria-invalid={!ceilingValid && priceCeiling !== ""}
                aria-label={spendMode === "hard_ceiling" ? "Authorized spend ceiling" : "Aggregate stop limit"}
                className="w-24 bg-transparent font-mono text-sm text-ink outline-none dark:text-bright"
                inputMode="decimal"
                min="0.01"
                step="0.01"
                type="number"
                value={priceCeiling}
                disabled={interactionLocked}
                onChange={(event) => {
                  setPriceCeiling(event.target.value);
                  setCeilingApproved(false);
                  setAuthorityDigest(null);
                  setApprovedSessionId(null);
                }}
              />
            </span>
          </label>
          <p className="pb-2 text-xs text-ink-mute dark:text-moonlight">
            {spendMode === "hard_ceiling"
              ? "Each paid request reserves its maximum before it is sent."
              : estimate ?? "Set when this plan should stop."}
          </p>
        </div>
        {!ceilingValid && priceCeiling !== "" && (
          <p className="mt-1 text-xs text-emperor" role="alert">
            Enter a positive amount with at most two decimal places.
          </p>
        )}
        <p id="aggregate-stop-limit-note" className="mt-2 text-xs text-ink-mute dark:text-moonlight">
          {spendMode === "hard_ceiling"
            ? "This bounds spend Antiek authorizes. Taxes, currency conversion, external fees, and provider misbilling are outside the guarantee and remain visible as breaches."
            : "Research stops after reported spend reaches this amount. Final in-flight steps can exceed it."}
        </p>
        <label className="mt-3 flex items-start gap-2 text-xs text-ink dark:text-bright">
          <input
            checked={ceilingApproved}
            className="mt-0.5 size-4 accent-sun"
            disabled={!ceilingValid || interactionLocked}
            onChange={(event) => void changeApproval(event.target.checked)}
            type="checkbox"
          />
          <span>
            I approve a {ceilingValid ? `$${parsedCeiling.toFixed(2)}` : "configured"} {spendMode === "hard_ceiling" ? "hard authorized-spend ceiling" : "aggregate stop limit"} for this exact plan.
          </span>
        </label>
      </fieldset>

      <div className="flex items-center justify-between gap-3">
        <p className="text-[11px] font-mono text-ink-mute dark:text-moonlight">
          {launchCount} {launchCount === 1 ? "research" : "researches"}
        </p>
        <div className="flex gap-2">
          <LemonButton variant="tertiary" size="sm" onClick={onFallBackToAsk} disabled={interactionLocked}>
            Ask one question instead
          </LemonButton>
          <LemonButton
            variant="primary"
            size="lg"
            onClick={() => void onLaunch()}
            disabled={interactionLocked || !ceilingApproved || !ceilingValid || (spendMode === "hard_ceiling" && authorityDigest === null)}
          >
            {phase === "launching"
              ? "Starting…"
              : `Start ${launchCount} ${launchCount === 1 ? "research" : "researches"}`}
          </LemonButton>
        </div>
      </div>
    </div>
  );
}
