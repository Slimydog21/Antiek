/**
 * Residual (ava): pure Antiek-bench offline dogfood run CTA readiness.
 *
 * Run offline suite to produce weekly ranking data. Never auto-promotes the
 * suite (propose≠promote · suite approve is separate pure aux). Requires
 * non-empty week_id. Offline-only · HTML view_format expected after run.
 *
 * Outside pure install thrash (aut–auy) · outside dogfood fixture thrash.
 */

export type OfflineBenchRunBlockReason = "ok" | "no_week_id";

export type OfflineBenchRunReadiness = {
  has_week_id: boolean;
  week_id: string;
  run_ready: boolean;
  block_reason: OfflineBenchRunBlockReason;
  offline_only: true;
  never_auto_promote: true;
  propose_neq_promote: true;
  html_first: true;
  summary: string;
  run_title: string;
};

/**
 * Offline dogfood run CTA readiness from week field.
 * run_ready only when week_id is non-empty after trim.
 */
export function offlineBenchRunReadiness(opts: {
  week_id?: string | null;
}): OfflineBenchRunReadiness {
  const week_id = String(opts.week_id || "").trim();
  const has_week_id = Boolean(week_id);
  const run_ready = has_week_id;
  const block_reason: OfflineBenchRunBlockReason = run_ready
    ? "ok"
    : "no_week_id";

  let summary: string;
  let run_title: string;
  if (run_ready) {
    summary = `run ready · week=${week_id} · offline only · never auto-promote · propose≠promote`;
    run_title =
      "Run offline dogfood suite for this week (offline · HTML · never auto-promote · propose≠promote)";
  } else {
    summary = "week id empty · enter week before offline run";
    run_title = "Enter a week id before running offline dogfood suite";
  }

  return {
    has_week_id,
    week_id,
    run_ready,
    block_reason,
    offline_only: true,
    never_auto_promote: true,
    propose_neq_promote: true,
    html_first: true,
    summary,
    run_title,
  };
}
