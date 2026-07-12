/**
 * Draft-before-full-merge gate + floating fullscreen Antiek-bench weekly ND MO (pure).
 *
 * Operator vision: after floating deep research (fullscreen pack with weekly
 * bench learn + ND multi-select research), create a provisional combined draft
 * before fully merging into the parent asset — without live dispatch, bench
 * mutation, or production NotDiamond routing.
 *
 * draft_written / merge_executed / live_dispatched / pack_dispatched always false.
 * backlog_mutated / store_mutated always false.
 * production_router_verdict always REJECT; live_router_authorized always false.
 */

import {
  composeFloatingDraftBeforeFullMergeGate,
  type FloatingDraftBeforeFullMergeGateCompose,
  type FloatingDraftBeforeFullMergeGateInput,
} from "./floatingDraftBeforeFullMergeGateCompose";
import {
  composeFloatingFullscreenAntiekBenchWeeklyNdMo,
  type FloatingFullscreenAntiekBenchWeeklyNdMoCompose,
  type FloatingFullscreenAntiekBenchWeeklyNdMoInput,
} from "./floatingFullscreenAntiekBenchWeeklyNdMoCompose";

export interface FloatingDraftBeforeFullMergeFullscreenWeeklyNdMoInput {
  /** Draft gate fields without operator_ack (injected from top-level). */
  draft_gate: Omit<FloatingDraftBeforeFullMergeGateInput, "operator_ack">;
  /** Fullscreen + weekly ND pack without operator_ack. */
  fullscreen_pack: Omit<
    FloatingFullscreenAntiekBenchWeeklyNdMoInput,
    "operator_ack"
  >;
  operator_ack: boolean;
  require_both?: boolean;
}

export interface FloatingDraftBeforeFullMergeFullscreenWeeklyNdMoCompose {
  session_id: string;
  parent_asset_id: string;
  week_id: string;
  draft_gate: FloatingDraftBeforeFullMergeGateCompose;
  fullscreen_pack: FloatingFullscreenAntiekBenchWeeklyNdMoCompose;
  pack_ready: boolean;
  draft_written: false;
  merge_executed: false;
  live_dispatched: false;
  pack_dispatched: false;
  backlog_mutated: false;
  store_mutated: false;
  production_router_verdict: "REJECT";
  live_router_authorized: false;
  purchase_executed: false;
  twin_written: false;
  live_execution_authorized: false;
  notes: string[];
  authority: "floating_draft_before_full_merge_fullscreen_weekly_nd_mo_compose_advisory";
}

function requireNonEmpty(value: unknown, name: string): string {
  if (typeof value !== "string" || !value.trim()) {
    throw new Error(`${name} must be a non-empty string`);
  }
  return value.trim();
}

/**
 * Compose draft-before-full-merge with fullscreen weekly ND multi-select pack.
 * Never writes draft; never merges parent; never live-dispatches; ND REJECT.
 */
