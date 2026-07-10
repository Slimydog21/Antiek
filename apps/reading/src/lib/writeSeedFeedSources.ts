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
  "spawn_merge",
  "collective_doc_merge",
  "hosted_html_document",
  "evidence_pack",
  "publication_hydrate",
  "session_flywheel_complete",
  "context_search",
  "research_context_pack",
  "twin_promote_context",
] as const;

export function isWriteSeedFeedSource(source: string | null | undefined): boolean {
  const s = String(source || "").trim();
  if (!s) return false;
  return (WRITE_SEED_FEED_SOURCES as readonly string[]).includes(s);
}
