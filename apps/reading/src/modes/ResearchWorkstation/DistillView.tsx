import { useCallback, useEffect, useRef, useState } from "react";

import {
  getDistillation,
  challengeNote,
  ApiError,
  classifyInvestigationPromotionFailure,
  promoteInvestigationToWrite,
} from "../../lib/api";
import type { DistilledNode } from "../../lib/api";
import AIActionFailure from "../../shared/AIActionFailure";
import Thinking from "../../shared/Thinking";
import ArtifactOutlineShelf from "./ArtifactOutlineShelf";

/**
 * DistillView — insights & open questions as first-class objects (SPR-03 M2),
 * with the escalation seam + honest no-key state (M4).
 *
 * The durable PRODUCT of a research, distinct from the live narration
 * (ThinkingStream) and the answer prose (MasterMdViewer, SPR-04). It reads the
 * insight + question GRAPH NODES off the backend (GET /research/{id}/distill)
 * — it does NOT re-derive them from the event log, so a note that was
 * challenged shows its refined text (the node row is the source of truth).
 *
 * Two sections, matching the §2.1 primitive:
 *   - INSIGHTS: grounded claims, each carrying its named source.
 *   - OPEN QUESTIONS: unresolved threads the user can chase (SPR-04). A
 *     question whose challenge the graph couldn't resolve is marked "this
 *     needs more research" and carries a RESERVED child research id — nothing
 *     is launched here (per living_note's escalation contract; SPR-04/05
 *     launch into the reserved id).
 *
 * Honest no-key (M4): with no provider, distillation produces nothing, so the
 * surface shows the shared AIActionFailure no-result state — never canned
 * insights. An empty graph result and a failed fetch both land there.
 *
 * The "challenge this" gesture lives on NotesPanel (the live surface); here a
 * completed-research insight can also be challenged, driving the same backend
 * living-note path. On success we refetch so the (possibly refined) node text
 * re-renders from the graph rather than guessed in the client.
 */

export interface DistillViewProps {
  investigationId: string;
  /** True while the research is still running — the distillation is partial,
   *  so we say so rather than implying it's the final product. */
  running?: boolean;
  /** Chase an open question (hand off to SPR-04). Optional — when absent, the
   *  question is shown but not chaseable from here. */
  onChase?: (question: DistilledNode) => void;
  /** The event stream contains a completed synthesis worth asking the server
   * to promote. The server remains the final evidence/eligibility authority. */
  canStartWriting?: boolean;
  onOpenWrite?: (deliverableId: string) => void;
}

type LoadState =
  | { kind: "loading" }
  | { kind: "loaded"; insights: DistilledNode[]; questions: DistilledNode[] }
  | { kind: "error"; reason: string | null };

export default function DistillView({
  investigationId,
  running,
  onChase,
  canStartWriting = false,
  onOpenWrite,
}: DistillViewProps) {
  const [state, setState] = useState<LoadState>({ kind: "loading" });

  const load = useCallback(async () => {
    setState({ kind: "loading" });
    try {
      const res = await getDistillation(investigationId);
      setState({ kind: "loaded", insights: res.insights, questions: res.questions });
    } catch (e) {
      const reason = e instanceof ApiError ? e.body || null : null;
      setState({ kind: "error", reason });
    }
  }, [investigationId]);

  useEffect(() => {
    void load();
  }, [load]);

  if (state.kind === "loading") {
    return (
      <div className="flex items-center gap-2 px-4 py-6" role="status" aria-live="polite">
        <Thinking size={28} label="Gathering the insights and questions" status="reading the graph…" />
      </div>
    );
  }

  if (state.kind === "error") {
    return (
      <div className="px-4 py-6">
        <AIActionFailure
          title="Couldn’t load the insights and questions"
          reason={state.reason}
          onRetry={() => void load()}
        />
      </div>
    );
  }

  const { insights, questions } = state;

  // Honest no-result (M4): nothing distilled — the common no-provider case.
  if (insights.length === 0 && questions.length === 0) {
    return (
      <div className="px-4 py-6">
        <AIActionFailure
          title={
            running
              ? "No insights or questions yet — the research is still working"
              : "This research distilled no insights or open questions"
          }
          reason={null}
          onRetry={() => void load()}
          retryLabel="Check again"
        />
      </div>
    );
  }

  return (
    <div className="flex flex-col gap-5 px-4 py-4">
      {running && (
        <p className="font-mono text-[11px] text-shadow-1 dark:text-moonlight">
          still working — this is what’s distilled so far
        </p>
      )}

      {insights.length > 0 && (
        <Section heading="Insights">
          <ul className="space-y-2.5">
            {insights.map((n) => (
              <InsightRow key={n.node_id} node={n} investigationId={investigationId} onRefined={load} />
            ))}
          </ul>
        </Section>
      )}

      {questions.length > 0 && (
        <Section heading="Open questions">
          <ul className="space-y-2.5">
            {questions.map((q) => (
              <QuestionRow key={q.node_id} node={q} onChase={onChase} />
            ))}
          </ul>
        </Section>
      )}

      {canStartWriting && onOpenWrite ? (
        <StartWritingAction
          investigationId={investigationId}
          onOpenWrite={onOpenWrite}
        />
      ) : null}

      <ArtifactOutlineShelf investigationId={investigationId} />
    </div>
  );
}

