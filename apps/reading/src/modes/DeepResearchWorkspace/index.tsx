/**
 * DRW SPR-09 — the glass-box workspace: edit a cascade plan, launch N
 * researches at once, and watch every one live as a steerable panel with a
 * session-aggregate cost meter. The product's hero moment.
 *
 * Density strategy (M3, justified): the N researches render as a responsive
 * CSS grid of cards, not N floating workspace panels — 20 floating panels
 * would be an unmanageable wall; a grid gives overview + per-card focus and
 * scrolls. (A windowing/virtualization pass is the documented next step past
 * ~50 cards; below that a plain grid is jank-free.)
 *
 * Liveness (M4): `useResearchSession` polls SPR-06's durable status endpoint,
 * so reconnect/resume after a dropped poll or a server restart is free.
 *
 * §16 honored: concurrency is whatever the host-local runner allows; we show
 * the researches the backend launched and surface the aggregate cap — we do
 * not reach for Daytona.
 */

import { useCallback, useEffect, useRef, useState } from "react";
import { useParams } from "react-router-dom";

import { PanelHost } from "../../workspace/PanelHost";
import type { StarterPanel } from "../../workspace/PanelHost";
import LemonButton from "../../components/lemon/LemonButton";
import {
  approvePlan,
  createPlan,
  editPlan,
  getPlan,
  getGatherStatus,
  getCascadeDriverReadiness,
  launchPlan,
  LaunchOutcomeUnknownError,
  steerResearch,
  type PlanTree,
  type GatherStatus,
  type SteerKind,
  type CascadeDriverReadiness,
} from "../../api/research";
import {
  acquireCascadeLaunchAttempt,
  clearCascadeLaunchAttempt,
} from "../../workspace/cascadeLaunchAttempt";
import { track } from "../../lib/analytics";
import type { DistilledNode } from "../../lib/api";
import CostMeter from "./CostMeter";
import PlanEditor from "./PlanEditor";
import ResearchPanel from "./ResearchPanel";
import Canvas from "./Canvas/Canvas";
import BlockDetail from "./BlockDetail";
import { useResearchSession } from "./useResearchSession";
import { DecisionTreeDriverBadge } from "../../components/engagement/DecisionTreeDriverBadge";
import {
  ResearchLaunchBudgetPanel,
  type ResearchLaunchTier,
} from "../../components/engagement/ResearchLaunchBudgetPanel";

interface PlanState {
  rootNodeId: string;
  tree: PlanTree;
  launchable: boolean;
}

const NO_STARTERS: StarterPanel[] = [];

export default function DeepResearchWorkspace() {
  return (
    <PanelHost starters={NO_STARTERS}>
      <Workspace />
    </PanelHost>
  );
}

