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

import { lazy, Suspense, useCallback, useRef, useState, type RefObject } from "react";
import { useParams } from "react-router-dom";

import { PanelHost } from "../../workspace/PanelHost";
import type { StarterPanel } from "../../workspace/PanelHost";
import LemonButton from "../../components/lemon/LemonButton";
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
import CostMeter from "./CostMeter";
import HardCeilingEvidence from "./HardCeilingEvidence";
import PlanEditor from "./PlanEditor";
import ResearchPanel from "./ResearchPanel";
import ResearchSessionTwinRail from "./ResearchSessionTwinRail";
import Canvas from "./Canvas/Canvas";
import BlockDetail from "./BlockDetail";
import { useResearchSession } from "./useResearchSession";
import { useWernerResearchReactions } from "./useWernerResearchReactions";
import thinkingArt from "../../brand/werner/poses/session/werner_thinking_session_v1.png";
import livingTvArt from "../../brand/werner/poses/session/werner_crt_living_tv_session_v1.webp";
import { emitWernerExperience, notifyResearchStarted } from "../../werner";
import { wernerResearchWaitArcadeEnabled } from "../../arcade/waitArcadeFlag";
import { usePrefersReducedMotion } from "../../workspace/usePrefersReducedMotion";
import { deriveResearchWaitArcadeMode } from "./researchWaitArcadePolicy";

const LazyResearchWaitArcade = lazy(() => import("./ResearchWaitArcade"));

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
  const [sessionGeneration, setSessionGeneration] = useState(0);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);

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
      const r = await createPlan({ problem: q });
      track("deep_research_cascade_created", {
        problem_length: q.length,
      });
      // Living-TV: starting a cascade plan is happy craft (piece started).
      emitWernerExperience("piece_started");
      setPlan({ rootNodeId: r.root_node_id, tree: r.tree, launchable: false });
      setSessionId(null);
    });

  const handleEdit = (edit: { op: "add_child" | "remove" | "reword"; target_local_id: string; question?: string }) =>
    guard(async () => {
      if (!plan) return;
      const r = await editPlan(plan.rootNodeId, edit);
      setPlan({ rootNodeId: r.root_node_id, tree: r.tree, launchable: r.launchable });
    });

  const handleApprove = () =>
    guard(async () => {
      if (!plan) return;
      await approvePlan(plan.rootNodeId);
      const r = await getPlan(plan.rootNodeId); // refresh tree + launchable
      track("deep_research_plan_approved");
      // Living-TV: approving the cascade is a craft beat (curious glance).
      emitWernerExperience("highlight");
      setPlan({ rootNodeId: r.root_node_id, tree: r.tree, launchable: r.launchable });
    });

  const handleLaunch = () =>
    guard(async () => {
      if (!plan || !plan.launchable) return;
      const r = await launchPlan(plan.rootNodeId);
      track("deep_research_cascade_launched", {
        session_id: r.session_id,
      });
      notifyResearchStarted(r.session_id);
      setSessionId(r.session_id);
      // Session IDs are deterministic per plan. A successful relaunch can
      // therefore reuse the same ID after its prior monitor stopped polling;
      // generation forces a fresh polling + reaction episode in that case.
      setSessionGeneration((generation) => generation + 1);
    });

  return (
    <div className="flex h-full flex-col gap-4 overflow-auto p-4">
      <ComposeBar problem={problem} setProblem={setProblem} busy={busy} onCreate={handleCreate} />
      {error && (
        <p className="rounded border border-emperor/40 bg-emperor/5 px-3 py-2 text-sm text-emperor">{error}</p>
      )}
      {plan && (
        <PlanEditor
          tree={plan.tree}
          launchable={plan.launchable}
          busy={busy}
          onEdit={handleEdit}
          onApprove={handleApprove}
          onLaunch={handleLaunch}
        />
      )}
      {sessionId && (
        <Monitor
          key={`${sessionId}:${sessionGeneration}`}
          sessionId={sessionId}
          sessionGeneration={sessionGeneration}
          busy={busy}
        />
      )}
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
    <div className="space-y-2">
      <div className="flex items-center gap-2">
        <img
          src={thinkingArt}
          alt=""
          aria-hidden="true"
          data-testid="drw-compose-werner-brand"
          className="h-9 w-9 shrink-0 object-contain"
        />
        <div className="min-w-0">
          <h1 className="text-sm font-semibold text-ink dark:text-bright">
            Deep research cascade
          </h1>
          <p className="text-[11px] text-shadow-1 dark:text-moonlight">
            One problem → glass-box plan → N steerable researches. Antiek is the
            home of the penguin.
          </p>
        </div>
      </div>
      <img
        src={livingTvArt}
        alt=""
        aria-hidden="true"
        data-testid="drw-compose-living-tv-art"
        className="h-14 w-full max-w-xl rounded-md object-cover object-center"
        loading="lazy"
        decoding="async"
      />
      <form
        className="flex gap-2"
        onSubmit={(e) => {
          e.preventDefault();
          onCreate();
        }}
      >
        <input
          className="min-w-0 flex-1 rounded-md border-2 border-sun bg-ice-0 px-3 py-2 text-sm text-ink dark:bg-charcoal-2 dark:text-bright"
          placeholder="State one problem — it cascades into focused, steerable deep researches…"
          value={problem}
          onChange={(e) => setProblem(e.target.value)}
          aria-label="research problem"
        />
        <LemonButton
          variant="primary"
          type="submit"
          disabled={busy || !problem.trim()}
        >
          Cascade
        </LemonButton>
      </form>
    </div>
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
  const [canvasFor, setCanvasFor] = useState<string | null>(null);
  // SPR-04: the block whose detail (the SECOND FloatMenu host) is open, or null.
  // Clicking a BlockCard on the canvas opens its detail as an overlay panel —
  // a highlight inside it mounts the SAME shared FloatMenu the synthesis host
  // uses. Non-breaking: the canvas keeps rendering underneath; the detail is an
  // overlay, dismissed back to the canvas.
  const [openNode, setOpenNode] = useState<DistilledNode | null>(null);
  const monitorHeadingRef = useRef<HTMLHeadingElement | null>(null);

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
      <div
        className="flex flex-col items-center gap-2 py-8"
        role="status"
        aria-live="polite"
      >
        <img
          src={thinkingArt}
          alt=""
          aria-hidden="true"
          data-testid="drw-connecting-werner-brand"
          className="h-10 w-10 object-contain"
        />
        <p className="text-sm font-serif text-ink dark:text-bright">
          Connecting to your researches…
        </p>
        <p className="text-[11px] font-mono text-shadow-1 dark:text-moonlight">
          they&rsquo;re starting in parallel
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
          />
        ))}
      </div>
      {sessionId ? <ResearchSessionTwinRail parentAssetId={sessionId} /> : null}
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
  returnFocusRef,
}: ResearchWaitArcadeGateProps) {
  const reducedMotion = usePrefersReducedMotion();
  const eligible = activeResearchCount > 0 && deriveResearchWaitArcadeMode({
    featureEnabled: enabled,
    hasAuthoritativeSnapshot,
    researchCount,
    allTerminal,
    reducedMotion,
    offerReady: false,
    optedIn: false,
  }) !== "hidden";

  if (!eligible) return null;
  return (
    <Suspense fallback={null}>
      <LazyResearchWaitArcade
        key={episodeId}
        episodeId={episodeId}
        activeResearchCount={activeResearchCount}
        returnFocusRef={returnFocusRef}
      />
    </Suspense>
  );
}
