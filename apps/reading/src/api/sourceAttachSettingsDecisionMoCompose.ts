/**
 * HTML-native arxiv/substack source attach over settings decision-tree +
 * Midnight Oil unattended fullscreen pack (pure).
 *
 * Operator vision: call knowledge-dense publications into deep research while
 * choosing the model driver with budget bar/projection and MO unattended
 * readiness — every source HTML-native, never remote-fetched in pure layer.
 *
 * remote_fetched / pdf_primary always false.
 * live_router_authorized / live_execution_authorized always false.
 * production_router_verdict always REJECT.
 */

import {
  composeHtmlNativeSourceAttach,
  type HtmlNativeSourceAttachCompose,
  type HtmlNativeSourceAttachInput,
} from "./htmlNativeSourceAttachCompose";
import {
  composeSettingsDecisionMoUnattendedFullscreen,
  type SettingsDecisionMoUnattendedFullscreenCompose,
  type SettingsDecisionMoUnattendedFullscreenInput,
} from "./settingsDecisionMoUnattendedFullscreenCompose";

export interface SourceAttachSettingsDecisionMoInput {
  sources: Omit<HtmlNativeSourceAttachInput, "operator_ack">;
  settings_mo: Omit<
    SettingsDecisionMoUnattendedFullscreenInput,
    "operator_ack"
  >;
  operator_ack: boolean;
  require_both?: boolean;
}

export interface SourceAttachSettingsDecisionMoCompose {
  session_id: string;
  parent_asset_id: string;
  title: string;
  account_id: string;
  week_id: string;
  asset_id: string;
  sources: HtmlNativeSourceAttachCompose;
  settings_mo: SettingsDecisionMoUnattendedFullscreenCompose;
  pack_ready: boolean;
  remote_fetched: false;
  pdf_view_authorized: false;
  pdf_primary: false;
  store_mutated: false;
  live_router_authorized: false;
  secrets_stored: false;
  live_meter_read: false;
  live_execution_authorized: false;
  live_dispatched: false;
  pack_dispatched: false;
  merge_executed: false;
  draft_written: false;
  analysis_written: false;
  purchase_executed: false;
  charge_executed: false;
  hosted: false;
  twin_written: false;
  prompts_injected: false;
  live_dispatch_authorized: false;
  backlog_mutated: false;
  suite_rewritten: false;
  remote_index_queried: false;
  inventory_mutated: false;
  record_persisted: false;
  production_router_verdict: "REJECT";
  notes: string[];
  authority: "source_attach_settings_decision_mo_compose_advisory";
}

function requireNonEmpty(value: unknown, name: string): string {
  if (typeof value !== "string" || !value.trim()) {
    throw new Error(`${name} must be a non-empty string`);
  }
  return value.trim();
}

/**
 * Source attach + settings decision + MO unattended fullscreen.
 * Never remote-fetches; never live-routes; ND REJECT.
 */
