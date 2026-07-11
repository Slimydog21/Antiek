/**
 * Marketplace HTML+twin → workstation interrogation compose (pure).
 *
 * Operator vision: free-first or paid digital book hosted as HTML with twin
 * note substrate, then immediately interrogate the book in the research
 * workstation (chase questions → record → prompt/model decision). Reading
 * and research share the same HTML asset surface.
 *
 * purchase_executed / charge_executed / hosted always false.
 * pdf_view_authorized always false.
 * twin_written / record_persisted / live_dispatched always false.
 * prompts_injected / live_router_authorized always false.
 */

import {
  composeMarketplaceHtmlViewTwinSession,
  type MarketplaceHtmlViewTwinSessionCompose,
  type MarketplaceHtmlViewTwinSessionInput,
} from "./marketplaceHtmlViewTwinSessionCompose";
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

export interface MarketplaceHtmlTwinInterrogationInput
  extends MarketplaceHtmlViewTwinSessionInput {
  /**
   * When true (default), compose interrogation loop when market session_ready.
   * When false, market+twin only.
   */
  include_interrogation?: boolean;
  questions?: ChaseQuestion[] | null;
  chase_mode?: ChaseMode;
  prior_records?: SessionRecordItem[] | null;
  user_prompt?: string | null;
  selected_model_id?: string | null;
  models?: ModelOption[] | null;
  daily_cap_usd?: number | null;
  spent_usd?: number | null;
  projected_cost_usd_high?: number | null;
  projected_cost_usd_low?: number | null;
  would_exceed?: boolean | null;
  operator_override?: boolean;
  source_families?: SourceFamilyHint[] | null;
  bench_bests?: BenchTaskBest[] | null;
  focus_task?: string | null;
  nd_shadow?: NotDiamondShadowRec | null;
}

export interface MarketplaceHtmlTwinInterrogationCompose {
  session_id: string;
  asset_id: string;
  market_twin: MarketplaceHtmlViewTwinSessionCompose;
  interrogation: ResearchWorkstationInterrogationLoopCompose | null;
  /**
   * True when market_twin.session_ready and (interrogation skipped or loop_ready).
   */
  pack_ready: boolean;
  purchase_executed: false;
  charge_executed: false;
  hosted: false;
  pdf_view_authorized: false;
  twin_written: false;
  record_persisted: false;
  live_dispatched: false;
  prompts_injected: false;
  live_router_authorized: false;
  store_mutated: false;
  notes: string[];
  authority: "marketplace_html_twin_interrogation_compose_advisory";
}

function requireNonEmpty(value: unknown, name: string): string {
  if (typeof value !== "string" || !value.trim()) {
    throw new Error(`${name} must be a non-empty string`);
  }
  return value.trim();
}

/**
 * Compose marketplace HTML+twin reading session with optional interrogation.
 * Never purchases, hosts, PDF-views, dispatches, or injects prompts.
 */
