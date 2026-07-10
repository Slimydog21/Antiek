/**
 * suiteProposalTasks — pure helpers for Antiek-bench suite proposal UI.
 *
 * Residual (hg): group proposed sub-benchmark item ids by task class so
 * Settings can show distill/synthesize/wrestle/book_qa breakdown without
 * auto-promoting anything.
 * Residual (qa / FUTURE-AGENT V3): primary by_source feed that drove the
 * weekly rewrite proposal delta (max count; ties → lexicographic source).
 */

/** Extract task_class token from shipped usage-derived item ids. */
export function taskClassFromProposedItemId(itemId: string): string | null {
  const id = (itemId || "").trim();
  if (!id) return null;
  // Convention from propose_suite_delta: usage-<task_class>-<hash>-<n>
  const m = id.match(/^usage-([a-z0-9_]+)-/i);
  if (m?.[1]) return m[1].toLowerCase();
  // Fallback: first path segment if dotted or slashy
  const head = id.split(/[./]/)[0];
  if (head && head !== id && /^[a-z0-9_]+$/i.test(head)) {
    return head.toLowerCase();
  }
  return null;
}

/** Count proposed item ids by inferred task class (unknown → "other"). */
export function groupProposedTasksByClass(
  itemIds: string[] | null | undefined,
): Record<string, number> {
  const out: Record<string, number> = {};
  for (const id of itemIds || []) {
    const tc = taskClassFromProposedItemId(id) || "other";
    out[tc] = (out[tc] || 0) + 1;
  }
  return out;
}

export type PrimaryFeedSource = {
  source: string;
  count: number;
};

/**
 * Residual (qa): which usage by_source most heavily fed the recursive suite
 * rewrite this week. Max count wins; ties break by source name (stable).
 * Never invents sources — empty map → null.
 */
export function primaryFeedSourceFromBySource(
  bySource: Record<string, number> | null | undefined,
): PrimaryFeedSource | null {
  if (!bySource || typeof bySource !== "object") return null;
  let best: PrimaryFeedSource | null = null;
  for (const [raw, n] of Object.entries(bySource)) {
    const source = String(raw || "").trim();
    if (!source) continue;
    const count = typeof n === "number" && Number.isFinite(n) ? n : 0;
    if (count <= 0) continue;
    if (
      !best ||
      count > best.count ||
      (count === best.count && source < best.source)
    ) {
      best = { source, count };
    }
  }
  return best;
}

/** Ranked feed sources (count desc, then name) for rewrite chrome. */
export function rankedFeedSourcesFromBySource(
  bySource: Record<string, number> | null | undefined,
): PrimaryFeedSource[] {
  if (!bySource || typeof bySource !== "object") return [];
  return Object.entries(bySource)
    .map(([raw, n]) => ({
      source: String(raw || "").trim(),
      count: typeof n === "number" && Number.isFinite(n) ? n : 0,
    }))
    .filter((x) => x.source && x.count > 0)
    .sort((a, b) => b.count - a.count || a.source.localeCompare(b.source));
}

/**
 * Residual (aoy): north-star product surfaces that should feed Antiek-bench
 * recursive weekly rewrite. Listing/coverage honesty only — never invents
 * events or auto-promotes suite items.
 * Residual (aqv): expand vision feed with multi-agent written analysis ·
 * spawn merge · marketplace host · research context pack · twin promote
 * (reading ≡ research ≡ writing flywheel for recursive rewrite).
 */
export const VISION_USAGE_FEED_SOURCES = [
  "twin_chase",
  "floating_deep_research",
  "midnight_oil",
  "midnight_oil_deposit",
  "collective_merge",
  "book_qa",
  // Residual (aqv): multi-agent written analysis from collective deep research.
  "collective_written_analysis",
  // Residual (aqv): single-spawn merge path (highlight float → merge unit).
  "spawn_merge",
  // Residual (aqv): HTML-first marketplace host into account.
  "marketplace_host",
  // Residual (aqv): wrestle substrate pack from ResearchContext.
  "research_context_pack",
  // Residual (aqv): recursive twin promote → context depth-graph.
  "twin_promote_context",
  // Residual (ari): knowledge-dense arxiv/substack hydrate path (offline-honest).
  "publication_hydrate",
  // Residual (asj): knowledge-dense attach path (asb readiness · never auto-hydrate).
  "publication_attach",
  // Residual (asj): free HTML host-into-account (arw free-host CTA path).
  "marketplace_free_host",
  // Residual (asj): operator decision-tree model install (asd · never auto-route).
  "decision_tree_install",
  // Residual (ast): highlight → float|full DR launch path (asq pure helper).
  "highlight_dr_launch",
  // Residual (atd): long-horizon progress complete (asx/asz multi-stage open → host).
  "research_progress_complete",
  // Residual (atd): session→prompt flywheel complete (atb host honesty path).
  "session_flywheel_complete",
  // Residual (atd): recursive note-taker multi-asset twin merge (atc host path).
  "twin_cross_asset_merge",
  // Residual (atx): intelligent context search open path (atv) → recursive rewrite.
  "context_search",
  // Residual (atx): citation-trust evidence pack open path (atu) → recursive rewrite.
  "evidence_pack",
] as const;

