import type { Event } from "../../generated/types";
import type {
  CitationHistoryState,
} from "../../reading-physics/types";

/**
 * resolveCitationHistory — the SURFACE-side resolver that assembles a cited
 * source's {@link CitationHistoryState} from the substrate event log, so
 * SiteSee's tint goes live (Living Roadmap SPR-07 M4). This is step 2 of the
 * SPR-06 gap doc's "exact next step": SiteSee READS a resolved view; THIS
 * builds it (the augmentation opens no writer and computes no history — PR-2).
 *
 * The three substrate signals → the closed tint vocabulary, in PRECEDENCE
 * order (the order `CitationHistoryState` documents): cited ≻ saved ≻ read ≻
 * unseen. A source the reader cited is shown as `cited` even if also read; the
 * strongest relationship wins one tint (SiteSee paints one class per source).
 *
 *   - `cited`  : a claim cites this source's chunk — already substrate-derived
 *                (a synthesize.delivered's `supporting_chunk_ids`, an authored
 *                section's `cited_chunk_ids`). Resolved here from the events the
 *                surface already pulls; the caller passes the cited chunk-id set.
 *   - `saved`  : the source was promoted/saved — already substrate-derived; the
 *                caller passes the saved set.
 *   - `read`   : the NET-NEW `source.read` event (SPR-07 M4) — the reader
 *                dwelled past the threshold. THIS is the signal that was missing;
 *                resolving it here is what lights the previously-dormant tint.
 *
 * §9.0: this reads only EVENT METADATA (action_type + the chunk/document the
 * read was attributed to) — never a source body. `source.read` carries no body
 * by construction (the schema has no body field), so the resolved state can
 * never smuggle withheld content.
 */

/** A source.read event's attribution — the chunk it tinted + the document it
 * sat in. Read off the event metadata, never the body. */
function readChunkId(e: Event): string | null {
  const p = e.payload as unknown as { chunk_id?: string | null } | null;
  return (p && typeof p === "object" ? (p.chunk_id ?? null) : null);
}

export interface ResolveCitationHistoryInput {
  /** The reading thread's events (source.read lives here). */
  events: readonly Event[];
  /** Chunk-ids a claim cites (already substrate-derived). */
  citedChunkIds?: ReadonlySet<string>;
  /** Chunk-ids the reader saved/promoted (already substrate-derived). */
  savedChunkIds?: ReadonlySet<string>;
}

/**
 * Build a `chunkId → CitationHistoryState` map from the substrate signals.
 * Precedence: cited ≻ saved ≻ read ≻ unseen (a chunk not in the map is unseen,
 * which SiteSee tints nothing — the honest default).
 */
export function resolveCitationHistory(
  input: ResolveCitationHistoryInput,
): Map<string, CitationHistoryState> {
  const cited = input.citedChunkIds ?? new Set<string>();
  const saved = input.savedChunkIds ?? new Set<string>();

  // The set of chunks marked read by a source.read event in the thread.
  const read = new Set<string>();
  for (const e of input.events) {
    if (e.action_type !== "source.read") continue;
    const cid = readChunkId(e);
    if (cid) read.add(cid);
  }

  const out = new Map<string, CitationHistoryState>();
  // Apply weakest → strongest so a stronger signal overwrites; result respects
  // precedence cited ≻ saved ≻ read.
  for (const cid of read) out.set(cid, "read");
  for (const cid of saved) out.set(cid, "saved");
  for (const cid of cited) out.set(cid, "cited");
  return out;
}

/** A single source's state (defaults to the honest "unseen" — no history ⇒ no
 * tint), for the surface that builds one SiteSeeSourceView at a time. */
export function stateForChunk(
  history: Map<string, CitationHistoryState>,
  chunkId: string,
): CitationHistoryState {
  return history.get(chunkId) ?? "unseen";
}
