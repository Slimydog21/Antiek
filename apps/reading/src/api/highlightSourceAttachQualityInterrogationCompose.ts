/**
 * Highlight → floating DR launch + source attach quality interrogation (pure).
 *
 * Operator vision: from a reading/research highlight, spin up floating deep
 * research and attach arxiv/substack HTML sources under quality/budget gates
 * with workstation interrogation chase — same craft as research workstation
 * because reading and research share the HTML asset path.
 *
 * live_dispatched / merge_executed / remote_fetched / pdf_view_authorized
 * always false.
 */

import {
  composeHighlightDeepResearchLaunch,
  type HighlightDeepResearchLaunchCompose,
  type LaunchPreferredView,
  type SourceFamilyHint,
} from "./highlightDeepResearchLaunchCompose";
import {
  composeSourceAttachQualityInterrogation,
  type SourceAttachQualityInterrogationCompose,
} from "./sourceAttachQualityInterrogationCompose";
import type { HtmlNativeSourceRef } from "./htmlNativeSourceAttachCompose";
import type { CitationRecord } from "./deepResearchSourceCitationPack";
import type { PublicationFamily } from "./sourcePublicationRegistry";
import type {
  ChaseMode,
  ChaseQuestion,
} from "./researchInterrogationSubagentChaseCompose";
import type { SessionRecordItem } from "./workstationSessionInsightRecordCompose";
import type { ModelOption } from "./modelDecisionPromptCompose";
import type {
  BenchTaskBest,
  NotDiamondShadowRec,
} from "./settingsModelDriverTabCompose";

export type { LaunchPreferredView, SourceFamilyHint };

export interface HighlightSourceAttachQualityInterrogationInput {
  parent_asset_id: string;
  highlight: string;
  gated: boolean;
  prompt?: string;
  preferred_view_mode?: LaunchPreferredView;
  would_exceed: boolean | null;
  operator_override?: boolean;
  selected_model_id?: string | null;
  source_families?: SourceFamilyHint[] | null;
  operator_ack: boolean;
  /** Session for source attach / interrogation. */
  session_id: string;
  requested_families: PublicationFamily[];
  sources: HtmlNativeSourceRef[];
  citations?: CitationRecord[] | null;
  derive_citations_from_sources?: boolean;
  quality_overall: number | null;
  quality_floor?: number;
  questions: ChaseQuestion[];
  chase_mode: ChaseMode;
  prior_records?: SessionRecordItem[] | null;
  user_prompt?: string | null;
  models: ModelOption[];
  daily_cap_usd: number | null;
  spent_usd: number | null;
  projected_cost_usd_high?: number | null;
  projected_cost_usd_low?: number | null;
  bench_bests?: BenchTaskBest[] | null;
  focus_task?: string | null;
  nd_shadow?: NotDiamondShadowRec | null;
  require_both?: boolean;
}

export interface HighlightSourceAttachQualityInterrogationCompose {
  parent_asset_id: string;
  session_id: string;
  highlight_launch: HighlightDeepResearchLaunchCompose;
  source_interrogation: SourceAttachQualityInterrogationCompose;
  pack_ready: boolean;
  live_dispatched: false;
  merge_executed: false;
  remote_fetched: false;
  pdf_view_authorized: false;
  record_persisted: false;
  prompts_injected: false;
  store_mutated: false;
  notes: string[];
  authority: "highlight_source_attach_quality_interrogation_compose_advisory";
}

function requireNonEmpty(value: unknown, name: string): string {
  if (typeof value !== "string" || !value.trim()) {
    throw new Error(`${name} must be a non-empty string`);
  }
  return value.trim();
}

/**
 * Compose highlight DR launch + source attach quality interrogation.
 * Never dispatches; never merges; never scrapes.
 */
