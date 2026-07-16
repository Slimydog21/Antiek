import { useCallback, useEffect, useState } from "react";
import { useParams } from "react-router-dom";

import SessionBrandChrome from "../../brand/SessionBrandChrome";
import { getDistillation, ApiError } from "../../lib/api";
import type { DistilledNode } from "../../lib/api";
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

/**
 * AutoNotebook — the auto-generated, always-current narrative VIEW of a
 * workstation's insight/question graph (SPR-06 M1).
 *
 * ⚠️ PROPOSED — SIGN-OFF PENDING. The operator's resolution that "a notebook IS
 * the auto-generated narrative view of the graph (document lens over the
 * block-lens canvas), one per investigation, always auto, no manual save" is
 * PROPOSED, not ratified. This surface ships behind a visible "proposed
 * (sign-off pending)" banner and is a DERIVED, REVERSIBLE leaf:
 *   - it adds NO new persisted store and NO new writes — the single-writer
 *     DuckDB invariant is untouched (it only READS getDistillation + the
 *     synthesis events the workstation already streams);
 *   - removing this route + the banner reverts cleanly to the manual TipTap
 *     Notebook (modes/Notebook/index.tsx), which is a SEPARATE surface this
 *     does not touch;
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

const PROPOSED_BANNER_TEXT =
  "Proposed — sign-off pending. This notebook is generated from your research's graph and regenerates as you work; the design isn't ratified yet.";

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
      <AutoNotebookBody notebook={notebook} />
    </AutoNotebookShell>
  );
}

/** The shell — always carries the "proposed (sign-off pending)" banner at the
 *  top. The banner is ONLY on the AUTO view (the manual Notebook editor is a
 *  separate, unbannered surface). */
function AutoNotebookShell({ children }: { children: React.ReactNode }) {
  return (
    <div className="flex flex-col h-screen">
      <ProposedBanner />
      <main className="flex-1 min-h-0 bg-ice-0 dark:bg-charcoal-2 overflow-y-auto">
        {children}
      </main>
    </div>
  );
}

/**
 * The "Proposed — sign-off pending" banner. §5 voice (plain, honest), warning
 * affordance built on the design system's warning palette (the `sun` family is
 * the brand's warning/attention token — see design/tokens.ts; here expressed via
 * the `sun` Tailwind utilities the rest of the app uses for attention states).
 * Honest copy: this is NOT a ratified feature.
 */
function ProposedBanner() {
  return (
    <div
      role="note"
      aria-label="Proposed feature — sign-off pending"
      data-testid="auto-notebook-proposed-banner"
      className="flex items-start gap-2 border-b border-sun/40 bg-sun/15 px-6 py-2.5 text-[13px] leading-relaxed text-ink dark:text-bright"
    >
      <span className="mt-[2px] font-mono text-[10px] font-bold uppercase tracking-wider text-sun-deep dark:text-sun shrink-0">
        proposed
      </span>
      <p className="font-serif">{PROPOSED_BANNER_TEXT}</p>
    </div>
  );
}

function AutoNotebookBody({ notebook }: { notebook: DerivedNotebook }) {
  if (notebook.isEmpty) {
    // RIGOR #1: nothing in the graph to narrate yet — say so honestly, never
    // invent a section/insight/question.
    return (
      <article className="max-w-3xl mx-auto px-8 py-12">
        <div className="mx-auto max-w-md space-y-3 text-center">
          <SessionBrandChrome
            testIdPrefix="auto-notebook-empty"
            title={notebook.title}
            titleClassName="text-2xl font-serif text-ink dark:text-bright leading-tight"
          >
            <p className="text-sm text-ink-soft dark:text-starlight leading-relaxed">
              This notebook writes itself from the research’s insights and open
              questions. There’s nothing in the graph to narrate yet — as the
              research produces insights and questions, they appear here.
            </p>
          </SessionBrandChrome>
        </div>
      </article>
    );
  }

  return (
    <article className="max-w-3xl mx-auto px-8 py-10 space-y-8">
      <SessionBrandChrome
        testIdPrefix="auto-notebook"
        title={notebook.title}
        titleClassName="text-2xl font-serif text-ink dark:text-bright leading-tight"
      >
        <p className="text-xs font-mono text-shadow-1 dark:text-moonlight">
          generated from this research’s graph · regenerates as you work
        </p>
      </SessionBrandChrome>

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
              {s.heading}
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
      <section data-section="synthesis">
        <MasterMdViewer synthesis={synthesis} />
      </section>
    );
  }

  // Insights / open-questions sections — graph leaves, read-only.
  return (
    <section data-section={section.kind}>
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
