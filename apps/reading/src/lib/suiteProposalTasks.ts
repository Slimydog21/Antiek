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
