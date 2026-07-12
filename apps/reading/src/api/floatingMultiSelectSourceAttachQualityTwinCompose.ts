/**
 * Floating multi-select + source quality → twin chase feed (pure).
 *
 * Operator vision: multi-select cohesive DR with knowledge-dense sources
 * feeds recursive twin note-taker so collective findings and source titles
 * inform future workstation prompts.
 *
 * live_dispatched / twin_written / remote_fetched always false.
 */

import {
  composeFloatingMultiSelectSourceAttachQuality,
  type FloatingMultiSelectSourceAttachQualityCompose,
  type FloatingMultiSelectSourceAttachQualityInput,
} from "./floatingMultiSelectSourceAttachQualityCompose";
import {
  composeTwinChaseAnalysisFeed,
  type ChaseFeedFinding,
  type TwinChaseAnalysisFeedCompose,
} from "./twinChaseAnalysisFeedCompose";

export interface FloatingMultiSelectSourceAttachQualityTwinInput
  extends FloatingMultiSelectSourceAttachQualityInput {
  existing_twin_asset_id?: string | null;
  analysis_excerpt?: string | null;
  mark_for_prompt_context?: boolean;
  twin_findings?: ChaseFeedFinding[] | null;
  require_both_with_twin?: boolean;
}

export interface FloatingMultiSelectSourceAttachQualityTwinCompose {
  session_id: string;
  parent_asset_id: string;
  multi_source: FloatingMultiSelectSourceAttachQualityCompose;
  twin_feed: TwinChaseAnalysisFeedCompose;
  pack_ready: boolean;
  live_dispatched: false;
  pack_dispatched: false;
  merge_executed: false;
  analysis_written: false;
  remote_fetched: false;
  twin_written: false;
  prompts_injected: false;
  store_mutated: false;
  notes: string[];
  authority: "floating_multi_select_source_attach_quality_twin_compose_advisory";
}

function requireNonEmpty(value: unknown, name: string): string {
  if (typeof value !== "string" || !value.trim()) {
    throw new Error(`${name} must be a non-empty string`);
  }
  return value.trim();
}

function deriveFindings(
  input: FloatingMultiSelectSourceAttachQualityTwinInput,
): ChaseFeedFinding[] {
  const findings: ChaseFeedFinding[] = [];
  for (const s of input.sources) {
    findings.push({
      source_id: `src-${s.source_id}`,
      body: s.title,
      kind: "data",
    });
  }
  for (const m of input.members) {
    if (input.selected_instance_ids.includes(m.instance_id)) {
      const body =
        m.highlight?.trim() ||
        m.prior_prompt?.trim() ||
        m.findings?.[0]?.trim() ||
        m.instance_id;
      findings.push({
        source_id: `inst-${m.instance_id}`,
        body,
        kind: m.findings?.length ? "insight" : "question",
      });
    }
  }
  if (input.cohesive_prompt.trim()) {
    findings.push({
      source_id: "cohesive-prompt",
      body: input.cohesive_prompt.trim(),
      kind: "question",
    });
  }
  return findings;
}

export function composeFloatingMultiSelectSourceAttachQualityTwin(
  input: FloatingMultiSelectSourceAttachQualityTwinInput,
): FloatingMultiSelectSourceAttachQualityTwinCompose {
  if (!input || typeof input !== "object") {
    throw new Error("input must be an object");
  }
  if (typeof input.operator_ack !== "boolean") {
    throw new Error("operator_ack must be an explicit boolean");
  }
  const session_id = requireNonEmpty(input.session_id, "session_id");
  const parent_asset_id = requireNonEmpty(
    input.parent_asset_id,
    "parent_asset_id",
  );

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
    "live_dispatched=false · pack_dispatched=false · merge_executed=false",
    "remote_fetched=false · twin_written=false · prompts_injected=false",
  ];

  const multi_source = composeFloatingMultiSelectSourceAttachQuality({
    session_id: input.session_id,
    parent_asset_id: input.parent_asset_id,
    members: input.members,
    selected_instance_ids: input.selected_instance_ids,
    pack_mode: input.pack_mode,
    cohesive_prompt: input.cohesive_prompt,
    operator_ack: input.operator_ack,
    extra_context: input.extra_context,
    analysis_kind: input.analysis_kind,
    extra_findings: input.extra_findings,
    requested_families: input.requested_families,
    sources: input.sources,
    citations: input.citations,
    derive_citations_from_sources: input.derive_citations_from_sources,
    quality_overall: input.quality_overall,
    quality_floor: input.quality_floor,
    would_exceed: input.would_exceed,
    operator_override: input.operator_override,
    require_both: input.require_both,
  });
  notes.push(...multi_source.notes.map((n) => `[multi_source] ${n}`));

  let twin_findings: ChaseFeedFinding[];
  if (input.twin_findings != null) {
    if (!Array.isArray(input.twin_findings)) {
      throw new Error("twin_findings must be an array when set");
    }
    twin_findings = input.twin_findings;
    notes.push(`twin_findings=${twin_findings.length} caller-supplied`);
  } else {
    twin_findings = deriveFindings(input);
    notes.push(
      `twin_findings=${twin_findings.length} derived from sources+selected members+prompt`,
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
      multi_source.pack_ready === true &&
      twin_feed.feed_ready === true &&
      input.operator_ack === true;
  } else {
    pack_ready =
      input.operator_ack === true &&
      (multi_source.pack_ready === true || twin_feed.feed_ready === true);
  }

  if (pack_ready) {
    notes.push(
      "pack_ready=true — multi-select+sources + twin feed ready; still pure",
    );
  } else {
    notes.push(
      "pack_ready=false — multi-source, twin feed, or operator_ack gate open",
    );
  }

  if (
    multi_source.live_dispatched !== false ||
    multi_source.remote_fetched !== false ||
    twin_feed.twin_written !== false ||
    twin_feed.prompts_injected !== false
  ) {
    throw new Error("invariant: honesty flags must remain false");
  }

  notes.push("live_dispatched=false");
  notes.push("pack_dispatched=false");
  notes.push("merge_executed=false");
  notes.push("analysis_written=false");
  notes.push("remote_fetched=false");
  notes.push("twin_written=false");
  notes.push("prompts_injected=false");
  notes.push("store_mutated=false");

  return {
    session_id,
    parent_asset_id,
    multi_source,
    twin_feed,
    pack_ready,
    live_dispatched: false,
    pack_dispatched: false,
    merge_executed: false,
    analysis_written: false,
    remote_fetched: false,
    twin_written: false,
    prompts_injected: false,
    store_mutated: false,
    notes,
    authority:
      "floating_multi_select_source_attach_quality_twin_compose_advisory",
  };
}

export function formatFloatingMultiSelectSourceAttachQualityTwinSummary(
  c: FloatingMultiSelectSourceAttachQualityTwinCompose,
): string {
  return (
    `pack_ready=${c.pack_ready} · ` +
    `multi_source_ready=${c.multi_source.pack_ready} · ` +
    `twin_feed_ready=${c.twin_feed.feed_ready} · ` +
    `findings=${c.twin_feed.finding_count} · ` +
    `live_dispatched=false · twin_written=false · remote_fetched=false`
  );
}
