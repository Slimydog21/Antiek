/**
 * language.ts — the no-jargon rule, as data.
 *
 * The product runs on a substrate whose nouns are engineering nouns
 * (investigation, deliverable, chunk, block, the `inv-…` id, the
 * `subject_status` enum). Those are correct in code and in the event log;
 * they are wrong in front of a user. "Don't show jargon" rots as a
 * guideline — the leaks the four product specs flagged are the proof — so
 * U-04 makes it mechanical: a glossary of the chosen user-facing wording,
 * plus a list of banned raw patterns the copy-lint (copyLint.test.ts) refuses
 * to let into a user-facing component.
 *
 * Scope discipline (spec, out-of-scope): this translates at the UI edge. It
 * does NOT rename the substrate — `investigation_id` stays `investigation_id`
 * in the API and the event log. The glossary is what the surface says; the
 * field name is what the code passes.
 */

/** A substrate term and what the surface should say instead. */
export interface GlossaryEntry {
  /** The substrate / engineering term. */
  term: string;
  /** What the user-facing surface should say. */
  userFacing: string;
  /** When the right move is to show nothing (raw ids, internal handles). */
  neverShown?: boolean;
  /** One line on where this leaks / why the chosen wording. */
  note?: string;
}

/**
 * The glossary — seeded from the leaks the product specs flagged (cited in
 * the copy-lint baseline and the U-04 handoff). Each substrate term maps to
 * the wording the surface should use, or is marked `neverShown` when the
 * honest move is to hide it entirely.
 */
export const GLOSSARY: readonly GlossaryEntry[] = [
  {
    term: "investigation",
    userFacing: "research",
    note: "The Research workflow's unit of work; the noun the user reads.",
  },
  {
    term: "inv-… id",
    userFacing: "",
    neverShown: true,
    note: "The investigation's raw id (`inv-` + hex). Never a user-facing label.",
  },
  {
    term: "[N chunks]",
    userFacing: "N sources",
    note: "Retrieval chunks are an engine detail; the user thinks in sources.",
  },
  {
    term: "[N claims]",
    userFacing: "N points",
    note: "Extracted claim spans; say what they are to a reader, not the schema noun.",
  },
  {
    term: "chunk UUID",
    userFacing: "the source's title",
    neverShown: true,
    note: "A raw 32/40-hex id is never a label — show the source it belongs to.",
  },
  {
    term: "block_id",
    userFacing: "",
    neverShown: true,
    note: "Write's repository block handle; an internal id, never shown.",
  },
  {
    term: "deliverable",
    userFacing: "draft / piece",
    note: "Write's unit of work; the user is writing a piece, not a deliverable.",
  },
  {
    term: "subject_status",
    userFacing: "plain words (e.g. living / deceased)",
    note: "Speak's subject-status enum; show the plain word, not the token.",
  },
  {
    term: "publish_intent",
    userFacing: "plain words (e.g. keep private / will be public)",
    note: "Speak's publish-intent enum; the user reads intent, not the enum value.",
  },
];

/** A banned raw pattern + the glossary wording to use instead. */
export interface BannedPattern {
  /** Stable id for the rule (used in the lint message). */
  id: string;
  /** The matcher. Global flag so a count is available. */
  pattern: RegExp;
  /** One-line human description of what's banned. */
  description: string;
  /** What to show instead (points at the glossary). */
  replacement: string;
}

/**
 * The banned user-facing patterns the copy-lint enforces. These are the
 * substrate strings that must not appear as rendered copy. The lint scans
 * user-facing components, records the current leaks as a grandfathered
 * baseline, and fails only on NEW occurrences — exactly mirroring the
 * token-lint (scripts/lint_tokens.ts). The `replacement` is named in the
 * failure message so the fix is obvious.
 *
 * NOTE: these match raw substrings the way token-lint matches raw hex — they
 * will also match legitimate code identifiers (a `subject_status` field in an
 * API type, the `inv-` id generator). That is intentional: those legitimate
 * uses are absorbed by the grandfathered baseline, and the lint's job is to
 * stop NEW user-facing leaks, not to relitigate the substrate's own naming.
 */
