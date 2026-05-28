import { describe, expect, it } from "vitest";

import type { BookSummary } from "../../api/books";
import type { InvestigationSummary } from "../../lib/api";
import { documentsByTheme, themeTermsFromInvestigations } from "./documentsByTheme";

function book(over: Partial<BookSummary> & { document_id: string }): BookSummary {
  return {
    title: null,
    author: null,
    servability: "public_domain",
    servable_full_text: true,
    page_count: 1,
    cover_uri: null,
    ip_holder_id: null,
    taken_down: false,
    ...over,
  };
}

function inv(question: string | null, id = `inv-${Math.random()}`): InvestigationSummary {
  return {
    investigation_id: id,
    question,
    status: "in_progress",
    started_at: null,
    completed_at: null,
    cost_usd_total: 0,
    parent_investigation_id: null,
  };
}

describe("themeTermsFromInvestigations", () => {
  it("extracts content-word themes, dropping stopwords + short words", () => {
    const terms = themeTermsFromInvestigations([
      inv("How does Stoicism shape modern resilience?"),
    ]);
    expect(terms).toContain("stoicism");
    expect(terms).toContain("resilience");
    expect(terms).toContain("modern");
    // stopwords / sub-3-char words dropped
    expect(terms).not.toContain("how");
    expect(terms).not.toContain("the");
  });

  it("ranks more-frequent terms first across questions", () => {
    const terms = themeTermsFromInvestigations([
      inv("Stoicism and ethics"),
      inv("Stoicism in practice"),
      inv("Ethics of war"),
    ]);
    // "stoicism" (x2) leads "ethics" (x2 too) — both before singletons; the
    // dominant themes are at the front.
    expect(terms.slice(0, 2).sort()).toEqual(["ethics", "stoicism"]);
  });
});

describe("documentsByTheme", () => {
  const meditations = book({ document_id: "d1", title: "Meditations", author: "Marcus Aurelius" });
  const warAndPeace = book({ document_id: "d2", title: "War and Peace", author: "Tolstoy" });
  const stoicGuide = book({ document_id: "d3", title: "A Guide to Stoicism", author: "Anon" });

  it("ranks the shelf by active research themes, most-relevant first (theme ordering)", () => {
    const feed = documentsByTheme(
      [warAndPeace, meditations, stoicGuide],
      [inv("How does Stoicism shape resilience?")],
    );
    expect(feed.ordering).toBe("theme");
    // "A Guide to Stoicism" matches the theme term "stoicism"; it rises to top.
    expect(feed.books[0].document_id).toBe("d3");
    expect(feed.themeTerms).toContain("stoicism");
  });

  it("falls back to recency with a STATED label when there are no active themes (thin signal a)", () => {
    const shelf = [warAndPeace, meditations];
    const feed = documentsByTheme(shelf, []); // no investigations
    expect(feed.ordering).toBe("recency");
    expect(feed.themeTerms).toEqual([]);
    // Order is preserved (the shelf's recency order), not reshuffled.
    expect(feed.books.map((b) => b.document_id)).toEqual(["d2", "d1"]);
  });

  it("falls back to recency when themes exist but nothing on the shelf matches them (thin signal b — never fabricate relevance)", () => {
    const feed = documentsByTheme(
      [warAndPeace, meditations],
      [inv("Quantum chromodynamics lattice gauge theory")],
    );
    // Themes are present, but no book title/author matches → a 0-vs-0
    // "relevance" order would be dishonest. Recency, said out loud.
    expect(feed.ordering).toBe("recency");
    expect(feed.themeTerms).toEqual([]);
    expect(feed.books.map((b) => b.document_id)).toEqual(["d2", "d1"]);
  });

  it("preserves recency as the tiebreak among equally-relevant books", () => {
    // Both match "stoicism"; the more-recent (earlier in shelf order) stays
    // first among the equally-scored matches.
    const a = book({ document_id: "a", title: "Stoicism Today" });
    const b = book({ document_id: "b", title: "Stoicism Yesterday" });
    const feed = documentsByTheme([a, b], [inv("stoicism")]);
    expect(feed.ordering).toBe("theme");
    expect(feed.books.map((x) => x.document_id)).toEqual(["a", "b"]);
  });

  it("handles an empty shelf (zero documents) without inventing an order", () => {
    const feed = documentsByTheme([], [inv("stoicism")]);
    expect(feed.books).toEqual([]);
    // No book matched (none exist) → honest recency.
    expect(feed.ordering).toBe("recency");
  });
});
