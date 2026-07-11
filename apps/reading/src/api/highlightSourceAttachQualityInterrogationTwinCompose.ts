/**
 * Highlight source attach quality interrogation → twin feed (pure).
 *
 * Operator vision: from a highlight, attach sources, chase questions, feed
 * recursive twin note-taker so reading insights inform future work.
 *
 * live_dispatched / merge_executed / twin_written / remote_fetched always false.
 */

import {
  composeHighlightSourceAttachQualityInterrogation,
  type HighlightSourceAttachQualityInterrogationCompose,
  type HighlightSourceAttachQualityInterrogationInput,
} from "./highlightSourceAttachQualityInterrogationCompose";
import {
  composeTwinChaseAnalysisFeed,
  type ChaseFeedFinding,
  type TwinChaseAnalysisFeedCompose,
} from "./twinChaseAnalysisFeedCompose";

export interface HighlightSourceAttachQualityInterrogationTwinInput
  extends HighlightSourceAttachQualityInterrogationInput {
  existing_twin_asset_id?: string | null;
  analysis_excerpt?: string | null;
  mark_for_prompt_context?: boolean;
  twin_findings?: ChaseFeedFinding[] | null;
  require_both_with_twin?: boolean;
}

export interface HighlightSourceAttachQualityInterrogationTwinCompose {
  parent_asset_id: string;
  session_id: string;
  highlight_pack: HighlightSourceAttachQualityInterrogationCompose;
  twin_feed: TwinChaseAnalysisFeedCompose;
  pack_ready: boolean;
  live_dispatched: false;
  merge_executed: false;
  remote_fetched: false;
  twin_written: false;
  prompts_injected: false;
  store_mutated: false;
  notes: string[];
  authority: "highlight_source_attach_quality_interrogation_twin_compose_advisory";
}

function requireNonEmpty(value: unknown, name: string): string {
  if (typeof value !== "string" || !value.trim()) {
    throw new Error(`${name} must be a non-empty string`);
  }
  return value.trim();
}

function deriveFindings(
  highlight: string,
  sources: HighlightSourceAttachQualityInterrogationInput["sources"],
  questions: HighlightSourceAttachQualityInterrogationInput["questions"],
): ChaseFeedFinding[] {
  const findings: ChaseFeedFinding[] = [
    { source_id: "hl-highlight", body: highlight, kind: "data" },
  ];
  for (const s of sources) {
    findings.push({
      source_id: `src-${s.source_id}`,
      body: s.title,
      kind: "data",
    });
  }
  for (const q of questions) {
    findings.push({
      source_id: `q-${q.question_id}`,
      body: q.body,
      kind: "question",
    });
  }
  return findings;
}

