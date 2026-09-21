import { useCallback, useEffect, useState } from "react";
import { Link, useParams } from "react-router-dom";

import {
  getDistillation,
  getPromptTelemetry,
  ApiError,
} from "../../lib/api";
import type { DistilledNode, PromptTelemetryResponse } from "../../lib/api";
import { parseSynthesis } from "../../lib/synthesisParser";
import { useInvestigation } from "../../hooks/useInvestigation";
import AIActionFailure from "../../shared/AIActionFailure";
import Thinking from "../../shared/Thinking";
import MasterMdViewer from "../ResearchWorkstation/MasterMdViewer";
import {
  deriveAutoNotebook,
  type AutoNotebook as DerivedNotebook,
  type AutoNotebookSection,
} from "./deriveAutoNotebook";
import NotebookLoopNav, { writeHandoffHref } from "./NotebookLoopNav";

/**
 * AutoNotebook — the auto-generated, always-current narrative VIEW of a
 * workstation's insight/question graph (SPR-06 M1).
 *
 * ✅ RATIFIED 2026-09-18 — auto-generated narrative view of the graph;
 * derived leaf (no new DuckDB store). See
 * docs/decisions/spr-06-auto-notebook-proposed.md.
 *   - it is NOT a hard dependency of SPR-05 (research home) or SPR-07 (Read).
 * Rationale + what-would-ratify-vs-revert: docs/decisions/spr-06-auto-notebook-proposed.md.
 *
 * HOW IT RE-DERIVES ON GRAPH CHANGE: it subscribes to the investigation's event
 * stream via the SHARED useInvestigation hook (the same WS plumbing the
 * workstation uses). When the graph changes — a new insight/question node, or
 * the synthesis settling — the event list changes, which re-runs the
 * distillation re-fetch effect; the pure deriveAutoNotebook() then recomputes
 * the outline + sections from the new graph state. The DOCUMENT is the BLOCK
 * graph re-rendered, never a saved snapshot.
 *
 * RIGOR #1: it renders ONLY real graph content. An investigation with no
 * distillation and no synthesis derives an empty notebook → an honest empty
 * state, never invented sections. The synthesis section is rendered by
 * MasterMdViewer, which honors the §9.0 servable guard (a withheld source's body
 * never renders), so this view inherits the no-leak guarantee rather than
 * re-extracting bodies.
 *
 * SPR-09 NOTE: this notebook's dynamic OUTLINE is the artifact the Write surface
 * (SPR-09) will later consume as its outline. We do NOT build Write here — we
 * only produce the outline shape (deriveAutoNotebook → AutoNotebook.outline) it
 * will read.
 */

type DistillState =
  | { kind: "loading" }
  | { kind: "loaded"; insights: DistilledNode[]; questions: DistilledNode[] }
  | { kind: "error"; reason: string | null };

export default function AutoNotebook() {
  const params = useParams<{ investigationId?: string }>();
  const investigationId = params.investigationId ?? null;

  if (!investigationId) {
    return (
      <AutoNotebookShell>
        <div className="max-w-md text-center space-y-3 mx-auto">
          <h2 className="text-lg font-serif text-ink dark:text-bright">
            Auto-notebook
          </h2>
          <p className="text-sm text-ink-soft dark:text-starlight leading-relaxed">
            The auto-notebook is the narrative view of one research's graph.
            Open it for a specific research at{" "}
            <code className="font-mono">/notebook/auto/&lt;research-id&gt;</code>.
          </p>
        </div>
      </AutoNotebookShell>
    );
  }

  return <AutoNotebookForInvestigation investigationId={investigationId} />;
}

