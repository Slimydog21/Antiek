/**
 * HTML-native view session authority + recursive twin MO write pack (pure).
 *
 * Operator vision: every asset viewed as HTML — bind HTML-native session
 * authority onto the recursive twin + MO price-ceiling write pack so reading
 * and research share one HTML surface without PDF primary or live dispatch.
 *
 * pdf_view_authorized / pdf_primary always false.
 * twin_written / charge_executed / live_execution_authorized always false.
 * production_router_verdict always REJECT; live_router_authorized always false.
 */

import {
  composeHtmlNativeViewSessionAuthority,
  type HtmlNativeViewSessionAuthorityCompose,
  type HtmlNativeViewSessionAuthorityInput,
} from "./htmlNativeViewSessionAuthorityCompose";
import {
  composeRecursiveTwinMoPriceCeilingWritePack,
  type RecursiveTwinMoPriceCeilingWritePackCompose,
  type RecursiveTwinMoPriceCeilingWritePackInput,
} from "./recursiveTwinMoPriceCeilingWritePackCompose";

export interface HtmlNativeRecursiveTwinMoWritePackInput {
  html_view: Omit<HtmlNativeViewSessionAuthorityInput, "operator_ack">;
  twin_mo: Omit<RecursiveTwinMoPriceCeilingWritePackInput, "operator_ack">;
  operator_ack: boolean;
  require_both?: boolean;
}

export interface HtmlNativeRecursiveTwinMoWritePackCompose {
  session_id: string;
  parent_asset_id: string;
  week_id: string;
  html_view: HtmlNativeViewSessionAuthorityCompose;
  twin_mo: RecursiveTwinMoPriceCeilingWritePackCompose;
  pack_ready: boolean;
  pdf_view_authorized: false;
  pdf_primary: false;
  twin_written: false;
  prompts_injected: false;
  live_dispatch_authorized: false;
  charge_executed: false;
  live_execution_authorized: false;
  draft_written: false;
  analysis_written: false;
  merge_executed: false;
  secrets_stored: false;
  inventory_mutated: false;
  live_dispatched: false;
  pack_dispatched: false;
  backlog_mutated: false;
  store_mutated: false;
  production_router_verdict: "REJECT";
  live_router_authorized: false;
  purchase_executed: false;
  notes: string[];
  authority: "html_native_recursive_twin_mo_write_pack_compose_advisory";
}

function requireNonEmpty(value: unknown, name: string): string {
  if (typeof value !== "string" || !value.trim()) {
    throw new Error(`${name} must be a non-empty string`);
  }
  return value.trim();
}

/**
 * HTML-native view authority over recursive twin MO write pack.
 * Never authorizes PDF primary; never writes twin; never charges MO.
 */
