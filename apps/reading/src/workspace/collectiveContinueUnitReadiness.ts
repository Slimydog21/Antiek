/**
 * Residual (aul): pure collective continue-as-unit readiness.
 *
 * Continue as cohesive multi-agent unit requires non-empty prompt_block ·
 * HTML-first · never PDF. L6 live multi-agent remains dual-gate deferred.
 * Parity researchContextPackOpenReadiness · open-path pure matrix craft.
 */

export type CollectiveContinueUnitReadiness = {
  has_prompt_body: boolean;
  has_collective_id: boolean;
  has_parent_asset: boolean;
  spawn_count: number;
  unit_continue_ready: boolean;
  seamless_unit_continue: boolean;
  l6_live_multiagent: "deferred";
  view_format: "html";
  html_first: true;
  never_pdf_view: true;
  summary: string;
  open_title_float: string;
  open_title_full: string;
};

/**
 * Cohesive unit continue path readiness from collective unit fields.
 * unit_continue_ready when prompt_block present; seamless when id + parent.
 */
export function collectiveContinueUnitReadiness(opts: {
  prompt_block?: string | null;
  collective_id?: string | null;
  parent_asset_id?: string | null;
  spawn_count?: number | null;
  spawn_ids?: readonly string[] | null;
  selected_count?: number | null;
}): CollectiveContinueUnitReadiness {
  const has_prompt_body = Boolean(String(opts.prompt_block || "").trim());
  const has_collective_id = Boolean(String(opts.collective_id || "").trim());
  const has_parent_asset = Boolean(String(opts.parent_asset_id || "").trim());
  const fromSpawnIds = (opts.spawn_ids || []).filter(Boolean).length;
  const spawn_count =
    typeof opts.spawn_count === "number" && Number.isFinite(opts.spawn_count)
      ? Math.max(0, Math.floor(opts.spawn_count))
      : fromSpawnIds > 0
        ? fromSpawnIds
        : typeof opts.selected_count === "number" &&
            Number.isFinite(opts.selected_count)
          ? Math.max(0, Math.floor(opts.selected_count))
          : 0;
  const unit_continue_ready = has_prompt_body;
  const seamless_unit_continue = has_collective_id && has_parent_asset;

  let summary: string;
  let open_title_float: string;
  let open_title_full: string;
  if (unit_continue_ready) {
    summary = "cohesive unit prompt ready · continue float|full HTML";
    open_title_float =
      "Open a new floating deep research session seeded with this collective prompt (offline unit · HTML-first · L6 live multi-agent deferred · never PDF)";
    open_title_full =
      "Open collective unit deep research expanded to full working region (offline unit · HTML-first · L6 live multi-agent deferred · never PDF)";
  } else {
    summary = "cohesive unit prompt empty · continue not ready";
    open_title_float = "Cohesive unit prompt empty — continue not ready";
    open_title_full = "Cohesive unit prompt empty — continue not ready";
  }

  return {
    has_prompt_body,
    has_collective_id,
    has_parent_asset,
    spawn_count,
    unit_continue_ready,
    seamless_unit_continue,
    l6_live_multiagent: "deferred",
    view_format: "html",
    html_first: true,
    never_pdf_view: true,
    summary,
    open_title_float,
    open_title_full,
  };
}
