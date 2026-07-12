/**
 * HTML-native view session authority over recursive twin settings fullscreen
 * MO pack (pure).
 *
 * Operator vision: every information asset (books, research output) is viewed
 * as HTML — never PDF-primary — while recursive twin note-taker + settings
 * model inventory + fullscreen MO draft multi honesty remain pure.
 *
 * pdf_view_authorized / pdf_primary always false.
 * twin_written / secrets_stored / charge_executed always false.
 * production_router_verdict always REJECT.
 */

import {
  composeHtmlNativeViewSessionAuthority,
  type HtmlNativeViewSessionAuthorityCompose,
  type HtmlNativeViewSessionAuthorityInput,
} from "./htmlNativeViewSessionAuthorityCompose";
import {
  composeRecursiveTwinSettingsFullscreenMo,
  type RecursiveTwinSettingsFullscreenMoCompose,
  type RecursiveTwinSettingsFullscreenMoInput,
} from "./recursiveTwinSettingsFullscreenMoCompose";

export interface HtmlNativeRecursiveTwinSettingsFullscreenMoInput {
  html_view: Omit<HtmlNativeViewSessionAuthorityInput, "operator_ack">;
  twin_pack: Omit<RecursiveTwinSettingsFullscreenMoInput, "operator_ack">;
  operator_ack: boolean;
  /**
   * When true (default), require html_view.pack_ready AND twin_pack.pack_ready,
   * session/parent alignment, and PDF honesty flags.
   */
  require_both?: boolean;
}

export interface HtmlNativeRecursiveTwinSettingsFullscreenMoCompose {
  session_id: string;
  parent_asset_id: string;
  asset_id: string;
  html_view: HtmlNativeViewSessionAuthorityCompose;
  twin_pack: RecursiveTwinSettingsFullscreenMoCompose;
  pack_ready: boolean;
  pdf_view_authorized: false;
  pdf_primary: false;
  store_mutated: false;
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
  backlog_mutated: false;
  notes: string[];
  authority: "html_native_recursive_twin_settings_fullscreen_mo_compose_advisory";
}

function requireNonEmpty(value: unknown, name: string): string {
  if (typeof value !== "string" || !value.trim()) {
    throw new Error(`${name} must be a non-empty string`);
  }
  return value.trim();
}

/**
 * HTML-native view authority stacked on recursive twin settings fullscreen MO.
 * Never authorizes PDF primary; never writes twins or stores secrets.
 */
export function composeHtmlNativeRecursiveTwinSettingsFullscreenMo(
  input: HtmlNativeRecursiveTwinSettingsFullscreenMoInput,
): HtmlNativeRecursiveTwinSettingsFullscreenMoCompose {
  if (!input || typeof input !== "object") {
    throw new Error("input must be an object");
  }
  if (typeof input.operator_ack !== "boolean") {
    throw new Error("operator_ack must be an explicit boolean");
  }
  if (!input.html_view || typeof input.html_view !== "object") {
    throw new Error("html_view must be an object");
  }
  if (!input.twin_pack || typeof input.twin_pack !== "object") {
    throw new Error("twin_pack must be an object");
  }

  const require_both =
    input.require_both === undefined ? true : input.require_both;
  if (typeof require_both !== "boolean") {
    throw new Error("require_both must be boolean when set");
  }

  const notes: string[] = [
    "pdf_view_authorized=false · pdf_primary=false · store_mutated=false",
    "twin_written=false · secrets_stored=false · charge_executed=false",
    "production_router_verdict=REJECT",
  ];

  const html_view = composeHtmlNativeViewSessionAuthority({
    ...input.html_view,
    operator_ack: input.operator_ack,
  });
  notes.push(...html_view.notes.map((n) => `[html_view] ${n}`));

  const twin_pack = composeRecursiveTwinSettingsFullscreenMo({
    ...input.twin_pack,
    operator_ack: input.operator_ack,
  });
  notes.push(...twin_pack.notes.map((n) => `[twin_pack] ${n}`));

  const session_id = requireNonEmpty(html_view.session_id, "session_id");
  const asset_id = requireNonEmpty(html_view.asset_id, "asset_id");
  const parent_asset_id = requireNonEmpty(
    twin_pack.parent_asset_id,
    "parent_asset_id",
  );

  const session_aligned = twin_pack.session_id === session_id;
  const parent_aligned = twin_pack.parent_asset_id === asset_id;
  if (!session_aligned) {
    notes.push(
      "session_id mismatch between html_view and twin_pack — pack_ready blocked",
    );
  }
  if (!parent_aligned) {
    notes.push(
      "asset_id/parent_asset_id mismatch between html_view and twin_pack — pack_ready blocked",
    );
  }

  let pack_ready = false;
  if (require_both) {
    pack_ready =
      session_aligned &&
      parent_aligned &&
      html_view.pack_ready === true &&
      twin_pack.pack_ready === true &&
      twin_pack.production_router_verdict === "REJECT" &&
      html_view.pdf_view_authorized === false &&
      html_view.pdf_primary === false &&
      twin_pack.twin_written === false &&
      twin_pack.secrets_stored === false &&
      twin_pack.charge_executed === false &&
      input.operator_ack === true;
  } else {
    pack_ready =
      session_aligned &&
      parent_aligned &&
      input.operator_ack === true &&
      twin_pack.production_router_verdict === "REJECT" &&
      html_view.pdf_view_authorized === false &&
      html_view.pdf_primary === false &&
      (html_view.pack_ready === true || twin_pack.pack_ready === true);
  }

  if (pack_ready) {
    notes.push(
      "pack_ready=true — HTML-native view + recursive twin settings fullscreen MO ready; still pure",
    );
  } else {
    notes.push(
      "pack_ready=false — html_view, twin_pack, alignment, or operator_ack gate open",
    );
  }

  if (
    html_view.pdf_view_authorized !== false ||
    html_view.pdf_primary !== false ||
    html_view.store_mutated !== false ||
    twin_pack.twin_written !== false ||
    twin_pack.prompts_injected !== false ||
    twin_pack.secrets_stored !== false ||
    twin_pack.charge_executed !== false ||
    twin_pack.production_router_verdict !== "REJECT"
  ) {
    throw new Error("invariant: honesty flags must remain false");
  }

  notes.push("pdf_view_authorized=false");
  notes.push("pdf_primary=false");
  notes.push("store_mutated=false");
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
  notes.push("backlog_mutated=false");

  return {
    session_id,
    parent_asset_id,
    asset_id,
    html_view,
    twin_pack,
    pack_ready,
    pdf_view_authorized: false,
    pdf_primary: false,
    store_mutated: false,
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
    backlog_mutated: false,
    notes,
    authority:
      "html_native_recursive_twin_settings_fullscreen_mo_compose_advisory",
  };
}

export function formatHtmlNativeRecursiveTwinSettingsFullscreenMoSummary(
  c: HtmlNativeRecursiveTwinSettingsFullscreenMoCompose,
): string {
  return (
    `pack_ready=${c.pack_ready} · ` +
    `html_ready=${c.html_view.pack_ready} · ` +
    `twin_ready=${c.twin_pack.pack_ready} · ` +
    `verdict=${c.production_router_verdict} · ` +
    `pdf_view_authorized=false · pdf_primary=false · twin_written=false`
  );
}