export function composeSourceAttachSettingsDecisionMo(
  input: SourceAttachSettingsDecisionMoInput,
): SourceAttachSettingsDecisionMoCompose {
  if (!input || typeof input !== "object") {
    throw new Error("input must be an object");
  }
  if (typeof input.operator_ack !== "boolean") {
    throw new Error("operator_ack must be an explicit boolean");
  }
  if (!input.sources || typeof input.sources !== "object") {
    throw new Error("sources must be an object");
  }
  if (!input.settings_mo || typeof input.settings_mo !== "object") {
    throw new Error("settings_mo must be an object");
  }

  const require_both =
    input.require_both === undefined ? true : input.require_both;
  if (typeof require_both !== "boolean") {
    throw new Error("require_both must be boolean when set");
  }

  const notes: string[] = [
    "remote_fetched=false · pdf_primary=false · store_mutated=false",
    "live_router_authorized=false · live_execution_authorized=false",
    "production_router_verdict=REJECT",
  ];

  const sources = composeHtmlNativeSourceAttach({
    ...input.sources,
    operator_ack: input.operator_ack,
  });
  notes.push(...sources.notes.map((n) => `[sources] ${n}`));

  const settings_mo = composeSettingsDecisionMoUnattendedFullscreen({
    ...input.settings_mo,
    operator_ack: input.operator_ack,
  });
  notes.push(...settings_mo.notes.map((n) => `[settings_mo] ${n}`));

  const session_id = requireNonEmpty(sources.session_id, "session_id");
  const parent_asset_id = requireNonEmpty(
    sources.parent_asset_id,
    "parent_asset_id",
  );
  const title = requireNonEmpty(settings_mo.title, "title");
  const account_id = requireNonEmpty(settings_mo.account_id, "account_id");
  const week_id = requireNonEmpty(settings_mo.week_id, "week_id");
  const asset_id = requireNonEmpty(settings_mo.asset_id, "asset_id");

  const session_aligned = settings_mo.session_id === session_id;
  const parent_aligned = settings_mo.parent_asset_id === parent_asset_id;
  if (!session_aligned) {
    notes.push(
      "session_id mismatch between sources and settings_mo — pack_ready blocked",
    );
  }
  if (!parent_aligned) {
    notes.push(
      "parent_asset_id mismatch between sources and settings_mo — pack_ready blocked",
    );
  }

  let pack_ready = false;
  if (require_both) {
    pack_ready =
      session_aligned &&
      parent_aligned &&
      sources.attach_ready === true &&
      settings_mo.pack_ready === true &&
      sources.remote_fetched === false &&
      sources.pdf_view_authorized === false &&
      sources.store_mutated === false &&
      settings_mo.live_router_authorized === false &&
      settings_mo.live_execution_authorized === false &&
      settings_mo.purchase_executed === false &&
      settings_mo.production_router_verdict === "REJECT" &&
      input.operator_ack === true;
  } else {
    pack_ready =
      session_aligned &&
      parent_aligned &&
      input.operator_ack === true &&
      sources.remote_fetched === false &&
      settings_mo.purchase_executed === false &&
      settings_mo.production_router_verdict === "REJECT" &&
      (sources.attach_ready === true || settings_mo.pack_ready === true);
  }

  if (pack_ready) {
    notes.push(
      "pack_ready=true — source attach + settings decision MO pack ready; still pure",
    );
  } else {
    notes.push(
      "pack_ready=false — sources, settings_mo, alignment, or operator_ack gate open",
    );
  }

  if (
    sources.remote_fetched !== false ||
    sources.pdf_view_authorized !== false ||
    sources.store_mutated !== false ||
    settings_mo.live_router_authorized !== false ||
    settings_mo.live_execution_authorized !== false ||
    settings_mo.purchase_executed !== false ||
    settings_mo.production_router_verdict !== "REJECT"
  ) {
    throw new Error("invariant: honesty flags must remain false / REJECT");
  }

  notes.push("remote_fetched=false");
  notes.push("pdf_view_authorized=false");
  notes.push("pdf_primary=false");
  notes.push("store_mutated=false");
  notes.push("live_router_authorized=false");
  notes.push("secrets_stored=false");
  notes.push("live_meter_read=false");
  notes.push("live_execution_authorized=false");
  notes.push("live_dispatched=false");
  notes.push("pack_dispatched=false");
  notes.push("merge_executed=false");
  notes.push("draft_written=false");
  notes.push("analysis_written=false");
  notes.push("purchase_executed=false");
  notes.push("charge_executed=false");
  notes.push("hosted=false");
  notes.push("twin_written=false");
  notes.push("prompts_injected=false");
  notes.push("live_dispatch_authorized=false");
  notes.push("backlog_mutated=false");
  notes.push("suite_rewritten=false");
  notes.push("remote_index_queried=false");
  notes.push("inventory_mutated=false");
  notes.push("record_persisted=false");
  notes.push("production_router_verdict=REJECT");

  return {
    session_id,
    parent_asset_id,
    title,
    account_id,
    week_id,
    asset_id,
    sources,
    settings_mo,
    pack_ready,
    remote_fetched: false,
    pdf_view_authorized: false,
    pdf_primary: false,
    store_mutated: false,
    live_router_authorized: false,
    secrets_stored: false,
    live_meter_read: false,
    live_execution_authorized: false,
    live_dispatched: false,
    pack_dispatched: false,
    merge_executed: false,
    draft_written: false,
    analysis_written: false,
    purchase_executed: false,
    charge_executed: false,
    hosted: false,
    twin_written: false,
    prompts_injected: false,
    live_dispatch_authorized: false,
    backlog_mutated: false,
    suite_rewritten: false,
    remote_index_queried: false,
    inventory_mutated: false,
    record_persisted: false,
    production_router_verdict: "REJECT",
    notes,
    authority: "source_attach_settings_decision_mo_compose_advisory",
  };
}

export function formatSourceAttachSettingsDecisionMoSummary(
  c: SourceAttachSettingsDecisionMoCompose,
): string {
  return (
    `pack_ready=${c.pack_ready} · ` +
    `attach_ready=${c.sources.attach_ready} · ` +
    `html_ready=${c.sources.html_ready_count} · ` +
    `settings_mo_ready=${c.settings_mo.pack_ready} · ` +
    `verdict=${c.production_router_verdict} · ` +
    `remote_fetched=false · live_router_authorized=false · live_execution_authorized=false`
  );
}
