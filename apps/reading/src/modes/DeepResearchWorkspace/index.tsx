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

import { lazy, Suspense, useCallback, useEffect, useRef, useState, type ReactNode, type RefObject } from "react";
import { useParams } from "react-router-dom";

import { PanelHost } from "../../workspace/PanelHost";
import type { StarterPanel } from "../../workspace/PanelHost";
import LemonButton from "../../components/lemon/LemonButton";
import { openWindow } from "../../components/windows/openWindow";
import missionControlEnvironment from "../../brand/werner/research/deep_research_mission_control_v1.webp";
import {
  approvePlan,
  createPlan,
  editPlan,
  getPlan,
  launchPlan,
  steerResearch,
  TERMINAL_STATES,
  type PlanTree,
  type SteerKind,
} from "../../api/research";
import { track } from "../../lib/analytics";
import type { DistilledNode } from "../../lib/api";
import { DEFAULT_WINDOW_RECT } from "../../workspace/windowsStore";
import CostMeter from "./CostMeter";
import HardCeilingEvidence from "./HardCeilingEvidence";
import PlanEditor from "./PlanEditor";
import ResearchPanel from "./ResearchPanel";
import Canvas from "./Canvas/Canvas";
import {
  anchorRelativeToLayer,
  chooseAdjacentWindowRect,
  type AnchorRect,
} from "./Canvas/adjacentWindowPlacement";
import BlockDetail from "./BlockDetail";
import { useResearchSession } from "./useResearchSession";
import { useWernerResearchReactions } from "./useWernerResearchReactions";
import { emitWernerExperience, notifyResearchStarted } from "../../werner";
import { wernerResearchWaitArcadeEnabled } from "../../arcade/waitArcadeFlag";
import { usePrefersReducedMotion } from "../../workspace/usePrefersReducedMotion";
import "./deep-research-mission-control.css";

const LazyResearchWaitArcade = lazy(() => import("./ResearchWaitArcade"));

interface PlanState {
  rootNodeId: string;
  tree: PlanTree;
  launchable: boolean;
}
const NO_STARTERS: StarterPanel[] = [];

export interface DeepResearchWorkspaceProps {
  createResearchPlan?: typeof createPlan;
  withWorkspacePanels?: boolean;
}

export default function DeepResearchWorkspace({
  createResearchPlan = createPlan,
  withWorkspacePanels = true,
}: DeepResearchWorkspaceProps = {}) {
  const workspace = <Workspace createResearchPlan={createResearchPlan} />;
  if (!withWorkspacePanels) return workspace;
  return (
    <PanelHost starters={NO_STARTERS}>
      {workspace}
    </PanelHost>
  );
}

