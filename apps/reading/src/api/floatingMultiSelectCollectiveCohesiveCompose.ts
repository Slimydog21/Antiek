/**
 * Floating multi-select → collective cohesive deep research pack (pure).
 *
 * Operator vision: click multiple floating/sub-agent deep research instances
 * and engage them as one cohesive unit — prompt pack + optional post-completion
 * analysis merge intent — without live dispatch or asset writes.
 *
 * live_dispatched always false.
 * pack_dispatched always false.
 * merge_executed always false.
 * analysis_written always false.
 */

import {
  buildCollectiveFloatingCohesivePrompt,
  type CohesiveFloatingMember,
  type CohesiveUnitPromptIntent,
} from "./collectiveFloatingCohesivePrompt";
import {
  composeFloatingInstanceTray,
  type FloatingInstanceTrayCompose,
  type TrayMember,
  type TrayMemberStatus,
} from "./floatingInstanceTrayCompose";
import {
  proposeCollectiveAnalysisMerge,
  type AnalysisMergeKind,
  type CollectiveAnalysisIntent,
  type CompletedResearchInstance,
} from "./collectiveDeepResearchMerge";

export type MultiSelectPackMode =
  | "cohesive_prompt"
  | "collective_pack"
  | "cohesive_plus_analysis";

export interface FloatingMultiSelectMember {
  instance_id: string;
  parent_asset_id: string;
  status: TrayMemberStatus;
  highlight?: string;
  prior_prompt?: string;
  /** Caller-supplied context only — never invented. */
  context?: string[];
  /** Caller-supplied findings for analysis path — never invented. */
  findings?: string[];
  live_dispatched?: false;
  merge_executed?: false;
}

export interface FloatingMultiSelectCollectiveCohesiveInput {
  session_id: string;
  parent_asset_id: string;
  members: FloatingMultiSelectMember[];
  selected_instance_ids: string[];
  /**
   * cohesive_prompt | collective_pack | cohesive_plus_analysis
   * (analysis requires ≥2 non-closed selected; full needs completed).
   */
  pack_mode: MultiSelectPackMode;
  cohesive_prompt: string;
  operator_ack: boolean;
  extra_context?: string[] | null;
  analysis_kind?: AnalysisMergeKind | null;
  extra_findings?: string[] | null;
}

export interface FloatingMultiSelectCollectiveCohesiveCompose {
  session_id: string;
  parent_asset_id: string;
  pack_mode: MultiSelectPackMode;
  tray: FloatingInstanceTrayCompose;
  cohesive: CohesiveUnitPromptIntent | null;
  analysis: CollectiveAnalysisIntent | null;
  /**
   * True when tray_ready and (cohesive pack_ready when required)
   * and (analysis path ready when mode includes analysis).
   * Never authorizes live dispatch/write.
   */
  pack_ready: boolean;
  live_dispatched: false;
  pack_dispatched: false;
  merge_executed: false;
  analysis_written: false;
  notes: string[];
  authority: "floating_multi_select_collective_cohesive_compose_advisory";
}

function requireNonEmpty(value: unknown, name: string): string {
  if (typeof value !== "string" || !value.trim()) {
    throw new Error(`${name} must be a non-empty string`);
  }
  return value.trim();
}

/**
 * Multi-select floating instances → cohesive unit prompt (+ optional analysis).
 * Never dispatches packs; never merges; never writes analysis.
 */
