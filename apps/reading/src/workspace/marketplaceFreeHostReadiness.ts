/**
 * Residual (aru): pure free HTML host-into-account path readiness.
 *
 * Free / public_domain catalog rows use Host into account without receipt.
 * Never invents free inventory counts · never PDF view · no live payment.
 * Parity marketplaceReceiptReadiness (ars) for the free path.
 */

export type MarketplaceFreeHostReadiness = {
  free_catalog_visible: number;
  free_pd_only_filter: boolean;
  host_ready: boolean;
  receipt_required: false;
  view_format: "html";
  html_first: true;
  live_payment: false;
  never_pdf_view: true;
  summary: string;
};

function nonNegInt(n: number | null | undefined): number {
  if (typeof n !== "number" || !Number.isFinite(n) || n < 0) return 0;
  return Math.floor(n);
}

/**
 * Free host path readiness from visible free count and free-only filter.
 * host_ready when at least one free book is visible (never invents catalog).
 */
export function marketplaceFreeHostReadiness(opts: {
  freeCatalogVisible?: number | null;
  freePdOnlyFilter?: boolean | null;
}): MarketplaceFreeHostReadiness {
  const free_catalog_visible = nonNegInt(opts.freeCatalogVisible);
  const free_pd_only_filter = opts.freePdOnlyFilter === true;
  const host_ready = free_catalog_visible > 0;

  let summary: string;
  if (!host_ready) {
    summary = free_pd_only_filter
      ? "no free books visible under free-only filter · never PDF · no receipt required"
      : "no free books visible · never PDF · no receipt required";
  } else {
    summary =
      `free HTML host path · ${free_catalog_visible} free book(s) can Host into account` +
      (free_pd_only_filter ? " · free-only filter on" : "") +
      " · never PDF view · no receipt required";
  }

  return {
    free_catalog_visible,
    free_pd_only_filter,
    host_ready,
    receipt_required: false,
    view_format: "html",
    html_first: true,
    live_payment: false,
    never_pdf_view: true,
    summary,
  };
}