function Workspace() {
  // A :sessionId in the route means we arrived from a launch elsewhere (the
  // Research-entry cascade). Open straight onto the live monitor — the
  // session's status is durable, so the monitor reconstructs it from the
  // event log even if this process never held the in-memory session.
  const { sessionId: routeSessionId } = useParams<{ sessionId?: string }>();
  const [problem, setProblem] = useState("");
  const [plan, setPlan] = useState<PlanState | null>(null);
  const [sessionId, setSessionId] = useState<string | null>(routeSessionId ?? null);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [gather, setGather] = useState<GatherStatus | null>(null);
  const [stubAcknowledged, setStubAcknowledged] = useState(false);
  const [researchTier, setResearchTier] = useState<ResearchLaunchTier>("deep");
  const [driverReadiness, setDriverReadiness] = useState<CascadeDriverReadiness | null>(null);
  const launchInFlight = useRef(false);
  const launchAttemptKey = useRef<string | null>(null);

  useEffect(() => {
    if (!plan) {
      setGather(null);
      return;
    }
    let active = true;
    setGather(null);
    void getGatherStatus(plan.rootNodeId)
      .then((value) => { if (active) setGather(value); })
      .catch(() => { if (active) setGather(null); });
    return () => { active = false; };
  }, [plan?.rootNodeId]);

  useEffect(() => {
    if (!plan || launchAttemptKey.current === null) return;
    clearCascadeLaunchAttempt(plan.rootNodeId);
    launchAttemptKey.current = null;
  }, [plan, gather?.gather_mode, stubAcknowledged, researchTier]);

  useEffect(() => {
    let active = true;
    setDriverReadiness(null);
    void getCascadeDriverReadiness(researchTier)
      .then((value) => { if (active) setDriverReadiness(value); })
      .catch(() => { if (active) setDriverReadiness(null); });
    return () => { active = false; };
  }, [researchTier]);

  const guard = useCallback(async (fn: () => Promise<void>) => {
    setBusy(true);
    setError(null);
    try {
      await fn();
    } catch (e) {
      setError(e instanceof Error ? e.message : String(e));
    } finally {
      setBusy(false);
    }
  }, []);

  const handleCreate = () =>
    guard(async () => {
      const q = problem.trim();
      if (!q) return;
      if (plan) clearCascadeLaunchAttempt(plan.rootNodeId);
      const r = await createPlan({ problem: q });
      launchAttemptKey.current = null;
      track("deep_research_cascade_created", {
        problem_length: q.length,
      });
      setPlan({ rootNodeId: r.root_node_id, tree: r.tree, launchable: false });
      setSessionId(null);
    });

  const handleEdit = (edit: { op: "add_child" | "remove" | "reword"; target_local_id: string; question?: string }) =>
    guard(async () => {
      if (!plan) return;
      const r = await editPlan(plan.rootNodeId, edit);
      clearCascadeLaunchAttempt(plan.rootNodeId);
      launchAttemptKey.current = null;
      setPlan({ rootNodeId: r.root_node_id, tree: r.tree, launchable: r.launchable });
    });

  const handleApprove = () =>
    guard(async () => {
      if (!plan) return;
      await approvePlan(plan.rootNodeId);
      clearCascadeLaunchAttempt(plan.rootNodeId);
      launchAttemptKey.current = null;
      const r = await getPlan(plan.rootNodeId); // refresh tree + launchable
      track("deep_research_plan_approved");
      setPlan({ rootNodeId: r.root_node_id, tree: r.tree, launchable: r.launchable });
    });

  const handleLaunch = () =>
    guard(async () => {
      if (launchInFlight.current) return;
      if (!plan || !plan.launchable || !gather?.launch_ready || !driverReadiness?.ready || driverReadiness.research_tier !== researchTier) return;
      if (gather.stub_requires_acknowledgment && !stubAcknowledged) return;
      launchInFlight.current = true;
      try {
        launchAttemptKey.current ??= acquireCascadeLaunchAttempt(plan.rootNodeId, {
          planVersion: plan.tree.approval.plan_version,
          gatherMode: gather.gather_mode,
          gatherPlanFingerprint: gather.reviewed_gather_plan?.fingerprint ?? null,
          allowContractStub: gather.gather_mode === "contract_stub" && stubAcknowledged,
          researchTier,
        });
        let r;
        try {
          r = await launchPlan(plan.rootNodeId, {
            expected_gather_mode: gather.gather_mode,
            expected_gather_plan_fingerprint: gather.reviewed_gather_plan?.fingerprint ?? null,
            allow_contract_stub: gather.gather_mode === "contract_stub" && stubAcknowledged,
            research_tier: researchTier,
          }, launchAttemptKey.current);
        } catch (error) {
          if (error instanceof LaunchOutcomeUnknownError) {
            setSessionId(error.sessionId);
            return;
          }
          throw error;
        }
        clearCascadeLaunchAttempt(plan.rootNodeId);
        launchAttemptKey.current = null;
        track("deep_research_cascade_launched", {
          session_id: r.session_id,
        });
        setSessionId(r.session_id);
      } finally {
        launchInFlight.current = false;
      }
    });

  return (
    <div className="flex h-full flex-col gap-4 overflow-auto p-4">
      <ComposeBar problem={problem} setProblem={setProblem} busy={busy} onCreate={handleCreate} />
      {error && (
        <p className="rounded border border-emperor/40 bg-emperor/5 px-3 py-2 text-sm text-emperor">{error}</p>
      )}
      {plan && (
        <>
          <DecisionTreeDriverBadge researchTier={researchTier} promptText={problem} />
          <ResearchLaunchBudgetPanel
            promptText={problem}
            researchTier={researchTier}
            allowTierPick
            onResearchTierChange={setResearchTier}
          />
          <p className="rounded border border-rule p-2 text-xs font-mono" role="status">
            {driverReadiness === null || driverReadiness.research_tier !== researchTier
              ? "Checking boot-attested model availability…"
              : driverReadiness.ready
                ? `Launch target: ${driverReadiness.provider}/${driverReadiness.model} · candidate ${driverReadiness.candidate_rank}`
                : `Launch locked: ${driverReadiness.reason}`}
          </p>
          <PlanEditor
            tree={plan.tree}
            launchable={plan.launchable && Boolean(gather?.launch_ready) && Boolean(driverReadiness?.ready) && driverReadiness?.research_tier === researchTier && (!gather?.stub_requires_acknowledgment || stubAcknowledged)}
            busy={busy}
            onEdit={handleEdit}
            onApprove={handleApprove}
            onLaunch={handleLaunch}
          />
          <div className="rounded border border-rule p-2 text-xs" role="status" data-testid="workspace-gather-truth">
            {!gather ? "Retrieval readiness unverified · launch locked." : gather.gather_mode === "contract_stub" ? (
              <label className="flex gap-2"><input type="checkbox" checked={stubAcknowledged} onChange={(event) => setStubAcknowledged(event.target.checked)} />No network evidence will be retrieved; explicitly allow contract-stub launch.</label>
            ) : gather.gather_mode === "authorized_multi_source" ? (
              <span>Multi-source review: {gather.reviewed_gather_plan?.sources.join(", ") || "configuration unavailable"} · {gather.reviewed_gather_plan ? `launch ceiling $${(gather.reviewed_gather_plan.launch_max_cost_micros / 1_000_000).toFixed(3)}` : "launch locked"} · execution {gather.multi_source_execution_activated ? "ready" : "not yet activated"}. This is not labeled comprehensive until evidence receipts complete.</span>
            ) : gather.production_defensible ? "Exa retrieval ready · exact durable SQL policy snapshot will be pinned through dispatch." : `Exa configured but locked · ${gather.legal_policy.reason_code || "durable legal-policy readiness is incomplete"}.`}
          </div>
        </>
      )}
      {sessionId && <Monitor sessionId={sessionId} busy={busy} />}
    </div>
  );
}

