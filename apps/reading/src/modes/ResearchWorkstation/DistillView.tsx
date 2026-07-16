import { useCallback, useEffect, useState } from "react";
import { ChevronDown, ChevronRight } from "lucide-react";

import {
  getDistillation,
  getNoteHistory,
  challengeNote,
  ApiError,
} from "../../lib/api";
import type { DistilledNode } from "../../lib/api";
import type { NoteHistoryResponse } from "../../lib/api";
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
}

type LoadState =
  | { kind: "loading" }
  | { kind: "loaded"; insights: DistilledNode[]; questions: DistilledNode[] }
  | { kind: "error"; reason: string | null };

export default function DistillView({ investigationId, running, onChase }: DistillViewProps) {
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

      <ArtifactOutlineShelf investigationId={investigationId} />
    </div>
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
  const [challengeKey, setChallengeKey] = useState(() => crypto.randomUUID());
  const [historyVersion, setHistoryVersion] = useState(0);

  const runChallenge = async () => {
    setOutcome("busy");
    try {
      const res = await challengeNote(node.node_id, {
        investigation_id: investigationId,
        idempotency_key: challengeKey,
      });
      if (res.applied) {
        setHistoryVersion((version) => version + 1);
        setOutcome("changed");
        await onRefined(); // refetch so the refined node text re-renders from the graph
        setChallengeKey(crypto.randomUUID());
      } else if (res.escalated) {
        setOutcome("escalated");
        await onRefined();
        setChallengeKey(crypto.randomUUID());
      } else if (res.superseded) {
        setHistoryVersion((version) => version + 1);
        setChallengeKey(crypto.randomUUID());
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
            {node.refinement_count > 0 && (
              <NoteHistoryDisclosure node={node} investigationId={investigationId} version={historyVersion} />
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

function NoteHistoryDisclosure({
  node,
  investigationId,
  version,
}: {
  node: DistilledNode;
  investigationId: string;
  version: number;
}) {
  const [open, setOpen] = useState(false);
  const [history, setHistory] = useState<NoteHistoryResponse | null>(null);
  const [loading, setLoading] = useState(false);
  const [failed, setFailed] = useState(false);

  useEffect(() => {
    setOpen(false);
    setHistory(null);
    setLoading(false);
    setFailed(false);
  }, [node.node_id, node.refinement_count, version]);

  const load = async () => {
    setOpen(true);
    setLoading(true);
    setFailed(false);
    try {
      setHistory(await getNoteHistory(node.node_id, investigationId));
    } catch {
      setFailed(true);
    } finally {
      setLoading(false);
    }
  };

  const toggle = () => {
    if (open) setOpen(false);
    else if (history) setOpen(true);
    else void load();
  };

  return (
    <div className="basis-full">
      <button
        type="button"
        onClick={toggle}
        aria-expanded={open}
        className="inline-flex items-center gap-1 font-mono underline decoration-dotted underline-offset-2 transition-colors hover:text-ink dark:hover:text-bright"
      >
        {open ? <ChevronDown size={12} aria-hidden="true" /> : <ChevronRight size={12} aria-hidden="true" />}
        {node.refinement_count} {node.refinement_count === 1 ? "change" : "changes"}
      </button>
      {open && loading && (
        <p className="mt-1.5 font-mono text-[11px] italic" role="status">loading change history…</p>
      )}
      {open && failed && (
        <p className="mt-1.5 font-mono text-[11px]" role="alert">
          Couldn’t load change history.{" "}
          <button type="button" onClick={() => void load()} className="underline decoration-dotted underline-offset-2">
            Try again
          </button>
        </p>
      )}
      {open && history && !loading && !failed && (
        <div className="mt-2 border-l-2 border-rule pl-2.5 dark:border-charcoal-1">
          {!history.complete && (
            <p className="mb-2 font-mono text-[11px] text-shadow-1 dark:text-moonlight">
              Earlier changes predate the authoritative history available here.
            </p>
          )}
          <ol className="space-y-2">
            {history.entries.map((entry) => (
              <li key={entry.event_id} className="text-[12px] leading-relaxed">
                <p className="font-mono text-[10px] uppercase text-shadow-1 dark:text-moonlight">
                  {entry.outcome === "applied" ? "Changed" : "Attempt did not replace the note"}
                </p>
                <p className="font-serif text-ink dark:text-bright">{entry.new_text}</p>
                {entry.outcome === "applied" && (
                  <p className="font-serif italic text-ink-mute dark:text-moonlight">was: {entry.previous_text}</p>
                )}
              </li>
            ))}
          </ol>
        </div>
      )}
    </div>
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
