/**
 * Marketplace HTML+twin session → write twin collective analysis (pure).
 *
 * Operator vision: free-first or paid digital book hosted as HTML, twin
 * note-taker substrate ready, then fold into write draft + collective
 * analysis for reading→writing without PDF or live charge/host.
 *
 * purchase_executed / charge_executed / hosted / pdf_view_authorized always false.
 * twin_written / draft_written / analysis_written / merge_executed always false.
 */

import {
  composeMarketplaceHtmlViewTwinSession,
  type MarketplaceHtmlViewTwinSessionCompose,
  type MarketplaceHtmlViewTwinSessionInput,
} from "./marketplaceHtmlViewTwinSessionCompose";
import {
  composeWriteModeTwinCollectiveAnalysis,
  type WriteModeTwinCollectiveAnalysisCompose,
} from "./writeModeTwinCollectiveAnalysisCompose";
import type { TwinWriteSlice } from "./writeModeTwinDraftMergeCompose";
import type { CompletedChaseSlot } from "./chaseCompletionCollectiveAnalysisCompose";
import type { AnalysisMergeKind } from "./collectiveDeepResearchMerge";
import type { ChaseFeedFinding } from "./twinChaseAnalysisFeedCompose";

export interface MarketplaceHtmlTwinWriteInput
  extends MarketplaceHtmlViewTwinSessionInput {
  draft_id: string;
  analysis_kind?: AnalysisMergeKind;
  twin_slices?: TwinWriteSlice[] | null;
  chase_slots?: CompletedChaseSlot[] | null;
  base_draft_html?: string | null;
  extra_write_findings?: string[] | null;
  require_both_with_write?: boolean;
}

export interface MarketplaceHtmlTwinWriteCompose {
  session_id: string;
  asset_id: string;
  draft_id: string;
  market_twin: MarketplaceHtmlViewTwinSessionCompose;
  write_pack: WriteModeTwinCollectiveAnalysisCompose;
  pack_ready: boolean;
  purchase_executed: false;
  charge_executed: false;
  hosted: false;
  pdf_view_authorized: false;
  twin_written: false;
  draft_written: false;
  analysis_written: false;
  merge_executed: false;
  store_mutated: false;
  live_dispatched: false;
  notes: string[];
  authority: "marketplace_html_twin_write_compose_advisory";
}

function requireNonEmpty(value: unknown, name: string): string {
  if (typeof value !== "string" || !value.trim()) {
    throw new Error(`${name} must be a non-empty string`);
  }
  return value.trim();
}

function findingsToSlicesAndSlots(
  parent_asset_id: string,
  title: string,
  findings: ChaseFeedFinding[] | null | undefined,
): { slices: TwinWriteSlice[]; slots: CompletedChaseSlot[] } {
  const insights: string[] = [title];
  const questions: string[] = [];
  const slots: CompletedChaseSlot[] = [];

  if (findings != null) {
    for (const f of findings) {
      if (f.kind === "question") {
        questions.push(f.body);
        slots.push({
          slot_id: `mk-${f.source_id}`,
          question_id: f.source_id,
          parent_asset_id,
          status: "open",
          findings: [f.body],
          body: f.body,
        });
      } else {
        insights.push(f.body);
        slots.push({
          slot_id: `mk-${f.source_id}`,
          question_id: f.source_id,
          parent_asset_id,
          status: "completed",
          findings: [f.body],
          body: f.body,
        });
      }
    }
  }

  if (questions.length === 0) {
    questions.push(`What does "${title}" claim?`);
  }

  // Ensure ≥2 slots for write pack contract.
  while (slots.length < 2) {
    const i = slots.length;
    slots.push({
      slot_id: `mk-pad-${i}`,
      question_id: `pad-${i}`,
      parent_asset_id,
      status: i === 0 ? "completed" : "open",
      findings: [`padding-${i}: ${title}`],
      body: `padding-${i}: ${title}`,
    });
  }

  return {
    slices: [{ parent_asset_id, insights, questions }],
    slots,
  };
}

/**
 * Compose marketplace HTML+twin session with write twin/analysis pack.
 * Never charges, hosts, PDF-views, or writes assets.
 */