function ComposeBar({
  problem, setProblem, busy, onCreate,
}: {
  problem: string;
  setProblem: (v: string) => void;
  busy: boolean;
  onCreate: () => void;
}) {
  return (
    <form
      className="flex gap-2"
      onSubmit={(e) => { e.preventDefault(); onCreate(); }}
    >
      <input
        className="min-w-0 flex-1 rounded-md border-2 border-sun bg-ice-0 px-3 py-2 text-sm text-ink dark:bg-charcoal-2 dark:text-bright"
        placeholder="State one problem — it cascades into focused, steerable deep researches…"
        value={problem}
        onChange={(e) => setProblem(e.target.value)}
        aria-label="research problem"
      />
      <LemonButton variant="primary" type="submit" disabled={busy || !problem.trim()}>
        Cascade
      </LemonButton>
    </form>
  );
}

function Monitor({ sessionId, busy }: { sessionId: string; busy: boolean }) {
  const session = useResearchSession(sessionId);
  const [steering, setSteering] = useState<string | null>(null);
  // SPR-03: the "organism" canvas branch. When set to a completed
  // investigation id, the monitor swaps the live-card grid for the
  // block-canvas view of that research's insight/question graph. Null = the
  // default live-card monitor (non-breaking: the existing shell is unchanged
  // until the operator opts into the canvas).
  const [canvasFor, setCanvasFor] = useState<string | null>(null);
  // SPR-04: the block whose detail (the SECOND FloatMenu host) is open, or null.
  // Clicking a BlockCard on the canvas opens its detail as an overlay panel —
  // a highlight inside it mounts the SAME shared FloatMenu the synthesis host
  // uses. Non-breaking: the canvas keeps rendering underneath; the detail is an
  // overlay, dismissed back to the canvas.
  const [openNode, setOpenNode] = useState<DistilledNode | null>(null);

  const steer = (iid: string) => async (kind: SteerKind, payload?: Record<string, unknown>) => {
    setSteering(iid);
    try {
      await steerResearch(sessionId, iid, kind, payload);
    } catch {
      // The next poll reflects the authoritative state; a failed steer is
      // surfaced by the research not changing — no optimistic lie.
    } finally {
      setSteering(null);
    }
  };

  // Connecting: arrived on a session (e.g. a fresh launch from the Research
  // entry) before the first status poll has resolved. Show an honest
  // connecting state rather than a bare "0 researches".
  if (session.loading && session.researches.length === 0) {
    return (
      <div className="flex flex-col items-center gap-2 py-8" role="status" aria-live="polite">
        <p className="text-sm font-serif text-ink dark:text-bright">Connecting to your researches…</p>
        <p className="text-[11px] font-mono text-shadow-1 dark:text-moonlight">
          they’re starting in parallel
        </p>
      </div>
    );
  }

  // SPR-03: render the organism canvas for the chosen completed research.
  if (canvasFor) {
    return (
      <div className="flex h-full flex-col gap-2">
        <div className="flex items-center gap-3">
          <LemonButton variant="tertiary" size="sm" onClick={() => setCanvasFor(null)}>
            ← back to monitor
          </LemonButton>
          <span className="font-mono text-[11px] text-shadow-1 dark:text-moonlight">
            organism canvas
          </span>
        </div>
        <div className="relative min-h-[480px] flex-1 overflow-hidden rounded-hog border-edge border-sun">
          <Canvas investigationId={canvasFor} onOpenDetail={setOpenNode} />
          {/* SPR-04: the block detail is the SECOND live FloatMenu host. It
              opens off a BlockCard click as an overlay over the canvas (the
              canvas stays mounted underneath — non-breaking) and dismisses
              back to it. A text selection inside it mounts the SAME FloatMenu. */}
          {openNode && (
            <div className="absolute inset-0 z-10 overflow-auto bg-ice-0 dark:bg-charcoal-1">
              <BlockDetail
                node={openNode}
                investigationId={canvasFor}
                onClose={() => setOpenNode(null)}
              />
            </div>
          )}
        </div>
      </div>
    );
  }

  return (
    <div className="flex flex-col gap-3">
      <div className="flex items-center justify-between gap-4">
        <h2 className="text-sm font-semibold text-ink dark:text-bright">
          {session.researches.length} researches
          {!session.allTerminal && session.researches.length > 0 && (
            <span className="ml-2 text-[11px] font-normal text-aurora">live</span>
          )}
          {session.allTerminal && (
            <span className="ml-2 text-[11px] font-normal text-shadow-1 dark:text-moonlight">complete</span>
          )}
        </h2>
        <div className="flex items-center gap-3">
          {/* SPR-03 entry: open the first completed research as the organism
              canvas. A completed research's insight/question graph is the
              durable product the canvas lays out. */}
          {session.researches.some((r) => r.state === "done") && (
            <LemonButton
              variant="tertiary"
              size="sm"
              onClick={() => {
                const done = session.researches.find((r) => r.state === "done");
                if (done) {
                  track("deep_research_canvas_opened", { investigation_id: done.investigation_id });
                  setCanvasFor(done.investigation_id);
                }
              }}
            >
              view as canvas
            </LemonButton>
          )}
          <div className="w-64"><CostMeter cost={session.cost} /></div>
        </div>
      </div>
      {session.error && (
        <p className="text-[11px] text-shadow-1 dark:text-moonlight">reconnecting… ({session.error})</p>
      )}
      {session.gatherReports.length > 0 && (
        <section className="rounded border border-rule p-3" aria-label="Durable gather reports">
          <div className="mb-2 flex items-center justify-between gap-3">
            <h3 className="text-xs font-semibold text-ink dark:text-bright">Evidence receipts</h3>
            <span className="font-mono text-[10px] text-shadow-1 dark:text-moonlight">
              {session.gatherReports.filter((report) => report.evidence_complete).length}/{session.researches.length} evidence-complete
            </span>
          </div>
          <div className="grid gap-2 sm:grid-cols-2">
            {session.gatherReports.map((report) => (
              <div key={report.investigation_id} className="rounded border border-rule/70 p-2 text-[11px]">
                <p className="font-mono text-shadow-1 dark:text-moonlight">{report.investigation_id}</p>
                <p className={report.unknown_outcome ? "text-emperor" : report.evidence_complete ? "text-aurora" : "text-shadow-1"}>
                  {report.unknown_outcome ? "Outcome unknown · reconciliation required" : report.evidence_complete ? report.partial ? "Evidence complete · partial source coverage" : "Evidence complete" : "Minimum evidence not met"}
                </p>
                <ul className="mt-1 grid grid-cols-2 gap-x-2">
                  {report.receipts.map((receipt) => (
                    <li key={receipt.source}>{receipt.source}: {receipt.status} ({receipt.document_ids.length})</li>
                  ))}
                </ul>
              </div>
            ))}
          </div>
        </section>
      )}
      {session.gatherReportErrors.length > 0 && (
        <p className="rounded border border-emperor/40 bg-emperor/5 px-3 py-2 text-xs text-emperor" role="alert">
          Evidence receipt verification failed for {session.gatherReportErrors.map((error) => error.investigation_id).join(", ")}. This research is not evidence-complete; inspect the authenticated trajectory before retrying.
        </p>
      )}
      <div className="grid grid-cols-1 gap-3 sm:grid-cols-2 lg:grid-cols-3 xl:grid-cols-4">
        {session.researches.map((r) => (
          <ResearchPanel
            key={r.investigation_id}
            research={r}
            costUsd={session.cost?.per_research[r.investigation_id] ?? 0}
            busy={busy || steering === r.investigation_id}
            onSteer={steer(r.investigation_id)}
          />
        ))}
      </div>
    </div>
  );
}
