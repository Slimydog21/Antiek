/**
 * productModeRoutes — thin registry of campaign product modes that ship on
 * authenticated routes. App.tsx imports these paths + components; tests assert
 * the registry without reimplementing create/approve or host-into-account.
 *
 * Residual (af): Midnight Oil + Marketplace Host shell registration.
 * Both modes declare HTML human-view stance (data-view-format="html").
 */

import type { ComponentType } from "react";

import MarketplaceHost from "./modes/MarketplaceHost";
import MidnightOil from "./modes/MidnightOil";

export type ProductModeRoute = {
  /** Stable URL path segment (authenticated). */
  path: string;
  /** Mode id aligned with workflowTaxonomy. */
  modeId: string;
  /** Default export mode component. */
  Component: ComponentType;
  /** Human-view contract — always html for these products. */
  viewFormat: "html";
  /** One-line product job. */
  blurb: string;
};

/**
 * Shipped product-mode routes consumed by AuthenticatedRoutes.
 * Order is declaration order only (not rail order).
 */
export const PRODUCT_MODE_ROUTES: readonly ProductModeRoute[] = [
  {
    path: "/midnight-oil",
    modeId: "MidnightOil",
    Component: MidnightOil,
    viewFormat: "html",
    blurb:
      "Autonomous multi-goal deep research: goals (one per line · templates) + duration + fan-out → recommended price ceiling → explicit approve (HTML deliverable).",
  },
  {
    path: "/marketplace/host",
    modeId: "MarketplaceHost",
    Component: MarketplaceHost,
    viewFormat: "html",
    blurb:
      "Catalog → host book into account → HTML library view (PDF ingest source only).",
  },
] as const;

/** Path keys for structural tests / double-run stability. */
export function productModePaths(): string[] {
  return PRODUCT_MODE_ROUTES.map((r) => r.path);
}

/** Lookup by path (exact). */
export function productModeByPath(path: string): ProductModeRoute | undefined {
  return PRODUCT_MODE_ROUTES.find((r) => r.path === path);
}

/** Structural registry snapshot for launch/double-run checks. */
export function productModeRegistrySnapshot(): Array<{
  path: string;
  modeId: string;
  viewFormat: "html";
  componentName: string;
}> {
  return PRODUCT_MODE_ROUTES.map((r) => ({
    path: r.path,
    modeId: r.modeId,
    viewFormat: r.viewFormat,
    componentName: r.Component.displayName || r.Component.name || r.modeId,
  }));
}
