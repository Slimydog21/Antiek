/**
 * Residual (asb): pure knowledge-dense publication attach+hydrate readiness.
 *
 * arxiv / substack / URL refs attach to a spawn then hydrate HTML assets.
 * Never invents spawn binding or refs · never auto-claims live body · HTML-first.
 * Live L1/L2 hydrate injectors remain dual-gate deferred.
 */

export type PublicationAttachReadiness = {
  spawn_bound: boolean;
  ref_count: number;
  /** True when spawn bound and ≥1 publication ref ready to attach. */
  attach_ready: boolean;
  view_format: "html";
  html_first: true;
  live_hydrate_deferred: true;
  never_auto_hydrate: true;
  summary: string;
};

function nonNegInt(n: number | null | undefined): number {
  if (typeof n !== "number" || !Number.isFinite(n) || n < 0) return 0;
  return Math.floor(n);
}

/**
 * Attach+hydrate path readiness from spawn bind and parsed ref count.
 * ref_count should come from parsePublicationRefs (one non-empty line each).
 */
export function publicationAttachReadiness(opts: {
  spawnId?: string | null;
  refCount?: number | null;
}): PublicationAttachReadiness {
  const spawn_bound = Boolean(String(opts.spawnId || "").trim());
  const ref_count = nonNegInt(opts.refCount);
  const attach_ready = spawn_bound && ref_count >= 1;

  let summary: string;
  if (!spawn_bound && ref_count < 1) {
    summary =
      "bind spawn + add arxiv/substack/URL refs · offline hydrate · never auto-hydrate";
  } else if (!spawn_bound) {
    summary =
      "bind spawn for attach+hydrate · refs present · offline hydrate · never invent live body";
  } else if (ref_count < 1) {
    summary =
      "add publication refs (quick-call or paste) · offline hydrate until Attach";
  } else {
    summary = `attach ready · ${ref_count} ref(s) · HTML hydrate · live L1/L2 deferred · never auto-hydrate`;
  }

  return {
    spawn_bound,
    ref_count,
    attach_ready,
    view_format: "html",
    html_first: true,
    live_hydrate_deferred: true,
    never_auto_hydrate: true,
    summary,
  };
}
