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

import { useCallback, useState } from "react";

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
  type PlanTree,
  type SteerKind,
} from "../../api/research";
import CostMeter from "./CostMeter";
import PlanEditor from "./PlanEditor";
import ResearchPanel from "./ResearchPanel";
import { useResearchSession } from "./useResearchSession";

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
  const [problem, setProblem] = useState("");
  const [plan, setPlan] = useState<PlanState | null>(null);
  const [sessionId, setSessionId] = useState<string | null>(null);
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
      setPlan({ rootNodeId: r.root_node_id, tree: r.tree, launchable: r.launchable });
    });

  const handleLaunch = () =>
    guard(async () => {
      if (!plan || !plan.launchable) return;
      const r = await launchPlan(plan.rootNodeId);
      setSessionId(r.session_id);
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
        <div className="w-64"><CostMeter cost={session.cost} /></div>
      </div>
      {session.error && (
        <p className="text-[11px] text-shadow-1 dark:text-moonlight">reconnecting… ({session.error})</p>
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
