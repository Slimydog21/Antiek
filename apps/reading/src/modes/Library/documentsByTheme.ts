import type { BookSummary } from "../../api/books";
import type { InvestigationSummary } from "../../lib/api";

/**
 * documentsByTheme — order the servable shelf by relevance to the user's
 * ACTIVE RESEARCH THEMES (Living Roadmap SPR-07 M1). "Fill up this library":
 * the shelf the reader sees first is what's relevant to what they're actually
 * researching, not an undifferentiated chronological pile.
 *
 * ════════════════════════════════════════════════════════════════════════
 * THE SIGNAL — what "theme" means here, and why it's HONEST (rigor #1)
 * ════════════════════════════════════════════════════════════════════════
 * The graph exposes the user's active research as INVESTIGATIONS, each with a
 * `question` (the Research surface's `listInvestigations`). The themes are the
 * salient terms across those questions — what the user is currently digging
 * into. A book is ranked by how many distinct theme terms appear in its
 * title/author (the bounded metadata the shelf already carries). This is a
 * REAL graph-derived signal (documents ↔ the active-research themes), kept
 * deliberately simple: it ranks on substrate-present fields, invents no
 * embedding score, and never claims more confidence than term-overlap warrants.
 *
 * WHY NOT EMBEDDINGS: the embedding-ranked path already exists as the
 * prompt-to-curate seam (`curateBooks`, server-side). That is an explicit,
 * user-typed query. This is the AMBIENT default ordering — the shelf before the
 * user types anything — so it must work from signal already on the client (the
 * active investigations) without a per-load model call. The two are
 * complementary: curate answers "find me books about X"; documentsByTheme
 * answers "what should the shelf show me given what I'm researching".
 *
 * ════════════════════════════════════════════════════════════════════════
 * THIN SIGNAL → RECENCY FALLBACK, SAID OUT LOUD (the spec's acceptance)
 * ════════════════════════════════════════════════════════════════════════
 * When the theme signal is thin or absent — no active investigations, or no
 * book matches any theme term — we do NOT fabricate a relevance order. We fall
 * back to a stated default (recency: most-recently-ingested first, approximated
 * by the shelf's existing order which the corpus API returns newest-leaning)
 * and the RESULT carries `ordering: "recency"` so the SURFACE can SAY which
 * ordering is active. A theme-ranked result carries `ordering: "theme"`. The
 * surface renders the label; the honesty is structural, not a comment.
 *
 * This inherits the FLAT LIBRARY's honesty for the fallback (rigor #2): when we
 * have no opinion we surface everything in a stated order and admit we have no
 * opinion, rather than dressing recency up as relevance.
 */

/** Which ordering the feed actually used — the surface renders this so the
 * user knows whether the shelf is theme-ranked or fell back to recency. */
export type FeedOrdering = "theme" | "recency";

export interface RankedFeed {
  books: BookSummary[];
  ordering: FeedOrdering;
  /** The theme terms that drove a `theme` ordering (for the honest label —
   * "ranked to your research on X, Y"). Empty for a recency fallback. */
  themeTerms: string[];
}

// Common words that are never a "theme" — stripped so ranking keys off the
// content words of a research question, not its scaffolding.
const STOPWORDS = new Set([
  "the", "a", "an", "and", "or", "but", "of", "to", "in", "on", "for", "with",
  "is", "are", "was", "were", "be", "been", "being", "do", "does", "did",
  "how", "what", "why", "when", "where", "who", "which", "whom", "whose",
  "this", "that", "these", "those", "it", "its", "as", "at", "by", "from",
  "into", "about", "over", "under", "between", "vs", "versus", "can", "could",
  "should", "would", "will", "may", "might", "than", "then", "so", "if",
]);

/** Extract content-word theme terms from a set of investigation questions. */
export function themeTermsFromInvestigations(
  investigations: readonly InvestigationSummary[],
): string[] {
  const counts = new Map<string, number>();
  for (const inv of investigations) {
    const q = inv.question;
    if (!q) continue;
    for (const raw of q.toLowerCase().split(/[^a-z0-9]+/)) {
      const w = raw.trim();
      if (w.length < 3 || STOPWORDS.has(w)) continue;
      counts.set(w, (counts.get(w) ?? 0) + 1);
    }
  }
  // Most-frequent first — the dominant themes lead the label.
  return [...counts.entries()].sort((a, b) => b[1] - a[1]).map(([w]) => w);
}

/** A book's relevance score against the theme terms: distinct terms that
 * appear in its title or author. Title/author are the only body-free fields
 * the shelf carries (§9.0: a gated book exposes no body here either). */
function scoreBook(book: BookSummary, terms: ReadonlySet<string>): number {
  const hay = `${book.title ?? ""} ${book.author ?? ""}`.toLowerCase();
  let score = 0;
  for (const term of terms) {
    if (hay.includes(term)) score += 1;
  }
  return score;
}

/**
 * Order the servable shelf by relevance to active research themes, falling
 * back to recency (the shelf's given order) with a STATED label when the theme
 * signal is thin. `books` is taken in its server order (newest-leaning), so the
 * recency fallback is a stable no-op re-statement of that order.
 */
export function documentsByTheme(
  books: readonly BookSummary[],
  investigations: readonly InvestigationSummary[],
): RankedFeed {
  const terms = themeTermsFromInvestigations(investigations);
  const termSet = new Set(terms);

  // Thin signal (a): no active themes at all → recency, said out loud.
  if (termSet.size === 0) {
    return { books: [...books], ordering: "recency", themeTerms: [] };
  }

  const scored = books.map((book, idx) => ({
    book,
    score: scoreBook(book, termSet),
    idx, // preserve the original (recency) order as the tiebreak
  }));

  const anyMatch = scored.some((s) => s.score > 0);
  // Thin signal (b): themes exist but NOTHING on the shelf matches them →
  // fabricating a 0-vs-0 "relevance" order would be dishonest. Fall back to
  // recency and say so.
  if (!anyMatch) {
    return { books: [...books], ordering: "recency", themeTerms: [] };
  }

  // Real theme signal: most-relevant first, recency as the tiebreak among
  // equally-relevant (incl. equally-zero) books — a matched theme rises, the
  // rest keep their recency order.
  scored.sort((a, b) => (b.score - a.score) || (a.idx - b.idx));
  // The label names only the terms that actually matched something on the
  // shelf — never a theme with no book behind it (honest label).
  const matchedTerms = terms.filter((t) =>
    books.some((book) =>
      `${book.title ?? ""} ${book.author ?? ""}`.toLowerCase().includes(t),
    ),
  );
  return {
    books: scored.map((s) => s.book),
    ordering: "theme",
    themeTerms: matchedTerms,
  };
}