export function composeHtmlNativeRecursiveTwinMoWritePack(
  input: HtmlNativeRecursiveTwinMoWritePackInput,
): HtmlNativeRecursiveTwinMoWritePackCompose {
  if (!input || typeof input !== "object") {
    throw new Error("input must be an object");
  }
  if (typeof input.operator_ack !== "boolean") {
    throw new Error("operator_ack must be an explicit boolean");
  }
  if (!input.html_view || typeof input.html_view !== "object") {
    throw new Error("html_view must be an object");
  }
  if (!input.twin_mo || typeof input.twin_mo !== "object") {
    throw new Error("twin_mo must be an object");
  }

  const require_both =
    input.require_both === undefined ? true : input.require_both;
  if (typeof require_both !== "boolean") {
    throw new Error("require_both must be boolean when set");
  }

  const notes: string[] = [
    "pdf_view_authorized=false · pdf_primary=false",
    "twin_written=false · charge_executed=false · live_execution_authorized=false",
    "production_router_verdict=REJECT · live_router_authorized=false",
  ];

  const html_view = composeHtmlNativeViewSessionAuthority({
    ...input.html_view,
    operator_ack: input.operator_ack,
  });
  notes.push(...html_view.notes.map((n) => `[html_view] ${n}`));

  const twin_mo = composeRecursiveTwinMoPriceCeilingWritePack({
    ...input.twin_mo,
    operator_ack: input.operator_ack,
  });
  notes.push(...twin_mo.notes.map((n) => `[twin_mo] ${n}`));

  const session_id = requireNonEmpty(html_view.session_id, "session_id");
  const parent_asset_id = requireNonEmpty(
    twin_mo.parent_asset_id,
    "parent_asset_id",
  );
  const week_id = requireNonEmpty(twin_mo.week_id, "week_id");

  // Align HTML view asset with research parent when both name the same surface
  const aligned =
    html_view.session_id === twin_mo.session_id &&
    html_view.asset_id === twin_mo.parent_asset_id;
  if (!aligned) {
    notes.push(
      "session/asset mismatch between html_view and twin_mo — pack_ready blocked",
    );
  }

  let pack_ready = false;
  if (require_both) {
    pack_ready =
      aligned &&
      html_view.pack_ready === true &&
      twin_mo.pack_ready === true &&
      twin_mo.production_router_verdict === "REJECT" &&
      html_view.pdf_view_authorized === false &&
      html_view.pdf_primary === false &&
      input.operator_ack === true;
  } else {
    pack_ready =
      aligned &&
      input.operator_ack === true &&
      twin_mo.production_router_verdict === "REJECT" &&
      html_view.pdf_primary === false &&
      (html_view.pack_ready === true || twin_mo.pack_ready === true);
  }

  if (pack_ready) {
    notes.push(
      "pack_ready=true — HTML-native view + recursive twin MO write pack ready; still pure",
    );
  } else {
    notes.push(
      "pack_ready=false — html_view, twin_mo, alignment, or operator_ack gate open",
    );
  }

  if (
    html_view.pdf_view_authorized !== false ||
    html_view.pdf_primary !== false ||
    html_view.store_mutated !== false ||
    twin_mo.twin_written !== false ||
    twin_mo.charge_executed !== false ||
    twin_mo.live_execution_authorized !== false ||
    twin_mo.production_router_verdict !== "REJECT" ||
    twin_mo.live_router_authorized !== false
  ) {
    throw new Error("invariant: honesty flags must remain false");
  }

  notes.push("pdf_view_authorized=false");
  notes.push("pdf_primary=false");
  notes.push("twin_written=false");
  notes.push("prompts_injected=false");
  notes.push("live_dispatch_authorized=false");
  notes.push("charge_executed=false");
  notes.push("live_execution_authorized=false");
  notes.push("draft_written=false");
  notes.push("analysis_written=false");
  notes.push("merge_executed=false");
  notes.push("secrets_stored=false");
  notes.push("inventory_mutated=false");
  notes.push("live_dispatched=false");
  notes.push("pack_dispatched=false");
  notes.push("backlog_mutated=false");
  notes.push("store_mutated=false");
  notes.push("production_router_verdict=REJECT");
  notes.push("live_router_authorized=false");
  notes.push("purchase_executed=false");

  return {
    session_id,
    parent_asset_id,
    week_id,
    html_view,
    twin_mo,
    pack_ready,
    pdf_view_authorized: false,
    pdf_primary: false,
    twin_written: false,
    prompts_injected: false,
    live_dispatch_authorized: false,
    charge_executed: false,
    live_execution_authorized: false,
    draft_written: false,
    analysis_written: false,
    merge_executed: false,
    secrets_stored: false,
    inventory_mutated: false,
    live_dispatched: false,
    pack_dispatched: false,
    backlog_mutated: false,
    store_mutated: false,
    production_router_verdict: "REJECT",
    live_router_authorized: false,
    purchase_executed: false,
    notes,
    authority: "html_native_recursive_twin_mo_write_pack_compose_advisory",
  };
}

export function formatHtmlNativeRecursiveTwinMoWritePackSummary(
  c: HtmlNativeRecursiveTwinMoWritePackCompose,
): string {
  return (
    `pack_ready=${c.pack_ready} · ` +
    `html_view_ready=${c.html_view.pack_ready} · ` +
    `twin_mo_ready=${c.twin_mo.pack_ready} · ` +
    `verdict=${c.production_router_verdict} · ` +
    `pdf_primary=false · twin_written=false · charge_executed=false`
  );
}
