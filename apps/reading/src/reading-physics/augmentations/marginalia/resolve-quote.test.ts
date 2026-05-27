/**
 * resolve-quote.test.ts — SPR-07 M1 + M6: the Canon Cat insight, made HONEST.
 *
 * THE MECHANICAL GATE: a short quote resolves to 0 / exactly 1 / many passages,
 * and the resolver NEVER silently anchors to the first hit. This file proves:
 *   - M1 0/1/many — zero matches → `no-match`; exactly one → `match` (a passage
 *     anchor with chunk-relative offsets that index the REAL chunk text, PR-4);
 *     many → `ambiguous` carrying EVERY candidate (never first-hit);
 *   - rigor #3 edge cases — a quote spanning a chunk BOUNDARY → `no-match`
 *     (honest, not a partial wrong anchor); normalisation (whitespace/case) so a
 *     spoken/typed quote that differs only in casing/spacing still resolves;
 *   - M6 §9.0 — a quote whose target is a NON-servable source: the resolver
 *     never searches or returns the withheld body; the per-chunk path returns a
 *     `withheld` outcome anchoring to the bounded chunk surface, body-free.
 *
 * The "false-match" behaviour is REPORTED, not hidden: a measured false-match
 * (a 3-4 word quote matching >1 place) on the fixtures is asserted to surface as
 * `ambiguous`. Quote-anchoring is presented as PROBABILISTIC, not deterministic.
 */
import { describe, expect, it } from "vitest";

import {
  resolveQuote,
  resolveQuoteOnChunk,
  synthesisChunkIds,
} from "./resolve-quote";
import type { ChunkId, ReadingContext, SubstrateReadApi } from "../../types";

// ── a substrate read API backed by an in-memory chunk fixture ───────────────
//
// Mirrors the shipped `ChunkResponse` shape verbatim (snake_case). A NON-servable
// chunk withholds its body exactly as the endpoint does: `servable: false` +
// `text: ""` (the body is never delivered) — so the resolver structurally cannot
// match against it even if it tried (it doesn't — it skips the search).

interface FixtureChunk {
  chunk_id: string;
  text: string;
  servable: boolean;
  servability: string | null;
}

function fakeSubstrate(chunks: FixtureChunk[]): SubstrateReadApi {
  const byId = new Map(chunks.map((c) => [c.chunk_id, c]));
  return {
    getChunk: (id: ChunkId) => {
      const c = byId.get(id);
      if (!c) return Promise.reject(new Error(`no chunk ${id}`));
      return Promise.resolve({
        chunk_id: c.chunk_id,
        text: c.servable ? c.text : "", // §9.0: withheld body is NOT delivered
        section_path: null,
        token_count: 0,
        document_id: "doc1",
        document_title: "Doc",
        source_tier: 1,
        servable: c.servable,
        ip_holder_name: null,
        ip_holder_status: null,
        servability: c.servability,
      });
    },
  };
}

function ctxFor(
  chunks: FixtureChunk[],
  claims: { claimId: string; chunkIds: string[] }[],
): ReadingContext {
  return {
    synthesis: {
      question: null,
      claims: claims.map((c) => ({
        claimId: c.claimId as never,
        chunkIds: c.chunkIds as never,
      })),
    },
    layout: { resolve: () => null },
    substrate: fakeSubstrate(chunks),
  };
}

// A fixture synthesis: two cited chunks of one document.
const CHUNKS: FixtureChunk[] = [
  {
    chunk_id: "c1",
    // The talk's own example phrase, embedded once.
    text: "The narrator notes that the rival, though only three years older, had already left.",
    servable: true,
    servability: null,
  },
  {
    chunk_id: "c2",
    // A common phrase appearing TWICE (the ambiguity case) + a unique phrase.
    text: "As a result, the plan changed. As a result, nobody objected to the revision.",
    servable: true,
    servability: null,
  },
];
const CLAIMS = [
  { claimId: "1", chunkIds: ["c1"] },
  { claimId: "2", chunkIds: ["c2"] },
];

// ── M1 — the 0/1/many gate ──────────────────────────────────────────────────

describe("resolveQuote — the 0/1/many gate (M1, the mechanical gate)", () => {
  it("exactly ONE match → `match` with a passage anchor indexing the real text (PR-4)", async () => {
    const ctx = ctxFor(CHUNKS, CLAIMS);
    const res = await resolveQuote("though only three years older", ctx);
    expect(res.kind).toBe("match");
    if (res.kind !== "match") return;
    const cand = res.candidate;
    expect(cand.chunkId).toBe("c1");
    expect(cand.anchor).toEqual({
      kind: "passage",
      chunkId: "c1",
      start: cand.start,
      end: cand.end,
    });
    // The offsets index the REAL chunk text (not the normalised view).
    expect(CHUNKS[0].text.slice(cand.start, cand.end)).toBe(
      "though only three years older",
    );
    expect(cand.excerpt).toBe("though only three years older");
  });

  it("ZERO matches → `no-match` (honest 'I don't see that run of words')", async () => {
    const ctx = ctxFor(CHUNKS, CLAIMS);
    const res = await resolveQuote("a phrase that is simply not present", ctx);
    expect(res.kind).toBe("no-match");
  });

  it("MANY matches → `ambiguous` carrying EVERY candidate, NEVER first-hit", async () => {
    const ctx = ctxFor(CHUNKS, CLAIMS);
    // "as a result" appears twice in c2 — the measured false-match case.
    const res = await resolveQuote("as a result", ctx);
    expect(res.kind).toBe("ambiguous");
    if (res.kind !== "ambiguous") return;
    // BOTH occurrences are candidates — the resolver did not pick the first.
    expect(res.candidates).toHaveLength(2);
    // Distinct offsets (two real positions in the chunk text).
    const starts = res.candidates.map((c) => c.start).sort((a, b) => a - b);
    expect(starts[0]).not.toBe(starts[1]);
    // Each candidate's offsets index the real text.
    for (const c of res.candidates) {
      expect(CHUNKS[1].text.slice(c.start, c.end).toLowerCase()).toBe("as a result");
    }
  });
});

