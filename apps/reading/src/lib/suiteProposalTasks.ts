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
 */
export const VISION_USAGE_FEED_SOURCES = [
  "twin_chase",
  "floating_deep_research",
  "midnight_oil",
  "midnight_oil_deposit",
  "collective_merge",
  "book_qa",
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
    return ["twin_chase", "midnight_oil", "collective_merge"];
  }
  if (t === "synthesize") {
    return ["floating_deep_research", "twin_chase", "midnight_oil_deposit"];
  }
  if (t === "distill") {
    return ["floating_deep_research", "book_qa"];
  }
  if (t === "book_qa") {
    return ["book_qa", "midnight_oil_deposit"];
  }
  return [];
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
