/**
 * Reading highlight → float tray + twin feed compose (pure).
 *
 * Operator vision: from a reading highlight, spin floating deep research /
 * tray merge intents AND feed twin note substrate with insights/questions
 * seeded from the highlight (and optional findings).
 *
 * live_dispatched always false.
 * merge_executed always false.
 * pack_dispatched always false.
 * twin_written always false.
 * record_persisted always false.
 */

import {
  composeReadingHighlightFloatMergeTray,
  type ReadingHighlightFloatMergeTrayCompose,
  type ReadingHighlightFloatMergeTrayInput,
  type ReadingSurfaceAction,
} from "./readingHighlightFloatMergeTrayCompose";
import {
  composeTwinChaseAnalysisFeed,
  type ChaseFeedFinding,
  type TwinChaseAnalysisFeedCompose,
} from "./twinChaseAnalysisFeedCompose";
import type { LaunchPreferredView } from "./highlightDeepResearchLaunchCompose";
import type { SourceFamilyHint } from "./highlightDeepResearchLaunchCompose";
import type { TrayMember } from "./floatingInstanceTrayCompose";

export interface ReadingHighlightFloatTwinFeedInput {
  session_id: string;
  parent_asset_id: string;
  highlight: string;
  gated: boolean;
  would_exceed: boolean | null;
  surface_action: ReadingSurfaceAction;
  operator_ack: boolean;
  prompt?: string;
  preferred_view_mode?: LaunchPreferredView;
  operator_override?: boolean;
  selected_model_id?: string | null;
  source_families?: SourceFamilyHint[] | null;
  existing_members?: TrayMember[] | null;
  selected_instance_ids?: string[] | null;
  /**
   * Optional twin findings beyond the highlight seed (caller-supplied).
   * Highlight is always included as a question finding when twin feed runs.
   */
  twin_findings?: ChaseFeedFinding[] | null;
  existing_twin_asset_id?: string | null;
  mark_for_prompt_context?: boolean;
  /**
   * When false, skip twin feed (surface tray only). Default true.
   */
  include_twin_feed?: boolean;
}

export interface ReadingHighlightFloatTwinFeedCompose {
  session_id: string;
  surface: ReadingHighlightFloatMergeTrayCompose;
  twin_feed: TwinChaseAnalysisFeedCompose | null;
  /**
   * True when surface.surface_ready and (twin skipped or twin feed_ready).
   */
  pack_ready: boolean;
  live_dispatched: false;
  merge_executed: false;
  pack_dispatched: false;
  twin_written: false;
  record_persisted: false;
  notes: string[];
  authority: "reading_highlight_float_twin_feed_compose_advisory";
}

function requireNonEmpty(value: unknown, name: string): string {
  if (typeof value !== "string" || !value.trim()) {
    throw new Error(`${name} must be a non-empty string`);
  }
  return value.trim();
}

/**
 * Compose reading surface float/tray pack + twin feed from one highlight.
 */
export function composeReadingHighlightFloatTwinFeed(
  input: ReadingHighlightFloatTwinFeedInput,
): ReadingHighlightFloatTwinFeedCompose {
  if (!input || typeof input !== "object") {
    throw new Error("input must be an object");
  }
  if (typeof input.operator_ack !== "boolean") {
    throw new Error("operator_ack must be an explicit boolean");
  }
  const session_id = requireNonEmpty(input.session_id, "session_id");
  const include_twin =
    input.include_twin_feed === undefined ? true : input.include_twin_feed;
  if (typeof include_twin !== "boolean") {
    throw new Error("include_twin_feed must be boolean when set");
  }

  const notes: string[] = [
    "live_dispatched=false — reading float/twin pack is pure intent",
    "merge_executed=false",
    "pack_dispatched=false",
    "twin_written=false",
    "record_persisted=false",
  ];

  const surfaceInput: ReadingHighlightFloatMergeTrayInput = {
    parent_asset_id: input.parent_asset_id,
    highlight: input.highlight,
    gated: input.gated,
    would_exceed: input.would_exceed,
    surface_action: input.surface_action,
    operator_ack: input.operator_ack,
    prompt: input.prompt,
    preferred_view_mode: input.preferred_view_mode,
    operator_override: input.operator_override,
    selected_model_id: input.selected_model_id,
    source_families: input.source_families,
    existing_members: input.existing_members,
    selected_instance_ids: input.selected_instance_ids,
  };
  const surface = composeReadingHighlightFloatMergeTray(surfaceInput);
  notes.push(...surface.notes);

  let twin_feed: TwinChaseAnalysisFeedCompose | null = null;
  if (include_twin) {
    const findings: ChaseFeedFinding[] = [
      {
        source_id: `highlight_${session_id}`,
        body: requireNonEmpty(input.highlight, "highlight"),
        kind: "question",
      },
    ];
    if (input.twin_findings != null) {
      if (!Array.isArray(input.twin_findings)) {
        throw new Error("twin_findings must be an array when set");
      }
      for (const f of input.twin_findings) {
        findings.push(f);
      }
    }
    twin_feed = composeTwinChaseAnalysisFeed({
      session_id,
      parent_asset_id: input.parent_asset_id,
      findings,
      analysis_excerpt: `highlight seed: ${input.highlight.trim()}`,
      existing_twin_asset_id: input.existing_twin_asset_id,
      operator_ack: input.operator_ack,
      mark_for_prompt_context: input.mark_for_prompt_context,
    });
    notes.push(...twin_feed.notes);
  } else {
    notes.push("twin_feed skipped — include_twin_feed=false");
  }

  const twin_ok = !include_twin || (twin_feed != null && twin_feed.feed_ready);
  const pack_ready = surface.surface_ready && twin_ok;

  if (!surface.surface_ready) {
    notes.push("pack_ready=false — surface tray/launch not ready");
  } else if (!twin_ok) {
    notes.push("pack_ready=false — twin feed not ready");
  } else {
    notes.push(
      "pack_ready=true — highlight float+twin intent only; still pure",
    );
  }

  if (
    surface.live_dispatched !== false ||
    surface.merge_executed !== false ||
    surface.pack_dispatched !== false ||
    (twin_feed != null &&
      (twin_feed.twin_written !== false ||
        twin_feed.record_persisted !== false ||
        twin_feed.live_dispatch_authorized !== false))
  ) {
    throw new Error("invariant: nested honesty flags must remain false");
  }

  notes.push("live_dispatched=false");
  notes.push("merge_executed=false");
  notes.push("pack_dispatched=false");
  notes.push("twin_written=false");
  notes.push("record_persisted=false");

  return {
    session_id,
    surface,
    twin_feed,
    pack_ready,
    live_dispatched: false,
    merge_executed: false,
    pack_dispatched: false,
    twin_written: false,
    record_persisted: false,
    notes,
    authority: "reading_highlight_float_twin_feed_compose_advisory",
  };
}

export function formatReadingHighlightFloatTwinFeedSummary(
  c: ReadingHighlightFloatTwinFeedCompose,
): string {
  return (
    `pack_ready=${c.pack_ready} · surface_ready=${c.surface.surface_ready} · ` +
    `feed_ready=${c.twin_feed ? c.twin_feed.feed_ready : "n/a"} · ` +
    `live_dispatched=false · merge_executed=false · pack_dispatched=false · ` +
    `twin_written=false · record_persisted=false`
  );
}
