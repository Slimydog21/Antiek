import { MODE_TAXONOMY, type ModeEntry } from "./workflowTaxonomy";

const BARE_ROUTES = new Set(
  MODE_TAXONOMY.filter((m) => m.route && !m.route.includes(":")).map(
    (m) => m.route as string,
  ),
);

/**
 * Resolve a taxonomy mode to a concrete launcher/sub-action destination.
 *
 * Bare routes navigate directly. Param routes navigate only when their bare
 * index is itself a real route. Instance-only routes stay visible in inventory
 * surfaces, but selecting them is an honest no-op until an instance exists.
 */
export function destinationForMode(m: ModeEntry): string | null {
  if (!m.built || !m.route) return null;
  if (!m.route.includes(":")) return m.route;
  const index = m.route.split("/:")[0];
  return BARE_ROUTES.has(index) ? index : null;
}
