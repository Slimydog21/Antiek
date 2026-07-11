/**
 * Source attach (arxiv/substack) + quality gate + interrogation loop (pure).
 *
 * Operator vision: highest-quality deep research — attach knowledge-dense
 * HTML sources, enforce quality/budget honesty, then chase questions in the
 * research workstation with those source families on every chase slot.
 *
 * remote_fetched always false.
 * pdf_view_authorized always false.
 * live_dispatch_authorized / live_dispatched always false.
 * record_persisted / prompts_injected always false.
 */

import {
  composeSourcePublicationDrAttachQuality,
  type SourcePublicationDrAttachQualityCompose,
} from "./sourcePublicationDrAttachQualityCompose";
import type { HtmlNativeSourceRef } from "./htmlNativeSourceAttachCompose";
import type { CitationRecord } from "./deepResearchSourceCitationPack";
import type { PublicationFamily } from "./sourcePublicationRegistry";
import {
  composeResearchWorkstationInterrogationLoop,
  type ResearchWorkstationInterrogationLoopCompose,
} from "./researchWorkstationInterrogationLoopCompose";
import type {
  ChaseMode,
  ChaseQuestion,
  SourceFamilyHint,
} from "./researchInterrogationSubagentChaseCompose";
import type { SessionRecordItem } from "./workstationSessionInsightRecordCompose";
import type { ModelOption } from "./modelDecisionPromptCompose";
import type {
  BenchTaskBest,
  NotDiamondShadowRec,
} from "./settingsModelDriverTabCompose";

export interface SourceAttachQualityInterrogationInput {
  session_id: string;
  parent_asset_id: string;
  /** arxiv/substack/etc. families for attach + chase. */
  requested_families: PublicationFamily[];
  sources: HtmlNativeSourceRef[];
  citations?: CitationRecord[] | null;
  derive_citations_from_sources?: boolean;
  quality_overall: number | null;
  quality_floor?: number;
  would_exceed: boolean | null;
  operator_override?: boolean;
  /** Interrogation loop. */
  questions: ChaseQuestion[];
  chase_mode: ChaseMode;
  prior_records?: SessionRecordItem[] | null;
  user_prompt: string;
  selected_model_id: string;
  models: ModelOption[];
  daily_cap_usd: number | null;
  spent_usd: number | null;
  projected_cost_usd_high?: number | null;
  projected_cost_usd_low?: number | null;
  bench_bests?: BenchTaskBest[] | null;
  focus_task?: string | null;
  nd_shadow?: NotDiamondShadowRec | null;
  operator_ack: boolean;
  /**
   * When true (default), require source quality pack_ready AND loop_ready.
   * When false, pack_ready if either path ready (after operator_ack).
   */
  require_both?: boolean;
}

export interface SourceAttachQualityInterrogationCompose {
  session_id: string;
  parent_asset_id: string;
  source_quality: SourcePublicationDrAttachQualityCompose;
  interrogation: ResearchWorkstationInterrogationLoopCompose;
  /**
   * True when source_quality.pack_ready and interrogation.loop_ready
   * (or either when require_both=false) and operator_ack.
   */
  pack_ready: boolean;
  remote_fetched: false;
  pdf_view_authorized: false;
  live_dispatch_authorized: false;
  live_dispatched: false;
  record_persisted: false;
  prompts_injected: false;
  store_mutated: false;
  notes: string[];
  authority: "source_attach_quality_interrogation_compose_advisory";
}

function requireNonEmpty(value: unknown, name: string): string {
  if (typeof value !== "string" || !value.trim()) {
    throw new Error(`${name} must be a non-empty string`);
  }
  return value.trim();
}

/**
 * Map publication families to chase source family hints (same string union).
 */
function familiesToChaseHints(
  families: PublicationFamily[],
): SourceFamilyHint[] {
  return families as SourceFamilyHint[];
}

/**
 * Seed prior records from attached source titles (caller-supplied only).
 */
function seedSourcePriorRecords(
  sources: HtmlNativeSourceRef[],
  prior: SessionRecordItem[] | null | undefined,
): SessionRecordItem[] {
  const records: SessionRecordItem[] = [];
  if (prior != null) {
    if (!Array.isArray(prior)) {
      throw new Error("prior_records must be an array when set");
    }
    for (const r of prior) {
      records.push(r);
    }
  }
  for (const s of sources) {
    records.push({
      record_id: `src-${s.source_id}`,
      kind: "data",
      body: s.title,
      source_ref: s.source_id,
    });
  }
  return records;
}