function AutoNotebookForInvestigation({
  investigationId,
}: {
  investigationId: string;
}) {
  // The SHARED event stream — re-derives on graph change (M1). The workstation
  // uses this exact hook; the auto-notebook is the SAME live context, rendered
  // as a document.
  const investigation = useInvestigation(investigationId);
  const [distill, setDistill] = useState<DistillState>({ kind: "loading" });

  const loadDistill = useCallback(async () => {
    try {
      const res = await getDistillation(investigationId);
      setDistill({
        kind: "loaded",
        insights: res.insights,
        questions: res.questions,
      });
    } catch (e) {
      const reason = e instanceof ApiError ? e.body || null : null;
      setDistill({ kind: "error", reason });
    }
  }, [investigationId]);

  // Re-fetch the distillation whenever the graph's event count moves — a new
  // insight/question node appended, or the synthesis settling. This is the
  // event-driven re-derive: the outline + sections flip to the new graph state.
  // HONEST NOTE: the count advances on EVERY streamed event (incl. thinking /
  // dispatch frames), so during an active run this re-fetches getDistillation
  // MORE OFTEN than the graph strictly changes — an over-fetch, never a miss.
  // That is the chosen tradeoff: the re-derive is idempotent and the distillation
  // GET is cheap, so we over-fetch to GUARANTEE we never miss a real graph change.
  // A graph-bearing-event allowlist could trim it, but would risk going stale if
  // a new node-event type is added — the safe over-fetch is preferred for this
  // PROPOSED, reversible view.
  const eventCount = investigation.events.length;
  useEffect(() => {
    void loadDistill();
  }, [loadDistill, eventCount]);

  // The synthesis is parsed from the SAME graph events (no second fetch). Null
  // until a synthesize.delivered lands — the in-progress / no-key case.
  const synthesis = parseSynthesis(investigation.events);

  // Loading: still seeding the graph + first distillation fetch.
  if (
    investigation.status === "loading" ||
    distill.kind === "loading"
  ) {
    return (
      <AutoNotebookShell>
        <div
          className="flex items-center gap-2 px-4 py-6"
          role="status"
          aria-live="polite"
        >
          <Thinking
            size={28}
            label="Generating the notebook from your research's graph"
            status="reading the graph…"
          />
        </div>
      </AutoNotebookShell>
    );
  }

  if (investigation.status === "not_found") {
    return (
      <AutoNotebookShell>
        <p className="text-sm text-shadow-1 dark:text-moonlight font-serif text-center">
          No research with id{" "}
          <code className="font-mono">{investigationId}</code>.
        </p>
      </AutoNotebookShell>
    );
  }

  if (distill.kind === "error") {
    return (
      <AutoNotebookShell>
        <div className="px-4 py-6">
          <AIActionFailure
            title="Couldn’t generate the notebook"
            reason={distill.reason}
            onRetry={() => void loadDistill()}
          />
        </div>
      </AutoNotebookShell>
    );
  }

  // Derive the notebook from the EXISTING graph. Pure — recomputed each render
  // from the current distillation + parsed synthesis, so a graph change flips
  // the outline + sections (M1, rigor #1: only real graph content).
  const notebook = deriveAutoNotebook({
    investigationId,
    question: investigation.question ?? synthesis?.question ?? null,
    insights: distill.insights,
    questions: distill.questions,
    synthesis,
  });

  return (
    <AutoNotebookShell>
      <AutoNotebookBody
        notebook={notebook}
        investigationId={investigationId}
      />
    </AutoNotebookShell>
  );
}

/** The shell — always carries the "proposed (sign-off pending)" banner at the
 *  top. The banner is ONLY on the AUTO view (the manual Notebook editor is a
 *  separate, unbannered surface). */
function AutoNotebookShell({ children }: { children: React.ReactNode }) {
  return (
    <div className="flex flex-col h-full" data-testid="auto-notebook-shell">
      <main className="flex-1 min-h-0 bg-ice-0 dark:bg-charcoal-2 overflow-y-auto">
        {children}
      </main>
    </div>
  );
}


