/**
 * Midnight Oil unattended + model decision + HTML-native competition (pure).
 *
 * Operator vision: unattended deep research (“midnight oil”) with time/goals/
 * price ceiling, model selection + budget projection, and competition-quality
 * HTML-native write→twin-search pack — without live workers or live routing.
 *
 * live_execution_authorized always false.
 * live_router_authorized / secrets_stored / live_meter_read always false.
 * pdf_view_authorized / pdf_primary always false.
 * live_dispatch / remote / write honesty flags always false.
 */

import {
  composeMidnightOilUnattendedPackage,
  type MidnightOilUnattendedPackageCompose,
  type MidnightOilUnattendedPackageInput,
} from "./midnightOilUnattendedPackageCompose";
import {
  composeModelDecisionHtmlNativeCompetition,
  type ModelDecisionHtmlNativeCompetitionCompose,
  type ModelDecisionHtmlNativeCompetitionInput,
} from "./modelDecisionHtmlNativeCompetitionCompose";

export interface MoModelDecisionHtmlNativeCompetitionInput {
  mo: MidnightOilUnattendedPackageInput;
  research: Omit<ModelDecisionHtmlNativeCompetitionInput, "operator_ack">;
  operator_ack: boolean;
  /**
   * When true (default), require mo.unattended_package_ready AND
   * research.pack_ready.
   */
  require_both?: boolean;
}

export interface MoModelDecisionHtmlNativeCompetitionCompose {
  mo: MidnightOilUnattendedPackageCompose;
  research: ModelDecisionHtmlNativeCompetitionCompose;
  pack_ready: boolean;
  live_execution_authorized: false;
  live_router_authorized: false;
  secrets_stored: false;
  live_meter_read: false;
  pdf_view_authorized: false;
  pdf_primary: false;
  live_dispatch_authorized: false;
  remote_fetched: false;
  remote_index_queried: false;
  twin_written: false;
  draft_written: false;
  store_mutated: false;
  live_dispatched: false;
  notes: string[];
  authority: "mo_model_decision_html_native_competition_compose_advisory";
}

/**
 * Compose MO unattended package with model decision + HTML competition pack.
 * Never authorizes live execution or live routing.
 */
export function composeMoModelDecisionHtmlNativeCompetition(
  input: MoModelDecisionHtmlNativeCompetitionInput,
): MoModelDecisionHtmlNativeCompetitionCompose {
  if (!input || typeof input !== "object") {
    throw new Error("input must be an object");
  }
  if (typeof input.operator_ack !== "boolean") {
    throw new Error("operator_ack must be an explicit boolean");
  }
  if (!input.mo || typeof input.mo !== "object") {
    throw new Error("mo must be an object");
  }
  if (!input.research || typeof input.research !== "object") {
    throw new Error("research must be an object");
  }

  const require_both =
    input.require_both === undefined ? true : input.require_both;
  if (typeof require_both !== "boolean") {
    throw new Error("require_both must be boolean when set");
  }

  const notes: string[] = [
    "live_execution_authorized=false — midnight oil never launches workers",
    "live_router_authorized=false · secrets_stored=false · live_meter_read=false",
    "pdf_view_authorized=false · pdf_primary=false",
    "live_dispatch_authorized=false · remote_fetched=false · remote_index_queried=false",
    "twin_written=false · draft_written=false · store_mutated=false · live_dispatched=false",
  ];

  const mo = composeMidnightOilUnattendedPackage({
    ...input.mo,
    operator_ack: input.operator_ack,
  });
  notes.push(...mo.notes.map((n) => `[mo] ${n}`));

  const research = composeModelDecisionHtmlNativeCompetition({
    ...input.research,
    operator_ack: input.operator_ack,
  });
  notes.push(...research.notes.map((n) => `[research] ${n}`));

  let pack_ready = false;
  if (require_both) {
    pack_ready =
      mo.unattended_package_ready === true &&
      research.pack_ready === true &&
      input.operator_ack === true;
  } else {
    pack_ready =
      input.operator_ack === true &&
      (mo.unattended_package_ready === true || research.pack_ready === true);
  }

  if (pack_ready) {
    notes.push(
      "pack_ready=true — MO unattended + model decision HTML competition ready; still pure",
    );
  } else {
    notes.push(
      "pack_ready=false — mo, research, or operator_ack gate open",
    );
  }

  if (
    mo.live_execution_authorized !== false ||
    research.live_router_authorized !== false ||
    research.secrets_stored !== false ||
    research.live_meter_read !== false ||
    research.pdf_view_authorized !== false ||
    research.pdf_primary !== false ||
    research.live_dispatch_authorized !== false ||
    research.remote_fetched !== false ||
    research.remote_index_queried !== false ||
    research.twin_written !== false ||
    research.draft_written !== false ||
    research.store_mutated !== false
  ) {
    throw new Error("invariant: honesty flags must remain false");
  }

  notes.push("live_execution_authorized=false");
  notes.push("live_router_authorized=false");
  notes.push("secrets_stored=false");
  notes.push("live_meter_read=false");
  notes.push("pdf_view_authorized=false");
  notes.push("pdf_primary=false");
  notes.push("live_dispatch_authorized=false");
  notes.push("remote_fetched=false");
  notes.push("remote_index_queried=false");
  notes.push("twin_written=false");
  notes.push("draft_written=false");
  notes.push("store_mutated=false");
  notes.push("live_dispatched=false");

  return {
    mo,
    research,
    pack_ready,
    live_execution_authorized: false,
    live_router_authorized: false,
    secrets_stored: false,
    live_meter_read: false,
    pdf_view_authorized: false,
    pdf_primary: false,
    live_dispatch_authorized: false,
    remote_fetched: false,
    remote_index_queried: false,
    twin_written: false,
    draft_written: false,
    store_mutated: false,
    live_dispatched: false,
    notes,
    authority: "mo_model_decision_html_native_competition_compose_advisory",
  };
}

export function formatMoModelDecisionHtmlNativeCompetitionSummary(
  c: MoModelDecisionHtmlNativeCompetitionCompose,
): string {
  return (
    `pack_ready=${c.pack_ready} · ` +
    `mo_ready=${c.mo.unattended_package_ready} · ` +
    `research_ready=${c.research.pack_ready} · ` +
    `model=${c.research.decision.driver.decision.selected_model_id} · ` +
    `live_execution_authorized=false · live_router_authorized=false · ` +
    `pdf_view_authorized=false · twin_written=false`
  );
}
