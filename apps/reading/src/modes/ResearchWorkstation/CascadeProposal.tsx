import { useCallback, useEffect, useRef, useState } from "react";

import LemonButton from "../../components/lemon/LemonButton";
import AIActionFailure from "../../shared/AIActionFailure";
import {
  classifyClientError,
  type ClientFailureClassification,
} from "../../lib/api";
import Thinking from "../../shared/Thinking";
import {
  approvePlan,
  applyLegalPolicy,
  createPlan,
  dryRunLegalPolicy,
  editPlan,
  getBudgetDefaults,
  getCascadeDriverReadiness,
  getGatherStatus,
  launchPlan,
  listLegalPolicyDispatchLeases,
  getLaunchAttemptStatus,
  LaunchOutcomeUnknownError,
  revokeLegalPolicy,
  recoverLegalPolicyDispatchLease,
  type GatherStatus,
  type CascadeDriverReadiness,
  type LegalPolicyDispatchLease,
  type PlanNode,
  type PlanTree,
} from "../../api/research";
import {
  acquireCascadeLaunchAttempt,
  clearCascadeLaunchAttempt,
} from "../../workspace/cascadeLaunchAttempt";
import { DecisionTreeDriverBadge } from "../../components/engagement/DecisionTreeDriverBadge";
import {
  ResearchLaunchBudgetPanel,
  type ResearchLaunchTier,
} from "../../components/engagement/ResearchLaunchBudgetPanel";

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