function AutoNotebookBody({
  notebook,
  investigationId,
}: {
  notebook: DerivedNotebook;
  investigationId: string;
}) {
  if (notebook.isEmpty) {
    // RIGOR #1: nothing in the graph to narrate yet — say so honestly, never
    // invent a section/insight/question.
    return (
      <article className="max-w-3xl mx-auto px-8 py-12">
        <NotebookLoopNav
          investigationId={investigationId}
          canWrite={false}
          writeTitle={notebook.title}
        />

        <div className="max-w-md mx-auto text-center space-y-3">
          <h1 className="text-2xl font-serif text-ink dark:text-bright leading-tight">
            {notebook.title}
          </h1>
          <p className="text-sm text-ink-soft dark:text-starlight leading-relaxed">
            This notebook writes itself from the research’s insights and open
            questions. There’s nothing in the graph to narrate yet — keep researching
            (or open Distill); as insights land, they appear here. When you’re
            ready, continue in Write with this research connected.
          </p>
        </div>
        <div className="mt-10">
          <PromptTelemetryPanel investigationId={investigationId} />
        </div>
      </article>
    );
  }

  return (
    <article className="max-w-3xl mx-auto px-8 py-10 space-y-8">
      <header className="space-y-2">
        <NotebookLoopNav
          investigationId={notebook.investigationId}
          canWrite
          writeTitle={notebook.title}
        />
        <h1 className="text-2xl font-serif text-ink dark:text-bright leading-tight">
          {notebook.title}
        </h1>
        <p className="text-xs font-mono text-shadow-1 dark:text-moonlight">
          generated from this research’s graph · regenerates as you work
        </p>
        <p className="pt-1">
          <Link
            to={writeHandoffHref(notebook.investigationId, notebook.title)}
            data-testid="auto-notebook-import-write"
            className="inline-flex font-mono text-[11px] uppercase tracking-wider text-aurora underline-offset-2 hover:underline"
          >
            Import outline into Write →
          </Link>
        </p>
      </header>

      {/* The dynamic OUTLINE — derived from which sections the graph carries.
          It flips when the graph changes. This is the artifact SPR-09's Write
          surface will consume (its dynamic outline). */}
      <nav
        aria-label="Notebook outline"
        data-testid="auto-notebook-outline"
        className="border-l-2 border-rule dark:border-charcoal-1 pl-3 space-y-1"
      >
        <p className="font-mono text-[10px] uppercase tracking-wider text-shadow-1 dark:text-moonlight">
          Outline
        </p>
        <ul className="space-y-0.5">
          {notebook.outline.map((s) => (
            <li
              key={s.kind}
              data-outline-section={s.kind}
              className="text-[13px] font-serif text-ink-soft dark:text-starlight"
            >
              <a
                href={`#notebook-section-${s.kind}`}
                className="underline-offset-2 hover:underline focus-visible:outline focus-visible:outline-2 focus-visible:outline-sun"
              >
                {s.heading}
              </a>
            </li>
          ))}
        </ul>
      </nav>

      {/* The SECTIONS — the same graph data as a living document. */}
      <div className="space-y-8">
        {notebook.outline.map((s) => (
          <SectionView
            key={s.kind}
            section={s}
            synthesis={notebook.synthesis}
          />
        ))}
      </div>

      <PromptTelemetryPanel investigationId={investigationId} />
    </article>
  );
}

function SectionView({
  section,
  synthesis,
}: {
  section: AutoNotebookSection;
  synthesis: DerivedNotebook["synthesis"];
}) {
  if (section.kind === "synthesis") {
    // The synthesis is rendered by MasterMdViewer — which OWNS the §9.0 servable
    // guard (a restricted source's body is never served; it shows "not available
    // to open"). The auto-notebook inherits that no-leak guarantee rather than
    // re-extracting bodies. Null guard is defensive: deriveAutoNotebook only
    // emits this section when synthesis has content.
    if (!synthesis) return null;
    return (
      <section id="notebook-section-synthesis" data-section="synthesis">
        <MasterMdViewer synthesis={synthesis} />
      </section>
    );
  }

  // Insights / open-questions sections — graph leaves, read-only.
  return (
    <section id={`notebook-section-${section.kind}`} data-section={section.kind}>
      <h2 className="mb-2 font-mono text-[11px] uppercase tracking-wider text-shadow-1 dark:text-moonlight">
        {section.heading}
      </h2>
      <ul className="space-y-2.5">
        {section.entries.map((e) => (
          <li key={e.nodeId} className="flex items-start gap-2.5">
            <span
              className={`mt-[7px] h-1.5 w-1.5 shrink-0 rounded-full ${
                section.kind === "insights"
                  ? "bg-aurora"
                  : "bg-sun-deep dark:bg-sun"
              }`}
              aria-hidden="true"
            />
            <div className="min-w-0 flex-1">
              <p className="font-serif text-[14px] leading-relaxed text-ink dark:text-bright">
                {e.text}
              </p>
              {e.sourceDocumentId && (
                <p
                  className="mt-0.5 font-mono text-[11px] text-shadow-1 dark:text-moonlight"
                  data-testid="auto-notebook-citation"
                >
                  <Link
                    to={`/read/${encodeURIComponent(e.sourceDocumentId)}`}
                    className="underline-offset-2 hover:underline text-aurora"
                    data-testid="auto-notebook-citation-link"
                  >
                    open source in reader →
                  </Link>
                </p>
              )}
              {e.escalated && (
                <p className="mt-0.5 font-mono text-[11px] text-sun-deep dark:text-sun">
                  this needs more research
                </p>
              )}
            </div>
          </li>
        ))}
      </ul>
    </section>
  );
}


/** Trajectory-backed prompt / model-call telemetry (event-log SoT).
 *  Citations stay in insights/questions; this panel is the call ledger. */