export function composeFloatingMultiSelectCollectiveCohesive(
  input: FloatingMultiSelectCollectiveCohesiveInput,
): FloatingMultiSelectCollectiveCohesiveCompose {
  if (!input || typeof input !== "object") {
    throw new Error("input must be an object");
  }
  if (typeof input.operator_ack !== "boolean") {
    throw new Error("operator_ack must be an explicit boolean");
  }
  const session_id = requireNonEmpty(input.session_id, "session_id");
  const parent_asset_id = requireNonEmpty(
    input.parent_asset_id,
    "parent_asset_id",
  );
  if (
    input.pack_mode !== "cohesive_prompt" &&
    input.pack_mode !== "collective_pack" &&
    input.pack_mode !== "cohesive_plus_analysis"
  ) {
    throw new Error(
      "pack_mode must be cohesive_prompt|collective_pack|cohesive_plus_analysis",
    );
  }
  if (!Array.isArray(input.members) || input.members.length < 2) {
    throw new Error("members must be an array with at least 2 members");
  }
  if (
    !Array.isArray(input.selected_instance_ids) ||
    input.selected_instance_ids.length < 2
  ) {
    throw new Error(
      "selected_instance_ids must include at least 2 multi-selected instances",
    );
  }

  const notes: string[] = [
    "live_dispatched=false — pure multi-select cohesive pack only",
    "pack_dispatched=false — no multi-agent pack execution",
    "merge_executed=false — no parent asset merge",
    "analysis_written=false — analysis intent only when requested",
  ];

  const trayAction =
    input.pack_mode === "collective_pack"
      ? "collective_pack"
      : "cohesive_prompt";

  const trayMembers: TrayMember[] = input.members.map((m) => ({
    instance_id: m.instance_id,
    parent_asset_id: m.parent_asset_id,
    status: m.status,
    highlight: m.highlight,
    live_dispatched: m.live_dispatched,
    merge_executed: m.merge_executed,
  }));

  const tray = composeFloatingInstanceTray({
    parent_asset_id,
    members: trayMembers,
    selected_instance_ids: input.selected_instance_ids,
    action: trayAction,
    operator_ack: input.operator_ack,
  });
  notes.push(...tray.notes.map((n) => `[tray] ${n}`));

  // Build cohesive members from selected subset only
  const byId = new Map<string, FloatingMultiSelectMember>();
  for (const m of input.members) {
    byId.set(m.instance_id.trim(), m);
  }
  const selectedMembers: FloatingMultiSelectMember[] = [];
  for (const id of tray.selected_instance_ids) {
    const m = byId.get(id);
    if (!m) {
      throw new Error(`selected member missing: ${id}`);
    }
    selectedMembers.push(m);
  }

  let cohesive: CohesiveUnitPromptIntent | null = null;
  if (
    input.pack_mode === "cohesive_prompt" ||
    input.pack_mode === "cohesive_plus_analysis"
  ) {
    // Fail closed if any selected is closed (tray should already gate)
    for (const m of selectedMembers) {
      if (m.status === "closed") {
        throw new Error(
          "closed instances cannot join cohesive multi-select pack",
        );
      }
    }
    const cohesiveMembers: CohesiveFloatingMember[] = selectedMembers.map(
      (m) => ({
        instance_id: m.instance_id,
        parent_asset_id: m.parent_asset_id,
        status: m.status as "proposed" | "open" | "completed",
        highlight: m.highlight,
        prior_prompt: m.prior_prompt,
        context: m.context,
      }),
    );
    cohesive = buildCollectiveFloatingCohesivePrompt(cohesiveMembers, {
      cohesive_prompt: input.cohesive_prompt,
      operator_ack: input.operator_ack,
      extra_context: input.extra_context,
    });
    notes.push(...cohesive.notes.map((n) => `[cohesive] ${n}`));
  } else {
    // collective_pack mode: still require non-empty cohesive_prompt as scaffold
    requireNonEmpty(input.cohesive_prompt, "cohesive_prompt");
    notes.push(
      "pack_mode=collective_pack — tray multi-select pack intent; cohesive prompt scaffold held for operator",
    );
  }

  let analysis: CollectiveAnalysisIntent | null = null;
  let analysis_path_ready = true;
  if (input.pack_mode === "cohesive_plus_analysis") {
    const kind = input.analysis_kind;
    if (kind !== "draft_analysis" && kind !== "full_analysis") {
      throw new Error(
        "analysis_kind must be draft_analysis or full_analysis when pack_mode=cohesive_plus_analysis",
      );
    }
    const instances: CompletedResearchInstance[] = selectedMembers.map((m) => {
      if (m.status === "closed") {
        throw new Error("closed instances cannot join analysis merge");
      }
      return {
        instance_id: m.instance_id,
        parent_asset_id: m.parent_asset_id,
        status: m.status as "completed" | "open" | "proposed",
        highlight: m.highlight,
        prompt: m.prior_prompt,
        findings: m.findings,
      };
    });

    const allCompleted = selectedMembers.every((m) => m.status === "completed");
    if (kind === "full_analysis" && !allCompleted) {
      // Soft-gate: do not throw — pack_ready false; no full analysis intent.
      analysis = null;
      analysis_path_ready = false;
      notes.push(
        "analysis_path_ready=false — full_analysis requires all selected completed",
      );
    } else {
      analysis = proposeCollectiveAnalysisMerge(instances, {
        kind,
        operator_ack: input.operator_ack,
        extra_findings: input.extra_findings,
      });
      notes.push(...analysis.notes.map((n) => `[analysis] ${n}`));

      if (kind === "full_analysis") {
        analysis_path_ready = input.operator_ack && allCompleted;
        if (!input.operator_ack) {
          notes.push(
            "analysis_path_ready=false — full_analysis requires operator_ack",
          );
        } else {
          notes.push(
            "analysis_path_ready=true — full analysis intent; analysis_written=false",
          );
        }
      } else {
        analysis_path_ready = selectedMembers.length >= 2;
        notes.push(
          analysis_path_ready
            ? "analysis_path_ready=true — draft analysis intent; analysis_written=false"
            : "analysis_path_ready=false",
        );
      }
    }
  }

  const cohesive_ok =
    input.pack_mode === "collective_pack"
      ? true
      : cohesive !== null && cohesive.pack_ready === true;

  const pack_ready =
    tray.tray_ready === true &&
    cohesive_ok &&
    analysis_path_ready &&
    input.operator_ack === true;

  if (pack_ready) {
    notes.push(
      "pack_ready=true — multi-select cohesive pack intent ready; still no dispatch/write",
    );
  } else {
    notes.push(
      "pack_ready=false — tray, cohesive, analysis, or operator_ack gate open",
    );
  }

  notes.push("live_dispatched=false");
  notes.push("pack_dispatched=false");
  notes.push("merge_executed=false");
  notes.push("analysis_written=false");

  return {
    session_id,
    parent_asset_id,
    pack_mode: input.pack_mode,
    tray,
    cohesive,
    analysis,
    pack_ready,
    live_dispatched: false,
    pack_dispatched: false,
    merge_executed: false,
    analysis_written: false,
    notes,
    authority: "floating_multi_select_collective_cohesive_compose_advisory",
  };
}

export function formatFloatingMultiSelectCollectiveCohesiveSummary(
  c: FloatingMultiSelectCollectiveCohesiveCompose,
): string {
  return (
    `pack_ready=${c.pack_ready} · mode=${c.pack_mode} · ` +
    `selected=${c.tray.selected_count}/${c.tray.member_count} · ` +
    `live_dispatched=false · pack_dispatched=false · ` +
    `merge_executed=false · analysis_written=false`
  );
}