export function composeHighlightSourceAttachQualityInterrogationTwin(
  input: HighlightSourceAttachQualityInterrogationTwinInput,
): HighlightSourceAttachQualityInterrogationTwinCompose {
  if (!input || typeof input !== "object") {
    throw new Error("input must be an object");
  }
  if (typeof input.operator_ack !== "boolean") {
    throw new Error("operator_ack must be an explicit boolean");
  }
  const parent_asset_id = requireNonEmpty(
    input.parent_asset_id,
    "parent_asset_id",
  );
  const session_id = requireNonEmpty(input.session_id, "session_id");
  const highlight = requireNonEmpty(input.highlight, "highlight");

  const require_both_with_twin =
    input.require_both_with_twin === undefined
      ? true
      : input.require_both_with_twin;
  if (typeof require_both_with_twin !== "boolean") {
    throw new Error("require_both_with_twin must be boolean when set");
  }

  const mark_for_prompt_context =
    input.mark_for_prompt_context === undefined
      ? true
      : input.mark_for_prompt_context;
  if (typeof mark_for_prompt_context !== "boolean") {
    throw new Error("mark_for_prompt_context must be boolean when set");
  }

  const notes: string[] = [
    "live_dispatched=false · merge_executed=false",
    "remote_fetched=false · twin_written=false · prompts_injected=false",
  ];

  const highlight_pack = composeHighlightSourceAttachQualityInterrogation({
    parent_asset_id: input.parent_asset_id,
    highlight: input.highlight,
    gated: input.gated,
    prompt: input.prompt,
    preferred_view_mode: input.preferred_view_mode,
    would_exceed: input.would_exceed,
    operator_override: input.operator_override,
    selected_model_id: input.selected_model_id,
    source_families: input.source_families,
    operator_ack: input.operator_ack,
    session_id: input.session_id,
    requested_families: input.requested_families,
    sources: input.sources,
    citations: input.citations,
    derive_citations_from_sources: input.derive_citations_from_sources,
    quality_overall: input.quality_overall,
    quality_floor: input.quality_floor,
    questions: input.questions,
    chase_mode: input.chase_mode,
    prior_records: input.prior_records,
    user_prompt: input.user_prompt,
    models: input.models,
    daily_cap_usd: input.daily_cap_usd,
    spent_usd: input.spent_usd,
    projected_cost_usd_high: input.projected_cost_usd_high,
    projected_cost_usd_low: input.projected_cost_usd_low,
    bench_bests: input.bench_bests,
    focus_task: input.focus_task,
    nd_shadow: input.nd_shadow,
    require_both: input.require_both,
  });
  notes.push(...highlight_pack.notes.map((n) => `[highlight_pack] ${n}`));

  let twin_findings: ChaseFeedFinding[];
  if (input.twin_findings != null) {
    if (!Array.isArray(input.twin_findings)) {
      throw new Error("twin_findings must be an array when set");
    }
    twin_findings = input.twin_findings;
    notes.push(`twin_findings=${twin_findings.length} caller-supplied`);
  } else {
    twin_findings = deriveFindings(highlight, input.sources, input.questions);
    notes.push(
      `twin_findings=${twin_findings.length} derived from highlight+sources+questions`,
    );
  }

  const twin_feed = composeTwinChaseAnalysisFeed({
    session_id,
    parent_asset_id,
    findings: twin_findings,
    analysis_excerpt: input.analysis_excerpt,
    existing_twin_asset_id: input.existing_twin_asset_id,
    operator_ack: input.operator_ack,
    mark_for_prompt_context,
  });
  notes.push(...twin_feed.notes.map((n) => `[twin_feed] ${n}`));

  let pack_ready = false;
  if (require_both_with_twin) {
    pack_ready =
      highlight_pack.pack_ready === true &&
      twin_feed.feed_ready === true &&
      input.operator_ack === true;
  } else {
    pack_ready =
      input.operator_ack === true &&
      (highlight_pack.pack_ready === true || twin_feed.feed_ready === true);
  }

  if (pack_ready) {
    notes.push("pack_ready=true — highlight pack + twin feed ready; still pure");
  } else {
    notes.push(
      "pack_ready=false — highlight pack, twin feed, or operator_ack gate open",
    );
  }

  if (
    highlight_pack.live_dispatched !== false ||
    highlight_pack.merge_executed !== false ||
    twin_feed.twin_written !== false ||
    twin_feed.prompts_injected !== false
  ) {
    throw new Error("invariant: honesty flags must remain false");
  }

  notes.push("live_dispatched=false");
  notes.push("merge_executed=false");
  notes.push("remote_fetched=false");
  notes.push("twin_written=false");
  notes.push("prompts_injected=false");
  notes.push("store_mutated=false");

  return {
    parent_asset_id,
    session_id,
    highlight_pack,
    twin_feed,
    pack_ready,
    live_dispatched: false,
    merge_executed: false,
    remote_fetched: false,
    twin_written: false,
    prompts_injected: false,
    store_mutated: false,
    notes,
    authority:
      "highlight_source_attach_quality_interrogation_twin_compose_advisory",
  };
}

export function formatHighlightSourceAttachQualityInterrogationTwinSummary(
  c: HighlightSourceAttachQualityInterrogationTwinCompose,
): string {
  return (
    `pack_ready=${c.pack_ready} · ` +
    `highlight_ready=${c.highlight_pack.pack_ready} · ` +
    `twin_feed_ready=${c.twin_feed.feed_ready} · ` +
    `findings=${c.twin_feed.finding_count} · ` +
    `live_dispatched=false · twin_written=false · merge_executed=false`
  );
}
