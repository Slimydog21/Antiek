/**
 * paletteFacet.ts — the PURE ⌘K workflow-facet logic (SPR-04 M4),
 * extracted from CommandPalette.tsx so it can be unit-tested without
 * importing the palette component (which pulls in lib/api + the whole
 * app data layer). Keeping this dependency-free also keeps the test
 * isolated — it touches no module that another test file mocks.
 *
 * CommandPalette.tsx imports these and layers the React UI on top.
 */
import { WORKFLOW_ORDER, type Workflow } from "./workflowTaxonomy";
import type { ResearchState } from "../shared/researchState";

/**
 * The minimal shape the facet logic needs from a palette entry. The real
 * PaletteEntry union (defined in CommandPalette.tsx) is structurally
 * compatible with this — `kind` + `title` + `subtitle` + an optional
 * `workflow` facet (routes/actions) — plus the substrate kinds we infer
 * a facet for. `state` + `unseen` (herdr transfer, P0-5) let the palette
 * filter to what needs the operator.
 */
export interface FacetEntry {
  kind: string;
  title: string;
  subtitle: string;
  workflow?: Workflow;
  /** Research-state facet (investigation entries only). */
  state?: ResearchState;
  /** Unseen completion flag (drives the unread axis in filters). */
  unseen?: boolean;
}

/** State-filter vocabulary — the `state:` facet chips. Kept here (not in
 *  researchState.ts) because it is palette vocabulary, not research truth:
 *  `all` is a filter affordance, never a research state. */
export const STATE_FILTERS = ["blocked", "working", "done", "unseen"] as const;
export type StateFilter = (typeof STATE_FILTERS)[number];

export function isStateFilter(word: string): word is StateFilter {
  return (STATE_FILTERS as readonly string[]).includes(word);
}

/** Map a leading query word to a workflow id, if it names one. */
export function leadingWorkflow(q: string): Workflow | null {
  const first = q.trim().toLowerCase().split(/\s+/)[0];
  const byLabel: Record<string, Workflow> = {
    research: "research",
    read: "read",
    write: "write",
    speak: "speak",
  };
  return byLabel[first] ?? null;
}

/**
 * Read a palette entry's workflow facet. Routes + actions carry it
 * explicitly; substrate kinds (investigation/document/notebook/parked)
 * are inferred to the workflow they live in.
 */
export function entryWorkflow<E extends FacetEntry>(e: E): Workflow | undefined {
  if (e.kind === "route" || e.kind === "action") return e.workflow;
  if (e.kind === "investigation") return "research";
  if (e.kind === "document") return "read";
  if (e.kind === "notebook") return "read";
  if (e.kind === "parked_question") return "research";
  return undefined;
}

/** Parse a leading `state:<filter>` word ("state:blocked", "state:unseen").
 *  Returns null when the query does not lead with a state filter. */
export function leadingStateFilter(q: string): StateFilter | null {
  const m = q.trim().toLowerCase().match(/^state:([a-z]+)\b/);
  if (!m) return null;
  return isStateFilter(m[1]) ? m[1] : null;
}

/** Whether an entry matches a state filter. `unseen` matches unseen
 *  completions; the rest match the entry's research state. Entries without
 *  a state (routes, documents, …) match no state filter. */
export function entryMatchesStateFilter(
  e: FacetEntry,
  filter: StateFilter,
): boolean {
  if (filter === "unseen") return e.state === "done" && e.unseen === true;
  return e.state === filter;
}

/**
 * Rank entries against a query. SPR-04: when the query LEADS with a
 * workflow name ("research…"), that workflow's entries float to the top
 * (negative score). Text match still orders within. Non-workflow queries
 * behave exactly as before (no regression). herdr transfer P0-5: a leading
 * `state:<filter>` filters the candidate set first, then ranks the survivors.
 */
export function rankEntries<E extends FacetEntry & { id?: string }>(
  entries: E[],
  query: string,
): E[] {
  const q = query.trim().toLowerCase();
  if (!q) return entries;
  const stateFilter = leadingStateFilter(q);
  const candidates = stateFilter
    ? entries.filter((e) => entryMatchesStateFilter(e, stateFilter))
    : entries;
  // The `state:<word>` prefix is filter syntax, not search text — strip it
  // before text-matching so a state-filtered query still searches the rest.
  const matchQ = stateFilter ? q.replace(/^state:[a-z]+\s*/, "") : q;
  const wfLead = leadingWorkflow(matchQ);
  const scored = candidates
    .map((e) => {
      const hay = `${e.title} ${e.subtitle}`.toLowerCase();
      const facetBoost = wfLead && entryWorkflow(e) === wfLead ? -10_000 : 0;
      // State-only query: every candidate passes, ranked by original order.
      if (matchQ === "") {
        return { e, score: facetBoost };
      }
      if (hay.includes(matchQ)) {
        return { e, score: facetBoost + hay.indexOf(matchQ) };
      }
      const tokens = matchQ.split(/\s+/);
      const hits = tokens.filter((t) => hay.includes(t)).length;
      // A leading-workflow query matches that workflow's entries even
      // when the rest of the text doesn't.
      if (facetBoost && !hits) {
        return { e, score: facetBoost };
      }
      return hits ? { e, score: facetBoost + 1000 - hits * 10 } : null;
    })
    .filter((x): x is { e: E; score: number } => x !== null);
  scored.sort((a, b) => a.score - b.score);
  return scored.map((s) => s.e);
}

/** Re-export so callers can build workflow-jump actions consistently. */
export { WORKFLOW_ORDER };