type PromotionState =
  | { kind: "idle" }
  | { kind: "busy" }
  | { kind: "error"; message: string };

const PROMOTION_GATE_COPY: Record<string, string> = {
  status: "The synthesis did not converge, so it cannot start a draft yet.",
  recommendation: "The synthesis needs more evidence before it can start a draft.",
  no_source_nodes: "The synthesis has no grounded source blocks to carry into Write.",
  all_dangling: "The synthesis sources are no longer available to carry into Write.",
};

function StartWritingAction({
  investigationId,
  onOpenWrite,
}: {
  investigationId: string;
  onOpenWrite: (deliverableId: string) => void;
}) {
  const [promotion, setPromotion] = useState<PromotionState>({ kind: "idle" });
  const requestSequence = useRef(0);

  useEffect(() => {
    requestSequence.current += 1;
    setPromotion({ kind: "idle" });
    return () => {
      requestSequence.current += 1;
    };
  }, [investigationId]);

  const startWriting = async () => {
    if (promotion.kind === "busy") return;
    const request = ++requestSequence.current;
    setPromotion({ kind: "busy" });
    try {
      const result = await promoteInvestigationToWrite(investigationId);
      if (request !== requestSequence.current) return;
      onOpenWrite(result.deliverable_id);
    } catch (error) {
      if (request !== requestSequence.current) return;
      const failure = classifyInvestigationPromotionFailure(error);
      const message =
        failure.kind === "no_synthesis"
          ? "This research has no completed synthesis to write from."
          : failure.kind === "not_promotable"
            ? PROMOTION_GATE_COPY[failure.gate_failed]
            : "Couldn’t start a draft from this research. Try again.";
      setPromotion({ kind: "error", message });
    }
  };

  return (
    <section
      className="rounded-md border border-rule bg-ice-1 px-3 py-3 dark:border-charcoal-1 dark:bg-charcoal-2"
      data-testid="distill-start-writing"
    >
      <div className="flex flex-wrap items-center justify-between gap-3">
        <div>
          <h3 className="font-serif text-sm text-ink dark:text-bright">
            Turn this research into a draft
          </h3>
          <p className="mt-0.5 text-[11px] font-mono text-shadow-1 dark:text-moonlight">
            Carry the synthesis and its grounded blocks into Write with provenance intact.
          </p>
        </div>
        <button
          type="button"
          onClick={() => void startWriting()}
          disabled={promotion.kind === "busy"}
          className="rounded border border-ink/30 px-3 py-1.5 text-[11px] font-mono transition-colors hover:bg-ink/5 disabled:cursor-wait disabled:opacity-60 dark:border-bright/30"
        >
          {promotion.kind === "busy" ? "Starting…" : "Start writing"}
        </button>
      </div>
      {promotion.kind === "error" ? (
        <p className="mt-2 text-[11px] font-mono text-emperor" role="alert">
          {promotion.message}
        </p>
      ) : null}
    </section>
  );
}

function Section({ heading, children }: { heading: string; children: React.ReactNode }) {
  return (
    <section>
      <h3 className="mb-2 font-mono text-[11px] uppercase tracking-wider text-shadow-1 dark:text-moonlight">
        {heading}
      </h3>
      {children}
    </section>
  );
}