export function composeMarketplaceHtmlTwinWrite(
  input: MarketplaceHtmlTwinWriteInput,
): MarketplaceHtmlTwinWriteCompose {
  if (!input || typeof input !== "object") {
    throw new Error("input must be an object");
  }
  if (typeof input.operator_ack !== "boolean") {
    throw new Error("operator_ack must be an explicit boolean");
  }
  const session_id = requireNonEmpty(input.session_id, "session_id");
  const asset_id = requireNonEmpty(input.asset_id, "asset_id");
  const draft_id = requireNonEmpty(input.draft_id, "draft_id");
  const title = requireNonEmpty(input.title, "title");

  const require_both_with_write =
    input.require_both_with_write === undefined
      ? true
      : input.require_both_with_write;
  if (typeof require_both_with_write !== "boolean") {
    throw new Error("require_both_with_write must be boolean when set");
  }

  const notes: string[] = [
    "purchase_executed=false · charge_executed=false · hosted=false",
    "pdf_view_authorized=false — HTML-native book surface",
    "twin_written=false · draft_written=false · analysis_written=false",
    "merge_executed=false · store_mutated=false · live_dispatched=false",
  ];

  const market_twin = composeMarketplaceHtmlViewTwinSession({
    session_id: input.session_id,
    asset_id: input.asset_id,
    title: input.title,
    account_id: input.account_id,
    free_copy_available: input.free_copy_available,
    free_html_projection_sha: input.free_html_projection_sha,
    purchase_html_projection_sha: input.purchase_html_projection_sha,
    port_requested: input.port_requested,
    purchase_ack: input.purchase_ack,
    list_price_usd: input.list_price_usd,
    approved_spend_usd: input.approved_spend_usd,
    remaining_budget_usd: input.remaining_budget_usd,
    operator_ack: input.operator_ack,
    view_requested: input.view_requested,
    twin_bound: input.twin_bound,
    twin_substrate_ready: input.twin_substrate_ready,
    claimed_format: input.claimed_format,
    twin_findings: input.twin_findings,
    existing_twin_asset_id: input.existing_twin_asset_id,
    mark_for_prompt_context: input.mark_for_prompt_context,
    include_twin_feed: input.include_twin_feed,
  });
  notes.push(...market_twin.notes.map((n) => `[market_twin] ${n}`));

  let twin_slices: TwinWriteSlice[];
  let chase_slots: CompletedChaseSlot[];
  if (input.twin_slices != null && input.chase_slots != null) {
    twin_slices = input.twin_slices;
    chase_slots = input.chase_slots;
    notes.push("twin_slices/chase_slots caller-supplied");
  } else {
    const derived = findingsToSlicesAndSlots(
      asset_id,
      title,
      input.twin_findings,
    );
    twin_slices = input.twin_slices ?? derived.slices;
    chase_slots = input.chase_slots ?? derived.slots;
    notes.push(
      `derived twin_slices=${twin_slices.length} slots=${chase_slots.length} from book twin findings`,
    );
  }

  while (chase_slots.length < 2) {
    const i = chase_slots.length;
    chase_slots = [
      ...chase_slots,
      {
        slot_id: `mk-pad-${i}`,
        question_id: `pad-${i}`,
        parent_asset_id: asset_id,
        status: "open",
        findings: [`padding-${i}`],
        body: `padding-${i}`,
      },
    ];
    notes.push("chase_slots padded to ≥2 for write collective analysis");
  }

  let analysis_kind: AnalysisMergeKind =
    input.analysis_kind ?? "draft_analysis";
  const completed = chase_slots.filter((s) => s.status === "completed");
  const all_completed =
    chase_slots.length >= 2 && completed.length === chase_slots.length;
  if (
    input.analysis_kind == null &&
    all_completed &&
    input.operator_ack === true
  ) {
    analysis_kind = "full_analysis";
  }
  if (analysis_kind === "full_analysis" && !all_completed) {
    analysis_kind = "draft_analysis";
    notes.push(
      "analysis_kind demoted to draft_analysis — full needs all slots completed",
    );
  }
  if (analysis_kind === "full_analysis" && input.operator_ack !== true) {
    analysis_kind = "draft_analysis";
    notes.push(
      "analysis_kind demoted to draft_analysis — full_analysis requires operator_ack",
    );
  }

  const write_pack = composeWriteModeTwinCollectiveAnalysis({
    session_id,
    draft_id,
    parent_asset_id: asset_id,
    twin_slices,
    base_draft_html: input.base_draft_html,
    chase_slots,
    analysis_kind,
    extra_findings: input.extra_write_findings,
    operator_ack: input.operator_ack,
    require_both: true,
  });
  notes.push(...write_pack.notes.map((n) => `[write_pack] ${n}`));

  let pack_ready = false;
  if (require_both_with_write) {
    pack_ready =
      market_twin.session_ready === true &&
      write_pack.pack_ready === true &&
      input.operator_ack === true;
  } else {
    pack_ready =
      input.operator_ack === true &&
      (market_twin.session_ready === true || write_pack.pack_ready === true);
  }

  if (pack_ready) {
    notes.push(
      "pack_ready=true — marketplace HTML+twin + write pack ready; still pure",
    );
  } else {
    notes.push(
      "pack_ready=false — market session, write pack, or operator_ack gate open",
    );
  }

  if (
    market_twin.purchase_executed !== false ||
    market_twin.charge_executed !== false ||
    market_twin.hosted !== false ||
    market_twin.pdf_view_authorized !== false ||
    market_twin.twin_written !== false ||
    write_pack.draft_written !== false ||
    write_pack.analysis_written !== false ||
    write_pack.merge_executed !== false ||
    write_pack.live_dispatched !== false
  ) {
    throw new Error("invariant: honesty flags must remain false");
  }

  notes.push("purchase_executed=false");
  notes.push("charge_executed=false");
  notes.push("hosted=false");
  notes.push("pdf_view_authorized=false");
  notes.push("twin_written=false");
  notes.push("draft_written=false");
  notes.push("analysis_written=false");
  notes.push("merge_executed=false");
  notes.push("store_mutated=false");
  notes.push("live_dispatched=false");

  return {
    session_id,
    asset_id,
    draft_id,
    market_twin,
    write_pack,
    pack_ready,
    purchase_executed: false,
    charge_executed: false,
    hosted: false,
    pdf_view_authorized: false,
    twin_written: false,
    draft_written: false,
    analysis_written: false,
    merge_executed: false,
    store_mutated: false,
    live_dispatched: false,
    notes,
    authority: "marketplace_html_twin_write_compose_advisory",
  };
}

export function formatMarketplaceHtmlTwinWriteSummary(
  c: MarketplaceHtmlTwinWriteCompose,
): string {
  return (
    `pack_ready=${c.pack_ready} · ` +
    `market_session=${c.market_twin.session_ready} · ` +
    `write_ready=${c.write_pack.pack_ready} · ` +
    `purchase_executed=false · pdf_view_authorized=false · ` +
    `draft_written=false · analysis_written=false · charge_executed=false`
  );
}
