// ─────────────────────────────────────────────────────────────────────────
// resolve-quote.ts — the Canon Cat insight, made HONEST (SPR-07 M1 + M6).
//
// The talk's most personal demo: the reader speaks (or types) a short quote —
// "though only three years older" — and that 3–4 word run resolves to the exact
// position in the source. Inspired by Canon Cat, the talk observes that a
// sequence of three or four words uniquely identifies almost any point in a
// book. Antiek is the natural home because every chunk is addressable and
// carries provenance: a quote resolves to a substrate `chunk_id` + a
// chunk-relative `[start, end)` PASSAGE anchor (the frozen §6 `Anchor` passage
// variant — chunkId + offsets, never a pixel — PR-4).
//
// ── HONESTY (rigor #1) — the insight is PROBABILISTIC, not magic ───────────
//
// "3–4 words is unique" is USUALLY true, not ALWAYS. A short quote can match:
//   - ZERO passages (a typo, a paraphrase, content not in this synthesis),
//   - exactly ONE passage (the happy path → a single passage anchor),
//   - MANY passages (a common phrase: "as a result", "in this case").
// The resolver NEVER silently anchors to the first hit. It returns a tagged
// union the caller must branch on: `match` (1), `no-match` (0), `ambiguous`
// (N>1, every candidate carried so the surface can disambiguate). This is the
// mechanical 0/1/many gate the sprint names.
//
// ── §9.0 (M6) — the resolver NEVER returns withheld body text ──────────────
//
// A quote may resolve INTO a non-servable source. The §9.0 gate
// (`getChunk().servable === false` ⇒ the endpoint withholds `text`) is REUSED,
// never recomputed (PR-6). For a non-servable chunk the endpoint returns an
// EMPTY/withheld `text`, so a quote structurally CANNOT match its body here —
// but to be defensible we make it explicit: the resolver SKIPS the body search
// for a non-servable chunk and, when the caller anchors a note onto a source it
// already knows is non-servable (e.g. by chunk id), it returns a `withheld`
// outcome carrying ONLY the chunk id + bounded servability reason — never any
// body text. The note still anchors (to the bounded/withheld surface — M6); the
// resolver simply never surfaces a withheld body to do it.
//
// ── PR boundaries this module honors ──────────────────────────────────────
// PR-2 (no side store): reads the substrate via `ctx.substrate.getChunk`;
//   stores nothing; no browser-storage / KV / network-of-record.
// PR-4 (semantic anchor): every resolved location is a `passage` Anchor
//   (chunkId + chunk-relative offsets) or a `chunk` Anchor — never a pixel.
// PR-6 (substrate upstream): the §9.0 `servable` verdict is READ, never
//   recomputed; the chunk text is the substrate's, never fabricated.
// PR-8 (agent-authorable): imports ONLY `../../types` (the facet contract).
// ─────────────────────────────────────────────────────────────────────────

import type {
  Anchor,
  ChunkId,
  ReadingContext,
  SubstrateReadApi,
} from "../../types";

// ── The chunk view the resolver searches (the adaptation boundary) ─────────
//
// `getChunk` returns the shipped `ChunkResponse` shape verbatim (snake_case).
// The resolver only needs three of its fields. Declaring a NARROW alias keeps
// the resolution logic readable and pins exactly what §9.0 governs (`servable`
// + `servability` + `text`). The fields are read straight off `getChunk`'s
// return; the alias invents nothing.
interface ResolvableChunk {
  readonly chunk_id: string;
  /** The chunk body. For a NON-servable chunk the endpoint withholds this
   *  (empty / placeholder) — the resolver never treats a withheld body as
   *  searchable content (§9.0). */
  readonly text: string;
  /** §9.0 verdict, READ never recomputed (PR-6). False ⇒ body withheld. */
  readonly servable: boolean;
  /** Why a source is withheld ("restricted" | "taken_down"); null when
   *  servable. The bounded reason the withheld surface may show. */
  readonly servability: string | null;
}

// ── Normalisation — what "matching a quote" means ──────────────────────────
//
// Quote-matching is whitespace- and case-insensitive over a normalised view of
// the text, because a reader who SPEAKS or TYPES a quote will not reproduce the
// source's exact casing or interior whitespace. We normalise BOTH the quote and
// the chunk text the SAME way and search the normalised text, then map the
// normalised match offset back to the ORIGINAL chunk offsets (so the passage
// anchor's `[start, end)` index the real chunk text — PR-4). Punctuation is
// preserved (it disambiguates), only whitespace is collapsed + case folded.
//
// HONESTY: this is a literal-substring match over normalised text, NOT fuzzy /
// semantic search. A paraphrase will (correctly) NOT match — it returns
// `no-match`, which is the honest answer ("I don't see that exact run of words
// here"), not a wrong anchor. The false-MATCH risk is a SHORT, common quote
// matching MANY places; we surface that as `ambiguous`, never silently anchor.

