/**
 * Midnight Oil + source attach quality → twin chase feed (pure).
 *
 * Operator vision: unattended deep research with knowledge-dense sources
 * seeds the recursive twin note-taker from goals + source titles so insights
 * and questions inform future workstation prompts.
 *
 * live_execution_authorized / remote_fetched / twin_written /
 * live_dispatched / prompts_injected always false.
 */

import {
  composeMidnightOilSourceAttachQuality,
  type MidnightOilSourceAttachQualityCompose,
  type MidnightOilSourceAttachQualityInput,
} from "./midnightOilSourceAttachQualityCompose";
import {
  composeTwinChaseAnalysisFeed,
  type ChaseFeedFinding,
  type TwinChaseAnalysisFeedCompose,
} from "./twinChaseAnalysisFeedCompose";

export interface MidnightOilSourceAttachQualityTwinInput
  extends MidnightOilSourceAttachQualityInput {
  existing_twin_asset_id?: string | null;
  analysis_excerpt?: string | null;
  mark_for_prompt_context?: boolean;
  twin_findings?: ChaseFeedFinding[] | null;
  /** Outer pack requires both MO+source pack and twin feed (default true). */
  require_both_with_twin?: boolean;
}

export interface MidnightOilSourceAttachQualityTwinCompose {
  operator_id: string;
  session_id: string;
  parent_asset_id: string;
  mo_source: MidnightOilSourceAttachQualityCompose;
  twin_feed: TwinChaseAnalysisFeedCompose;
  pack_ready: boolean;
  live_execution_authorized: false;
  remote_fetched: false;
  pdf_view_authorized: false;
  twin_written: false;
  live_dispatched: false;
  prompts_injected: false;
  store_mutated: false;
  notes: string[];
  authority: "midnight_oil_source_attach_quality_twin_compose_advisory";
}

function requireNonEmpty(value: unknown, name: string): string {
  if (typeof value !== "string" || !value.trim()) {
    throw new Error(`${name} must be a non-empty string`);
  }
  return value.trim();
}

function deriveFindings(
  sources: MidnightOilSourceAttachQualityInput["sources"],
  goals: MidnightOilSourceAttachQualityInput["goals"],
): ChaseFeedFinding[] {
  const findings: ChaseFeedFinding[] = [];
  for (const s of sources) {
    findings.push({
      source_id: `src-${s.source_id}`,
      body: s.title,
      kind: "data",
    });
  }
  for (const g of goals) {
    findings.push({
      source_id: `goal-${g.goal_id}`,
      body: g.title,
      kind: "question",
    });
  }
  return findings;
}

/**
 * Compose MO+source quality pack with twin chase feed.
 * Never launches; never scrapes; never writes twin.
 */
export function composeMidnightOilSourceAttachQualityTwin(
  input: MidnightOilSourceAttachQualityTwinInput,
): MidnightOilSourceAttachQualityTwinCompose {
  if (!input || typeof input !== "object") {
    throw new Error("input must be an object");
  }
  if (typeof input.operator_ack !== "boolean") {
    throw new Error("operator_ack must be an explicit boolean");
  }
  const operator_id = requireNonEmpty(input.operator_id, "operator_id");
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
    "live_execution_authorized=false — midnight oil never launches workers",
    "remote_fetched=false · pdf_view_authorized=false",
    "twin_written=false · prompts_injected=false · live_dispatched=false",
  ];

  const mo_source = composeMidnightOilSourceAttachQuality({
    operator_id: input.operator_id,
    work_minutes: input.work_minutes,
    goals: input.goals,
    usd_per_hour: input.usd_per_hour,
    approved_ceiling_usd: input.approved_ceiling_usd,
    operator_ack: input.operator_ack,
    unattended_ack: input.unattended_ack,
    spend_consent: input.spend_consent,
    brief_dispatch_ready: input.brief_dispatch_ready,
    session_id: input.session_id,
    parent_asset_id: input.parent_asset_id,
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
  notes.push(...mo_source.notes.map((n) => `[mo_source] ${n}`));

  let twin_findings: ChaseFeedFinding[];
  if (input.twin_findings != null) {
    if (!Array.isArray(input.twin_findings)) {
      throw new Error("twin_findings must be an array when set");
    }
    twin_findings = input.twin_findings;
    notes.push(`twin_findings=${twin_findings.length} caller-supplied`);
  } else {
    twin_findings = deriveFindings(input.sources, input.goals);
    notes.push(
      `twin_findings=${twin_findings.length} derived from sources+goals`,
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
      mo_source.pack_ready === true &&
      twin_feed.feed_ready === true &&
      input.operator_ack === true;
  } else {
    pack_ready =
      input.operator_ack === true &&
      (mo_source.pack_ready === true || twin_feed.feed_ready === true);
  }

  if (pack_ready) {
    notes.push(
      "pack_ready=true — MO+sources + twin feed ready; still pure",
    );
  } else {
    notes.push(
      "pack_ready=false — MO+source, twin feed, or operator_ack gate open",
    );
  }

  if (
    mo_source.live_execution_authorized !== false ||
    mo_source.remote_fetched !== false ||
    twin_feed.twin_written !== false ||
    twin_feed.prompts_injected !== false
  ) {
    throw new Error("invariant: honesty flags must remain false");
  }

  notes.push("live_execution_authorized=false");
  notes.push("remote_fetched=false");
  notes.push("pdf_view_authorized=false");
  notes.push("twin_written=false");
  notes.push("live_dispatched=false");
  notes.push("prompts_injected=false");
  notes.push("store_mutated=false");

  return {
    operator_id,
    session_id,
    parent_asset_id,
    mo_source,
    twin_feed,
    pack_ready,
    live_execution_authorized: false,
    remote_fetched: false,
    pdf_view_authorized: false,
    twin_written: false,
    live_dispatched: false,
    prompts_injected: false,
    store_mutated: false,
    notes,
    authority: "midnight_oil_source_attach_quality_twin_compose_advisory",
  };
}

export function formatMidnightOilSourceAttachQualityTwinSummary(
  c: MidnightOilSourceAttachQualityTwinCompose,
): string {
  return (
    `pack_ready=${c.pack_ready} · ` +
    `mo_source_ready=${c.mo_source.pack_ready} · ` +
    `twin_feed_ready=${c.twin_feed.feed_ready} · ` +
    `findings=${c.twin_feed.finding_count} · ` +
    `live_execution_authorized=false · twin_written=false · remote_fetched=false`
  );
}