function Workspace({ createResearchPlan }: { createResearchPlan: typeof createPlan }) {
  // A :sessionId in the route means we arrived from a launch elsewhere (the
  // Research-entry cascade). Open straight onto the live monitor — the
  // session's status is durable, so the monitor reconstructs it from the
  // event log even if this process never held the in-memory session.
  const { sessionId: routeSessionId } = useParams<{ sessionId?: string }>();
  const [problem, setProblem] = useState("");
  const [plan, setPlan] = useState<PlanState | null>(null);
  const [sessionId, setSessionId] = useState<string | null>(routeSessionId ?? null);
  const [sessionGeneration, setSessionGeneration] = useState(0);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState(false);
  const mounted = useRef(true);
  const operationGeneration = useRef(0);
  const operationInFlight = useRef(false);

  useEffect(() => {
    mounted.current = true;
    return () => {
      mounted.current = false;
      operationGeneration.current += 1;
      operationInFlight.current = false;
    };
  }, []);

  const guard = useCallback(async (fn: () => Promise<void | (() => void)>) => {
    if (operationInFlight.current) return;
    operationInFlight.current = true;
    const generation = ++operationGeneration.current;
    setBusy(true);
    setError(false);
    try {
      const commit = await fn();
      if (!mounted.current || generation !== operationGeneration.current) return;
      commit?.();
    } catch {
      if (!mounted.current || generation !== operationGeneration.current) return;
      setError(true);
    } finally {
      if (mounted.current && generation === operationGeneration.current) {
        operationInFlight.current = false;
        setBusy(false);
      }
    }
  }, []);

  const handleCreate = () => {
    const q = problem.trim();
    if (!q) return;
    void guard(async () => {
      const r = await createResearchPlan({ problem: q });
      return () => {
        track("deep_research_cascade_created", { problem_length: q.length });
        setPlan({ rootNodeId: r.root_node_id, tree: r.tree, launchable: false });
        setSessionId(null);
      };
    });
  };

  const handleEdit = (edit: { op: "add_child" | "remove" | "reword"; target_local_id: string; question?: string }) =>
    void guard(async () => {
      if (!plan) return;
      const r = await editPlan(plan.rootNodeId, edit);
      return () => setPlan({ rootNodeId: r.root_node_id, tree: r.tree, launchable: r.launchable });
    });

  const handleApprove = () =>
    void guard(async () => {
      if (!plan) return;
      await approvePlan(plan.rootNodeId);
      const r = await getPlan(plan.rootNodeId); // refresh tree + launchable
      return () => {
        track("deep_research_plan_approved");
        setPlan({ rootNodeId: r.root_node_id, tree: r.tree, launchable: r.launchable });
      };
    });

  const handleLaunch = () =>
    void guard(async () => {
      if (!plan || !plan.launchable) return;
      const r = await launchPlan(plan.rootNodeId);
      return () => {
        track("deep_research_cascade_launched", { session_id: r.session_id });
        notifyResearchStarted(r.session_id);
        setSessionId(r.session_id);
        // Session IDs are deterministic per plan. A successful relaunch can
        // therefore reuse the same ID after its prior monitor stopped polling;
        // generation forces a fresh polling + reaction episode in that case.
        setSessionGeneration((generation) => generation + 1);
      };
    });

  const phase = sessionId ? "Live session" : plan ? "Plan room" : busy ? "Charting" : "Ready";
  return (
    <DeepResearchMissionControlFrame phase={phase} active={Boolean(sessionId)}>
      <ComposeBar problem={problem} setProblem={setProblem} busy={busy} onCreate={handleCreate} />
      {error && (
        <div role="alert" className="deep-research-mission-control__notice">
          <strong>Mission control could not complete that operation.</strong>
          <p>Nothing new was launched or approved. Review the current plan and try again.</p>
        </div>
      )}
      {busy && !plan && (
        <div role="status" aria-live="polite" className="deep-research-mission-control__status">
          <span className="deep-research-mission-control__spinner motion-safe:animate-spin" aria-hidden="true" />
          <div><strong>Charting the first research paths…</strong><p>No research has launched yet.</p></div>
        </div>
      )}
      {plan && <PlanEditor tree={plan.tree} launchable={plan.launchable} busy={busy} onEdit={handleEdit} onApprove={handleApprove} onLaunch={handleLaunch} />}
      {sessionId && <Monitor key={`${sessionId}:${sessionGeneration}`} sessionId={sessionId} sessionGeneration={sessionGeneration} busy={busy} />}
    </DeepResearchMissionControlFrame>
  );
}

export function DeepResearchMissionControlFrame({
  phase,
  active = false,
  visualFixture = false,
  children,
}: {
  phase: string;
  active?: boolean;
  visualFixture?: boolean;
  children: ReactNode;
}) {
  return (
    <div className={`deep-research-mission-control ${active ? "deep-research-mission-control--active" : ""} ${visualFixture ? "deep-research-mission-control--fixture" : ""}`}>
      <img src={missionControlEnvironment} alt="" aria-hidden="true" decoding="sync" draggable={false} data-testid="deep-research-mission-control-environment" />
      <div className="deep-research-mission-control__veil" aria-hidden="true" />
      <header className="deep-research-mission-control__header">
        <div><p className="deep-research-mission-control__eyebrow">Antiek · parallel inquiry</p><h1>Deep research mission control</h1><p>Shape one hard problem, inspect its paths, then send only the plan you approve.</p></div>
        <div className="deep-research-mission-control__phase"><span aria-hidden="true" /><strong>{phase}</strong></div>
      </header>
      <section className="deep-research-mission-control__console" aria-label="Deep research controls">{children}</section>
    </div>
  );
}

