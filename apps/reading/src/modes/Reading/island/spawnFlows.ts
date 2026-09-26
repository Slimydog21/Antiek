/**
 * spawnFlows.ts — the island's two spawn flows (island SPR-03), carried as
 * one orchestration module so the failure matrix is testable in isolation.
 *
 * Both flows end in an anchor linked to a thread (the anchors unit's
 * write-back — consumed, not re-specified):
 *
 *   (a) HIGHLIGHT path (deep-research from a selection):
 *       dedupe-by-location (retry/second-spawn reuses the SAME anchor, never
 *       a duplicate pin) → pin if absent → spin → write-back (first link
 *       wins; a 409 is an honest keep, never an error). The island emerges
 *       collapsed at the passage — the reader does NOT navigate away.
 *
 *   (b) FREE-INQUIRY ("Research from here"): pin the current page's lead
 *       passage FIRST (source=pin) → spin with the pinned passage →
 *       write-back → island. A gated book has no anchor-map, so no passage
 *       can anchor — the caller's pin step refuses honestly ("Couldn't
 *       anchor this passage") with NO pin, NO spawn, and NO withheld text
 *       anywhere (the §9.0 rule: no anchor → no island).
 *
 * THE FAILURE MATRIX (the spec's own):
 *   - pin fails (ambiguous passage → the anchors unit's 422): NO thread is
 *     spawned and the caller sees the pin failure — never an anchorless
 *     island (result.failedAt === "pin", zero spin calls);
 *   - spawn fails after a successful pin: the plain pinned highlight
 *     remains (lawful anchors-unit state) with an honest error
 *     (result.failedAt === "spawn"), and a RETRY reuses the SAME anchor —
 *     the dedupe-by-location skips the pin, asserted by request count;
 *   - link fails with 409 (already linked): first link wins — an honest
 *     keep, NOT an error (the island shows the first thread); any other
 *     link failure is reported honestly (result.failedAt === "link").
 */
import { ApiError } from "../../../lib/api";
import type { BookAnchor } from "../../../lib/api";
import type { SpinResearchResponse } from "../../../api/books";

/** Where a spawn flow stopped (null = it ran clean). */
export type SpawnFailure = "pin" | "spawn" | "link" | null;

export interface SpawnFlowResult {
  ok: boolean;
  failedAt: SpawnFailure;
  /** The anchor the flow ended with (null only when the pin failed or the
   *  flow refused before pinning). */
  anchorId: string | null;
  /** The spawned thread (null when the flow stopped before the spin). */
  investigationId: string | null;
  /** The honest, operator-facing reason for a failure or refusal. */
  message: string | null;
}

export interface SpawnFlowDeps {
  /** The anchors currently on record (for dedupe-by-location). */
  anchors: readonly BookAnchor[];
  /** The location tuple of the passage, when it resolves (null = nowhere to
   *  anchor — a gated book's passage or an unlocatable one). */
  locate: () => { chunkId: string; start: number; end: number } | null;
  /** Pin the passage (the anchors unit's pin machinery). */
  pin: () => Promise<BookAnchor>;
  /** Spin the research (spinResearch — gate-safe by its own contract). */
  spin: (passageText: string) => Promise<SpinResearchResponse>;
  /** The SPR-04 write-back (first-link-wins PATCH). */
  link: (anchorId: string, investigationId: string) => Promise<unknown>;
  /** The passage text the spin is seeded with (already §9.0-safe — the
   *  caller's own readable text; a gated book's passage never arrives here). */
  passageText: string;
}

/** The dedupe key: chunk + offsets identify one anchored passage. */
export function anchorAtLocation(
  anchors: readonly BookAnchor[],
  chunkId: string,
  start: number,
  end: number,
): BookAnchor | null {
  return (
    anchors.find(
      (a) =>
        a.anchor.node_id === chunkId &&
        a.anchor.start_scalar === start &&
        a.anchor.end_scalar === end,
    ) ?? null
  );
}

/**
 * Run one spawn flow. NEVER throws for the failure matrix's cases — each
 * maps to a SpawnFlowResult with an honest message; an unexpected error
 * propagates (a bug, not a matrix case).
 */
export async function runSpawnFlow(deps: SpawnFlowDeps): Promise<SpawnFlowResult> {
  const loc = deps.locate();

  // 1. Dedupe-by-location: an existing anchor for this passage is reused
  //    (a retry after a spawn failure, or a second spawn from the same
  //    passage) — never a duplicate pin.
  let anchor = loc
    ? anchorAtLocation(deps.anchors, loc.chunkId, loc.start, loc.end)
    : null;
  if (!anchor) {
    try {
      // The caller's pin decides what "anchorable" means for THIS selection:
      // a servable passage pins by quote (the server resolves — no local
      // location needed); a withheld passage pins metadata-only, which needs
      // the local resolution and fails honestly without it (a gated book's
      // passage can never anchor — no anchor → no island → no spawn, and no
      // withheld text anywhere).
      anchor = await deps.pin();
    } catch (e) {
      const detail = e instanceof ApiError ? e.body || e.message : String(e);
      // An ambiguous passage (the 422) is the pin failure the operator sees:
      // NO thread is spawned — never an anchorless island.
      return {
        ok: false,
        failedAt: "pin",
        anchorId: null,
        investigationId: null,
        message: `Couldn't anchor this passage — ${detail}`,
      };
    }
  }

  // 2. The spin. A failure here leaves the lawful pinned highlight in place
  //    with an honest error; a retry reuses the SAME anchor (the dedupe
  //    above skips the pin).
  let spawned: SpinResearchResponse;
  try {
    spawned = await deps.spin(deps.passageText);
  } catch (e) {
    const detail = e instanceof Error ? e.message : String(e);
    return {
      ok: false,
      failedAt: "spawn",
      anchorId: anchor.anchor_id,
      investigationId: null,
      message: `The research didn't start — ${detail}. Your highlight is still pinned; you can try again.`,
    };
  }

  // 3. The write-back. First link wins: a 409 (already linked) is an honest
  //    keep — never an error. Any other link failure is reported honestly.
  try {
    await deps.link(anchor.anchor_id, spawned.investigation_id);
  } catch (e) {
    if (e instanceof ApiError && e.status === 409) {
      return {
        ok: true,
        failedAt: null,
        anchorId: anchor.anchor_id,
        investigationId: spawned.investigation_id,
        message: null,
      };
    }
    const detail = e instanceof Error ? e.message : String(e);
    return {
      ok: false,
      failedAt: "link",
      anchorId: anchor.anchor_id,
      investigationId: spawned.investigation_id,
      message: `The research started but couldn't link to the passage — ${detail}.`,
    };
  }

  return {
    ok: true,
    failedAt: null,
    anchorId: anchor.anchor_id,
    investigationId: spawned.investigation_id,
    message: null,
  };
}
