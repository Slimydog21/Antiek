import type { ModeEntry, Workflow } from "./workflowTaxonomy";

export type PaletteRouteSeed = {
  kind: "route";
  id: string;
  title: string;
  subtitle: string;
  path: string;
  workflow?: Workflow;
};

/**
 * Build the command-palette route inventory from the shell taxonomy.
 *
 * Curated rows are presentation overrides only, so a newly classified mode
 * cannot disappear from ⌘K. Taxonomy also owns the rare explicit exclusion
 * for real routes that are unusable from the authenticated palette.
 * Multiple component modes may intentionally share one product door (for
 * example Write's repository and editor); the first taxonomy entry owns the
 * single navigation row.
 */
export function buildTaxonomyRouteIndex(
  curated: readonly PaletteRouteSeed[],
  taxonomy: readonly ModeEntry[],
): PaletteRouteSeed[] {
  const curatedByPath = new Map(curated.map((entry) => [entry.path, entry]));
  const seenPaths = new Set<string>();
  const routes: PaletteRouteSeed[] = [];

  for (const mode of taxonomy) {
    const path = mode.route;
    if (
      !mode.built ||
      mode.paletteVisible === false ||
      !path ||
      path.includes(":") ||
      seenPaths.has(path)
    ) {
      continue;
    }
    seenPaths.add(path);
    const override = curatedByPath.get(path);
    routes.push(
      override
        ? { ...override, workflow: mode.workflow }
        : {
            kind: "route",
            id: `route:${mode.id
              .replace(/([a-z0-9])([A-Z])/g, "$1-$2")
              .replace(/[^a-zA-Z0-9]+/g, "-")
              .toLowerCase()}`,
            title: mode.label,
            subtitle: `${mode.blurb} (${path})`,
            path,
            workflow: mode.workflow,
          },
    );
  }

  return routes;
}