export function composeHighlightSourceAttachQualityInterrogation(
  input: HighlightSourceAttachQualityInterrogationInput,
): HighlightSourceAttachQualityInterrogationCompose {
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

  const require_both =
    input.require_both === undefined ? true : input.require_both;
  if (typeof require_both !== "boolean") {
    throw new Error("require_both must be boolean when set");
  }

  const notes: string[] = [
    "live_dispatched=false — highlight launch + interrogation pure intent",
    "merge_executed=false — parent asset not mutated",
    "remote_fetched=false — no live arxiv/substack scrape",
    "pdf_view_authorized=false — HTML-native only",
  ];

  // Prefer explicit selected_model_id for both paths; default first model if set.
  let selected_model_id =
    input.selected_model_id != null && input.selected_model_id !== undefined
      ? requireNonEmpty(input.selected_model_id, "selected_model_id")
      : null;
  if (selected_model_id == null && input.models.length > 0) {
    selected_model_id = requireNonEmpty(
      input.models[0].model_id,
      "models[0].model_id",
    );
  }
  if (selected_model_id == null) {
    throw new Error("selected_model_id or models[0] required");
  }

  const user_prompt =
    input.user_prompt != null && input.user_prompt !== undefined
      ? requireNonEmpty(input.user_prompt, "user_prompt")
      : requireNonEmpty(input.highlight, "highlight");

  // Merge source_families hints: prefer requested_families for attach path.
  const launch_families: SourceFamilyHint[] =
    input.source_families != null && input.source_families.length > 0
      ? input.source_families
      : (input.requested_families as SourceFamilyHint[]);

  const highlight_launch = composeHighlightDeepResearchLaunch({
    parent_asset_id,
    highlight: input.highlight,
    gated: input.gated,
    prompt: input.prompt ?? user_prompt,
    preferred_view_mode: input.preferred_view_mode,
    would_exceed: input.would_exceed,
    operator_override: input.operator_override,
    selected_model_id,
    source_families: launch_families,
    operator_ack: input.operator_ack,
  });
  notes.push(...highlight_launch.notes.map((n) => `[highlight_launch] ${n}`));

  const source_interrogation = composeSourceAttachQualityInterrogation({
    session_id,
    parent_asset_id,
    requested_families: input.requested_families,
    sources: input.sources,
    citations: input.citations,
    derive_citations_from_sources: input.derive_citations_from_sources,
    quality_overall: input.quality_overall,
    quality_floor: input.quality_floor,
    would_exceed: input.would_exceed,
    operator_override: input.operator_override,
    questions: input.questions,
    chase_mode: input.chase_mode,
    prior_records: input.prior_records,
    user_prompt,
    selected_model_id,
    models: input.models,
    daily_cap_usd: input.daily_cap_usd,
    spent_usd: input.spent_usd,
    projected_cost_usd_high: input.projected_cost_usd_high,
    projected_cost_usd_low: input.projected_cost_usd_low,
    bench_bests: input.bench_bests,
    focus_task: input.focus_task ?? "deep_research",
    nd_shadow: input.nd_shadow,
    operator_ack: input.operator_ack,
    require_both: true,
  });
  notes.push(
    ...source_interrogation.notes.map((n) => `[source_interrogation] ${n}`),
  );

  let pack_ready = false;
  if (require_both) {
    pack_ready =
      highlight_launch.launch_ready === true &&
      source_interrogation.pack_ready === true &&
      input.operator_ack === true;
  } else {
    pack_ready =
      input.operator_ack === true &&
      (highlight_launch.launch_ready === true ||
        source_interrogation.pack_ready === true);
  }

  if (pack_ready) {
    notes.push(
      "pack_ready=true — highlight launch + source interrogation ready; still pure",
    );
  } else {
    notes.push(
      "pack_ready=false — launch, source interrogation, or operator_ack gate open",
    );
  }

  if (
    highlight_launch.live_dispatched !== false ||
    highlight_launch.merge_executed !== false ||
    source_interrogation.remote_fetched !== false ||
    source_interrogation.live_dispatched !== false ||
    source_interrogation.record_persisted !== false ||
    source_interrogation.prompts_injected !== false
  ) {
    throw new Error("invariant: honesty flags must remain false");
  }

  notes.push("live_dispatched=false");
  notes.push("merge_executed=false");
  notes.push("remote_fetched=false");
  notes.push("pdf_view_authorized=false");
  notes.push("record_persisted=false");
  notes.push("prompts_injected=false");
  notes.push("store_mutated=false");

  return {
    parent_asset_id,
    session_id,
    highlight_launch,
    source_interrogation,
    pack_ready,
    live_dispatched: false,
    merge_executed: false,
    remote_fetched: false,
    pdf_view_authorized: false,
    record_persisted: false,
    prompts_injected: false,
    store_mutated: false,
    notes,
    authority: "highlight_source_attach_quality_interrogation_compose_advisory",
  };
}

export function formatHighlightSourceAttachQualityInterrogationSummary(
  c: HighlightSourceAttachQualityInterrogationCompose,
): string {
  return (
    `pack_ready=${c.pack_ready} · ` +
    `launch_ready=${c.highlight_launch.launch_ready} · ` +
    `source_ready=${c.source_interrogation.pack_ready} · ` +
    `live_dispatched=false · merge_executed=false · remote_fetched=false`
  );
}
