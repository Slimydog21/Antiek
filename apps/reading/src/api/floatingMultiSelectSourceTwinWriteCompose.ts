/**
 * Floating multi-select + sources + twin → write collective analysis (pure).
 *
 * Operator vision: multi-select cohesive deep research with knowledge-dense
 * sources feeds the recursive twin note-taker, then folds into write draft +
 * collective analysis — HTML-native research→write path without live write.
 *
 * live_dispatched / twin_written / draft_written / analysis_written /
 * merge_executed / remote_fetched always false.
 */

import {
  composeFloatingMultiSelectSourceAttachQualityTwin,
  type FloatingMultiSelectSourceAttachQualityTwinCompose,
  type FloatingMultiSelectSourceAttachQualityTwinInput,
} from "./floatingMultiSelectSourceAttachQualityTwinCompose";
import {
  composeWriteModeTwinCollectiveAnalysis,
  type WriteModeTwinCollectiveAnalysisCompose,
} from "./writeModeTwinCollectiveAnalysisCompose";
import type { TwinWriteSlice } from "./writeModeTwinDraftMergeCompose";
import type { CompletedChaseSlot } from "./chaseCompletionCollectiveAnalysisCompose";
import type { AnalysisMergeKind } from "./collectiveDeepResearchMerge";

export interface FloatingMultiSelectSourceTwinWriteInput
  extends FloatingMultiSelectSourceAttachQualityTwinInput {
  draft_id: string;
  analysis_kind?: AnalysisMergeKind;
  twin_slices?: TwinWriteSlice[] | null;
  chase_slots?: CompletedChaseSlot[] | null;
  base_draft_html?: string | null;
  extra_write_findings?: string[] | null;
  /** Outer pack requires multi-twin pack_ready AND write pack_ready (default true). */
  require_both_with_write?: boolean;
}

export interface FloatingMultiSelectSourceTwinWriteCompose {
  session_id: string;
  draft_id: string;
  parent_asset_id: string;
  multi_twin: FloatingMultiSelectSourceAttachQualityTwinCompose;
  write_pack: WriteModeTwinCollectiveAnalysisCompose;
  pack_ready: boolean;
  live_dispatched: false;
  pack_dispatched: false;
  twin_written: false;
  draft_written: false;
  analysis_written: false;
  merge_executed: false;
  remote_fetched: false;
  store_mutated: false;
  notes: string[];
  authority: "floating_multi_select_source_twin_write_compose_advisory";
}

function requireNonEmpty(value: unknown, name: string): string {
  if (typeof value !== "string" || !value.trim()) {
    throw new Error(`${name} must be a non-empty string`);
  }
  return value.trim();
}

/**
 * Derive write twin slices + chase slots from multi-select members + sources.
 */
function deriveSlicesAndSlots(
  parent_asset_id: string,
  input: FloatingMultiSelectSourceTwinWriteInput,
): { slices: TwinWriteSlice[]; slots: CompletedChaseSlot[] } {
  const insights: string[] = [];
  const questions: string[] = [];
  const slots: CompletedChaseSlot[] = [];

  for (const s of input.sources) {
    insights.push(s.title);
  }

  for (const m of input.members) {
    if (!input.selected_instance_ids.includes(m.instance_id)) continue;
    const body =
      m.highlight?.trim() ||
      m.prior_prompt?.trim() ||
      m.findings?.[0]?.trim() ||
      m.instance_id;
    const completed =
      m.status === "completed" || (m.findings != null && m.findings.length > 0);
    if (completed) {
      insights.push(body);
      slots.push({
        slot_id: `ms-${m.instance_id}`,
        question_id: m.instance_id,
        parent_asset_id,
        status: "completed",
        findings: m.findings?.length ? m.findings : [body],
        body,
      });
    } else if (m.status === "closed") {
      questions.push(body);
      slots.push({
        slot_id: `ms-${m.instance_id}`,
        question_id: m.instance_id,
        parent_asset_id,
        status: "closed",
        findings: [body],
        body,
      });
    } else {
      questions.push(body);
      slots.push({
        slot_id: `ms-${m.instance_id}`,
        question_id: m.instance_id,
        parent_asset_id,
        status: "open",
        findings: [body],
        body,
      });
    }
  }

  if (input.cohesive_prompt.trim()) {
    questions.push(input.cohesive_prompt.trim());
  }

  if (insights.length === 0 && questions.length === 0) {
    questions.push(`Open multi-select write for ${parent_asset_id}`);
  }

  const slices: TwinWriteSlice[] = [
    { parent_asset_id, insights, questions },
  ];
  return { slices, slots };
}