function PromptTelemetryPanel({ investigationId }: { investigationId: string }) {
  const [state, setState] = useState<
    | { kind: "loading" }
    | { kind: "error"; reason: string }
    | { kind: "loaded"; data: PromptTelemetryResponse }
  >({ kind: "loading" });

  useEffect(() => {
    let cancelled = false;
    setState({ kind: "loading" });
    // Promise.resolve so a missing/undefined mock or sync throw never
    // becomes an unhandled rejection during tests / dogfood.
    void Promise.resolve(getPromptTelemetry(investigationId))
      .then((data) => {
        if (!cancelled) setState({ kind: "loaded", data });
      })
      .catch((err: unknown) => {
        if (!cancelled) {
          setState({
            kind: "error",
            reason: err instanceof Error ? err.message : "couldn’t load telemetry",
          });
        }
      });
    return () => {
      cancelled = true;
    };
  }, [investigationId]);

  if (state.kind === "loading") {
    return (
      <section
        data-testid="prompt-telemetry"
        data-telemetry-state="loading"
        className="border-t border-rule dark:border-charcoal-1 pt-6"
      >
        <p className="font-mono text-[10px] uppercase tracking-wider text-shadow-1 dark:text-moonlight">
          Prompts & model calls
        </p>
        <p className="mt-2 text-sm text-ink-soft dark:text-starlight">Loading telemetry…</p>
      </section>
    );
  }
  if (state.kind === "error") {
    return (
      <section
        data-testid="prompt-telemetry"
        data-telemetry-state="error"
        className="border-t border-rule dark:border-charcoal-1 pt-6"
      >
        <p className="font-mono text-[10px] uppercase tracking-wider text-shadow-1 dark:text-moonlight">
          Prompts & model calls
        </p>
        <p className="mt-2 text-sm text-ink-soft dark:text-starlight">{state.reason}</p>
      </section>
    );
  }

  const { data } = state;
  const qPreview =
    data.question && data.question.length > 280
      ? `${data.question.slice(0, 280)}…`
      : data.question;

  return (
    <section
      data-testid="prompt-telemetry"
      data-telemetry-state="loaded"
      data-call-count={data.call_count}
      className="border-t border-rule dark:border-charcoal-1 pt-6 space-y-3"
    >
      <div className="flex flex-wrap items-baseline justify-between gap-2">
        <p className="font-mono text-[10px] uppercase tracking-wider text-shadow-1 dark:text-moonlight">
          Prompts & model calls
        </p>
        <p className="font-mono text-[10px] text-shadow-1 dark:text-moonlight">
          {data.call_count} call{data.call_count === 1 ? "" : "s"}
          {data.total_latency_ms > 0
            ? ` · ${(data.total_latency_ms / 1000).toFixed(1)}s model time`
            : ""}
          {data.total_cost_usd > 0
            ? ` · $${data.total_cost_usd.toFixed(4)}`
            : ""}
        </p>
      </div>
      {qPreview ? (
        <div className="rounded-md bg-ice-1 dark:bg-charcoal-1 px-3 py-2">
          <p className="font-mono text-[10px] uppercase tracking-wider text-shadow-1 dark:text-moonlight mb-1">
            Research question
          </p>
          <p className="font-serif text-[13px] leading-relaxed text-ink dark:text-bright whitespace-pre-wrap">
            {qPreview}
          </p>
        </div>
      ) : null}
      {data.call_count === 0 ? (
        <p
          className="text-sm text-ink-soft dark:text-starlight"
          data-telemetry-empty="true"
        >
          No model calls on this trajectory yet — prompts stay hashed in the event log once research roles run (bodies never stored here).
        </p>
      ) : (
        <ul className="space-y-2" data-testid="prompt-telemetry-calls">
          {data.calls.map((c, i) => (
            <li
              key={c.event_id ?? `${c.role}-${i}`}
              className="rounded-md border border-rule dark:border-charcoal-1 px-3 py-2 text-[12px]"
            >
              <div className="flex flex-wrap gap-x-3 gap-y-0.5 font-mono text-[11px] text-ink dark:text-bright">
                <span className="font-semibold">{c.role}</span>
                <span>
                  {c.provider}/{c.model}
                </span>
                <span>{c.finish_reason ?? "—"}</span>
                <span>{c.latency_ms}ms</span>
                {c.cost_usd > 0 ? <span>${c.cost_usd.toFixed(4)}</span> : null}
              </div>
              {c.prompt_hash ? (
                <p className="mt-1 font-mono text-[10px] text-shadow-1 dark:text-moonlight truncate">
                  prompt_hash {c.prompt_hash.slice(0, 16)}…
                </p>
              ) : null}
            </li>
          ))}
        </ul>
      )}
      <p className="font-mono text-[10px] text-shadow-1 dark:text-moonlight">
        From event log · prompt bodies not stored (hash only)
      </p>
    </section>
  );
}
