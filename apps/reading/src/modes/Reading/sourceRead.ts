import { postTypedEvent } from "../../lib/api";
import type { SourceReadPayload } from "../../generated/types";
import { notifySourceReadCommitted } from "../../werner/shellExperienceSignals";

/**
 * source.read emit — light SiteSee's "read" tint with a REAL dwell signal
 * (Living Roadmap SPR-07 M4). Closes the SPR-06 gap
 * (`docs/decisions/spr-06-source-read-event-gap.md`): `cited`/`saved` were
 * already substrate-derived; the per-source `read` signal was not, so the tint
 * shipped dormant.
 *
 * ════════════════════════════════════════════════════════════════════════
 * "WHAT COUNTS AS READ" — the JUSTIFIED dwell threshold (rigor #1 / #5)
 * ════════════════════════════════════════════════════════════════════════
 * A `read` verdict must be a REAL reading signal, never fabricated. We do NOT
 * mark a source "read" the instant it opens (a glance is not a read) and we do
 * NOT spam one event per page-turn. The verdict is BOTH:
 *
 *   1. focused dwell ≥ {@link READ_DWELL_MS_THRESHOLD} (30s), AND
 *   2. the reader moved past the first page ({@link READ_MIN_PAGES} ≥ 2),
 *
 * measured by the SAME focused-dwell clock the ad-impression tracker already
 * uses (`useReaderImpressions` — dwell accrues only while the tab is focused,
 * `visibilitychange` pauses it). Reusing that clock means "read" inherits the
 * "attention not while idle" honesty: a backgrounded tab adds no dwell.
 *
 * WHY 30s + page 2: the threshold is the smallest signal that distinguishes
 * "actually reading" from "opened and bounced". 30 focused seconds past the
 * opening page is well beyond an accidental open or a metadata skim, and well
 * under the time to read even one short page closely — so it fires for a
 * genuine reader and not for a bounce. It is deliberately a LOW bar (a v1 tint,
 * not a completion metric): the tint says "you've been here", not "you finished
 * it". RECONSIDER-IF (documented in the decision doc): bump it if the tint
 * proves noisy (everything goes green), or split into "started"/"read" tiers if
 * a single bar is too coarse. It is reversible — a tint, not a gate.
 *
 * EMITTED ONCE PER SOURCE PER READING SESSION (coalesced). The reader holds a
 * per-session emitted-set and calls this at most once per document; the event
 * is NOT per-page. §9.0: it carries NO body — only the chunk anchor + the dwell
 * evidence (the funnel envelope carries the document_id). It rides
 * `postTypedEvent → /events/typed → runtime/db_lock` (the single-writer funnel,
 * PR-6) — no client side-store.
 */

/** Focused-ms a reader must dwell before a source counts as "read". 30s — see
 * the module doc + `docs/decisions/spr-06-source-read-event-gap.md` for why. */
export const READ_DWELL_MS_THRESHOLD = 30_000;

/** Distinct pages the reader must have dwelled on (past the opener) before the
 * "read" verdict trips — a single-page glance is not a read. */
export const READ_MIN_PAGES = 2;

/** Has the reader dwelled enough on this source to count as "read"? Pure — the
 * caller supplies the measured evidence from the focused-dwell clock. */
export function isRead(dwellMs: number, pagesSeen: number): boolean {
  return dwellMs >= READ_DWELL_MS_THRESHOLD && pagesSeen >= READ_MIN_PAGES;
}

/**
 * Emit ONE `source.read` event through the single-writer funnel. Scoped to the
 * book's reading thread (`read-<documentId>`) so the read history sits on the
 * same thread the companion + notes read. Best-effort: a failed emit never
 * disrupts reading (the tint just stays dark, honestly).
 */
export async function emitSourceRead(args: {
  documentId: string;
  readingThreadId: string;
  /** The chunk the read is attributed to (the representative chunk SiteSee
   * tints). Null when the reader didn't resolve one — recorded honestly. */
  chunkId?: string | null;
  /** The dwell evidence that justified the verdict (carried so the verdict is
   * reconstructable from the event alone). */
  dwellMs: number;
  pageCount: number;
}): Promise<void> {
  const payload: SourceReadPayload = {
    action_type: "source.read",
    chunk_id: args.chunkId ?? null,
    // Integer ms — the schema pins ge=0; round the float dwell clock.
    dwell_ms: Math.max(0, Math.round(args.dwellMs)),
    page_count: Math.max(0, args.pageCount),
  };
  try {
    await postTypedEvent({
      investigation_id: args.readingThreadId,
      document_id: args.documentId,
      payload,
    });
    notifySourceReadCommitted();
  } catch {
    /* best-effort — a missed read-tint never disrupts reading */
  }
}