export function composeMarketplaceHtmlTwinInterrogation(
  input: MarketplaceHtmlTwinInterrogationInput,
): MarketplaceHtmlTwinInterrogationCompose {
  if (!input || typeof input !== "object") {
    throw new Error("input must be an object");
  }
  if (typeof input.operator_ack !== "boolean") {
    throw new Error("operator_ack must be an explicit boolean");
  }
  const session_id = requireNonEmpty(input.session_id, "session_id");
  const asset_id = requireNonEmpty(input.asset_id, "asset_id");

  const include_interrogation =
    input.include_interrogation === undefined
      ? true
      : input.include_interrogation;
  if (typeof include_interrogation !== "boolean") {
    throw new Error("include_interrogation must be boolean when set");
  }

  const notes: string[] = [
    "purchase_executed=false · charge_executed=false · hosted=false",
    "pdf_view_authorized=false — HTML-native book/research surface",
    "twin_written=false · record_persisted=false · live_dispatched=false",
    "prompts_injected=false · live_router_authorized=false · store_mutated=false",
  ];

  const market_twin = composeMarketplaceHtmlViewTwinSession(input);
  notes.push(...market_twin.notes.map((n) => `[market_twin] ${n}`));

  let interrogation: ResearchWorkstationInterrogationLoopCompose | null = null;
  if (!include_interrogation) {
    notes.push("interrogation skipped — include_interrogation=false");
  } else if (!market_twin.session_ready) {
    notes.push(
      "interrogation deferred — marketplace HTML+twin session not ready",
    );
  } else {
    if (!Array.isArray(input.questions) || input.questions.length === 0) {
      throw new Error(
        "questions must be a non-empty array when include_interrogation=true and market session ready",
      );
    }
    if (!Array.isArray(input.models) || input.models.length === 0) {
      throw new Error(
        "models must be a non-empty array when include_interrogation=true",
      );
    }
    const selected =
      input.selected_model_id != null &&
      String(input.selected_model_id).trim() !== ""
        ? requireNonEmpty(input.selected_model_id, "selected_model_id")
        : requireNonEmpty(input.models[0].model_id, "models[0].model_id");
    const user_prompt =
      input.user_prompt != null && String(input.user_prompt).trim() !== ""
        ? requireNonEmpty(input.user_prompt, "user_prompt")
        : `Interrogate hosted HTML asset: ${requireNonEmpty(input.title, "title")}`;

    // Seed prior records from twin findings when present
    const prior: SessionRecordItem[] = [];
    if (input.prior_records != null) {
      if (!Array.isArray(input.prior_records)) {
        throw new Error("prior_records must be an array when set");
      }
      for (const r of input.prior_records) {
        prior.push(r);
      }
    }
    // Seed title as insight for prompt context
    prior.push({
      record_id: `book-title-${asset_id}`,
      kind: "insight",
      body: requireNonEmpty(input.title, "title"),
      source_ref: asset_id,
    });

    interrogation = composeResearchWorkstationInterrogationLoop({
      session_id,
      parent_asset_id: asset_id,
      questions: input.questions,
      chase_mode: input.chase_mode ?? "swarm_fanout",
      prior_records: prior,
      user_prompt,
      selected_model_id: selected,
      models: input.models,
      daily_cap_usd:
        input.daily_cap_usd === undefined ? null : input.daily_cap_usd,
      spent_usd: input.spent_usd === undefined ? null : input.spent_usd,
      projected_cost_usd_high: input.projected_cost_usd_high,
      projected_cost_usd_low: input.projected_cost_usd_low,
      would_exceed:
        input.would_exceed === undefined ? null : input.would_exceed,
      operator_override: input.operator_override,
      source_families: input.source_families,
      bench_bests: input.bench_bests,
      focus_task: input.focus_task ?? "deep_research",
      nd_shadow: input.nd_shadow,
      operator_ack: input.operator_ack,
      mark_for_twin_record: true,
      mark_for_prompt_context: true,
    });
    notes.push(...interrogation.notes.map((n) => `[interrogation] ${n}`));
  }

  const inter_ok =
    !include_interrogation ||
    !market_twin.session_ready ||
    (interrogation != null && interrogation.loop_ready === true);

  // When include_interrogation but market not ready, pack_ready false
  // When include_interrogation and market ready, need loop_ready
  // When skip interrogation, pack_ready = market session_ready
  let pack_ready = false;
  if (!include_interrogation) {
    pack_ready = market_twin.session_ready === true && input.operator_ack;
  } else if (!market_twin.session_ready) {
    pack_ready = false;
    notes.push("pack_ready=false — market HTML+twin not ready");
  } else {
    pack_ready =
      interrogation != null &&
      interrogation.loop_ready === true &&
      input.operator_ack === true;
  }

  if (pack_ready) {
    notes.push(
      "pack_ready=true — marketplace HTML+twin" +
        (include_interrogation ? "+interrogation" : "") +
        " ready; still pure",
    );
  } else if (include_interrogation && market_twin.session_ready) {
    notes.push(
      "pack_ready=false — interrogation loop or operator_ack gate open",
    );
  }

  if (
    market_twin.purchase_executed !== false ||
    market_twin.charge_executed !== false ||
    market_twin.hosted !== false ||
    market_twin.pdf_view_authorized !== false ||
    market_twin.twin_written !== false ||
    market_twin.record_persisted !== false ||
    market_twin.store_mutated !== false ||
    (interrogation != null &&
      (interrogation.live_dispatched !== false ||
        interrogation.record_persisted !== false ||
        interrogation.prompts_injected !== false ||
        interrogation.live_router_authorized !== false))
  ) {
    throw new Error("invariant: honesty flags must remain false");
  }

  // silence unused inter_ok lint if any - use in notes
  if (!inter_ok && include_interrogation && market_twin.session_ready) {
    notes.push("interrogation_ok=false");
  }

  notes.push("purchase_executed=false");
  notes.push("charge_executed=false");
  notes.push("hosted=false");
  notes.push("pdf_view_authorized=false");
  notes.push("twin_written=false");
  notes.push("record_persisted=false");
  notes.push("live_dispatched=false");
  notes.push("prompts_injected=false");
  notes.push("live_router_authorized=false");
  notes.push("store_mutated=false");

  return {
    session_id,
    asset_id,
    market_twin,
    interrogation,
    pack_ready,
    purchase_executed: false,
    charge_executed: false,
    hosted: false,
    pdf_view_authorized: false,
    twin_written: false,
    record_persisted: false,
    live_dispatched: false,
    prompts_injected: false,
    live_router_authorized: false,
    store_mutated: false,
    notes,
    authority: "marketplace_html_twin_interrogation_compose_advisory",
  };
}

export function formatMarketplaceHtmlTwinInterrogationSummary(
  c: MarketplaceHtmlTwinInterrogationCompose,
): string {
  return (
    `pack_ready=${c.pack_ready} · market_session=${c.market_twin.session_ready} · ` +
    `loop_ready=${c.interrogation?.loop_ready ?? "n/a"} · ` +
    `purchase_executed=false · pdf_view_authorized=false · ` +
    `live_dispatched=false · twin_written=false`
  );
}
