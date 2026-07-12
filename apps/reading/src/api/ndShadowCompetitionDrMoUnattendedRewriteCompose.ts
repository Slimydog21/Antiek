/**
 * NotDiamond shadow advisory re-affirmation over competition DR + MO unattended + source-attach rewrite pack (pure).
 *
 * Operator vision: investigate NotDiamond as router — platform §16 REJECT as
 * production router; useful only as shadow/advisory beside operator model
 * decision. Re-affirms REJECT while competition DR MO pack is ready.
 *
 * live_router_authorized always false.
 * twin_written / merge_executed / purchase_executed always false.
 * production_router_verdict always REJECT.
 */

import {
  composeNotDiamondShadowAdvisory,
  type NotDiamondShadowAdvisoryCompose,
  type NotDiamondShadowAdvisoryInput,
} from "./notDiamondShadowAdvisoryCompose";
import {
  composeCompetitionDrMoUnattendedSourceAttachRewrite,
  type CompetitionDrMoUnattendedSourceAttachRewriteCompose,
  type CompetitionDrMoUnattendedSourceAttachRewriteInput,
} from "./competitionDrMoUnattendedSourceAttachRewriteCompose";

export interface NdShadowCompetitionDrMoUnattendedRewriteInput {
  nd_shadow: NotDiamondShadowAdvisoryInput;
  competition_pack: Omit<
    CompetitionDrMoUnattendedSourceAttachRewriteInput,
    "operator_ack"
  >;
  operator_ack: boolean;
  /**
   * When true (default), require nd shadow visible-or-kill-switch-honest AND
   * competition_pack.pack_ready.
   */
  require_both?: boolean;
}

export interface NdShadowCompetitionDrMoUnattendedRewriteCompose {
  parent_asset_id: string;
  session_id: string;
  title: string;
  account_id: string;
  week_id: string;
  asset_id: string;
  nd_shadow: NotDiamondShadowAdvisoryCompose;
  competition_pack: CompetitionDrMoUnattendedSourceAttachRewriteCompose;
  pack_ready: boolean;
  live_router_authorized: false;
  twin_written: false;
  prompts_injected: false;
  merge_executed: false;
  live_dispatch_authorized: false;
  remote_fetched: false;
  backlog_mutated: false;
  purchase_executed: false;
  hosted: false;
  pdf_view_authorized: false;
  pdf_primary: false;
  secrets_stored: false;
  live_meter_read: false;
  store_mutated: false;
  suite_rewritten: false;
  live_execution_authorized: false;
  charge_executed: false;
  remote_index_queried: false;
  inventory_mutated: false;
  live_dispatched: false;
  pack_dispatched: false;
  draft_written: false;
  record_persisted: false;
  analysis_written: false;
  production_router_verdict: "REJECT";
  notes: string[];
  authority: "nd_shadow_competition_dr_mo_unattended_rewrite_compose_advisory";
}

function requireNonEmpty(value: unknown, name: string): string {
  if (typeof value !== "string" || !value.trim()) {
    throw new Error(`${name} must be a non-empty string`);
  }
  return value.trim();
}

/**
 * ND shadow REJECT re-affirmation on competition DR MO unattended rewrite pack.
 * Never live-routes; never writes twin; never purchases.
 */