export const BANNED_PATTERNS: readonly BannedPattern[] = [
  {
    // Matches the enumerated long-id form (`inv-` + ≥6 hex). Un-bracketed bare
    // counts and short ids are a documented follow-up, not caught here yet —
    // no rule change needed now.
    id: "inv-id",
    pattern: /\binv-[0-9a-f]{6,}/gi,
    description: "a raw investigation id (`inv-…`)",
    replacement: "hide the id; say \"research\" (see GLOSSARY: investigation)",
  },
  {
    // Matches the enumerated bracketed form (`[…chunk…]`). An un-bracketed
    // count (e.g. "5 chunks" in prose) is a documented follow-up, not caught
    // here yet — no rule change needed now.
    id: "n-chunks",
    pattern: /\[\s*\{?[^[\]]{0,40}\bchunk(_id)?s?\b[^[\]]{0,40}\]/gi,
    description: "a bracketed chunk count / chunk-id label (`[N chunks]`)",
    replacement: "\"N sources\" (see GLOSSARY: [N chunks])",
  },
  {
    id: "n-claims",
    pattern: /\[\s*\{?[^[\]]{0,40}\bclaim(_id)?s?\b[^[\]]{0,40}\]/gi,
    description: "a bracketed claim count / claim-id label (`[N claims]`)",
    replacement: "\"N points\" (see GLOSSARY: [N claims])",
  },
  {
    id: "block-id",
    pattern: /\bblock_id\b/g,
    description: "the internal `block_id` handle",
    replacement: "never shown (see GLOSSARY: block_id)",
  },
  {
    id: "subject-status",
    pattern: /\bsubject_status\b/g,
    description: "the raw `subject_status` enum token",
    replacement: "plain words like living / deceased (see GLOSSARY: subject_status)",
  },
  {
    id: "publish-intent",
    pattern: /\bpublish_intent\b/g,
    description: "the raw `publish_intent` enum token",
    replacement: "plain words like keep private / will be public (see GLOSSARY: publish_intent)",
  },
  {
    // A bare 32- or 40-hex string used as a label. Hyphenated UUIDs are caught
    // by the inv-id rule when prefixed; this catches the unprefixed raw hex.
    id: "raw-hex-uuid",
    pattern: /\b[0-9a-f]{32,40}\b/gi,
    description: "a raw 32/40-hex id used as a label",
    replacement: "the source's title (see GLOSSARY: chunk UUID)",
  },
];

/** Look up the chosen wording for a substrate term. */
export function userFacingFor(term: string): GlossaryEntry | undefined {
  return GLOSSARY.find((g) => g.term === term);
}

/**
 * READING_STATE_COPY — the reading surface's SYSTEM-STATE microcopy, in §5 voice
 * (ALC SPR-07 M3).
 *
 * The glossary above governs WORDS (substrate noun → user noun). This governs
 * SENTENCES for the reading surface's loading / empty / error / fallback states
 * — the moments a surface most often reads as a default. Centralised here (the
 * copy home) so the wording has one place and the §5 discipline is enforceable.
 *
 * Every string is held to master-product-spec §5: prose flows, no LLM-slop
 * vocabulary, ≤1 em-dash per thesis, no padding ("It is important to note"), no
 * forced exclamation, confidence by rhythm not "(…)" markers, calm. And to the
 * SPR-07 firewall: no apology theatre, and the procedural scene is NEVER called
 * "degraded" or a "fallback" in front of a reader — the procedural floor is
 * normal (the rationale lives in docs, the copy treats it as ordinary).
 *
 * NOTE: a generic engine error string is NOT shown raw to the reader (a raw
 * diagnostic is exactly the LLM-slop/jargon §5 forbids). `errorGeneric` is the
 * calm sentence shown when there is no specific, user-meaningful reason; a
 * specific, known reason (e.g. a book that isn't in the library) gets its own
 * line.
 */
export const READING_STATE_COPY = {
  /** Loading a book. The world (the scene) is already there; we are opening the
   *  book INTO it, so the verb is "opening", not a mechanical "loading". */
  bookOpening: "Opening the book…",
  /** Loading a personal collection. Prose, not a bare ellipsis: it says what is
   *  happening in the reader's own words. */
  collectionGathering: "Gathering your readings…",
  /** A known, user-meaningful error: the requested book isn't in the library. */
  bookNotFound: "That book isn’t in the library.",
  /** The catch-all error. Calm and specific about what the reader can do, with
   *  no raw diagnostic, no apology, no blame. */
  errorGeneric:
    "That didn’t load. The book may have moved, or the connection dropped; try opening it again.",
  /** A personal collection that failed to load. */
  collectionError:
    "Your readings didn’t load just now. Refresh the page, or try again in a moment.",
  /** A meta-reading (the one-shot synthesis over the owned corpus) that failed
   *  to generate or re-open. Calm, specific about the next step, no raw engine
   *  diagnostic — the same firewall the rest of the reading surface holds. */
  metaReadingError:
    "That reading didn’t come through. Nothing was lost; try making it again, or open it in a moment.",
} as const;