export function ComposeBar({
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

export function Monitor({ sessionId, sessionGeneration, busy }: {
  sessionId: string;
  sessionGeneration: number;
  busy: boolean;
}) {
  const session = useResearchSession(sessionId);
  useWernerResearchReactions({
    sessionId,
    loading: session.loading,
    allTerminal: session.allTerminal,
    error: session.error,
    researchStates: session.researches.map((research) => research.state),
  });
  const [steering, setSteering] = useState<string | null>(null);
  // SPR-03: the "organism" canvas branch. When set to a completed
  // investigation id, the monitor swaps the live-card grid for the
  // block-canvas view of that research's insight/question graph. Null = the
  // default live-card monitor (non-breaking: the existing shell is unchanged
  // until the operator opts into the canvas).
  const [resultView, setResultView] = useState<{
    investigationId: string;
    returnFocusId: string;
  } | null>(null);
  // SPR-04: the block whose detail (the SECOND FloatMenu host) is open, or null.
  // Clicking a BlockCard on the canvas opens its detail as an overlay panel —
  // a highlight inside it mounts the SAME shared FloatMenu the synthesis host
  // uses. Non-breaking: the canvas keeps rendering underneath; the detail is an
  // overlay, dismissed back to the canvas.
  const [openNode, setOpenNode] = useState<DistilledNode | null>(null);
  const monitorHeadingRef = useRef<HTMLHeadingElement | null>(null);
  const pendingReturnFocusRef = useRef<string | null>(null);

  const focusResearchCard = useCallback((investigationId: string) => {
    window.requestAnimationFrame(() => {
      document.getElementById(`research-${investigationId}`)?.focus();
    });
  }, []);

  const openInvestigation = useCallback((
    investigationId: string,
    source: "werner_broadcast" | "terminal_card",
  ) => {
    const research = session.researches.find(
      (candidate) => candidate.investigation_id === investigationId,
    );
    if (!research || !TERMINAL_STATES.has(research.state)) return;
    if (research.state !== "done") {
      focusResearchCard(investigationId);
      return;
    }
    track("deep_research_canvas_opened", {
      investigation_id: investigationId,
      source,
      outcome: "done",
    });
    setOpenNode(null);
    setResultView({
      investigationId,
      returnFocusId:
        source === "terminal_card"
          ? `research-result-action-${investigationId}`
          : `research-${investigationId}`,
    });
  }, [focusResearchCard, session.researches]);

  useEffect(() => {
    if (resultView || !pendingReturnFocusRef.current) return;
    const returnFocusId = pendingReturnFocusRef.current;
    pendingReturnFocusRef.current = null;
    const frame = window.requestAnimationFrame(() => {
      const target = document.getElementById(returnFocusId);
      if (target) target.focus();
      else monitorHeadingRef.current?.focus();
    });
    return () => window.cancelAnimationFrame(frame);
  }, [resultView]);

  const closeResultView = () => {
    if (!resultView) return;
    pendingReturnFocusRef.current = resultView.returnFocusId;
    setOpenNode(null);
    setResultView(null);
  };

  const openEvidenceSource = useCallback((node: DistilledNode, anchor: AnchorRect) => {
    const documentId = node.source_document_id;
    if (!documentId?.trim()) return;
    const host = document.querySelector<HTMLElement>("[data-windows-layer]");
    const hostRect = host?.getBoundingClientRect();
    const layer = {
      left: hostRect?.left ?? 0,
      top: hostRect?.top ?? 0,
      width: hostRect?.width || window.innerWidth,
      height: hostRect?.height || window.innerHeight,
    };
    const relativeAnchor = anchorRelativeToLayer(anchor, layer);
    const rect = chooseAdjacentWindowRect(relativeAnchor, layer, {
      width: DEFAULT_WINDOW_RECT.width,
      height: DEFAULT_WINDOW_RECT.height,
    });
    openWindow(
      "reader",
      { documentId, evidenceSourceContext: true },
      {
        id: `win:reader:${encodeURIComponent(documentId)}`,
        title: "Research source",
        replaceOldestAtLimit: true,
        ...(rect ? { rect } : {}),
      },
    );
  }, []);

  const steer = (iid: string) => async (kind: SteerKind, payload?: Record<string, unknown>) => {
    setSteering(iid);
    try {
      await steerResearch(sessionId, iid, kind, payload);
    } catch {
      emitWernerExperience("deep_research_error");
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
  if (resultView) {
    return (
      <div className="flex h-full flex-col gap-2">
        <div className="flex items-center gap-3">
          <LemonButton variant="tertiary" size="sm" onClick={closeResultView}>
            ← back to monitor
          </LemonButton>
          <span className="font-mono text-[11px] text-shadow-1 dark:text-moonlight">
            organism canvas
          </span>
        </div>
        <div className="relative min-h-[480px] flex-1 overflow-hidden rounded-hog border-edge border-sun">
          <Canvas
            investigationId={resultView.investigationId}
            onOpenDetail={setOpenNode}
            onCiteSource={openEvidenceSource}
          />
          {/* SPR-04: the block detail is the SECOND live FloatMenu host. It
              opens off a BlockCard click as an overlay over the canvas (the
              canvas stays mounted underneath — non-breaking) and dismisses
              back to it. A text selection inside it mounts the SAME FloatMenu. */}
          {openNode && (
            <div className="absolute inset-0 z-10 overflow-auto bg-ice-0 dark:bg-charcoal-1">
              <BlockDetail
                node={openNode}
                investigationId={resultView.investigationId}
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
        <h2 ref={monitorHeadingRef} tabIndex={-1} className="text-sm font-semibold text-ink dark:text-bright">
          {session.researches.length} researches
          {!session.allTerminal && session.researches.length > 0 && (
            <span className="ml-2 text-[11px] font-normal text-aurora">live</span>
          )}
          {session.allTerminal && (
            <span className="ml-2 text-[11px] font-normal text-shadow-1 dark:text-moonlight">complete</span>
          )}
        </h2>
        <div className="flex items-center gap-3">
          <div className="w-64"><CostMeter cost={session.cost} /></div>
        </div>
      </div>
      {session.error && (
        <p className="text-[11px] text-shadow-1 dark:text-moonlight">reconnecting… status details stay private</p>
      )}
      {session.hardCeiling && (
        <HardCeilingEvidence sessionId={sessionId} snapshot={session.hardCeiling} />
      )}
      <ResearchWaitArcadeGate
        enabled={wernerResearchWaitArcadeEnabled}
        episodeId={`${sessionId}:${sessionGeneration}`}
        hasAuthoritativeSnapshot={!session.loading}
        researchCount={session.researches.length}
        activeResearchCount={session.researches.filter(
          (research) => !TERMINAL_STATES.has(research.state),
        ).length}
        allTerminal={session.allTerminal}
        researches={session.researches.map((research) => ({
          investigationId: research.investigation_id,
          subQuestion: research.sub_question,
          state: research.state,
        }))}
        onViewResearch={(investigationId) => {
          openInvestigation(investigationId, "werner_broadcast");
        }}
        returnFocusRef={monitorHeadingRef}
      />
      <div className="grid grid-cols-1 gap-3 sm:grid-cols-2 lg:grid-cols-3 xl:grid-cols-4">
        {session.researches.map((r) => (
          <ResearchPanel
            key={r.investigation_id}
            research={r}
            costUsd={session.cost?.per_research[r.investigation_id] ?? 0}
            busy={busy || steering === r.investigation_id}
            onSteer={steer(r.investigation_id)}
            onViewResult={
              r.state === "done"
                ? () => openInvestigation(r.investigation_id, "terminal_card")
                : undefined
            }
          />
        ))}
      </div>
    </div>
  );
}

export interface ResearchWaitArcadeGateProps {
  enabled: boolean;
  episodeId: string;
  hasAuthoritativeSnapshot: boolean;
  researchCount: number;
  activeResearchCount: number;
  allTerminal: boolean;
  researches?: readonly import("./researchBroadcast").ResearchBroadcastSnapshot[];
  onViewResearch?: (investigationId: string) => void;
  returnFocusRef: RefObject<HTMLElement | null>;
}

/** Disabled and ineligible sessions never render React.lazy. */
export function ResearchWaitArcadeGate({
  enabled,
  episodeId,
  hasAuthoritativeSnapshot,
  researchCount,
  activeResearchCount,
  allTerminal,
  researches = [],
  onViewResearch = () => {},
  returnFocusRef,
}: ResearchWaitArcadeGateProps) {
  const reducedMotion = usePrefersReducedMotion();
  const eligibilityRef = useRef({ episodeId, observedActive: false });
  if (eligibilityRef.current.episodeId !== episodeId) {
    eligibilityRef.current = { episodeId, observedActive: false };
  }
  if (
    enabled &&
    hasAuthoritativeSnapshot &&
    !reducedMotion &&
    activeResearchCount > 0
  ) {
    eligibilityRef.current.observedActive = true;
  }
  const eligible =
    enabled &&
    hasAuthoritativeSnapshot &&
    researchCount > 0 &&
    !reducedMotion &&
    (activeResearchCount > 0 ||
      (allTerminal && eligibilityRef.current.observedActive));

  if (!eligible) return null;
  return (
    <Suspense fallback={null}>
      <LazyResearchWaitArcade
        key={episodeId}
        episodeId={episodeId}
        activeResearchCount={activeResearchCount}
        researches={researches}
        allTerminal={allTerminal}
        onViewResearch={onViewResearch}
        returnFocusRef={returnFocusRef}
      />
    </Suspense>
  );
}
