/**
 * Antiek-bench weekly usage-learn over HTML-native recursive twin settings
 * fullscreen MO pack (pure).
 *
 * Operator vision: surface weekly bench learn (what worked / failed →
 * rewrite proposals) beside the HTML-native research workstation pack so
 * settings / decision-tree consumers can see learn readiness with the full
 * reading+research honesty stack — without mutating bench backlog or store.
 *
 * backlog_mutated / store_mutated always false.
 * pdf_view_authorized / pdf_primary always false.
 * twin_written / secrets_stored / charge_executed always false.
 * production_router_verdict always REJECT.
 */

import {
  composeAntiekBenchWeeklyUsageLearn,
  type AntiekBenchWeeklyUsageLearnCompose,
  type AntiekBenchWeeklyUsageLearnInput,
} from "./antiekBenchWeeklyUsageLearnCompose";
import {
  composeHtmlNativeRecursiveTwinSettingsFullscreenMo,
  type HtmlNativeRecursiveTwinSettingsFullscreenMoCompose,
  type HtmlNativeRecursiveTwinSettingsFullscreenMoInput,
} from "./htmlNativeRecursiveTwinSettingsFullscreenMoCompose";

export interface AntiekBenchWeeklyHtmlNativeRecursiveTwinInput {
  weekly_learn: Omit<AntiekBenchWeeklyUsageLearnInput, "operator_ack">;
  html_pack: Omit<
    HtmlNativeRecursiveTwinSettingsFullscreenMoInput,
    "operator_ack"
  >;
  operator_ack: boolean;
  /**
   * When true (default), require weekly_learn.learn_ready AND
   * html_pack.pack_ready, plus honesty gates.
   */
  require_both?: boolean;
}

export interface AntiekBenchWeeklyHtmlNativeRecursiveTwinCompose {
  week_id: string;
  session_id: string;
  parent_asset_id: string;
  asset_id: string;
  weekly_learn: AntiekBenchWeeklyUsageLearnCompose;
  html_pack: HtmlNativeRecursiveTwinSettingsFullscreenMoCompose;
  pack_ready: boolean;
  learn_ready: boolean;
  backlog_mutated: false;
  store_mutated: false;
  pdf_view_authorized: false;
  pdf_primary: false;
  twin_written: false;
  prompts_injected: false;
  live_dispatch_authorized: false;
  secrets_stored: false;
  inventory_mutated: false;
  live_router_authorized: false;
  live_dispatched: false;
  pack_dispatched: false;
  merge_executed: false;
  live_execution_authorized: false;
  charge_executed: false;
  draft_written: false;
  record_persisted: false;
  remote_index_queried: false;
  analysis_written: false;
  production_router_verdict: "REJECT";
  purchase_executed: false;
  hosted: false;
  suite_rewritten: false;
  notes: string[];
  authority: "antiek_bench_weekly_html_native_recursive_twin_compose_advisory";
}

function requireNonEmpty(value: unknown, name: string): string {
  if (typeof value !== "string" || !value.trim()) {
    throw new Error(`${name} must be a non-empty string`);
  }
  return value.trim();
}

/**
 * Weekly Antiek-bench learn surface stacked on HTML-native recursive twin
 * settings fullscreen MO. Never mutates bench; never PDF-primary; ND REJECT.
 */
