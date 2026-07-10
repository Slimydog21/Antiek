/**
 * Residual (aqy): pure readiness for highlight→DR operator path choices —
 * float|full · draft merge · into parent · written analysis.
 *
 * Shared contract for DeepResearchSessionHost (aqw), CollectiveResearchPanel
 * (aqx), and SpawnMergePanel. Never invents parent/spawn binding — empty → not ready.
 * Offline merge unit only · L6 live multi-agent deferred.
 */

export type ResearchPathChoicesReadiness = {
  parent_bound: boolean;
  /** At least one spawn/selection ready for merge actions. */
  spawn_or_selection_ready: boolean;
  /** Session/window bound so float⇄full controls can act. */
  float_full_ready: boolean;
  draft_merge_ready: boolean;
  into_parent_ready: boolean;
  /** Multi-agent written analysis needs ≥ minAnalysisSpawns (default 2). */
  written_analysis_ready: boolean;
  selected_count: number;
  /** Short operator-facing summary (no invented readiness). */
  summary: string;
};

export function researchPathChoicesReadiness(opts: {
  parentAssetId?: string | null;
  /** Spawn count selected (collective) or 1 when single spawn bound. */
  selectedCount?: number | null;
  /** Session/window id present for float|full controls. */
  sessionBound?: boolean | null;
  minAnalysisSpawns?: number;
}): ResearchPathChoicesReadiness {
  const parent_bound = Boolean(String(opts.parentAssetId || "").trim());
  const selected_count =
    typeof opts.selectedCount === "number" &&
    Number.isFinite(opts.selectedCount) &&
    opts.selectedCount > 0
      ? Math.floor(opts.selectedCount)
      : 0;
  const minAnalysis =
    typeof opts.minAnalysisSpawns === "number" &&
    Number.isFinite(opts.minAnalysisSpawns) &&
    opts.minAnalysisSpawns > 0
      ? Math.floor(opts.minAnalysisSpawns)
      : 2;
  const spawn_or_selection_ready = selected_count >= 1;
  const float_full_ready = Boolean(opts.sessionBound);
  const draft_merge_ready = parent_bound && spawn_or_selection_ready;
  const into_parent_ready = draft_merge_ready;
  const written_analysis_ready = parent_bound && selected_count >= minAnalysis;

  let summary: string;
  if (!parent_bound && !spawn_or_selection_ready) {
    summary = "bind parent + select spawns for merge paths";
  } else if (!parent_bound) {
    summary = "bind parent for draft / into-parent merge";
  } else if (!spawn_or_selection_ready) {
    summary = "parent bound · select spawns";
  } else if (written_analysis_ready) {
    summary = `${selected_count} selected · draft · into-parent · written analysis ready`;
  } else {
    summary = `${selected_count} selected · draft · into-parent ready`;
  }

  return {
    parent_bound,
    spawn_or_selection_ready,
    float_full_ready,
    draft_merge_ready,
    into_parent_ready,
    written_analysis_ready,
    selected_count,
    summary,
  };
}