function LegalPolicyEditor({ rootNodeId, onChanged }: { rootNodeId: string; onChanged: () => void }) {
  const [matcher, setMatcher] = useState("");
  const [citation, setCitation] = useState("");
  const [decision, setDecision] = useState<"allow" | "deny">("allow");
  const [previewed, setPreviewed] = useState<string | null>(null);
  const [receipt, setReceipt] = useState<{ eventId: string; matcher: string } | null>(null);
  const [busy, setBusy] = useState(false);
  const [message, setMessage] = useState<string | null>(null);
  const [leases, setLeases] = useState<LegalPolicyDispatchLease[]>([]);
  const attempt = useRef<string | null>(null);
  const recoveryAttempts = useRef(new Map<string, string>());
  const recoveriesInFlight = useRef(new Set<string>());
  const body = {
    matcher_kind: "domain" as const,
    matcher_value: matcher.trim(),
    decision,
    citation_ref: citation.trim(),
    issuer_id: "account-operator",
    reason_code: decision === "allow" ? "cited_account_allow" : "cited_account_deny",
  };
  const fingerprint = JSON.stringify(body);
  const ready = Boolean(body.matcher_value && body.citation_ref);

  const refreshLeases = useCallback(() => {
    void listLegalPolicyDispatchLeases(rootNodeId)
      .then((result) => setLeases(result.leases))
      .catch(() => setLeases([]));
  }, [rootNodeId]);
  useEffect(refreshLeases, [refreshLeases]);

  return (
    <details className="rounded-hog border border-rule dark:border-charcoal-1 p-3">
      <summary className="cursor-pointer text-xs font-mono">Manage cited retrieval policy</summary>
      <p className="mt-2 text-[11px] text-ink-mute dark:text-moonlight">
        A citation is evidence, not a lawyer-approval checkbox. Preview the exact account rule before applying it.
      </p>
      <div className="mt-2 grid gap-2 sm:grid-cols-[1fr_1fr_auto]">
        <input aria-label="Policy domain" placeholder="publication.example" value={matcher}
          onChange={(e) => { setMatcher(e.target.value); setPreviewed(null); attempt.current = null; }}
          className="rounded border border-rule bg-transparent px-2 py-1 text-xs" />
        <input aria-label="Policy citation" placeholder="License, terms, or decision reference" value={citation}
          onChange={(e) => { setCitation(e.target.value); setPreviewed(null); attempt.current = null; }}
          className="rounded border border-rule bg-transparent px-2 py-1 text-xs" />
        <select aria-label="Policy decision" value={decision}
          onChange={(e) => { setDecision(e.target.value as "allow" | "deny"); setPreviewed(null); attempt.current = null; }}
          className="rounded border border-rule bg-transparent px-2 py-1 text-xs">
          <option value="allow">Allow</option><option value="deny">Deny</option>
        </select>
      </div>
      <div className="mt-2 flex gap-2">
        <LemonButton size="sm" variant="secondary" disabled={!ready || busy} onClick={() => {
          setBusy(true); setMessage(null);
          void dryRunLegalPolicy(rootNodeId, body).then((p) => {
            setPreviewed(fingerprint);
            setMessage(p.would_append ? `Preview: append rule for ${p.normalized_matcher_value}.` : "Preview: an identical active decision already exists.");
          }).catch((e) => setMessage(e instanceof Error ? e.message : String(e))).finally(() => setBusy(false));
        }}>Preview</LemonButton>
        <LemonButton size="sm" variant="primary" disabled={!ready || busy || previewed !== fingerprint} onClick={() => {
          setBusy(true); setMessage(null); attempt.current ??= crypto.randomUUID();
          void applyLegalPolicy(rootNodeId, body, attempt.current).then((r) => {
            setReceipt({ eventId: r.event_id, matcher: body.matcher_value });
            setMessage(r.idempotency_replayed ? "Recovered the prior policy update." : "Cited policy update applied.");
            onChanged();
          }).catch((e) => setMessage(e instanceof Error ? e.message : String(e))).finally(() => setBusy(false));
        }}>Apply reviewed rule</LemonButton>
        {receipt && <LemonButton size="sm" variant="tertiary" disabled={busy} onClick={() => {
          setBusy(true); setMessage(null);
          void revokeLegalPolicy(rootNodeId, {
            event_id: receipt.eventId, matcher_kind: "domain", matcher_value: receipt.matcher,
            citation_ref: `${body.citation_ref}:revoke`, issuer_id: body.issuer_id,
            reason_code: "account_policy_revoked",
          }, crypto.randomUUID()).then(() => {
            setReceipt(null); setPreviewed(null); attempt.current = null;
            setMessage("Policy event revoked."); onChanged();
          }).catch((e) => setMessage(e instanceof Error ? e.message : String(e))).finally(() => setBusy(false));
        }}>Revoke applied rule</LemonButton>}
      </div>
      {leases.length > 0 && (
        <div className="mt-3 border-t border-rule pt-2" data-testid="policy-dispatch-leases">
          <p className="text-[11px] font-mono">Provider dispatch recovery</p>
          {leases.map((lease) => (
            <div key={lease.lease_id} className="mt-1 flex items-center justify-between gap-2 text-[11px]">
              <span>{lease.recovery_state === "terminal_recoverable"
                ? `Terminal evidence: ${lease.terminal_action}`
                : lease.recovery_state === "active"
                  ? "Active — elapsed time cannot release this lease"
                  : "Recovery evidence unavailable"}</span>
              {lease.recovery_state === "terminal_recoverable" && (
                <LemonButton size="sm" variant="secondary" disabled={busy} onClick={() => {
                  if (recoveriesInFlight.current.has(lease.lease_id)) return;
                  recoveriesInFlight.current.add(lease.lease_id);
                  setBusy(true); setMessage(null);
                  const key = recoveryAttempts.current.get(lease.lease_id) ?? crypto.randomUUID();
                  recoveryAttempts.current.set(lease.lease_id, key);
                  void recoverLegalPolicyDispatchLease(rootNodeId, lease.lease_id, key)
                    .then((result) => {
                      setMessage(result.idempotency_replayed
                        ? "Recovered the prior terminal lease cleanup."
                        : "Terminal provider lease recovered.");
                      refreshLeases(); onChanged();
                    })
                    .catch((e) => setMessage(e instanceof Error ? e.message : String(e)))
                    .finally(() => {
                      recoveriesInFlight.current.delete(lease.lease_id);
                      setBusy(false);
                    });
                }}>Recover terminal run</LemonButton>
              )}
            </div>
          ))}
        </div>
      )}
      {message && <p role="status" className="mt-2 text-[11px] font-mono">{message}</p>}
    </details>
  );
}