/**
 * Compose HTML source attach + quality gate + interrogation chase/prompt pack.
 * Never scrapes; never dispatches; never injects prompts.
 */
export function composeSourceAttachQualityInterrogation(
  input: SourceAttachQualityInterrogationInput,
): SourceAttachQualityInterrogationCompose {
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

  const require_both =
    input.require_both === undefined ? true : input.require_both;
  if (typeof require_both !== "boolean") {
    throw new Error("require_both must be boolean when set");
  }

  const notes: string[] = [
    "remote_fetched=false — no live arxiv/substack scrape",
    "pdf_view_authorized=false — HTML-native sources only",
    "live_dispatch_authorized=false · live_dispatched=false",
    "record_persisted=false · prompts_injected=false · store_mutated=false",
  ];

  const source_quality = composeSourcePublicationDrAttachQuality({
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
    operator_ack: input.operator_ack,
  });
  notes.push(...source_quality.notes.map((n) => `[source_quality] ${n}`));

  const prior = seedSourcePriorRecords(input.sources, input.prior_records);
  notes.push(
    `prior_records_seeded=${prior.length} (source titles + caller priors)`,
  );

  const interrogation = composeResearchWorkstationInterrogationLoop({
    session_id,
    parent_asset_id,
    questions: input.questions,
    chase_mode: input.chase_mode,
    prior_records: prior,
    user_prompt: input.user_prompt,
    selected_model_id: input.selected_model_id,
    models: input.models,
    daily_cap_usd: input.daily_cap_usd,
    spent_usd: input.spent_usd,
    projected_cost_usd_high: input.projected_cost_usd_high,
    projected_cost_usd_low: input.projected_cost_usd_low,
    would_exceed: input.would_exceed,
    operator_override: input.operator_override,
    source_families: familiesToChaseHints(input.requested_families),
    bench_bests: input.bench_bests,
    focus_task: input.focus_task ?? "deep_research",
    nd_shadow: input.nd_shadow,
    operator_ack: input.operator_ack,
    mark_for_twin_record: true,
    mark_for_prompt_context: true,
  });
  notes.push(...interrogation.notes.map((n) => `[interrogation] ${n}`));

  let pack_ready = false;
  if (require_both) {
    pack_ready =
      source_quality.pack_ready === true &&
      interrogation.loop_ready === true &&
      input.operator_ack === true;
  } else {
    pack_ready =
      input.operator_ack === true &&
      (source_quality.pack_ready === true ||
        interrogation.loop_ready === true);
  }

  if (pack_ready) {
    notes.push(
      "pack_ready=true — source attach/quality + interrogation ready; still pure",
    );
  } else {
    notes.push(
      "pack_ready=false — source quality, interrogation, or operator_ack gate open",
    );
  }

  if (
    source_quality.remote_fetched !== false ||
    source_quality.pdf_view_authorized !== false ||
    source_quality.live_dispatch_authorized !== false ||
    source_quality.store_mutated !== false ||
    interrogation.live_dispatched !== false ||
    interrogation.record_persisted !== false ||
    interrogation.prompts_injected !== false
  ) {
    throw new Error("invariant: honesty flags must remain false");
  }

  notes.push("remote_fetched=false");
  notes.push("pdf_view_authorized=false");
  notes.push("live_dispatch_authorized=false");
  notes.push("live_dispatched=false");
  notes.push("record_persisted=false");
  notes.push("prompts_injected=false");
  notes.push("store_mutated=false");

  return {
    session_id,
    parent_asset_id,
    source_quality,
    interrogation,
    pack_ready,
    remote_fetched: false,
    pdf_view_authorized: false,
    live_dispatch_authorized: false,
    live_dispatched: false,
    record_persisted: false,
    prompts_injected: false,
    store_mutated: false,
    notes,
    authority: "source_attach_quality_interrogation_compose_advisory",
  };
}

export function formatSourceAttachQualityInterrogationSummary(
  c: SourceAttachQualityInterrogationCompose,
): string {
  return (
    `pack_ready=${c.pack_ready} · ` +
    `source_ready=${c.source_quality.pack_ready} · ` +
    `loop_ready=${c.interrogation.loop_ready} · ` +
    `sources=${c.source_quality.attach.source_count} · ` +
    `chase_slots=${c.interrogation.chase.slot_count} · ` +
    `remote_fetched=false · live_dispatched=false · pdf_view_authorized=false`
  );
}
