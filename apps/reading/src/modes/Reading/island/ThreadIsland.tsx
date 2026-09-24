/**
 * ThreadIsland — the research-thread island component (island SPR-02). ONE
 * component, TWO render states driven by local view state:
 *
 *   COLLAPSED — a small status glyph at the passage's inline end (the unit-1
 *   highlight wash + underline on the text is the decorations pipeline's
 *   mark; this component adds the live-thread signal): a single 8px
 *   token-coloured dot — pulsing while the thread is live (motion only from
 *   the design system's animate-pulse + motion-reduce honored), steady sun
 *   when complete with findings, steady muted when complete-empty, an honest
 *   terminal glyph on failure/stop/budget-halt, and a hollow ring for a
 *   missing record (gone).
 *
 *   EXPANDED — the pinned overlay card (activated from the glyph), dismissed
 *   by Esc / click-away / Dismiss. NEVER a workspace window: it renders in
 *   the island's widget layer over the reading surface, positioned from the
 *   passage rect the surface resolved. Contents, per the spec:
 *     1. the status line (question, live state, cost-so-far);
 *     2. the distilled outcome when terminal (lead insights + open questions
 *        with refinement counts + honest empty states);
 *     3. the thread FAMILY (root + chases, per-node status);
 *     4. three actions: Open research (/inv/:id), Dig deeper (inert stub,
 *        placed for SPR-04), Dismiss (+ the per-device Hide preference).
 *
 * The §9.0 boundary is structural: `passageQuote` arrives null on a
 * metadata-only anchor, so the card can only ever show passage POSITION
 * there — never a withheld sentence.
 */
import { useCallback, useEffect, useRef, useState } from "react";
import { Link } from "react-router-dom";

import {
  researchStateDotClass,
  researchStateLabel,
} from "../../../shared/researchState";
import type { ResearchState } from "../../../shared/researchState";
import { hideIsland } from "./hiddenIslands";
import { useIslandThread } from "./useIslandThread";
import type { IslandStatus } from "./islandModel";

export interface ThreadIslandProps {
  anchorId: string;
  documentId: string;
  investigationId: string;
  servable: boolean;
  passageQuote: string | null;
  /** The anchor's page hint (position the card shows on a metadata-only
   *  anchor, where a quote would be a leak). */
  pageIndexHint: number | null;
}

/** The status-glyph vocabulary: dot class + accessible label per island
 *  status. Token colours only; the live pulse is the design system's own
 *  animate-pulse with motion-reduce honored. */
const STATUS_GLYPHS: Record<IslandStatus, { className: string; label: string; pulse: boolean }> = {
  live: { className: "bg-sun animate-pulse motion-reduce:animate-none", label: "research running", pulse: true },
  complete: { className: "bg-sun", label: "research complete", pulse: false },
  complete_empty: { className: "bg-[var(--state-muted)]", label: "research complete — no findings yet", pulse: false },
  failed: { className: "bg-[var(--state-blocked)]", label: "research needs attention", pulse: false },
  stopped: { className: "bg-[var(--state-stopped)]", label: "research stopped", pulse: false },
  budget_halted: { className: "bg-[var(--state-blocked)]", label: "research budget halted", pulse: false },
  gone: { className: "bg-transparent border border-current", label: "research record not found", pulse: false },
};

const STATUS_LINES: Record<IslandStatus, string> = {
  live: "working…",
  complete: "done",
  complete_empty: "done — no findings yet",
  failed: "needs attention",
  stopped: "stopped",
  budget_halted: "budget halted",
  gone: "record not found",
};

/** Map the family node's summary status to the shared research-state dot
 *  vocabulary (one registry, never a second encoding). */
function familyState(status: string | null): ResearchState {
  switch (status) {
    case "in_progress":
      return "working";
    case "completed":
      return "done";
    case "failed":
      return "blocked";
    case "stopped":
      return "stopped";
    default:
      return "unavailable";
  }
}

