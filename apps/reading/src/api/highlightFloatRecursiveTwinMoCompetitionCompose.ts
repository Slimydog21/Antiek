/**
 * Reading highlight float/twin feed → recursive twin MO competition (pure).
 *
 * Operator vision: from a reading highlight, float deep research + twin feed,
 * then fold into MO unattended + model decision + HTML competition research
 * with recursive twin note-taker — reading and research share one HTML surface.
 *
 * live_dispatched / merge_executed / pack_dispatched / twin_written always false.
 * live_execution_authorized / prompts_injected always false.
 */

import {
  composeReadingHighlightFloatTwinFeed,
  type ReadingHighlightFloatTwinFeedCompose,
  type ReadingHighlightFloatTwinFeedInput,
} from "./readingHighlightFloatTwinFeedCompose";
import {
  composeRecursiveTwinMoCompetition,
  type RecursiveTwinMoCompetitionCompose,
  type RecursiveTwinMoCompetitionInput,
} from "./recursiveTwinMoCompetitionCompose";

export interface HighlightFloatRecursiveTwinMoCompetitionInput {
  highlight_surface: ReadingHighlightFloatTwinFeedInput;
  mo_competition: Omit<
    RecursiveTwinMoCompetitionInput,
    "operator_ack" | "source_excerpt" | "parent_asset_id"
  > & {
    parent_asset_id?: string;
    source_excerpt?: string | null;
  };
  operator_ack: boolean;
  /**
   * When true (default), inject highlight text into twin MO source_excerpt
   * when mo_competition.source_excerpt omitted.
   */
  seed_excerpt_from_highlight?: boolean;
  require_both?: boolean;
}

export interface HighlightFloatRecursiveTwinMoCompetitionCompose {
  session_id: string;
  parent_asset_id: string;
  highlight_surface: ReadingHighlightFloatTwinFeedCompose;
  mo_competition: RecursiveTwinMoCompetitionCompose;
  pack_ready: boolean;
  live_dispatched: false;
  merge_executed: false;
  pack_dispatched: false;
  twin_written: false;
  record_persisted: false;
  live_execution_authorized: false;
  prompts_injected: false;
  live_router_authorized: false;
  pdf_view_authorized: false;
  store_mutated: false;
  notes: string[];
  authority: "highlight_float_recursive_twin_mo_competition_compose_advisory";
}

function requireNonEmpty(value: unknown, name: string): string {
  if (typeof value !== "string" || !value.trim()) {
    throw new Error(`${name} must be a non-empty string`);
  }
  return value.trim();
}

/**
 * Compose highlight float/twin feed with recursive twin MO competition pack.
 * Never dispatches live workers or writes twins.
 */
export function composeHighlightFloatRecursiveTwinMoCompetition(
  input: HighlightFloatRecursiveTwinMoCompetitionInput,
): HighlightFloatRecursiveTwinMoCompetitionCompose {
  if (!input || typeof input !== "object") {
    throw new Error("input must be an object");
  }
  if (typeof input.operator_ack !== "boolean") {
    throw new Error("operator_ack must be an explicit boolean");
  }
  if (!input.highlight_surface || typeof input.highlight_surface !== "object") {
    throw new Error("highlight_surface must be an object");
  }
  if (!input.mo_competition || typeof input.mo_competition !== "object") {
    throw new Error("mo_competition must be an object");
  }

  const require_both =
    input.require_both === undefined ? true : input.require_both;
  if (typeof require_both !== "boolean") {
    throw new Error("require_both must be boolean when set");
  }
  const seed =
    input.seed_excerpt_from_highlight === undefined
      ? true
      : input.seed_excerpt_from_highlight;
  if (typeof seed !== "boolean") {
    throw new Error("seed_excerpt_from_highlight must be boolean when set");
  }

  const notes: string[] = [
    "live_dispatched=false · merge_executed=false · pack_dispatched=false",
    "twin_written=false · record_persisted=false · prompts_injected=false",
    "live_execution_authorized=false · live_router_authorized=false",
    "pdf_view_authorized=false · store_mutated=false",
  ];

  const highlight_surface = composeReadingHighlightFloatTwinFeed({
    ...input.highlight_surface,
    operator_ack: input.operator_ack,
  });
  notes.push(...highlight_surface.notes.map((n) => `[highlight_surface] ${n}`));

  const session_id = requireNonEmpty(
    highlight_surface.session_id,
    "session_id",
  );
  const parent_asset_id = requireNonEmpty(
    input.mo_competition.parent_asset_id ??
      input.highlight_surface.parent_asset_id,
    "parent_asset_id",
  );

  let source_excerpt = input.mo_competition.source_excerpt;
  if (
    seed &&
    (source_excerpt == null || !String(source_excerpt).trim())
  ) {
    source_excerpt = `highlight: ${input.highlight_surface.highlight}`;
    notes.push("source_excerpt seeded from reading highlight");
  }

  const mo_competition = composeRecursiveTwinMoCompetition({
    ...input.mo_competition,
    parent_asset_id,
    source_excerpt,
    operator_ack: input.operator_ack,
  });
  notes.push(...mo_competition.notes.map((n) => `[mo_competition] ${n}`));

  let pack_ready = false;
  if (require_both) {
    pack_ready =
      highlight_surface.pack_ready === true &&
      mo_competition.pack_ready === true &&
      input.operator_ack === true;
  } else {
    pack_ready =
      input.operator_ack === true &&
      (highlight_surface.pack_ready === true ||
        mo_competition.pack_ready === true);
  }

  if (pack_ready) {
    notes.push(
      "pack_ready=true — highlight float + recursive twin MO competition ready; still pure",
    );
  } else {
    notes.push(
      "pack_ready=false — highlight_surface, mo_competition, or operator_ack gate open",
    );
  }

  if (
    highlight_surface.live_dispatched !== false ||
    highlight_surface.merge_executed !== false ||
    highlight_surface.pack_dispatched !== false ||
    highlight_surface.twin_written !== false ||
    mo_competition.twin_written !== false ||
    mo_competition.live_execution_authorized !== false ||
    mo_competition.prompts_injected !== false
  ) {
    throw new Error("invariant: honesty flags must remain false");
  }

  notes.push("live_dispatched=false");
  notes.push("merge_executed=false");
  notes.push("pack_dispatched=false");
  notes.push("twin_written=false");
  notes.push("record_persisted=false");
  notes.push("live_execution_authorized=false");
  notes.push("prompts_injected=false");
  notes.push("live_router_authorized=false");
  notes.push("pdf_view_authorized=false");
  notes.push("store_mutated=false");

  return {
    session_id,
    parent_asset_id,
    highlight_surface,
    mo_competition,
    pack_ready,
    live_dispatched: false,
    merge_executed: false,
    pack_dispatched: false,
    twin_written: false,
    record_persisted: false,
    live_execution_authorized: false,
    prompts_injected: false,
    live_router_authorized: false,
    pdf_view_authorized: false,
    store_mutated: false,
    notes,
    authority: "highlight_float_recursive_twin_mo_competition_compose_advisory",
  };
}

export function formatHighlightFloatRecursiveTwinMoCompetitionSummary(
  c: HighlightFloatRecursiveTwinMoCompetitionCompose,
): string {
  return (
    `pack_ready=${c.pack_ready} · ` +
    `highlight_ready=${c.highlight_surface.pack_ready} · ` +
    `mo_twin_ready=${c.mo_competition.pack_ready} · ` +
    `live_dispatched=false · twin_written=false · ` +
    `live_execution_authorized=false · prompts_injected=false`
  );
}
