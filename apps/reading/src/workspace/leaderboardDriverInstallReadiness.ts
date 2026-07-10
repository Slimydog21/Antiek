/**
 * Residual (auu): pure Antiek-bench leaderboard → decision-tree install readiness.
 *
 * Install recommended / best-by-task as driver is advisory only — never
 * auto-routes dispatch. Requires non-empty model_id and a resolvable
 * provider (selected or inventory).
 *
 * Parity aut NotDiamond install · aun manual decision-tree install.
 * Bench is never dispatch authority (L7 dual-gate · decision-tree sovereignty).
 */

export type LeaderboardDriverInstallBlockReason =
  | "ok"
  | "no_model"
  | "no_provider";

export type LeaderboardDriverInstallReadiness = {
  has_model_id: boolean;
  has_provider_id: boolean;
  model_id: string;
  provider_id: string;
  task_class: string;
  install_ready: boolean;
  block_reason: LeaderboardDriverInstallBlockReason;
  never_auto_route: true;
  advisory_only: true;
  install_is_decision_tree_only: true;
  /** Antiek-bench never owns dispatch — pure constant. */
  bench_is_dispatch_authority: false;
  summary: string;
  install_title: string;
};

/**
 * Leaderboard install-as-driver CTA readiness.
 * install_ready when model_id and provider_id are non-empty after trim.
 */
export function leaderboardDriverInstallReadiness(opts: {
  model_id?: string | null;
  provider_id?: string | null;
  /** Optional best-by-task class for title honesty. */
  task_class?: string | null;
}): LeaderboardDriverInstallReadiness {
  const model_id = String(opts.model_id || "").trim();
  const provider_id = String(opts.provider_id || "").trim();
  const task_class = String(opts.task_class || "").trim();
  const has_model_id = Boolean(model_id);
  const has_provider_id = Boolean(provider_id);

  let block_reason: LeaderboardDriverInstallBlockReason = "ok";
  if (!has_model_id) {
    block_reason = "no_model";
  } else if (!has_provider_id) {
    block_reason = "no_provider";
  }

  const install_ready = block_reason === "ok";

  let summary: string;
  let install_title: string;
  if (install_ready) {
    const taskBit = task_class ? ` · task=${task_class}` : "";
    summary = `install ready · bench advisory ${provider_id}/${model_id}${taskBit} → decision-tree only`;
    install_title = task_class
      ? `Install best-for-${task_class} (${model_id}) as decision-tree driver (advisory · never auto-route)`
      : `Install recommended (${model_id}) as decision-tree driver (advisory · never auto-route)`;
  } else if (block_reason === "no_model") {
    summary = "no model · run offline Antiek-bench first";
    install_title = "No model id to install from leaderboard";
  } else {
    summary = "no provider · select provider or load models inventory";
    install_title =
      "Select a provider (or ensure models inventory has one) before installing leaderboard driver";
  }

  return {
    has_model_id,
    has_provider_id,
    model_id,
    provider_id,
    task_class,
    install_ready,
    block_reason,
    never_auto_route: true,
    advisory_only: true,
    install_is_decision_tree_only: true,
    bench_is_dispatch_authority: false,
    summary,
    install_title,
  };
}

/**
 * Resolve provider for leaderboard install: explicit selection first, then
 * first ready model provider, then first inventory provider. Pure — no I/O.
 */
export function resolveLeaderboardInstallProvider(opts: {
  selected_provider_id?: string | null;
  models?: ReadonlyArray<{
    provider_id?: string | null;
    ready?: boolean | null;
  }> | null;
}): string {
  const selected = String(opts.selected_provider_id || "").trim();
  if (selected) return selected;
  const list = opts.models || [];
  const ready = list.find((m) => m.ready && String(m.provider_id || "").trim());
  if (ready?.provider_id) return String(ready.provider_id).trim();
  const any = list.find((m) => String(m.provider_id || "").trim());
  return any?.provider_id ? String(any.provider_id).trim() : "";
}
