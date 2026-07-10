/**
 * Residual (rt): Write twin_seed sources that feed Antiek-bench weekly rewrite.
 * Mirrors substrate TWIN_WRITE_SEED_USAGE_SOURCES for Settings honesty chrome.
 * twin_draft_selected is excluded (covered by twin_chase).
 */

export const WRITE_SEED_FEED_SOURCES: readonly string[] = [
  "deep_research_session",
  "research_progress_complete",
  "research_progress_draft",
  "midnight_oil_deposit",
  "marketplace_host",
  // Residual (aaj): catalog HTML projection → Write seed feed.
  "marketplace_catalog",
  "spawn_merge",
  "collective_doc_merge",
  "hosted_html_document",
  "evidence_pack",
  "publication_hydrate",
  "session_flywheel_complete",
  "context_search",
  "research_context_pack",
  "twin_promote_context",
  // Residual (tt): multi-spawn cohesive unit prompt float → Write seed feed.
  "collective_unit_prompt",
  // Residual (vd): recursive note-taker cross-asset merge → Write seed feed.
  "twin_cross_asset_merge",
  // Residual (vk): collective written analysis float → Write seed feed.
  "collective_written_analysis",
] as const;

export function isWriteSeedFeedSource(source: string | null | undefined): boolean {
  const s = String(source || "").trim();
  if (!s) return false;
  return (WRITE_SEED_FEED_SOURCES as readonly string[]).includes(s);
}

/**
 * Residual (ru): how many known weekly feed sources are Write twin_seed paths.
 * Used by Settings known-sources legend honesty chrome.
 */
export function countWriteSeedKnownSources(
  knownSources: readonly string[] | null | undefined,
): number {
  if (!knownSources || knownSources.length === 0) return 0;
  let n = 0;
  for (const s of knownSources) {
    if (isWriteSeedFeedSource(s)) n += 1;
  }
  return n;
}
