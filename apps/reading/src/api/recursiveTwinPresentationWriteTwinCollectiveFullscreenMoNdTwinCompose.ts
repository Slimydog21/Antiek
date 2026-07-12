/**
 * Recursive twin note-taker presentation residual over write-mode twin
 * collective analysis + fullscreen Midnight Oil unattended draft multiselect
 * model decision ND twin pack (pure).
 *
 * Operator vision: every asset has a twin of insights/questions; present that
 * twin as side-panel / overlay / fullscreen / inline while the workstation
 * holds write collective analysis + fullscreen + MO unattended + draft
 * multiselect + model decision ND twin — without writing the twin, merging
 * live, or live-dispatching.
 *
 * twin_written / prompts_injected / merge_executed always false.
 * draft_written / analysis_written / live_dispatched always false.
 * live_execution_authorized / live_router_authorized always false.
 * production_router_verdict always REJECT.
 */

import {
  composeRecursiveTwinNoteTaker,
  type RecursiveTwinNoteTakerCompose,
  type RecursiveTwinNoteTakerInput,
} from "./recursiveTwinNoteTakerCompose";
import {
  type TwinPresentationSurfaceInput,
  type TwinPresentationViewMode,
} from "./recursiveTwinPresentationCompetitionDrCompose";
import {
  composeWriteModeTwinCollectiveFullscreenMoUnattendedNdTwin,
  type WriteModeTwinCollectiveFullscreenMoUnattendedNdTwinCompose,
  type WriteModeTwinCollectiveFullscreenMoUnattendedNdTwinInput,
} from "./writeModeTwinCollectiveFullscreenMoUnattendedNdTwinCompose";

export interface RecursiveTwinPresentationWriteTwinCollectiveFullscreenMoNdTwinInput {
  twin: Omit<RecursiveTwinNoteTakerInput, "operator_ack">;
  presentation: TwinPresentationSurfaceInput;
  write_pack: Omit<
    WriteModeTwinCollectiveFullscreenMoUnattendedNdTwinInput,
    "operator_ack"
  >;
  operator_ack: boolean;
  require_both?: boolean;
}

export interface RecursiveTwinPresentationWriteTwinCollectiveFullscreenMoNdTwinCompose {
  session_id: string;
  parent_asset_id: string;
  week_id: string;
  asset_id: string;
  title: string;
  account_id: string;
  twin: RecursiveTwinNoteTakerCompose;
  presentation: {
    view_mode: TwinPresentationViewMode;
    open_requested: boolean;
    merge_to_parent_preview: boolean;
    presented_insight_count: number;
    presented_question_count: number;
    presentation_sections: string[];
    presentation_ready: boolean;
  };
  write_pack: WriteModeTwinCollectiveFullscreenMoUnattendedNdTwinCompose;
  session_aligned: boolean;
  parent_aligned: boolean;
  pack_ready: boolean;
  twin_written: false;
  prompts_injected: false;
  merge_executed: false;
  live_dispatch_authorized: false;
  draft_written: false;
  analysis_written: false;
  live_dispatched: false;
  pack_dispatched: false;
  live_execution_authorized: false;
  live_router_authorized: false;
  secrets_stored: false;
  live_meter_read: false;
  remote_index_queried: false;
  backlog_mutated: false;
  store_mutated: false;
  suite_rewritten: false;
  pdf_view_authorized: false;
  pdf_primary: false;
  inventory_mutated: false;
  charge_executed: false;
  record_persisted: false;
  purchase_executed: false;
  hosted: false;
  remote_fetched: false;
  production_router_verdict: "REJECT";
  notes: string[];
  authority: "recursive_twin_presentation_write_twin_collective_fullscreen_mo_nd_twin_compose_advisory";
}

const VIEW_MODES: readonly TwinPresentationViewMode[] = [
  "side_panel",
  "overlay",
  "fullscreen_twin",
  "inline",
] as const;

function requireNonEmpty(value: unknown, name: string): string {
  if (typeof value !== "string" || !value.trim()) {
    throw new Error(`${name} must be a non-empty string`);
  }
  return value.trim();
}

function requireStringList(value: unknown, name: string): string[] {
  if (value == null) return [];
  if (!Array.isArray(value)) {
    throw new Error(`${name} must be an array when set`);
  }
  return value.map((item, i) => requireNonEmpty(item, `${name}[${i}]`));
}

/**
 * Twin note-taker presentation stacked on write twin collective fullscreen MO ND twin.
 * Never writes twin; never merges; never live-dispatches; ND REJECT.
 */