// ── rigor #3 — normalisation + the chunk-boundary edge case ────────────────

describe("resolveQuote — normalisation + boundary edge cases (rigor #3)", () => {
  it("a quote differing only in CASE / WHITESPACE still resolves (spoken/typed)", async () => {
    const ctx = ctxFor(CHUNKS, CLAIMS);
    // Upper-cased + extra spaces — a reader's spoken/typed quote rarely matches
    // the source's exact casing/spacing.
    const res = await resolveQuote("  THOUGH   only Three years OLDER ", ctx);
    expect(res.kind).toBe("match");
    if (res.kind !== "match") return;
    // The anchor still indexes the ORIGINAL text exactly.
    expect(CHUNKS[0].text.slice(res.candidate.start, res.candidate.end)).toBe(
      "though only three years older",
    );
  });

  it("a quote SPANNING a chunk boundary → `no-match` (honest, not a partial anchor)", async () => {
    // The phrase "left. As a result" straddles c1's end + c2's start — it exists
    // in NEITHER single chunk's body, so it honestly does not resolve (rigor #3:
    // documented behaviour, never a partial wrong anchor).
    const ctx = ctxFor(CHUNKS, CLAIMS);
    const res = await resolveQuote("had already left. As a result the plan", ctx);
    expect(res.kind).toBe("no-match");
  });

  it("an empty quote → `no-match` (never anchors on nothing)", async () => {
    const ctx = ctxFor(CHUNKS, CLAIMS);
    expect((await resolveQuote("", ctx)).kind).toBe("no-match");
    expect((await resolveQuote("   ", ctx)).kind).toBe("no-match");
  });

  it("synthesisChunkIds de-duplicates a chunk cited by multiple claims", () => {
    const ids = synthesisChunkIds({
      question: null,
      claims: [
        { claimId: "1" as never, chunkIds: ["c1", "c2"] as never },
        { claimId: "2" as never, chunkIds: ["c2", "c3"] as never }, // c2 repeats
      ],
    });
    expect(ids).toEqual(["c1", "c2", "c3"]);
  });
});

// ── M6 — §9.0: a non-servable target, body never returned ──────────────────

describe("resolveQuote — §9.0 non-servable target (M6)", () => {
  const NON_SERVABLE: FixtureChunk[] = [
    {
      chunk_id: "c9",
      // This body would match the quote — BUT the source is non-servable, so the
      // endpoint withholds it and the resolver must never search or return it.
      text: "the secret restricted passage the reader quoted",
      servable: false,
      servability: "restricted",
    },
  ];

  it("the per-chunk path returns `withheld` anchored to the bounded chunk surface — no body", async () => {
    const substrate = fakeSubstrate(NON_SERVABLE);
    const res = await resolveQuoteOnChunk(
      "the secret restricted passage",
      "c9" as ChunkId,
      substrate,
    );
    expect(res.kind).toBe("withheld");
    if (res.kind !== "withheld") return;
    // Anchors to the bounded CHUNK surface (M6), never a passage offset.
    expect(res.anchor).toEqual({ kind: "chunk", chunkId: "c9" });
    expect(res.servability).toBe("restricted");
    // The outcome carries NO body field at all — structurally cannot leak it.
    expect(JSON.stringify(res)).not.toContain("secret restricted passage");
  });

  it("the synthesis-wide path never matches a non-servable chunk's withheld body", async () => {
    // c9 is the only chunk + it is non-servable: the endpoint delivers an empty
    // body, so the quote cannot match. The resolver returns `no-match`, never the
    // body. (The per-chunk path above is the one that surfaces the bounded
    // `withheld` anchor; the synthesis-wide path simply never sees the body.)
    const ctx: ReadingContext = {
      synthesis: { question: null, claims: [{ claimId: "1" as never, chunkIds: ["c9"] as never }] },
      layout: { resolve: () => null },
      substrate: fakeSubstrate(NON_SERVABLE),
    };
    const res = await resolveQuote("the secret restricted passage", ctx);
    expect(res.kind).toBe("no-match");
    expect(JSON.stringify(res)).not.toContain("secret restricted passage");
  });
});