export type VisionUsageFeedSource = (typeof VISION_USAGE_FEED_SOURCES)[number];

export type VisionFeedCoverage = {
  covered: VisionUsageFeedSource[];
  uncovered: VisionUsageFeedSource[];
  covered_count: number;
  uncovered_count: number;
  total: number;
  coverage_ratio: number;
  /** Event totals for covered vision sources only. */
  covered_event_count: number;
};

/**
 * Residual (aoy): which vision product surfaces appear in this week's
 * by_source map (positive counts only). Empty/unknown map → all uncovered.
 */
/**
 * Residual (apa): which vision usage surfaces most inform a given Antiek-bench
 * task_class (decision-tree best-for-task honesty · never auto-route).
 */
export function benchTaskClassToVisionFeeds(
  taskClass: string | null | undefined,
): VisionUsageFeedSource[] {
  const t = String(taskClass || "")
    .trim()
    .toLowerCase();
  if (t === "wrestle") {
    // Residual (aqv/ari/asj/atd/atx): long-horizon + intelligent search + evidence pack train wrestle.
    return [
      "twin_chase",
      "midnight_oil",
      "collective_merge",
      "research_context_pack",
      "twin_promote_context",
      "publication_hydrate",
      "publication_attach",
      "decision_tree_install",
      "research_progress_complete",
      "session_flywheel_complete",
      "twin_cross_asset_merge",
      "context_search",
      "evidence_pack",
    ];
  }
  if (t === "synthesize") {
    // Residual (aqv/ast/atd/atx): multi-agent analysis + evidence pack train synthesize.
    return [
      "floating_deep_research",
      "twin_chase",
      "midnight_oil_deposit",
      "collective_written_analysis",
      "spawn_merge",
      "highlight_dr_launch",
      "research_progress_complete",
      "twin_cross_asset_merge",
      "evidence_pack",
    ];
  }
  if (t === "distill") {
    // Residual (ari/asj/atx): knowledge-dense hydrate + attach + intelligent search train distill.
    return [
      "floating_deep_research",
      "book_qa",
      "spawn_merge",
      "publication_hydrate",
      "publication_attach",
      "context_search",
    ];
  }
  if (t === "book_qa") {
    // Residual (aqv/asj): marketplace HTML host + free-host train book_qa.
    return [
      "book_qa",
      "midnight_oil_deposit",
      "marketplace_host",
      "marketplace_free_host",
    ];
  }
  return [];
}

export type TaskTrainingFeedCoverage = {
  task_class: string;
  feeds: VisionUsageFeedSource[];
  covered: VisionUsageFeedSource[];
  uncovered: VisionUsageFeedSource[];
  covered_count: number;
  total: number;
  coverage_ratio: number;
};

/**
 * Residual (apc): for a bench task_class, which of its training vision feeds
 * have positive usage events this week (recursive rewrite honesty).
 * Never invents events · empty task → empty feeds.
 */
export function taskTrainingFeedCoverage(
  taskClass: string | null | undefined,
  bySource: Record<string, number> | null | undefined,
): TaskTrainingFeedCoverage {
  const task_class = String(taskClass || "")
    .trim()
    .toLowerCase();
  const feeds = benchTaskClassToVisionFeeds(task_class);
  const covered: VisionUsageFeedSource[] = [];
  const uncovered: VisionUsageFeedSource[] = [];
  for (const src of feeds) {
    const n = bySource?.[src];
    const count = typeof n === "number" && Number.isFinite(n) ? n : 0;
    if (count > 0) covered.push(src);
    else uncovered.push(src);
  }
  const total = feeds.length;
  const covered_count = covered.length;
  return {
    task_class,
    feeds,
    covered,
    uncovered,
    covered_count,
    total,
    coverage_ratio: total > 0 ? covered_count / total : 0,
  };
}

export function visionFeedCoverageFromBySource(
  bySource: Record<string, number> | null | undefined,
): VisionFeedCoverage {
  const total = VISION_USAGE_FEED_SOURCES.length;
  const covered: VisionUsageFeedSource[] = [];
  const uncovered: VisionUsageFeedSource[] = [];
  let covered_event_count = 0;
  for (const src of VISION_USAGE_FEED_SOURCES) {
    const n = bySource?.[src];
    const count = typeof n === "number" && Number.isFinite(n) ? n : 0;
    if (count > 0) {
      covered.push(src);
      covered_event_count += count;
    } else {
      uncovered.push(src);
    }
  }
  const covered_count = covered.length;
  const uncovered_count = uncovered.length;
  return {
    covered,
    uncovered,
    covered_count,
    uncovered_count,
    total,
    coverage_ratio: total > 0 ? covered_count / total : 0,
    covered_event_count,
  };
}