export function composeRecursiveTwinPresentationWriteTwinCollectiveFullscreenMoNdTwin(
  input: RecursiveTwinPresentationWriteTwinCollectiveFullscreenMoNdTwinInput,
): RecursiveTwinPresentationWriteTwinCollectiveFullscreenMoNdTwinCompose {
  if (!input || typeof input !== "object") {
    throw new Error("input must be an object");
  }
  if (typeof input.operator_ack !== "boolean") {
    throw new Error("operator_ack must be an explicit boolean");
  }
  if (!input.twin || typeof input.twin !== "object") {
    throw new Error("twin must be an object");
  }
  if (!input.presentation || typeof input.presentation !== "object") {
    throw new Error("presentation must be an object");
  }
  if (!input.write_pack || typeof input.write_pack !== "object") {
    throw new Error("write_pack must be an object");
  }

  const require_both =
    input.require_both === undefined ? true : input.require_both;
  if (typeof require_both !== "boolean") {
    throw new Error("require_both must be boolean when set");
  }

  const notes: string[] = [
    "twin_written=false · prompts_injected=false · merge_executed=false",
    "draft_written=false · analysis_written=false · live_dispatched=false",
    "live_execution_authorized=false · live_router_authorized=false",
    "production_router_verdict=REJECT",
  ];

  const twin = composeRecursiveTwinNoteTaker({
    ...input.twin,
    operator_ack: input.operator_ack,
  });
  notes.push(...twin.notes.map((n) => `[twin] ${n}`));

  const view_mode = input.presentation.view_mode;
  if (!(VIEW_MODES as readonly string[]).includes(view_mode)) {
    throw new Error(
      "presentation.view_mode must be side_panel|overlay|fullscreen_twin|inline",
    );
  }
  if (typeof input.presentation.open_requested !== "boolean") {
    throw new Error("presentation.open_requested must be an explicit boolean");
  }
  const merge_to_parent_preview =
    input.presentation.merge_to_parent_preview === undefined
      ? false
      : input.presentation.merge_to_parent_preview;
  if (typeof merge_to_parent_preview !== "boolean") {
    throw new Error(
      "presentation.merge_to_parent_preview must be boolean when set",
    );
  }

  const presented_insights = requireStringList(
    input.presentation.presented_insights,
    "presentation.presented_insights",
  );
  const presented_questions = requireStringList(
    input.presentation.presented_questions,
    "presentation.presented_questions",
  );

  const presentation_sections: string[] = [
    ...twin.twin_scaffold_sections,
    `<section data-role="presentation-chrome" data-view-mode="${view_mode}" data-open="${input.presentation.open_requested}" data-merge-preview="${merge_to_parent_preview}"></section>`,
  ];
  for (const insight of presented_insights) {
    presentation_sections.push(
      `<section data-role="presented-insight" data-parent="${twin.parent_asset_id}">${insight}</section>`,
    );
  }
  for (const question of presented_questions) {
    presentation_sections.push(
      `<section data-role="presented-question" data-parent="${twin.parent_asset_id}">${question}</section>`,
    );
  }

  const presentation_ready =
    input.operator_ack === true &&
    twin.twin_propose_ready === true &&
    input.presentation.open_requested === true &&
    twin.twin_written === false &&
    twin.prompts_injected === false;

  if (presentation_ready) {
    notes.push(
      `presentation_ready=true · view_mode=${view_mode} · insights=${presented_insights.length} · questions=${presented_questions.length}`,
    );
  } else {
    notes.push(
      "presentation_ready=false — operator_ack, twin_propose_ready, or open_requested gate open",
    );
  }
  if (merge_to_parent_preview) {
    notes.push(
      "merge_to_parent_preview=true — draft preview only; merge_executed=false",
    );
  }

  const write_pack = composeWriteModeTwinCollectiveFullscreenMoUnattendedNdTwin({
    ...input.write_pack,
    operator_ack: input.operator_ack,
  });
  notes.push(...write_pack.notes.map((n) => `[write_pack] ${n}`));

  const parent_asset_id = requireNonEmpty(
    twin.parent_asset_id,
    "parent_asset_id",
  );
  const session_id = requireNonEmpty(write_pack.session_id, "session_id");
  const week_id = requireNonEmpty(write_pack.week_id, "week_id");
  const asset_id = requireNonEmpty(write_pack.asset_id, "asset_id");
  const title = requireNonEmpty(write_pack.title, "title");
  const account_id = requireNonEmpty(write_pack.account_id, "account_id");

  const session_aligned = write_pack.session_id === session_id;
  const parent_aligned =
    write_pack.parent_asset_id === parent_asset_id ||
    write_pack.asset_id === parent_asset_id;
  if (!parent_aligned) {
    notes.push(
      "parent_asset_id mismatch between twin and write_pack — pack_ready blocked",
    );
  }

  let pack_ready = false;
  if (require_both) {
    pack_ready =
      session_aligned &&
      parent_aligned &&
      presentation_ready === true &&
      twin.twin_propose_ready === true &&
      write_pack.pack_ready === true &&
      twin.twin_written === false &&
      twin.prompts_injected === false &&
      twin.live_dispatch_authorized === false &&
      write_pack.draft_written === false &&
      write_pack.analysis_written === false &&
      write_pack.merge_executed === false &&
      write_pack.live_dispatched === false &&
      write_pack.live_execution_authorized === false &&
      write_pack.live_router_authorized === false &&
      write_pack.secrets_stored === false &&
      write_pack.remote_index_queried === false &&
      write_pack.pdf_primary === false &&
      write_pack.production_router_verdict === "REJECT" &&
      input.operator_ack === true;
  } else {
    pack_ready =
      session_aligned &&
      parent_aligned &&
      input.operator_ack === true &&
      twin.twin_written === false &&
      write_pack.production_router_verdict === "REJECT" &&
      write_pack.pdf_primary === false &&
      (presentation_ready === true || write_pack.pack_ready === true);
  }

  if (pack_ready) {
    notes.push(
      "pack_ready=true — twin presentation + write twin collective fullscreen MO ND twin ready; still pure",
    );
  } else {
    notes.push(
      "pack_ready=false — twin, presentation, write_pack, alignment, or operator_ack gate open",
    );
  }

  if (
    twin.twin_written !== false ||
    twin.prompts_injected !== false ||
    twin.live_dispatch_authorized !== false ||
    write_pack.draft_written !== false ||
    write_pack.analysis_written !== false ||
    write_pack.merge_executed !== false ||
    write_pack.live_dispatched !== false ||
    write_pack.live_execution_authorized !== false ||
    write_pack.live_router_authorized !== false ||
    write_pack.secrets_stored !== false ||
    write_pack.remote_index_queried !== false ||
    write_pack.pdf_primary !== false ||
    write_pack.production_router_verdict !== "REJECT"
  ) {
    throw new Error("invariant: honesty flags must remain false / REJECT");
  }

  notes.push("twin_written=false");
  notes.push("prompts_injected=false");
  notes.push("merge_executed=false");
  notes.push("live_dispatch_authorized=false");
  notes.push("draft_written=false");
  notes.push("analysis_written=false");
  notes.push("live_dispatched=false");
  notes.push("pack_dispatched=false");
  notes.push("live_execution_authorized=false");
  notes.push("live_router_authorized=false");
  notes.push("secrets_stored=false");
  notes.push("live_meter_read=false");
  notes.push("remote_index_queried=false");
  notes.push("backlog_mutated=false");
  notes.push("store_mutated=false");
  notes.push("suite_rewritten=false");
  notes.push("pdf_view_authorized=false");
  notes.push("pdf_primary=false");
  notes.push("inventory_mutated=false");
  notes.push("charge_executed=false");
  notes.push("record_persisted=false");
  notes.push("purchase_executed=false");
  notes.push("hosted=false");
  notes.push("remote_fetched=false");
  notes.push("production_router_verdict=REJECT");

  return {
    session_id,
    parent_asset_id,
    week_id,
    asset_id,
    title,
    account_id,
    twin,
    presentation: {
      view_mode,
      open_requested: input.presentation.open_requested,
      merge_to_parent_preview,
      presented_insight_count: presented_insights.length,
      presented_question_count: presented_questions.length,
      presentation_sections,
      presentation_ready,
    },
    write_pack,
    session_aligned,
    parent_aligned,
    pack_ready,
    twin_written: false,
    prompts_injected: false,
    merge_executed: false,
    live_dispatch_authorized: false,
    draft_written: false,
    analysis_written: false,
    live_dispatched: false,
    pack_dispatched: false,
    live_execution_authorized: false,
    live_router_authorized: false,
    secrets_stored: false,
    live_meter_read: false,
    remote_index_queried: false,
    backlog_mutated: false,
    store_mutated: false,
    suite_rewritten: false,
    pdf_view_authorized: false,
    pdf_primary: false,
    inventory_mutated: false,
    charge_executed: false,
    record_persisted: false,
    purchase_executed: false,
    hosted: false,
    remote_fetched: false,
    production_router_verdict: "REJECT",
    notes,
    authority:
      "recursive_twin_presentation_write_twin_collective_fullscreen_mo_nd_twin_compose_advisory",
  };
}

export function formatRecursiveTwinPresentationWriteTwinCollectiveFullscreenMoNdTwinSummary(
  c: RecursiveTwinPresentationWriteTwinCollectiveFullscreenMoNdTwinCompose,
): string {
  return (
    `pack_ready=${c.pack_ready} · ` +
    `presentation_ready=${c.presentation.presentation_ready} · ` +
    `write_ready=${c.write_pack.pack_ready} · ` +
    `view_mode=${c.presentation.view_mode} · ` +
    `parent_aligned=${c.parent_aligned} · ` +
    `verdict=${c.production_router_verdict} · ` +
    `twin_written=false · merge_executed=false · draft_written=false`
  );
}
