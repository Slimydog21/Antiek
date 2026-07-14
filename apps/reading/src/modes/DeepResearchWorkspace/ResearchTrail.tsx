import { useState } from "react";

import LemonButton from "../../components/lemon/LemonButton";
import {
  TERMINAL_STATES,
  type PlanNode,
  type ResearchStatus,
  type SessionPlan,
  type SteerKind,
} from "../../api/research";

const STATE_LABEL: Record<ResearchStatus["state"], string> = {
  pending: "queued",
  running: "running",
  paused: "paused",
  stopping: "stopping",
  done: "done",
  stopped: "stopped",
  failed: "failed",
  budget_halted: "budget halted",
};

interface Props {
  plan: SessionPlan;
  researches: ResearchStatus[];
  steeringId: string | null;
  onSteer: (investigationId: string, kind: SteerKind, payload?: Record<string, unknown>) => void;
  onFocusResearch: (investigationId: string) => void;
}

export default function ResearchTrail({ plan, researches, steeringId, onSteer, onFocusResearch }: Props) {
  const byPlanNode = new Map(
    researches
      .filter((research) => research.plan_node_local_id)
      .map((research) => [research.plan_node_local_id as string, research]),
  );

  return (
    <aside className="border-edge border-sun bg-ice-0 p-3 dark:bg-charcoal-2" aria-labelledby="research-trail-heading">
      <header className="mb-3 border-b border-ice-4 pb-2 dark:border-slate-2">
        <p className="font-mono text-[10px] uppercase tracking-[0.16em] text-sun-deep">approved expedition</p>
        <h2 id="research-trail-heading" className="font-serif text-lg text-ink dark:text-bright">Research trail</h2>
        <p className="text-[11px] text-shadow-1 dark:text-moonlight">The plan you approved, still attached to the work.</p>
      </header>
      <ol className="m-0 list-none p-0">
        <TrailNode
          node={plan.tree.root}
          depth={0}
          isRoot
          byPlanNode={byPlanNode}
          steeringId={steeringId}
          onSteer={onSteer}
          onFocusResearch={onFocusResearch}
        />
      </ol>
    </aside>
  );
}

function TrailNode({ node, depth, isRoot, byPlanNode, steeringId, onSteer, onFocusResearch }: {
  node: PlanNode;
  depth: number;
  isRoot?: boolean;
  byPlanNode: Map<string, ResearchStatus>;
  steeringId: string | null;
  onSteer: Props["onSteer"];
  onFocusResearch: Props["onFocusResearch"];
}) {
  const research = node.children.length === 0
    ? byPlanNode.get(node.local_id)
    : undefined;
  const isLeaf = node.children.length === 0;
  const terminal = research ? TERMINAL_STATES.has(research.state) : false;
  const busy = research ? steeringId === research.investigation_id : false;
  const [redirecting, setRedirecting] = useState(false);
  const [redirectText, setRedirectText] = useState("");

  return (
    <li className={depth ? "border-l border-ice-4 pl-3 dark:border-slate-2" : ""}>
      <div className={`relative py-2 ${isRoot ? "border-b border-ice-4 dark:border-slate-2" : ""}`}>
        {depth > 0 && <span aria-hidden className="absolute -left-3 top-4 w-2 border-t border-ice-4 dark:border-slate-2" />}
        <div className="flex items-start justify-between gap-2">
          {research ? <button
            type="button"
            aria-label={`Focus research: ${node.question}`}
            onClick={() => onFocusResearch(research.investigation_id)}
            className="min-w-0 flex-1 text-left"
          >
            <span className={`block text-sm text-ink dark:text-bright ${isRoot ? "font-semibold" : ""}`}>{node.question}</span>
            {!isRoot && node.rationale && <span className="mt-0.5 block text-[11px] leading-snug text-shadow-1 dark:text-moonlight">{node.rationale}</span>}
            {!isRoot && node.focus_boundary && <span className="mt-1 block font-mono text-[10px] text-shadow-1 dark:text-moonlight">boundary · {node.focus_boundary}</span>}
          </button> : <div className="min-w-0 flex-1">
            <span className={`block text-sm text-ink dark:text-bright ${isRoot ? "font-semibold" : ""}`}>{node.question}</span>
            {!isRoot && node.rationale && <span className="mt-0.5 block text-[11px] leading-snug text-shadow-1 dark:text-moonlight">{node.rationale}</span>}
            {!isRoot && node.focus_boundary && <span className="mt-1 block font-mono text-[10px] text-shadow-1 dark:text-moonlight">boundary · {node.focus_boundary}</span>}
          </div>}
          <span className="shrink-0 font-mono text-[10px] uppercase tracking-[0.1em] text-shadow-1 dark:text-moonlight">
            {research
              ? research.control_available !== true && !terminal
                ? "disconnected"
                : STATE_LABEL[research.state]
              : isLeaf ? "unmapped" : "branch"}
          </span>
        </div>

        {isLeaf && !research && (
          <p className="mt-1 text-[11px] text-shadow-1 dark:text-moonlight">Control unavailable for this older session.</p>
        )}

        {research && research.control_available !== true && !terminal && (
          <p className="mt-1 text-[11px] text-emperor">Runner disconnected. This durable state cannot be steered.</p>
        )}

        {research && research.control_available === true && !terminal && (
          <div className="mt-2 flex flex-wrap gap-1.5" aria-label={`Steer ${node.question}`}>
            {research.state === "paused" ? (
              <LemonButton size="sm" variant="secondary" disabled={busy} onClick={() => onSteer(research.investigation_id, "resume")}>Resume</LemonButton>
            ) : (
              <LemonButton size="sm" variant="secondary" disabled={busy || research.state !== "running"} onClick={() => onSteer(research.investigation_id, "pause")}>Pause</LemonButton>
            )}
            <LemonButton size="sm" variant="tertiary" disabled={busy} onClick={() => setRedirecting((open) => !open)}>Redirect</LemonButton>
            <LemonButton size="sm" variant="tertiary" disabled={busy} onClick={() => onSteer(research.investigation_id, "deepen", { extra_budget_usd: 0.25 })}>Deepen</LemonButton>
            <LemonButton size="sm" variant="danger" disabled={busy} onClick={() => onSteer(research.investigation_id, "stop")}>Stop</LemonButton>
          </div>
        )}

        {research && redirecting && research.control_available === true && !terminal && (
          <form className="mt-2 flex gap-1.5" onSubmit={(event) => {
            event.preventDefault();
            const question = redirectText.trim();
            if (!question) return;
            onSteer(research.investigation_id, "redirect", { sub_question: question });
            setRedirectText("");
            setRedirecting(false);
          }}>
            <input className="min-w-0 flex-1 border border-ice-4 bg-ice-1 px-2 py-1 text-xs text-ink dark:border-slate-2 dark:bg-charcoal-1 dark:text-bright" value={redirectText} onChange={(event) => setRedirectText(event.target.value)} aria-label={`Redirect ${node.question}`} />
            <LemonButton size="sm" variant="primary" type="submit">Send</LemonButton>
          </form>
        )}
      </div>
      {node.children.length > 0 && (
        <ol className="m-0 list-none p-0">
          {node.children.map((child) => (
            <TrailNode key={child.local_id} node={child} depth={depth + 1} byPlanNode={byPlanNode} steeringId={steeringId} onSteer={onSteer} onFocusResearch={onFocusResearch} />
          ))}
        </ol>
      )}
    </li>
  );
}
