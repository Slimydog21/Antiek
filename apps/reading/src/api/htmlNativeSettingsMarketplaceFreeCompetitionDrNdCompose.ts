/**
 * HTML-native view session authority residual over settings add-model +
 * marketplace free-before-buy + competition DR + NotDiamond shadow REJECT pack (pure).
 *
 * Operator vision: every information asset viewed as HTML — never PDF-primary —
 * while BYOK settings inventory, free-first marketplace, competition DR quality,
 * and NotDiamond REJECT honesty remain pure.
 *
 * pdf_view_authorized / pdf_primary always false.
 * secrets_stored / inventory_mutated / purchase_executed / hosted always false.
 * live_router_authorized always false; production_router_verdict always REJECT.
 */

import {
  composeHtmlNativeViewSessionAuthority,
  type HtmlNativeViewSessionAuthorityCompose,
  type HtmlNativeViewSessionAuthorityInput,
} from "./htmlNativeViewSessionAuthorityCompose";
import {
  composeSettingsAddModelMarketplaceFreeCompetitionDrNd,
  type SettingsAddModelMarketplaceFreeCompetitionDrNdCompose,
  type SettingsAddModelMarketplaceFreeCompetitionDrNdInput,
} from "./settingsAddModelMarketplaceFreeCompetitionDrNdCompose";

export interface HtmlNativeSettingsMarketplaceFreeCompetitionDrNdInput {
  html_view: Omit<HtmlNativeViewSessionAuthorityInput, "operator_ack">;
  settings_pack: Omit<
    SettingsAddModelMarketplaceFreeCompetitionDrNdInput,
    "operator_ack"
  >;
  operator_ack: boolean;
  require_both?: boolean;
}

export interface HtmlNativeSettingsMarketplaceFreeCompetitionDrNdCompose {
  session_id: string;
  parent_asset_id: string;
  asset_id: string;
  title: string;
  account_id: string;
  week_id: string;
  html_view: HtmlNativeViewSessionAuthorityCompose;
  settings_pack: SettingsAddModelMarketplaceFreeCompetitionDrNdCompose;
  session_aligned: boolean;
  parent_aligned: boolean;
  pack_ready: boolean;
  pdf_view_authorized: false;
  pdf_primary: false;
  store_mutated: false;
  secrets_stored: false;
  inventory_mutated: false;
  purchase_executed: false;
  hosted: false;
  live_dispatch_authorized: false;
  remote_fetched: false;
  backlog_mutated: false;
  suite_rewritten: false;
  twin_written: false;
  prompts_injected: false;
  merge_executed: false;
  draft_written: false;
  analysis_written: false;
  live_dispatched: false;
  pack_dispatched: false;
  live_execution_authorized: false;
  live_router_authorized: false;
  live_meter_read: false;
  remote_index_queried: false;
  charge_executed: false;
  record_persisted: false;
  production_router_verdict: "REJECT";
  notes: string[];
  authority: "html_native_settings_marketplace_free_competition_dr_nd_compose_advisory";
}

function requireNonEmpty(value: unknown, name: string): string {
  if (typeof value !== "string" || !value.trim()) {
    throw new Error(`${name} must be a non-empty string`);
  }
  return value.trim();
}

/**
 * HTML-native view authority stacked on settings marketplace free competition DR ND pack.
 * Never authorizes PDF primary; never purchases/hosts; ND REJECT.
 */
