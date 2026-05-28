import type { DistilledNode } from "../../lib/api";
import type { ParsedSynthesis } from "../../lib/synthesisParser";

/**
 * deriveAutoNotebook — the PURE derivation behind the auto-notebook
 * (SPR-06 M1, PROPOSED resolution; operator sign-off pending).
 *
 * ⚠️ PROPOSED — SIGN-OFF PENDING. The "notebook = the auto-generated,
 * always-current narrative VIEW of the workstation's insight/question graph"
 * definition is the operator's PROPOSED resolution, NOT a ratified feature.
 * This whole surface is built behind a "proposed (sign-off pending)" banner and
 * stays a DERIVED, REVERSIBLE view — there is NO new persisted store, NO new
 * writes (single-writer DuckDB untouched), and removing the route + banner
 * reverts cleanly. See docs/decisions/spr-06-auto-notebook-proposed.md and the
 * roadmap open-questions register. Do NOT make this a hard dependency of any
 * other sprint; it is a cuttable leaf.
 *
 * WHAT THIS IS: a pure function from the EXISTING graph (the investigation's
 * distillation — insights + open-questions, read via getDistillation — plus the
 * parsed synthesis, parsed by synthesisParser) to a narrative OUTLINE + SECTIONS.
 * It re-derives on every call, so when the React wrapper re-fetches on a graph
 * change (the event stream the workstation already uses) the outline + sections
 * flip to the new graph state. It is the document lens over the same graph the
 * block-lens canvas renders.
 *
 * RIGOR #1 (load-bearing — intellectual honesty): this renders ONLY what the
 * graph actually carries. It never fabricates a section, insight, or question
 * the graph doesn't have. A section is emitted ONLY when its underlying graph
 * data is non-empty; an investigation with no distillation and no synthesis
 * derives an EMPTY notebook (`isEmpty: true`), and the surface shows an honest
 * empty state rather than invented content.
 *
 * §9.0 NO-LEAK: this function carries NO claim/chunk BODIES — the synthesis
 * SECTION is rendered by MasterMdViewer, which honors the §9.0 servable guard
 * (a withheld source's body never renders). This derivation only carries the
 * synthesis as a structural reference (`synthesis`), not extracted bodies, so it
 * cannot itself leak a restricted source.
 */

/** A leaf entry in a section — one insight or one open-question, by node. */
export interface AutoNotebookEntry {
  nodeId: string;
  text: string;
  /** "insight" | "question" — the §2.1 primitive (carried from the graph). */
  kind: string;
  /** A question the graph couldn't resolve — flagged "needs more research". */
  escalated: boolean;
}

export type AutoNotebookSectionKind = "synthesis" | "insights" | "questions";

export interface AutoNotebookSection {
  kind: AutoNotebookSectionKind;
  /** The §5-voice heading for this section (plain language, no jargon). */
  heading: string;
  /** Insight/question leaves — empty for the synthesis section (it carries the
   *  parsed synthesis instead, rendered by MasterMdViewer). */
  entries: AutoNotebookEntry[];
}

export interface AutoNotebook {
  investigationId: string;
  /** The notebook's title — the research question when the graph carries one,
   *  else a plain fallback. NEVER an invented title. */
  title: string;
  /** The dynamic outline: one entry per emitted section, in render order. It is
   *  DERIVED from the graph's themes (which sections the graph actually has),
   *  so it flips when the graph changes. */
  outline: AutoNotebookSection[];
  /** The parsed synthesis, carried through for MasterMdViewer to render the
   *  synthesis section (which owns the §9.0 servable guard). Null when the
   *  investigation has no synthesis yet. */
  synthesis: ParsedSynthesis | null;
  /** True when the graph carries nothing to narrate (no synthesis, no insights,
   *  no questions) — the surface shows an honest empty state, not fabrication. */
  isEmpty: boolean;
}

export interface DeriveInput {
  investigationId: string;
  /** The research question off the graph, when known (synthesis carries it, or
   *  the investigation's start event). Used only for the title + synthesis
   *  heading — never fabricated. */
  question: string | null;
  insights: DistilledNode[];
  questions: DistilledNode[];
  synthesis: ParsedSynthesis | null;
}

/** Does the parsed synthesis carry anything worth rendering as a section?
 *  A null synthesis, or one with no thesis + no components, is "nothing" — we
 *  must NOT emit a synthesis section for it (rigor #1: no empty fabricated
 *  section). */
function synthesisHasContent(s: ParsedSynthesis | null): boolean {
  if (!s) return false;
  return s.thesisSummary.trim().length > 0 || s.components.length > 0;
}

function entryFrom(n: DistilledNode): AutoNotebookEntry {
  return {
    nodeId: n.node_id,
    text: n.text,
    kind: n.kind,
    escalated: n.escalated,
  };
}

/**
 * Derive the auto-notebook from the existing graph. PURE — no I/O, no store.
 * Re-call it whenever the graph changes and the outline + sections re-derive.
 */
export function deriveAutoNotebook(input: DeriveInput): AutoNotebook {
  const { investigationId, question, insights, questions, synthesis } = input;

  const hasSynthesis = synthesisHasContent(synthesis);
  const hasInsights = insights.length > 0;
  const hasQuestions = questions.length > 0;

  const outline: AutoNotebookSection[] = [];

  // The synthesis section — emitted ONLY when there is a real synthesis. Its
  // BODY is rendered by MasterMdViewer (the §9.0 servable guard lives there);
  // here we only declare the section exists.
  if (hasSynthesis) {
    outline.push({
      kind: "synthesis",
      heading: question ? `On ${question}` : "What the research found",
      entries: [],
    });
  }

  // The insights section — the grounded claims, as graph leaves.
  if (hasInsights) {
    outline.push({
      kind: "insights",
      heading: "Insights",
      entries: insights.map(entryFrom),
    });
  }

  // The open-questions section — the unresolved threads.
  if (hasQuestions) {
    outline.push({
      kind: "questions",
      heading: "Open questions",
      entries: questions.map(entryFrom),
    });
  }

  const isEmpty = outline.length === 0;

  // The title is the research question when the graph carries one; otherwise a
  // plain, honest fallback — NEVER an invented title.
  const title = question?.trim()
    ? question.trim()
    : "This research";

  return {
    investigationId,
    title,
    outline,
    synthesis: hasSynthesis ? synthesis : null,
    isEmpty,
  };
}
