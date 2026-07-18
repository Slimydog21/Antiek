/**
 * NotDiamond shadow router — pure selection contract (SPR-ND-01).
 *
 * Product rule (see docs/htmlspec/notdiamond-router/NO-GO-OR-GO.md):
 *   - Recommendation only; decision-tree still owns the final model id.
 *   - Fail-closed: missing key / timeout / error → recommended=null.
 *   - Candidates must be a subset of the operator BYOK registry (caller enforces).
 *   - Live HTTP is injectable; default transport is null (no network until wired).
 */

export type ModelRef = {
  /** Stable Antiek model id (settings registry). */
  id: string;
  /** Provider slug for display (openai, anthropic, …). */
  provider: string;
};

export type ShadowRouteRequest = {
  messages: ReadonlyArray<{ role: string; content: string }>;
  candidates: readonly ModelRef[];
  taskClass: string;
  /** Soft deadline; transport must respect. Default 800ms. */
  timeoutMs?: number;
};

export type ShadowRouteDecision = {
  recommended: ModelRef | null;
  reason: string;
  latencyMs: number;
  provider: "notdiamond" | "fallback_local" | "disabled";
  error?: string;
};

export type ShadowRouterTransport = (
  req: ShadowRouteRequest,
) => Promise<{ recommendedId: string | null; reason?: string }>;

export type ShadowRouterOptions = {
  /** When false, never call transport (default). */
  enabled?: boolean;
  /** Injected HTTP/SDK adapter. */
  transport?: ShadowRouterTransport | null;
  /** Clock for latency (tests). */
  now?: () => number;
};

/**
 * Local heuristic fallback when ND is disabled or fails.
 * Prefer last candidate that matches taskClass substring in id, else first.
 */
export function localHeuristicRecommend(
  candidates: readonly ModelRef[],
  taskClass: string,
): ModelRef | null {
  if (candidates.length === 0) return null;
  // Normalize separators so "deep_research" matches "deep-research-pro".
  const needle = taskClass.toLowerCase().replace(/[_/]+/g, "-");
  const tokens = needle.split("-").filter((t) => t.length > 2);
  const match = candidates.find((c) => {
    const id = c.id.toLowerCase().replace(/[_/]+/g, "-");
    if (id.includes(needle)) return true;
    return tokens.some((t) => id.includes(t));
  });
  return match ?? candidates[0] ?? null;
}

/**
 * Shadow select — pure orchestration around an optional transport.
 */
export async function selectModelShadow(
  req: ShadowRouteRequest,
  opts: ShadowRouterOptions = {},
): Promise<ShadowRouteDecision> {
  const now = opts.now ?? (() => Date.now());
  const t0 = now();
  const enabled = opts.enabled === true;
  const candidates = req.candidates;

  if (candidates.length === 0) {
    return {
      recommended: null,
      reason: "no_candidates",
      latencyMs: Math.max(0, now() - t0),
      provider: "disabled",
      error: "empty_candidate_set",
    };
  }

  if (!enabled || !opts.transport) {
    const rec = localHeuristicRecommend(candidates, req.taskClass);
    return {
      recommended: rec,
      reason: enabled
        ? "enabled_but_no_transport_local_heuristic"
        : "shadow_disabled_local_heuristic",
      latencyMs: Math.max(0, now() - t0),
      provider: "fallback_local",
    };
  }

  const timeoutMs = req.timeoutMs ?? 800;
  let timer: ReturnType<typeof setTimeout> | undefined;
  try {
    const result = await Promise.race([
      opts.transport(req),
      new Promise<never>((_, reject) => {
        timer = setTimeout(
          () => reject(new Error("notdiamond_timeout")),
          timeoutMs,
        );
      }),
    ]);
    const recommended =
      candidates.find((c) => c.id === result.recommendedId) ?? null;
    return {
      recommended,
      reason:
        result.reason ??
        (recommended ? "notdiamond_select" : "id_not_in_candidates"),
      latencyMs: Math.max(0, now() - t0),
      provider: "notdiamond",
      error: recommended ? undefined : "recommended_id_not_in_candidates",
    };
  } catch (e) {
    const rec = localHeuristicRecommend(candidates, req.taskClass);
    return {
      recommended: rec,
      reason: "transport_failed_local_heuristic",
      latencyMs: Math.max(0, now() - t0),
      provider: "fallback_local",
      error: e instanceof Error ? e.message : "transport_error",
    };
  } finally {
    if (timer !== undefined) clearTimeout(timer);
  }
}