export function composeNdShadowCompetitionDrMoUnattendedRewrite(
  input: NdShadowCompetitionDrMoUnattendedRewriteInput,
): NdShadowCompetitionDrMoUnattendedRewriteCompose {
  if (!input || typeof input !== "object") {
    throw new Error("input must be an object");
  }
  if (typeof input.operator_ack !== "boolean") {
    throw new Error("operator_ack must be an explicit boolean");
  }
  if (!input.nd_shadow || typeof input.nd_shadow !== "object") {
    throw new Error("nd_shadow must be an object");
  }
  if (!input.competition_pack || typeof input.competition_pack !== "object") {
    throw new Error("competition_pack must be an object");
  }

  const require_both =
    input.require_both === undefined ? true : input.require_both;
  if (typeof require_both !== "boolean") {
    throw new Error("require_both must be boolean when set");
  }

  const notes: string[] = [
    "production_router_verdict=REJECT — NotDiamond is not production router (§16)",
    "live_router_authorized=false · twin_written=false · merge_executed=false",
    "purchase_executed=false · remote_fetched=false",
  ];

  const nd_shadow = composeNotDiamondShadowAdvisory(input.nd_shadow);
  notes.push(...nd_shadow.notes.map((n) => `[nd_shadow] ${n}`));

  if (nd_shadow.production_router_verdict !== "REJECT") {
    throw new Error("invariant: production_router_verdict must be REJECT");
  }
  if (nd_shadow.live_router_authorized !== false) {
    throw new Error("invariant: live_router_authorized must be false");
  }

  const competition_pack = composeCompetitionDrMoUnattendedSourceAttachRewrite({
    ...input.competition_pack,
    operator_ack: input.operator_ack,
  });
  notes.push(
    ...competition_pack.notes.map((n) => `[competition_pack] ${n}`),
  );

  const parent_asset_id = requireNonEmpty(
    competition_pack.parent_asset_id,
    "parent_asset_id",
  );
  const session_id = requireNonEmpty(
    competition_pack.session_id,
    "session_id",
  );
  const title = requireNonEmpty(competition_pack.title, "title");
  const account_id = requireNonEmpty(
    competition_pack.account_id,
    "account_id",
  );
  const week_id = requireNonEmpty(competition_pack.week_id, "week_id");
  const asset_id = requireNonEmpty(competition_pack.asset_id, "asset_id");

  const nd_gate =
    nd_shadow.production_router_verdict === "REJECT" &&
    nd_shadow.live_router_authorized === false;

  let pack_ready = false;
  if (require_both) {
    pack_ready =
      nd_gate &&
      competition_pack.pack_ready === true &&
      competition_pack.twin_written === false &&
      competition_pack.merge_executed === false &&
      competition_pack.purchase_executed === false &&
      competition_pack.live_dispatch_authorized === false &&
      competition_pack.production_router_verdict === "REJECT" &&
      input.operator_ack === true;
  } else {
    pack_ready =
      nd_gate &&
      input.operator_ack === true &&
      competition_pack.purchase_executed === false &&
      competition_pack.production_router_verdict === "REJECT" &&
      (competition_pack.pack_ready === true ||
        nd_shadow.shadow_visible === true);
  }

  if (pack_ready) {
    notes.push(
      "pack_ready=true — ND shadow REJECT re-affirmed on competition DR MO unattended rewrite pack; still pure",
    );
  } else {
    notes.push(
      "pack_ready=false — nd_shadow, competition_pack, or operator_ack gate open",
    );
  }

  if (
    nd_shadow.live_router_authorized !== false ||
    nd_shadow.production_router_verdict !== "REJECT" ||
    competition_pack.twin_written !== false ||
    competition_pack.merge_executed !== false ||
    competition_pack.purchase_executed !== false ||
    competition_pack.live_dispatch_authorized !== false ||
    competition_pack.production_router_verdict !== "REJECT"
  ) {
    throw new Error("invariant: honesty flags must remain false / REJECT");
  }

  notes.push("live_router_authorized=false");
  notes.push("twin_written=false");
  notes.push("prompts_injected=false");
  notes.push("merge_executed=false");
  notes.push("live_dispatch_authorized=false");
  notes.push("remote_fetched=false");
  notes.push("backlog_mutated=false");
  notes.push("purchase_executed=false");
  notes.push("hosted=false");
  notes.push("pdf_view_authorized=false");
  notes.push("pdf_primary=false");
  notes.push("secrets_stored=false");
  notes.push("live_meter_read=false");
  notes.push("store_mutated=false");
  notes.push("suite_rewritten=false");
  notes.push("live_execution_authorized=false");
  notes.push("charge_executed=false");
  notes.push("remote_index_queried=false");
  notes.push("inventory_mutated=false");
  notes.push("live_dispatched=false");
  notes.push("pack_dispatched=false");
  notes.push("draft_written=false");
  notes.push("record_persisted=false");
  notes.push("analysis_written=false");
  notes.push("production_router_verdict=REJECT");

  return {
    parent_asset_id,
    session_id,
    title,
    account_id,
    week_id,
    asset_id,
    nd_shadow,
    competition_pack,
    pack_ready,
    live_router_authorized: false,
    twin_written: false,
    prompts_injected: false,
    merge_executed: false,
    live_dispatch_authorized: false,
    remote_fetched: false,
    backlog_mutated: false,
    purchase_executed: false,
    hosted: false,
    pdf_view_authorized: false,
    pdf_primary: false,
    secrets_stored: false,
    live_meter_read: false,
    store_mutated: false,
    suite_rewritten: false,
    live_execution_authorized: false,
    charge_executed: false,
    remote_index_queried: false,
    inventory_mutated: false,
    live_dispatched: false,
    pack_dispatched: false,
    draft_written: false,
    record_persisted: false,
    analysis_written: false,
    production_router_verdict: "REJECT",
    notes,
    authority: "nd_shadow_competition_dr_mo_unattended_rewrite_compose_advisory",
  };
}

export function formatNdShadowCompetitionDrMoUnattendedRewriteSummary(
  c: NdShadowCompetitionDrMoUnattendedRewriteCompose,
): string {
  return (
    `pack_ready=${c.pack_ready} · ` +
    `nd_visible=${c.nd_shadow.shadow_visible} · ` +
    `suggested=${c.nd_shadow.suggested_model_id ?? "null"} · ` +
    `competition_pack_ready=${c.competition_pack.pack_ready} · ` +
    `week=${c.week_id} · ` +
    `verdict=${c.production_router_verdict} · ` +
    `live_router_authorized=false · twin_written=false · purchase_executed=false`
  );
}