export function composeAntiekBenchWeeklyHtmlNativeRecursiveTwin(
  input: AntiekBenchWeeklyHtmlNativeRecursiveTwinInput,
): AntiekBenchWeeklyHtmlNativeRecursiveTwinCompose {
  if (!input || typeof input !== "object") {
    throw new Error("input must be an object");
  }
  if (typeof input.operator_ack !== "boolean") {
    throw new Error("operator_ack must be an explicit boolean");
  }
  if (!input.weekly_learn || typeof input.weekly_learn !== "object") {
    throw new Error("weekly_learn must be an object");
  }
  if (!input.html_pack || typeof input.html_pack !== "object") {
    throw new Error("html_pack must be an object");
  }

  const require_both =
    input.require_both === undefined ? true : input.require_both;
  if (typeof require_both !== "boolean") {
    throw new Error("require_both must be boolean when set");
  }

  const notes: string[] = [
    "backlog_mutated=false · store_mutated=false · suite_rewritten=false",
    "pdf_view_authorized=false · pdf_primary=false",
    "twin_written=false · secrets_stored=false · charge_executed=false",
    "production_router_verdict=REJECT",
  ];

  const weekly_learn = composeAntiekBenchWeeklyUsageLearn({
    ...input.weekly_learn,
    operator_ack: input.operator_ack,
  });
  notes.push(...weekly_learn.notes.map((n) => `[weekly_learn] ${n}`));

  const html_pack = composeHtmlNativeRecursiveTwinSettingsFullscreenMo({
    ...input.html_pack,
    operator_ack: input.operator_ack,
  });
  notes.push(...html_pack.notes.map((n) => `[html_pack] ${n}`));

  const week_id = requireNonEmpty(weekly_learn.week_id, "week_id");
  const session_id = requireNonEmpty(html_pack.session_id, "session_id");
  const asset_id = requireNonEmpty(html_pack.asset_id, "asset_id");
  const parent_asset_id = requireNonEmpty(
    html_pack.parent_asset_id,
    "parent_asset_id",
  );

  let pack_ready = false;
  if (require_both) {
    pack_ready =
      weekly_learn.learn_ready === true &&
      html_pack.pack_ready === true &&
      weekly_learn.backlog_mutated === false &&
      weekly_learn.store_mutated === false &&
      html_pack.production_router_verdict === "REJECT" &&
      html_pack.pdf_view_authorized === false &&
      html_pack.pdf_primary === false &&
      html_pack.twin_written === false &&
      html_pack.secrets_stored === false &&
      html_pack.charge_executed === false &&
      input.operator_ack === true;
  } else {
    pack_ready =
      input.operator_ack === true &&
      weekly_learn.backlog_mutated === false &&
      weekly_learn.store_mutated === false &&
      html_pack.production_router_verdict === "REJECT" &&
      html_pack.pdf_view_authorized === false &&
      html_pack.pdf_primary === false &&
      (weekly_learn.learn_ready === true || html_pack.pack_ready === true);
  }

  if (pack_ready) {
    notes.push(
      "pack_ready=true — weekly bench learn + HTML-native recursive twin settings MO ready; still pure",
    );
  } else {
    notes.push(
      "pack_ready=false — weekly_learn, html_pack, or operator_ack gate open",
    );
  }

  if (
    weekly_learn.backlog_mutated !== false ||
    weekly_learn.store_mutated !== false ||
    html_pack.pdf_view_authorized !== false ||
    html_pack.pdf_primary !== false ||
    html_pack.store_mutated !== false ||
    html_pack.twin_written !== false ||
    html_pack.secrets_stored !== false ||
    html_pack.charge_executed !== false ||
    html_pack.production_router_verdict !== "REJECT"
  ) {
    throw new Error("invariant: honesty flags must remain false");
  }

  notes.push("backlog_mutated=false");
  notes.push("store_mutated=false");
  notes.push("suite_rewritten=false");
  notes.push("pdf_view_authorized=false");
  notes.push("pdf_primary=false");
  notes.push("twin_written=false");
  notes.push("prompts_injected=false");
  notes.push("live_dispatch_authorized=false");
  notes.push("secrets_stored=false");
  notes.push("inventory_mutated=false");
  notes.push("live_router_authorized=false");
  notes.push("live_dispatched=false");
  notes.push("pack_dispatched=false");
  notes.push("merge_executed=false");
  notes.push("live_execution_authorized=false");
  notes.push("charge_executed=false");
  notes.push("draft_written=false");
  notes.push("record_persisted=false");
  notes.push("remote_index_queried=false");
  notes.push("analysis_written=false");
  notes.push("production_router_verdict=REJECT");
  notes.push("purchase_executed=false");
  notes.push("hosted=false");

  return {
    week_id,
    session_id,
    parent_asset_id,
    asset_id,
    weekly_learn,
    html_pack,
    pack_ready,
    learn_ready: weekly_learn.learn_ready,
    backlog_mutated: false,
    store_mutated: false,
    pdf_view_authorized: false,
    pdf_primary: false,
    twin_written: false,
    prompts_injected: false,
    live_dispatch_authorized: false,
    secrets_stored: false,
    inventory_mutated: false,
    live_router_authorized: false,
    live_dispatched: false,
    pack_dispatched: false,
    merge_executed: false,
    live_execution_authorized: false,
    charge_executed: false,
    draft_written: false,
    record_persisted: false,
    remote_index_queried: false,
    analysis_written: false,
    production_router_verdict: "REJECT",
    purchase_executed: false,
    hosted: false,
    suite_rewritten: false,
    notes,
    authority:
      "antiek_bench_weekly_html_native_recursive_twin_compose_advisory",
  };
}

export function formatAntiekBenchWeeklyHtmlNativeRecursiveTwinSummary(
  c: AntiekBenchWeeklyHtmlNativeRecursiveTwinCompose,
): string {
  return (
    `pack_ready=${c.pack_ready} · ` +
    `learn_ready=${c.learn_ready} · ` +
    `html_ready=${c.html_pack.pack_ready} · ` +
    `week=${c.week_id} · ` +
    `proposals=${c.weekly_learn.proposal_count} · ` +
    `verdict=${c.production_router_verdict} · ` +
    `backlog_mutated=false · suite_rewritten=false · pdf_primary=false`
  );
}