function InsightRow({
  node,
  investigationId,
  onRefined,
}: {
  node: DistilledNode;
  investigationId: string;
  onRefined: () => Promise<void>;
}) {
  const [outcome, setOutcome] = useState<
    "idle" | "busy" | "changed" | "unchanged" | "escalated" | "noSource" | "noModel" | "error"
  >("idle");

  const runChallenge = async () => {
    setOutcome("busy");
    try {
      const res = await challengeNote(node.node_id, { investigation_id: investigationId });
      if (res.applied) {
        setOutcome("changed");
        await onRefined(); // refetch so the refined node text re-renders from the graph
      } else if (res.escalated) {
        setOutcome("escalated");
        await onRefined();
      } else if (res.superseded) {
        setOutcome("unchanged");
      } else {
        setOutcome("idle");
      }
    } catch (e) {
      // 422 = the note has no source on record yet (not a model failure) — say
      // that honestly, not "the engine reported a problem".
      const status = e instanceof ApiError ? e.status : 0;
      setOutcome(status === 503 ? "noModel" : status === 422 ? "noSource" : "error");
    }
  };
  // Own the promise here — don't hand React a floating one.
  const onChallenge = () => {
    void runChallenge();
  };

  return (
    <li className="flex flex-col gap-1">
      <div className="flex items-start gap-2.5">
        <span className="mt-[7px] h-1.5 w-1.5 shrink-0 rounded-full bg-aurora" aria-hidden="true" />
        <div className="min-w-0 flex-1">
          <p className="font-serif text-[14px] leading-relaxed text-ink dark:text-bright">
            {node.text}
          </p>
          <div className="mt-1 flex flex-wrap items-center gap-2 text-[11px] text-shadow-1 dark:text-moonlight">
            <Grounding node={node} />
            <GraphNodeLink node={node} kind="insight" />
            {node.refinement_count > 0 && (
              <span className="font-mono">changed {node.refinement_count === 1 ? "once" : `${node.refinement_count} times`}</span>
            )}
            {outcome !== "busy" && outcome !== "noModel" && outcome !== "error" && outcome !== "noSource" && (
              <button
                type="button"
                onClick={onChallenge}
                className="font-mono underline decoration-dotted underline-offset-2 transition-colors hover:text-ink dark:hover:text-bright"
              >
                challenge this
              </button>
            )}
            {outcome === "busy" && <span className="font-mono italic" role="status">weighing…</span>}
          </div>
          {outcome === "changed" && (
            <p className="mt-1 font-mono text-[11px] text-emerald-700" role="status">
              the note changed in light of your challenge
            </p>
          )}
          {outcome === "unchanged" && (
            <p className="mt-1 font-mono text-[11px] text-shadow-1 dark:text-moonlight" role="status">
              a newer revision already settled this — unchanged
            </p>
          )}
          {outcome === "escalated" && (
            <p className="mt-1 font-mono text-[11px] text-sun-deep dark:text-sun" role="status">
              this needs more research — saved as an open question
            </p>
          )}
          {outcome === "noSource" && (
            <p className="mt-1 font-mono text-[11px] text-shadow-1 dark:text-moonlight" role="status">
              this note isn’t grounded in a source yet, so it can’t be challenged
            </p>
          )}
          {(outcome === "noModel" || outcome === "error") && (
            <div className="mt-1">
              <AIActionFailure
                title="Couldn’t weigh the challenge"
                reason={outcome === "noModel" ? null : "the engine reported a problem"}
                onRetry={onChallenge}
              />
            </div>
          )}
        </div>
      </div>
    </li>
  );
}

function QuestionRow({ node, onChase }: { node: DistilledNode; onChase?: (q: DistilledNode) => void }) {
  return (
    <li className="flex items-start gap-2.5">
      <span className="mt-[7px] h-1.5 w-1.5 shrink-0 rounded-full bg-sun-deep dark:bg-sun" aria-hidden="true" />
      <div className="min-w-0 flex-1">
        <p className="font-serif text-[14px] leading-relaxed text-ink dark:text-bright">{node.text}</p>
        <div className="mt-1 flex flex-wrap items-center gap-2 text-[11px] text-shadow-1 dark:text-moonlight">
          {node.escalated ? (
            <span className="font-mono text-sun-deep dark:text-sun">this needs more research</span>
          ) : null}
          <GraphNodeLink node={node} kind="question" />
          {onChase && (
            <button
              type="button"
              onClick={() => onChase(node)}
              className="font-mono underline decoration-dotted underline-offset-2 transition-colors hover:text-ink dark:hover:text-bright"
            >
              chase this
            </button>
          )}
        </div>
      </div>
    </li>
  );
}

/** The named source that grounds an insight, in human terms. We show the
 *  document the insight came from; a raw id is never a label, so when only an
 *  id is on record we say "grounded in a source" rather than print the id.
 *  (SPR-04 wires the source's title via the named-source rendering.) */
function Grounding({ node }: { node: DistilledNode }) {
  if (!node.source_document_id) {
    return <span className="font-mono italic">no source on record</span>;
  }
  return <span className="font-mono">grounded in a source</span>;
}

/** A distilled item is already the canonical graph node. Re-enter the graph
 * with that exact identity rather than searching by mutable display prose. */
function GraphNodeLink({
  node,
  kind,
}: {
  node: DistilledNode;
  kind: "insight" | "question";
}) {
  return (
    <a
      href={`/knowledge-graph?node_id=${encodeURIComponent(node.node_id)}`}
      data-testid={`distill-open-graph-${kind}`}
      className="font-mono underline decoration-sun decoration-2 underline-offset-2 transition-colors hover:text-ink dark:hover:text-bright"
      title="Inspect this distilled item and its evidence in the knowledge graph"
    >
      inspect in graph
    </a>
  );
}
