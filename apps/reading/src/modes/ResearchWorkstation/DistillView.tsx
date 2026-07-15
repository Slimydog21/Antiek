import { useCallback, useEffect, useState } from "react";

import {
  getDistillation,
  challengeNote,
  ApiError,
} from "../../lib/api";
import type { DistilledNode } from "../../lib/api";
import AIActionFailure from "../../shared/AIActionFailure";
import Thinking from "../../shared/Thinking";
import distillationEmpty from "../../brand/werner/research/distillation-empty-v1.webp";
import ArtifactOutlineShelf from "./ArtifactOutlineShelf";
import "./distillation-field-ledger.css";

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
  /** Story/test seam. Production uses the canonical API functions. */
  loadDistillation?: typeof getDistillation;
  challengeInsight?: typeof challengeNote;
  /** Isolated visual-proof seam; the workstation keeps the outline shelf on. */
  showArtifactOutline?: boolean;
}

type LoadState =
  | { kind: "loading" }
  | { kind: "loaded"; insights: DistilledNode[]; questions: DistilledNode[] }
  | { kind: "error"; reason: string | null };

export default function DistillView({
  investigationId,
  running,
  onChase,
  loadDistillation = getDistillation,
  challengeInsight = challengeNote,
  showArtifactOutline = true,
}: DistillViewProps) {
  const [state, setState] = useState<LoadState>({ kind: "loading" });

  const load = useCallback(async () => {
    setState({ kind: "loading" });
    try {
      const res = await loadDistillation(investigationId);
      setState({ kind: "loaded", insights: res.insights, questions: res.questions });
    } catch (e) {
      const reason = e instanceof ApiError ? e.body || null : null;
      setState({ kind: "error", reason });
    }
  }, [investigationId, loadDistillation]);

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
      <div className="distillation-empty px-4 py-6">
        <img
          src={distillationEmpty}
          alt=""
          aria-hidden="true"
          className="distillation-empty__image"
        />
        <div className="distillation-empty__message">
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
        <Section heading="Insights" descriptor="Filed findings" count={insights.length} kind="insight">
          <ol className="distillation-ledger__list">
            {insights.map((n, index) => (
              <InsightRow key={n.node_id} index={index + 1} node={n} investigationId={investigationId} onRefined={load} challengeInsight={challengeInsight} />
            ))}
          </ol>
        </Section>
      )}

      {questions.length > 0 && (
        <Section heading="Open questions" descriptor="Unresolved threads" count={questions.length} kind="question">
          <ol className="distillation-ledger__list">
            {questions.map((q, index) => (
              <QuestionRow key={q.node_id} index={index + 1} node={q} onChase={onChase} />
            ))}
          </ol>
        </Section>
      )}

      {showArtifactOutline ? <ArtifactOutlineShelf investigationId={investigationId} /> : null}
    </div>
  );
}

function Section({
  heading,
  descriptor,
  count,
  kind,
  children,
}: {
  heading: string;
  descriptor: string;
  count: number;
  kind: "insight" | "question";
  children: React.ReactNode;
}) {
  return (
    <section className={`distillation-ledger distillation-ledger--${kind}`}>
      <header className="distillation-ledger__header">
        <div>
          <p className="distillation-ledger__descriptor">{descriptor}</p>
          <h3 className="distillation-ledger__heading">{heading}</h3>
        </div>
        <span
          className="distillation-ledger__count"
          aria-label={`${count} ${count === 1 ? (kind === "insight" ? "insight" : "open question") : heading.toLowerCase()}`}
        >
          {String(count).padStart(2, "0")}
        </span>
      </header>
      {children}
    </section>
  );
}

function InsightRow({
  node,
  index,
  investigationId,
  onRefined,
  challengeInsight,
}: {
  node: DistilledNode;
  index: number;
  investigationId: string;
  onRefined: () => Promise<void>;
  challengeInsight: typeof challengeNote;
}) {
  const [outcome, setOutcome] = useState<
    "idle" | "busy" | "changed" | "unchanged" | "escalated" | "noSource" | "noModel" | "error"
  >("idle");

  const runChallenge = async () => {
    setOutcome("busy");
    try {
      const res = await challengeInsight(node.node_id, { investigation_id: investigationId });
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
    <li className="distillation-ledger__row">
      <div className="flex items-start gap-3">
        <span className="distillation-ledger__index" aria-hidden="true">{String(index).padStart(2, "0")}</span>
        <div className="min-w-0 flex-1">
          <p className="font-serif text-[14px] leading-relaxed text-ink dark:text-bright">
            {node.text}
          </p>
          <div className="mt-1 flex flex-wrap items-center gap-2 text-[11px] text-shadow-1 dark:text-moonlight">
            <Grounding node={node} />
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

function QuestionRow({ node, index, onChase }: { node: DistilledNode; index: number; onChase?: (q: DistilledNode) => void }) {
  return (
    <li className="distillation-ledger__row">
      <span className="distillation-ledger__index" aria-hidden="true">Q{String(index).padStart(2, "0")}</span>
      <div className="min-w-0 flex-1">
        <p className="font-serif text-[14px] leading-relaxed text-ink dark:text-bright">{node.text}</p>
        <div className="mt-1 flex flex-wrap items-center gap-2 text-[11px] text-shadow-1 dark:text-moonlight">
          {node.escalated ? (
            <span className="font-mono text-sun-deep dark:text-sun">this needs more research</span>
          ) : null}
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