/**
 * Compose multi-select+sources+twin with write twin draft + collective analysis.
 * Never writes assets; never dispatches.
 */
export function composeFloatingMultiSelectSourceTwinWrite(
  input: FloatingMultiSelectSourceTwinWriteInput,
): FloatingMultiSelectSourceTwinWriteCompose {
  if (!input || typeof input !== "object") {
    throw new Error("input must be an object");
  }
  if (typeof input.operator_ack !== "boolean") {
    throw new Error("operator_ack must be an explicit boolean");
  }
  const session_id = requireNonEmpty(input.session_id, "session_id");
  const draft_id = requireNonEmpty(input.draft_id, "draft_id");
  const parent_asset_id = requireNonEmpty(
    input.parent_asset_id,
    "parent_asset_id",
  );

  const require_both_with_write =
    input.require_both_with_write === undefined
      ? true
      : input.require_both_with_write;
  if (typeof require_both_with_write !== "boolean") {
    throw new Error("require_both_with_write must be boolean when set");
  }

  const notes: string[] = [
    "live_dispatched=false · pack_dispatched=false",
    "twin_written=false · draft_written=false · analysis_written=false",
    "merge_executed=false · remote_fetched=false · store_mutated=false",
  ];

  const multi_twin = composeFloatingMultiSelectSourceAttachQualityTwin({
    session_id: input.session_id,
    parent_asset_id: input.parent_asset_id,
    members: input.members,
    selected_instance_ids: input.selected_instance_ids,
    pack_mode: input.pack_mode,
    cohesive_prompt: input.cohesive_prompt,
    operator_ack: input.operator_ack,
    extra_context: input.extra_context,
    analysis_kind: input.analysis_kind,
    extra_findings: input.extra_findings,
    requested_families: input.requested_families,
    sources: input.sources,
    citations: input.citations,
    derive_citations_from_sources: input.derive_citations_from_sources,
    quality_overall: input.quality_overall,
    quality_floor: input.quality_floor,
    would_exceed: input.would_exceed,
    operator_override: input.operator_override,
    require_both: input.require_both,
    existing_twin_asset_id: input.existing_twin_asset_id,
    analysis_excerpt: input.analysis_excerpt,
    mark_for_prompt_context: input.mark_for_prompt_context,
    twin_findings: input.twin_findings,
    require_both_with_twin: input.require_both_with_twin,
  });
  notes.push(...multi_twin.notes.map((n) => `[multi_twin] ${n}`));

  let twin_slices: TwinWriteSlice[];
  let chase_slots: CompletedChaseSlot[];
  if (input.twin_slices != null && input.chase_slots != null) {
    twin_slices = input.twin_slices;
    chase_slots = input.chase_slots;
    notes.push("twin_slices/chase_slots caller-supplied");
  } else {
    const derived = deriveSlicesAndSlots(parent_asset_id, input);
    twin_slices = input.twin_slices ?? derived.slices;
    chase_slots = input.chase_slots ?? derived.slots;
    notes.push(
      `derived twin_slices=${twin_slices.length} slots=${chase_slots.length} from multi-select+sources`,
    );
  }

  // Ensure ≥2 chase slots for write collective analysis contract.
  if (chase_slots.length < 2) {
    while (chase_slots.length < 2) {
      const i = chase_slots.length;
      chase_slots = [
        ...chase_slots,
        {
          slot_id: `ms-pad-${i}`,
          question_id: `pad-${i}`,
          parent_asset_id,
          status: "open",
          findings: [`padding-slot-${i}`],
          body: `padding-slot-${i}`,
        },
      ];
    }
    notes.push("chase_slots padded to ≥2 for write collective analysis contract");
  }

  // Ensure twin slice has content.
  if (twin_slices.length > 0) {
    const s0 = twin_slices[0];
    if (s0.insights.length === 0 && s0.questions.length === 0) {
      twin_slices = [
        { ...s0, questions: [`Open: ${parent_asset_id}`] },
        ...twin_slices.slice(1),
      ];
      notes.push("twin_slices padded with placeholder question");
    }
  }

  let analysis_kind: AnalysisMergeKind =
    input.analysis_kind ?? "draft_analysis";
  const completed = chase_slots.filter((s) => s.status === "completed");
  const all_completed =
    chase_slots.length >= 2 && completed.length === chase_slots.length;
  if (
    input.analysis_kind == null &&
    all_completed &&
    input.operator_ack === true
  ) {
    analysis_kind = "full_analysis";
  }
  if (analysis_kind === "full_analysis" && !all_completed) {
    analysis_kind = "draft_analysis";
    notes.push(
      "analysis_kind demoted to draft_analysis — full_analysis needs all slots completed",
    );
  }
  if (analysis_kind === "full_analysis" && input.operator_ack !== true) {
    analysis_kind = "draft_analysis";
    notes.push(
      "analysis_kind demoted to draft_analysis — full_analysis requires operator_ack",
    );
  }

  const write_pack = composeWriteModeTwinCollectiveAnalysis({
    session_id,
    draft_id,
    parent_asset_id,
    twin_slices,
    base_draft_html: input.base_draft_html,
    chase_slots,
    analysis_kind,
    extra_findings: input.extra_write_findings ?? input.extra_findings,
    operator_ack: input.operator_ack,
    require_both: true,
  });
  notes.push(...write_pack.notes.map((n) => `[write_pack] ${n}`));

  let pack_ready = false;
  if (require_both_with_write) {
    pack_ready =
      multi_twin.pack_ready === true &&
      write_pack.pack_ready === true &&
      input.operator_ack === true;
  } else {
    pack_ready =
      input.operator_ack === true &&
      (multi_twin.pack_ready === true || write_pack.pack_ready === true);
  }

  if (pack_ready) {
    notes.push(
      "pack_ready=true — multi-select+twin + write pack ready; still pure",
    );
  } else {
    notes.push(
      "pack_ready=false — multi_twin, write pack, or operator_ack gate open",
    );
  }

  if (
    multi_twin.live_dispatched !== false ||
    multi_twin.twin_written !== false ||
    multi_twin.remote_fetched !== false ||
    write_pack.draft_written !== false ||
    write_pack.analysis_written !== false ||
    write_pack.merge_executed !== false ||
    write_pack.live_dispatched !== false
  ) {
    throw new Error("invariant: honesty flags must remain false");
  }

  notes.push("live_dispatched=false");
  notes.push("pack_dispatched=false");
  notes.push("twin_written=false");
  notes.push("draft_written=false");
  notes.push("analysis_written=false");
  notes.push("merge_executed=false");
  notes.push("remote_fetched=false");
  notes.push("store_mutated=false");

  return {
    session_id,
    draft_id,
    parent_asset_id,
    multi_twin,
    write_pack,
    pack_ready,
    live_dispatched: false,
    pack_dispatched: false,
    twin_written: false,
    draft_written: false,
    analysis_written: false,
    merge_executed: false,
    remote_fetched: false,
    store_mutated: false,
    notes,
    authority: "floating_multi_select_source_twin_write_compose_advisory",
  };
}

export function formatFloatingMultiSelectSourceTwinWriteSummary(
  c: FloatingMultiSelectSourceTwinWriteCompose,
): string {
  return (
    `pack_ready=${c.pack_ready} · ` +
    `multi_twin_ready=${c.multi_twin.pack_ready} · ` +
    `write_ready=${c.write_pack.pack_ready} · ` +
    `live_dispatched=false · twin_written=false · draft_written=false · analysis_written=false`
  );
}