/** Collapse runs of whitespace to a single space, trim, and case-fold. The
 *  returned string is what we search; we keep an index map back to the
 *  original so a match maps to real chunk offsets. */
function normalise(text: string): { normalised: string; toOriginal: number[] } {
  // `toOriginal[i]` = the index INTO the original `text` of the i-th char of
  // `normalised`. Built char-by-char so a collapsed whitespace run maps to the
  // first original whitespace char (a stable, defensible choice).
  const out: string[] = [];
  const toOriginal: number[] = [];
  let i = 0;
  let pendingSpace = false;
  // Skip leading whitespace.
  while (i < text.length && /\s/.test(text[i])) i++;
  for (; i < text.length; i++) {
    const ch = text[i];
    if (/\s/.test(ch)) {
      pendingSpace = true;
      continue;
    }
    if (pendingSpace && out.length > 0) {
      out.push(" ");
      // The collapsed space maps to THIS non-space char's position minus the
      // run; we record the current original index so a match landing on the
      // space still maps inside the original text.
      toOriginal.push(i);
      pendingSpace = false;
    }
    out.push(ch.toLowerCase());
    toOriginal.push(i);
  }
  return { normalised: out.join(""), toOriginal };
}

/** Find EVERY (non-overlapping) match of `needle` in `haystack`, returned as
 *  start indices into the NORMALISED haystack. Non-overlapping so two adjacent
 *  occurrences of a repeated quote count as two distinct candidates. */
function allMatchOffsets(haystack: string, needle: string): number[] {
  const offsets: number[] = [];
  if (needle.length === 0) return offsets;
  let from = 0;
  for (;;) {
    const at = haystack.indexOf(needle, from);
    if (at === -1) break;
    offsets.push(at);
    from = at + needle.length; // non-overlapping
  }
  return offsets;
}

// ── The resolution outcome (the 0/1/many tagged union) ─────────────────────

/** One resolved candidate passage: a chunk + the chunk-relative `[start, end)`
 *  (the frozen §6 `passage` Anchor offsets — PR-4). `anchor` is the ready-to-use
 *  semantic anchor the margin-note widget pins to. */
export interface QuoteCandidate {
  readonly chunkId: ChunkId;
  /** Char offset INTO the chunk's ORIGINAL text where the quote begins. */
  readonly start: number;
  /** Char offset INTO the chunk's ORIGINAL text just past the quote (half-open). */
  readonly end: number;
  /** The exact ORIGINAL substring matched (the block-quote text the note shows).
   *  Always servable content — a withheld body never reaches here (§9.0). */
  readonly excerpt: string;
  /** The ready passage anchor (PR-4). */
  readonly anchor: Anchor;
}

/**
 * The resolution result — the 0/1/many gate, made a TYPE the caller must branch
 * on (it cannot accidentally treat a `no-match` as a match). `withheld` is the
 * §9.0 outcome: the quote's target is a non-servable source, so the note anchors
 * to the bounded/withheld surface and NO body is returned.
 */
export type QuoteResolution =
  | { readonly kind: "match"; readonly candidate: QuoteCandidate }
  | { readonly kind: "no-match" }
  | { readonly kind: "ambiguous"; readonly candidates: readonly QuoteCandidate[] }
  | {
      readonly kind: "withheld";
      /** The non-servable chunk the quote's target lives in. The note anchors to
       *  this CHUNK (the bounded surface), never to a body offset. */
      readonly chunkId: ChunkId;
      /** The bounded reason ("restricted" | "taken_down" | null) — never any
       *  body text. */
      readonly servability: string | null;
      /** The chunk-level anchor the note pins to (the bounded surface — M6). */
      readonly anchor: Anchor;
    };

/** A chunk-level anchor (the bounded surface for a withheld source — M6). */
function chunkAnchor(chunkId: ChunkId): Anchor {
  return { kind: "chunk", chunkId };
}

/** A passage anchor (the resolved unique quote — PR-4). */
function passageAnchor(chunkId: ChunkId, start: number, end: number): Anchor {
  return { kind: "passage", chunkId, start, end };
}

/**
 * Resolve a quote within ONE chunk's text → the match offsets (original-text
 * relative). Returns an empty array for a withheld (non-servable) chunk — its
 * body is never searched (§9.0). Pure; no substrate read (the caller fetched
 * the chunk).
 */