export function composeHtmlNativeSettingsMarketplaceFreeCompetitionDrNd(
  input: HtmlNativeSettingsMarketplaceFreeCompetitionDrNdInput,
): HtmlNativeSettingsMarketplaceFreeCompetitionDrNdCompose {
  if (!input || typeof input !== "object") {
    throw new Error("input must be an object");
  }
  if (typeof input.operator_ack !== "boolean") {
    throw new Error("operator_ack must be an explicit boolean");
  }
  if (!input.html_view || typeof input.html_view !== "object") {
    throw new Error("html_view must be an object");
  }
  if (!input.settings_pack || typeof input.settings_pack !== "object") {
    throw new Error("settings_pack must be an object");
  }

  const require_both =
    input.require_both === undefined ? true : input.require_both;
  if (typeof require_both !== "boolean") {
    throw new Error("require_both must be boolean when set");
  }

  const notes: string[] = [
    "pdf_view_authorized=false · pdf_primary=false · store_mutated=false",
    "secrets_stored=false · inventory_mutated=false · purchase_executed=false · hosted=false",
    "production_router_verdict=REJECT",
  ];

  const html_view = composeHtmlNativeViewSessionAuthority({
    ...input.html_view,
    operator_ack: input.operator_ack,
  });
  notes.push(...html_view.notes.map((n) => `[html_view] ${n}`));

  const settings_pack = composeSettingsAddModelMarketplaceFreeCompetitionDrNd({
    ...input.settings_pack,
    operator_ack: input.operator_ack,
  });
  notes.push(...settings_pack.notes.map((n) => `[settings_pack] ${n}`));

  const session_id = requireNonEmpty(html_view.session_id, "session_id");
  const asset_id = requireNonEmpty(html_view.asset_id, "asset_id");
  const parent_asset_id = requireNonEmpty(
    settings_pack.parent_asset_id,
    "parent_asset_id",
  );
  const title = requireNonEmpty(settings_pack.title, "title");
  const account_id = requireNonEmpty(settings_pack.account_id, "account_id");
  const week_id = requireNonEmpty(settings_pack.week_id, "week_id");

  const session_aligned = settings_pack.session_id === session_id;
  const parent_aligned =
    settings_pack.parent_asset_id === asset_id ||
    settings_pack.asset_id === asset_id;
  if (!session_aligned) {
    notes.push(
      `session_aligned=false — html_view.session_id=${session_id} settings_pack.session_id=${settings_pack.session_id}`,
    );
  } else {
    notes.push("session_aligned=true");
  }
  if (!parent_aligned) {
    notes.push(
      `parent_aligned=false — html_view.asset_id=${asset_id} settings_pack.parent=${parent_asset_id} asset=${settings_pack.asset_id}`,
    );
  } else {
    notes.push("parent_aligned=true");
  }

  let pack_ready = false;
  if (require_both) {
    pack_ready =
      session_aligned === true &&
      parent_aligned === true &&
      html_view.pack_ready === true &&
      settings_pack.pack_ready === true &&
      settings_pack.production_router_verdict === "REJECT" &&
      html_view.pdf_view_authorized === false &&
      html_view.pdf_primary === false &&
      html_view.store_mutated === false &&
      settings_pack.pdf_view_authorized === false &&
      settings_pack.pdf_primary === false &&
      settings_pack.purchase_executed === false &&
      settings_pack.hosted === false &&
      settings_pack.secrets_stored === false &&
      settings_pack.inventory_mutated === false &&
      settings_pack.live_dispatch_authorized === false &&
      settings_pack.remote_fetched === false &&
      settings_pack.live_router_authorized === false &&
      settings_pack.twin_written === false &&
      settings_pack.merge_executed === false &&
      settings_pack.draft_written === false &&
      settings_pack.remote_index_queried === false &&
      settings_pack.suite_rewritten === false &&
      settings_pack.charge_executed === false &&
      input.operator_ack === true;
  } else {
    pack_ready =
      session_aligned === true &&
      parent_aligned === true &&
      input.operator_ack === true &&
      settings_pack.production_router_verdict === "REJECT" &&
      html_view.pdf_view_authorized === false &&
      html_view.pdf_primary === false &&
      settings_pack.purchase_executed === false &&
      settings_pack.hosted === false &&
      (html_view.pack_ready === true || settings_pack.pack_ready === true);
  }

  if (pack_ready) {
    notes.push(
      "pack_ready=true — HTML-native view + settings marketplace free competition DR ND ready; still pure",
    );
  } else {
    notes.push(
      "pack_ready=false — html_view, settings_pack, alignment, or operator_ack gate open",
    );
  }

  if (
    html_view.pdf_view_authorized !== false ||
    html_view.pdf_primary !== false ||
    html_view.store_mutated !== false ||
    settings_pack.pdf_view_authorized !== false ||
    settings_pack.pdf_primary !== false ||
    settings_pack.purchase_executed !== false ||
    settings_pack.hosted !== false ||
    settings_pack.secrets_stored !== false ||
    settings_pack.inventory_mutated !== false ||
    settings_pack.live_dispatch_authorized !== false ||
    settings_pack.remote_fetched !== false ||
    settings_pack.live_router_authorized !== false ||
    settings_pack.twin_written !== false ||
    settings_pack.merge_executed !== false ||
    settings_pack.draft_written !== false ||
    settings_pack.remote_index_queried !== false ||
    settings_pack.suite_rewritten !== false ||
    settings_pack.charge_executed !== false ||
    settings_pack.production_router_verdict !== "REJECT"
  ) {
    throw new Error("invariant: honesty flags must remain false / REJECT");
  }

  notes.push("pdf_view_authorized=false");
  notes.push("pdf_primary=false");
  notes.push("store_mutated=false");
  notes.push("secrets_stored=false");
  notes.push("inventory_mutated=false");
  notes.push("purchase_executed=false");
  notes.push("hosted=false");
  notes.push("live_dispatch_authorized=false");
  notes.push("remote_fetched=false");
  notes.push("backlog_mutated=false");
  notes.push("suite_rewritten=false");
  notes.push("twin_written=false");
  notes.push("prompts_injected=false");
  notes.push("merge_executed=false");
  notes.push("draft_written=false");
  notes.push("analysis_written=false");
  notes.push("live_dispatched=false");
  notes.push("pack_dispatched=false");
  notes.push("live_execution_authorized=false");
  notes.push("live_router_authorized=false");
  notes.push("live_meter_read=false");
  notes.push("remote_index_queried=false");
  notes.push("charge_executed=false");
  notes.push("record_persisted=false");
  notes.push("production_router_verdict=REJECT");

  return {
    session_id,
    parent_asset_id,
    asset_id,
    title,
    account_id,
    week_id,
    html_view,
    settings_pack,
    session_aligned,
    parent_aligned,
    pack_ready,
    pdf_view_authorized: false,
    pdf_primary: false,
    store_mutated: false,
    secrets_stored: false,
    inventory_mutated: false,
    purchase_executed: false,
    hosted: false,
    live_dispatch_authorized: false,
    remote_fetched: false,
    backlog_mutated: false,
    suite_rewritten: false,
    twin_written: false,
    prompts_injected: false,
    merge_executed: false,
    draft_written: false,
    analysis_written: false,
    live_dispatched: false,
    pack_dispatched: false,
    live_execution_authorized: false,
    live_router_authorized: false,
    live_meter_read: false,
    remote_index_queried: false,
    charge_executed: false,
    record_persisted: false,
    production_router_verdict: "REJECT",
    notes,
    authority:
      "html_native_settings_marketplace_free_competition_dr_nd_compose_advisory",
  };
}

export function formatHtmlNativeSettingsMarketplaceFreeCompetitionDrNdSummary(
  c: HtmlNativeSettingsMarketplaceFreeCompetitionDrNdCompose,
): string {
  return (
    `pack_ready=${c.pack_ready} · ` +
    `html_ready=${c.html_view.pack_ready} · ` +
    `settings_ready=${c.settings_pack.pack_ready} · ` +
    `session_aligned=${c.session_aligned} · ` +
    `parent_aligned=${c.parent_aligned} · ` +
    `verdict=${c.production_router_verdict} · ` +
    `pdf_primary=false · purchase_executed=false · secrets_stored=false`
  );
}
