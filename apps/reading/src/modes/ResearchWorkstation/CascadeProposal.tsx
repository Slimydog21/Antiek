import { useCallback, useEffect, useRef, useState } from "react";

import LemonButton from "../../components/lemon/LemonButton";
import AIActionFailure from "../../shared/AIActionFailure";
import Thinking from "../../shared/Thinking";
import {
  approvePlan,
  createPlan,
  editPlan,
  getBudgetDefaults,
  launchPlan,
  type PlanNode,
  type PlanTree,
} from "../../api/research";

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
  const [phase, setPhase] = useState<"proposing" | "ready" | "launching">("proposing");
  const [failed, setFailed] = useState<string | null>(null);
  // null until the failure carries no engine reason (the no-key case); a
  // string when the engine said why.
  const [editing, setEditing] = useState<string | null>(null);
  const [draft, setDraft] = useState("");
  const [perResearchCost, setPerResearchCost] = useState<number | null>(null);

  // Propose the tree once on mount (and on an explicit retry). A ref guards
  // React 18 StrictMode's double-invoke so we don't POST two plans.
  const proposedRef = useRef(false);

  const propose = useCallback(async () => {
    setPhase("proposing");
    setFailed(null);
    try {
      const r = await createPlan({ problem });
      setPlan({ rootNodeId: r.root_node_id, tree: r.tree, launchable: false });
      setPhase("ready");
    } catch (e) {
      // ApiError carries the HTTP body; we don't surface a stack trace. A
      // 5xx with the propose call almost always means the decomposer's model
      // provider isn't configured — let <AIActionFailure>'s no-reason branch
      // say that honestly rather than guessing here.
      setFailed("");
      setPhase("ready");
      void e;
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

  const applyEdit = useCallback(
    async (edit: { op: "remove" | "reword"; target_local_id: string; question?: string }) => {
      if (!plan) return;
      try {
        const r = await editPlan(plan.rootNodeId, edit);
        setPlan({ rootNodeId: r.root_node_id, tree: r.tree, launchable: r.launchable });
      } catch {
        // A failed edit leaves the prior tree on screen; the next action
        // re-reads authoritative state. No optimistic lie.
      }
    },
    [plan],
  );

  const onLaunch = useCallback(async () => {
    if (!plan) return;
    setPhase("launching");
    try {
      // The glass-box gate: approve, then launch. approvePlan pins the
      // current (possibly trimmed) plan; launchPlan refuses anything not
      // approved. We approve-then-launch in one user action because the
      // door's affordance is a single "Start these researches" — the
      // human-in-the-loop trim already happened above.
      await approvePlan(plan.rootNodeId);
      const r = await launchPlan(plan.rootNodeId);
      onLaunched(r.session_id);
    } catch {
      setFailed("");
      setPhase("ready");
    }
  }, [plan, onLaunched]);

  // ── Proposing: the AI is breaking the problem down. ──
  if (phase === "proposing") {
    return (
      <div className="flex flex-col items-center gap-3 py-8" role="status" aria-live="polite">
        <Thinking size={40} label="Breaking your question into sub-questions" />
        <p className="text-sm font-serif text-ink-mute dark:text-moonlight">
          Working out the sub-questions to research in parallel…
        </p>
      </div>
    );
  }

  // ── Honest failure: no tree came back (most often: no provider keys). ──
  if (failed !== null) {
    return (
      <div className="flex flex-col gap-3 py-4">
        <AIActionFailure
          title="Couldn’t break this into sub-questions"
          reason={failed || null}
          onRetry={() => void propose()}
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
      ? `estimated up to $${(perResearchCost * launchCount).toFixed(2)} for ${launchCount} ${
          launchCount === 1 ? "research" : "researches"
        }`
      : null;

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
                  autoFocus
                />
                <LemonButton variant="primary" size="sm" type="submit">
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

      <div className="flex items-center justify-between gap-3">
        <p className="text-[11px] font-mono text-ink-mute dark:text-moonlight">
          {launchCount} {launchCount === 1 ? "research" : "researches"}
          {estimate ? ` · ${estimate}` : ""}
        </p>
        <div className="flex gap-2">
          <LemonButton variant="tertiary" size="sm" onClick={onFallBackToAsk}>
            Ask one question instead
          </LemonButton>
          <LemonButton
            variant="primary"
            size="lg"
            onClick={() => void onLaunch()}
            disabled={phase === "launching"}
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