export default function ThreadIsland({
  anchorId,
  documentId: _documentId,
  investigationId,
  servable,
  passageQuote,
  pageIndexHint,
}: ThreadIslandProps) {
  const [expanded, setExpanded] = useState(false);
  const thread = useIslandThread(investigationId);
  const cardRef = useRef<HTMLDivElement>(null);

  const collapse = useCallback(() => setExpanded(false), []);

  // Esc (element-scoped — the card's own key, never a global binding) and
  // click-away collapse the open card. Dismiss is the same collapse.
  useEffect(() => {
    if (!expanded) return;
    function onKey(e: KeyboardEvent) {
      if (e.key === "Escape") collapse();
    }
    function onDocMouseDown(e: MouseEvent) {
      if (cardRef.current && !cardRef.current.contains(e.target as Node)) collapse();
    }
    document.addEventListener("keydown", onKey);
    document.addEventListener("mousedown", onDocMouseDown);
    return () => {
      document.removeEventListener("keydown", onKey);
      document.removeEventListener("mousedown", onDocMouseDown);
    };
  }, [expanded, collapse]);

  const glyph = STATUS_GLYPHS[thread.status];

  if (!expanded) {
    return (
      <button
        type="button"
        data-island-id={anchorId}
        data-island-state="collapsed"
        data-island-status={thread.status}
        aria-label={`Research thread: ${glyph.label}. Expand the island.`}
        title={glyph.label}
        onClick={() => setExpanded(true)}
        className="inline-flex items-center justify-center w-3 h-3 align-middle"
      >
        <span
          data-island-glyph
          className={`inline-block w-2 h-2 rounded-full ${glyph.className}`}
        />
      </button>
    );
  }

  const terminal =
    thread.status !== "live" && thread.status !== "gone";

  return (
    <div
      ref={cardRef}
      data-island-id={anchorId}
      data-island-state="expanded"
      data-island-status={thread.status}
      role="dialog"
      aria-label={`Research thread island — ${glyph.label}`}
      className="absolute left-0 top-full mt-1 z-30 w-72 rounded-md border-edge border-sun bg-ice-0 dark:bg-charcoal-2 text-ink dark:text-bright shadow-z3 dark:shadow-z3-night p-3 text-xs"
    >
      {/* 1 — the status line: question, live state, cost-so-far. */}
      <div className="flex items-baseline justify-between gap-2 mb-1.5">
        <p className="font-serif text-sm leading-snug min-w-0 truncate">
          {thread.question ?? "untitled research"}
        </p>
        <button
          type="button"
          onClick={collapse}
          aria-label="Dismiss the island"
          className="shrink-0 text-shadow-1 hover:text-ink dark:hover:text-bright px-1"
        >
          ×
        </button>
      </div>
      <p className="font-mono text-xxs text-shadow-1 dark:text-moonlight mb-2" data-island-statusline>
        {STATUS_LINES[thread.status]}
        {thread.costTotal > 0 ? ` · $${thread.costTotal.toFixed(2)} so far` : ""}
      </p>

      {/* The servability boundary, structural: the quote ONLY when servable. */}
      {servable && passageQuote ? (
        <blockquote
          data-island-quote
          className="font-serif italic text-ink-soft dark:text-starlight border-l-edge border-sun pl-2 mb-2 line-clamp-3"
        >
          “{passageQuote}”
        </blockquote>
      ) : (
        <p
          data-island-position
          className="font-mono text-xxs text-shadow-1 dark:text-moonlight mb-2"
        >
          {pageIndexHint !== null ? `Passage on page ${pageIndexHint + 1}` : "A passage in this book"}
        </p>
      )}

      {thread.status === "gone" ? (
        <p className="text-shadow-1 dark:text-moonlight italic" data-island-gone>
          This thread's record is missing — the island can't show it. The anchor
          is untouched; only the record is gone.
        </p>
      ) : null}

      {/* 2 — the distilled outcome when terminal. */}
      {terminal ? (
        <div data-island-outcome className="mb-2">
          {thread.outcomeLoading ? (
            <p className="text-shadow-1 dark:text-moonlight">Reading the outcome…</p>
          ) : thread.outcome && (thread.outcome.insights.length > 0 || thread.outcome.questions.length > 0) ? (
            <>
              {thread.outcome.insights.length > 0 ? (
                <ul className="mb-1.5 space-y-0.5" data-island-insights>
                  {thread.outcome.insights.slice(0, 3).map((insight) => (
                    <li key={insight.node_id} className="leading-snug">
                      <span className="text-sun-deep">·</span> {insight.text}
                      {insight.refinement_count > 0 ? (
                        <span className="text-shadow-1 dark:text-moonlight">
                          {" "}· refined ×{insight.refinement_count}
                        </span>
                      ) : null}
                    </li>
                  ))}
                </ul>
              ) : null}
              {thread.outcome.questions.length > 0 ? (
                <ul className="space-y-0.5" data-island-questions>
                  {thread.outcome.questions.slice(0, 3).map((q) => (
                    <li key={q.node_id} className="leading-snug text-shadow-1 dark:text-moonlight">
                      ? {q.text}
                      {q.refinement_count > 0 ? ` · refined ×${q.refinement_count}` : ""}
                    </li>
                  ))}
                </ul>
              ) : null}
            </>
          ) : (
            <p className="text-shadow-1 dark:text-moonlight italic" data-island-empty-outcome>
              No findings or open questions on record for this thread.
            </p>
          )}
        </div>
      ) : null}

      {/* 3 — the thread family (root + chases, per-node status). */}
      {thread.family.length > 0 ? (
        <ul className="mb-2 space-y-0.5" data-island-family>
          {thread.family.map((node) => (
            <li
              key={node.investigationId}
              className="flex items-center gap-1.5"
              style={{ paddingLeft: `${node.depth * 12}px` }}
            >
              <span
                className={`inline-block w-1.5 h-1.5 rounded-full shrink-0 ${researchStateDotClass(familyState(node.status), false)}`}
              />
              <span className="truncate text-shadow-1 dark:text-moonlight">
                {node.question ?? node.investigationId}
                <span className="text-xxs"> · {researchStateLabel(familyState(node.status))}</span>
              </span>
            </li>
          ))}
        </ul>
      ) : null}

      {/* 4 — the actions. */}
      <div className="flex items-center gap-2 border-t border-hairline pt-2">
        <Link
          to={`/inv/${encodeURIComponent(investigationId)}`}
          className="text-sun-deep underline-offset-2 hover:underline"
          data-island-open
        >
          Open research →
        </Link>
        <button
          type="button"
          disabled
          data-island-dig-deeper
          title="Dig deeper — wires in the next sprint (SPR-04)"
          className="text-shadow-1 dark:text-moonlight italic cursor-not-allowed"
        >
          Dig deeper (soon)
        </button>
        <button
          type="button"
          onClick={() => {
            hideIsland(anchorId);
            collapse();
          }}
          className="ml-auto text-shadow-1 hover:text-ink dark:hover:text-bright"
          title="Hide this island on this device (the anchor and thread are untouched)"
          data-island-hide
        >
          Hide
        </button>
      </div>
    </div>
  );
}