export function composeFloatingDraftBeforeFullMergeFullscreenWeeklyNdMo(
  input: FloatingDraftBeforeFullMergeFullscreenWeeklyNdMoInput,
): FloatingDraftBeforeFullMergeFullscreenWeeklyNdMoCompose {
  if (!input || typeof input !== "object") {
    throw new Error("input must be an object");
  }
  if (typeof input.operator_ack !== "boolean") {
    throw new Error("operator_ack must be an explicit boolean");
  }
  if (!input.draft_gate || typeof input.draft_gate !== "object") {
    throw new Error("draft_gate must be an object");
  }
  if (!input.fullscreen_pack || typeof input.fullscreen_pack !== "object") {
    throw new Error("fullscreen_pack must be an object");
  }

  const require_both =
    input.require_both === undefined ? true : input.require_both;
  if (typeof require_both !== "boolean") {
    throw new Error("require_both must be boolean when set");
  }

  const notes: string[] = [
    "draft_written=false · merge_executed=false · live_dispatched=false · pack_dispatched=false",
    "backlog_mutated=false · store_mutated=false",
    "production_router_verdict=REJECT · live_router_authorized=false",
    "purchase_executed=false · twin_written=false · live_execution_authorized=false",
  ];

  const draft_gate = composeFloatingDraftBeforeFullMergeGate({
    ...input.draft_gate,
    operator_ack: input.operator_ack,
  });
  notes.push(...draft_gate.notes.map((n) => `[draft_gate] ${n}`));

  const fullscreen_pack = composeFloatingFullscreenAntiekBenchWeeklyNdMo({
    ...input.fullscreen_pack,
    operator_ack: input.operator_ack,
  });
  notes.push(...fullscreen_pack.notes.map((n) => `[fullscreen_pack] ${n}`));

  const session_id = requireNonEmpty(draft_gate.session_id, "session_id");
  const parent_asset_id = requireNonEmpty(
    draft_gate.parent_asset_id,
    "parent_asset_id",
  );
  const week_id = requireNonEmpty(fullscreen_pack.week_id, "week_id");

  // Session/parent alignment when both sides identify the same reading surface
  if (
    fullscreen_pack.session_id !== session_id ||
    fullscreen_pack.parent_asset_id !== parent_asset_id
  ) {
    notes.push(
      "session/parent mismatch between draft_gate and fullscreen_pack — pack_ready blocked",
    );
  }

  let pack_ready = false;
  const aligned =
    fullscreen_pack.session_id === session_id &&
    fullscreen_pack.parent_asset_id === parent_asset_id;

  if (require_both) {
    pack_ready =
      aligned &&
      draft_gate.gate_ready === true &&
      fullscreen_pack.pack_ready === true &&
      fullscreen_pack.production_router_verdict === "REJECT" &&
      input.operator_ack === true;
  } else {
    pack_ready =
      aligned &&
      input.operator_ack === true &&
      fullscreen_pack.production_router_verdict === "REJECT" &&
      (draft_gate.gate_ready === true || fullscreen_pack.pack_ready === true);
  }

  if (pack_ready) {
    notes.push(
      "pack_ready=true — draft-before-merge + fullscreen weekly ND pack ready; still pure",
    );
  } else {
    notes.push(
      "pack_ready=false — draft_gate, fullscreen_pack, alignment, or operator_ack gate open",
    );
  }

  if (
    draft_gate.draft_written !== false ||
    draft_gate.merge_executed !== false ||
    draft_gate.live_dispatched !== false ||
    fullscreen_pack.live_dispatched !== false ||
    fullscreen_pack.merge_executed !== false ||
    fullscreen_pack.pack_dispatched !== false ||
    fullscreen_pack.backlog_mutated !== false ||
    fullscreen_pack.store_mutated !== false ||
    fullscreen_pack.production_router_verdict !== "REJECT" ||
    fullscreen_pack.live_router_authorized !== false ||
    fullscreen_pack.live_execution_authorized !== false
  ) {
    throw new Error("invariant: honesty flags must remain false");
  }

  notes.push("draft_written=false");
  notes.push("merge_executed=false");
  notes.push("live_dispatched=false");
  notes.push("pack_dispatched=false");
  notes.push("backlog_mutated=false");
  notes.push("store_mutated=false");
  notes.push("production_router_verdict=REJECT");
  notes.push("live_router_authorized=false");
  notes.push("purchase_executed=false");
  notes.push("twin_written=false");
  notes.push("live_execution_authorized=false");

  return {
    session_id,
    parent_asset_id,
    week_id,
    draft_gate,
    fullscreen_pack,
    pack_ready,
    draft_written: false,
    merge_executed: false,
    live_dispatched: false,
    pack_dispatched: false,
    backlog_mutated: false,
    store_mutated: false,
    production_router_verdict: "REJECT",
    live_router_authorized: false,
    purchase_executed: false,
    twin_written: false,
    live_execution_authorized: false,
    notes,
    authority:
      "floating_draft_before_full_merge_fullscreen_weekly_nd_mo_compose_advisory",
  };
}

export function formatFloatingDraftBeforeFullMergeFullscreenWeeklyNdMoSummary(
  c: FloatingDraftBeforeFullMergeFullscreenWeeklyNdMoCompose,
): string {
  return (
    `pack_ready=${c.pack_ready} · ` +
    `gate_ready=${c.draft_gate.gate_ready} · ` +
    `stage=${c.draft_gate.stage} · ` +
    `fullscreen_ready=${c.fullscreen_pack.fullscreen.fullscreen_ready} · ` +
    `weekly_nd_ready=${c.fullscreen_pack.weekly_nd.pack_ready} · ` +
    `verdict=${c.production_router_verdict} · ` +
    `draft_written=false · merge_executed=false · live_dispatched=false`
  );
}