export default function CascadeProposal({ problem, onLaunched, onFallBackToAsk }: Props) {
  const [plan, setPlan] = useState<PlanState | null>(null);
  // Phase gates the human-in-the-loop: a plan block is editable ONLY once
  // phase === "ready" (after createPlan resolves), so an edit can NEVER race the
  // planner while it is still proposing (the spec's rigor-#3 edit-while-streaming
  // edge — handled by construction, not left as a free-for-all).
  const [phase, setPhase] = useState<"proposing" | "ready" | "launching">("proposing");
  const [failure, setFailure] = useState<ClientFailureClassification | null>(
    null,
  );
  const [launchFailure, setLaunchFailure] = useState<ClientFailureClassification | null>(null);
  const [unknownLaunchSession, setUnknownLaunchSession] = useState<string | null>(null);
  const [editing, setEditing] = useState<string | null>(null);
  const [draft, setDraft] = useState("");
  const [perResearchCost, setPerResearchCost] = useState<number | null>(null);
  const [gather, setGather] = useState<GatherStatus | null>(null);
  const [gatherUnavailable, setGatherUnavailable] = useState(false);
  const [stubAcknowledged, setStubAcknowledged] = useState(false);
  const [researchTier, setResearchTier] = useState<ResearchLaunchTier>("deep");
  const [driverReadiness, setDriverReadiness] = useState<CascadeDriverReadiness | null>(null);
  const [unknownLaunchInspectable, setUnknownLaunchInspectable] = useState(false);

  // Propose the tree once on mount (and on an explicit retry). A ref guards
  // React 18 StrictMode's double-invoke so we don't POST two plans.
  const proposedRef = useRef(false);
  // React state updates are asynchronous; this closes the same-tick double
  // activation window before a paid launch request can be dispatched twice.
  const launchInFlight = useRef(false);
  // Retained across an ambiguous failure so a user retry recovers the same
  // durable server attempt instead of purchasing another session.
  const launchAttemptKey = useRef<string | null>(null);
  const approvedForLaunchAttempt = useRef(false);

  const propose = useCallback(async () => {
    setPhase("proposing");
    setFailure(null);
    try {
      const r = await createPlan({ problem });
      launchAttemptKey.current = null;
      approvedForLaunchAttempt.current = false;
      setUnknownLaunchSession(null);
      setUnknownLaunchInspectable(false);
      setPlan({ rootNodeId: r.root_node_id, tree: r.tree, launchable: false });
      setGatherUnavailable(false);
      void getGatherStatus(r.root_node_id)
        .then(setGather)
        .catch(() => {
          setGather(null);
          setGatherUnavailable(true);
        });
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
    if (!plan || launchAttemptKey.current === null) return;
    clearCascadeLaunchAttempt(plan.rootNodeId);
    launchAttemptKey.current = null;
    approvedForLaunchAttempt.current = false;
  }, [plan, gather?.gather_mode, stubAcknowledged, researchTier]);

  useEffect(() => {
    let active = true;
    setDriverReadiness(null);
    void getCascadeDriverReadiness(researchTier)
      .then((value) => { if (active) setDriverReadiness(value); })
      .catch(() => { if (active) setDriverReadiness(null); });
    return () => { active = false; };
  }, [researchTier]);

  const applyEdit = useCallback(
    async (edit: { op: "remove" | "reword"; target_local_id: string; question?: string }) => {
      if (!plan || launchInFlight.current || phase === "launching") return;
      try {
        const r = await editPlan(plan.rootNodeId, edit);
        clearCascadeLaunchAttempt(plan.rootNodeId);
        launchAttemptKey.current = null;
        approvedForLaunchAttempt.current = false;
        setUnknownLaunchSession(null);
        setUnknownLaunchInspectable(false);
        setPlan({ rootNodeId: r.root_node_id, tree: r.tree, launchable: r.launchable });
      } catch {
        // A failed edit leaves the prior tree on screen; the next action
        // re-reads authoritative state. No optimistic lie.
      }
    },
    [plan, phase],
  );

  const onLaunch = useCallback(async () => {
    if (launchInFlight.current) return;
    if (!plan || !gather || !gather.launch_ready || !driverReadiness?.ready || driverReadiness.research_tier !== researchTier) return;
    if (gather.stub_requires_acknowledgment && !stubAcknowledged) return;
    launchInFlight.current = true;
    setLaunchFailure(null);
    setPhase("launching");
    try {
      // The glass-box gate: approve, then launch. approvePlan pins the
      // current (possibly trimmed) plan; launchPlan refuses anything not
      // approved. We approve-then-launch in one user action because the
      // door's affordance is a single "Start these researches" — the
      // human-in-the-loop trim already happened above.
      launchAttemptKey.current ??= acquireCascadeLaunchAttempt(plan.rootNodeId, {
        planVersion: plan.tree.approval.plan_version,
        gatherMode: gather.gather_mode,
        gatherPlanFingerprint: gather.reviewed_gather_plan?.fingerprint ?? null,
        allowContractStub: gather.gather_mode === "contract_stub" && stubAcknowledged,
        researchTier,
      });
      if (!approvedForLaunchAttempt.current) {
        await approvePlan(plan.rootNodeId);
        approvedForLaunchAttempt.current = true;
      }
      const r = await launchPlan(plan.rootNodeId, {
        expected_gather_mode: gather.gather_mode,
        expected_gather_plan_fingerprint: gather.reviewed_gather_plan?.fingerprint ?? null,
        allow_contract_stub: gather.gather_mode === "contract_stub" && stubAcknowledged,
        research_tier: researchTier,
      }, launchAttemptKey.current);
      clearCascadeLaunchAttempt(plan.rootNodeId);
      launchAttemptKey.current = null;
      approvedForLaunchAttempt.current = false;
      onLaunched(r.session_id);
    } catch (e) {
      if (e instanceof LaunchOutcomeUnknownError) {
        setUnknownLaunchSession(e.sessionId);
        setUnknownLaunchInspectable(false);
        const key = launchAttemptKey.current;
        if (key !== null) {
          try {
            const attempt = await getLaunchAttemptStatus(plan.rootNodeId, key);
            if (attempt.session_id === e.sessionId && attempt.action === "inspect_session") {
              setUnknownLaunchInspectable(true);
            }
          } catch {
            // Retain the non-retry hold. Failure to reconcile is never evidence
            // that another launch is safe.
          }
        }
        setPhase("ready");
        return;
      }
      // Keep the reviewed plan and attempt key. Retrying this action must ask
      // the server to recover the same durable attempt, not create a new one.
      setLaunchFailure(classifyClientError(e));
      setPhase("ready");
    } finally {
      launchInFlight.current = false;
    }
  }, [plan, gather, stubAcknowledged, researchTier, driverReadiness, onLaunched]);

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
  if (failure !== null) {
    return (
      <div className="flex flex-col gap-3 py-4">
        <AIActionFailure
          title="Couldn’t break this into sub-questions"
          code={failure.code}
          retryable={failure.retryable}
          reason={failure.message ?? null}
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

      <DecisionTreeDriverBadge researchTier={researchTier} promptText={problem} />
      <ResearchLaunchBudgetPanel
        promptText={problem}
        researchTier={researchTier}
        allowTierPick
        onResearchTierChange={setResearchTier}
      />
      <p
        className="rounded border border-rule px-3 py-2 text-xs font-mono"
        role="status"
        data-testid="cascade-driver-readiness"
      >
        {driverReadiness === null || driverReadiness.research_tier !== researchTier
          ? "Checking boot-attested model availability…"
          : driverReadiness.ready
            ? `Launch target: ${driverReadiness.provider}/${driverReadiness.model} · candidate ${driverReadiness.candidate_rank}`
            : `Launch locked: ${driverReadiness.reason}`}
      </p>

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
                    disabled={phase === "launching"}
                  >
                    edit
                  </button>
                  <button
                    type="button"
                    className="text-[11px] font-mono text-shadow-1 dark:text-moonlight hover:text-emperor"
                    onClick={() => void applyEdit({ op: "remove", target_local_id: sub.local_id })}
                    disabled={phase === "launching"}
                  >
                    remove
                  </button>
                </div>
              </>
            )}
          </li>
        ))}
      </ul>

      <LegalPolicyEditor
        rootNodeId={plan.rootNodeId}
        onChanged={() => {
          setGather(null);
          void getGatherStatus(plan.rootNodeId)
            .then(setGather)
            .catch(() => setGatherUnavailable(true));
        }}
      />

      <div
        className="rounded-hog border border-rule dark:border-charcoal-1 bg-ice-1 dark:bg-charcoal-1 p-3 text-xs"
        role="status"
        data-testid="gather-launch-truth"
        data-gather-mode={gather?.gather_mode || "unverified"}
        data-production-defensible={gather?.production_defensible ? "true" : "false"}
      >
        {gatherUnavailable ? (
          <p>Retrieval readiness could not be verified · launch remains locked.</p>
        ) : !gather ? (
          <p>Checking retrieval readiness…</p>
        ) : gather.gather_mode === "contract_stub" ? (
          <label className="flex items-start gap-2">
            <input type="checkbox" checked={stubAcknowledged} onChange={(event) => setStubAcknowledged(event.target.checked)} />
            <span>No network evidence will be retrieved. I explicitly accept a contract-stub run.</span>
          </label>
        ) : gather.gather_mode === "authorized_multi_source" ? (
          <p>Reviewed multi-source gather: {gather.reviewed_gather_plan?.sources.join(", ") || "configuration unavailable"} · {gather.reviewed_gather_plan ? `maximum $${(gather.reviewed_gather_plan.launch_max_cost_micros / 1_000_000).toFixed(3)} across ${gather.reviewed_gather_plan.leaf_count} researches` : "launch locked"} · execution {gather.multi_source_execution_activated ? "ready" : "not yet activated"}. Partial evidence will remain visibly partial.</p>
        ) : gather.production_defensible ? (
          <p>Exa network retrieval ready · exact durable SQL policy snapshot will be pinned through dispatch.</p>
        ) : (
          <p>Exa configured but locked · {gather.legal_policy.reason_code || "durable legal-policy readiness is incomplete"}.</p>
        )}
      </div>

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
            disabled={phase === "launching" || Boolean(unknownLaunchSession) || !gather?.launch_ready || !driverReadiness?.ready || driverReadiness.research_tier !== researchTier || (gather.stub_requires_acknowledgment && !stubAcknowledged)}
          >
            {phase === "launching"
              ? "Starting…"
              : `Start ${launchCount} ${launchCount === 1 ? "research" : "researches"}`}
          </LemonButton>
        </div>
      </div>
      {launchFailure && (
        <AIActionFailure
          title="Research launch needs attention"
          code={launchFailure.code}
          retryable={launchFailure.retryable}
          reason={launchFailure.message ?? null}
          onRetry={() => void onLaunch()}
        />
      )}
      {unknownLaunchSession && (
        <div role="alert" className="text-xs font-mono text-emperor flex flex-col gap-2">
          <p>The prior launch may already be running. Antiek will not dispatch it again automatically.</p>
          {unknownLaunchInspectable ? <div>
            <LemonButton variant="secondary" size="sm" onClick={() => onLaunched(unknownLaunchSession)}>
              Inspect existing session
            </LemonButton>
          </div> : <p>Durable session evidence is not yet available. Operator reconciliation is required.</p>}
        </div>
      )}
    </div>
  );
}