function matchesInChunk(chunk: ResolvableChunk, quote: string): QuoteCandidate[] {
  // §9.0 (M6): a non-servable chunk's body is withheld — never search it, never
  // surface it. The caller handles the `withheld` outcome separately.
  if (!chunk.servable) return [];

  const q = normalise(quote);
  if (q.normalised.length === 0) return [];
  const h = normalise(chunk.text);

  const cid = chunk.chunk_id as ChunkId;
  const candidates: QuoteCandidate[] = [];
  for (const normStart of allMatchOffsets(h.normalised, q.normalised)) {
    const normEnd = normStart + q.normalised.length;
    // Map the normalised match back to ORIGINAL chunk offsets (PR-4: the
    // passage anchor indexes the real chunk text, not the normalised view).
    const origStart = h.toOriginal[normStart];
    // The original end is just past the last matched char; map the char BEFORE
    // normEnd and add 1 so `[start, end)` is half-open over the original text.
    const lastNormIdx = normEnd - 1;
    const origEnd = h.toOriginal[lastNormIdx] + 1;
    const excerpt = chunk.text.slice(origStart, origEnd);
    candidates.push({
      chunkId: cid,
      start: origStart,
      end: origEnd,
      excerpt,
      anchor: passageAnchor(cid, origStart, origEnd),
    });
  }
  return candidates;
}

/**
 * Resolve a short quote to a UNIQUE passage across the synthesis's chunks
 * (M1 + M6). The Canon Cat insight, made honest:
 *
 *   - reads each chunk the synthesis cites via `ctx.substrate.getChunk` (PR-2:
 *     the ONLY substrate access; no side store, no non-substrate origin);
 *   - searches the (servable) chunk bodies for the quote, normalised
 *     (whitespace-collapsed, case-folded);
 *   - exactly ONE match across all chunks → `match` (a `passage` anchor, PR-4);
 *   - zero matches → `no-match` (honest "I don't see that run of words");
 *   - more than one → `ambiguous` (every candidate carried; NEVER first-hit);
 *   - a quote whose only candidate source is NON-servable → never reaches the
 *     body search (§9.0); see `resolveQuoteOnChunk` for the explicit withheld
 *     path when the target chunk is known up front.
 *
 * The chunk set is the synthesis's cited chunks (dedup'd) — the doc model the
 * note resolves against. A quote spanning a chunk BOUNDARY (rigor #3) matches
 * NEITHER chunk's body (the run is split across two chunks), so it honestly
 * returns `no-match` rather than a partial wrong anchor — documented behaviour,
 * not a silent failure.
 */
export async function resolveQuote(
  quote: string,
  ctx: ReadingContext,
): Promise<QuoteResolution> {
  const chunkIds = synthesisChunkIds(ctx.synthesis);
  const candidates: QuoteCandidate[] = [];
  for (const id of chunkIds) {
    const chunk = await ctx.substrate.getChunk(id);
    candidates.push(...matchesInChunk(chunk, quote));
  }
  return classify(candidates);
}

/**
 * Resolve a quote against ONE known chunk (M1 + M6). Used when the reader is
 * already reading a specific source (the common case: anchor a note to the
 * passage I'm looking at). This is also the explicit §9.0 path: if the chunk is
 * non-servable, the resolver returns a `withheld` outcome — the note anchors to
 * the bounded CHUNK surface, and the body is never searched or returned (M6).
 */
export async function resolveQuoteOnChunk(
  quote: string,
  chunkId: ChunkId,
  substrate: SubstrateReadApi,
): Promise<QuoteResolution> {
  const chunk = await substrate.getChunk(chunkId);
  if (!chunk.servable) {
    // §9.0 (M6): anchor to the bounded surface; never search or return the body.
    const cid = chunk.chunk_id as ChunkId;
    return {
      kind: "withheld",
      chunkId: cid,
      servability: chunk.servability,
      anchor: chunkAnchor(cid),
    };
  }
  return classify(matchesInChunk(chunk, quote));
}

/** Turn a candidate list into the 0/1/many resolution (the gate). Shared by
 *  both entry points so the honesty rule lives in ONE place. */
function classify(candidates: QuoteCandidate[]): QuoteResolution {
  if (candidates.length === 0) return { kind: "no-match" };
  if (candidates.length === 1) return { kind: "match", candidate: candidates[0] };
  return { kind: "ambiguous", candidates };
}

/** The synthesis's cited chunk ids, de-duplicated, in stable claim order. The
 *  doc model the quote resolves against (PR-2: read from the parsed synthesis,
 *  the substrate-derived context). */
export function synthesisChunkIds(
  synthesis: ReadingContext["synthesis"],
): ChunkId[] {
  const seen = new Set<string>();
  const out: ChunkId[] = [];
  for (const claim of synthesis.claims) {
    for (const cid of claim.chunkIds) {
      if (seen.has(cid)) continue;
      seen.add(cid);
      out.push(cid);
    }
  }
  return out;
}
