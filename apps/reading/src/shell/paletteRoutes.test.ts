import { describe, expect, it } from "vitest";

import { buildTaxonomyRouteIndex } from "./paletteRoutes";
import { MODE_TAXONOMY } from "./workflowTaxonomy";

describe("taxonomy-owned command palette routes", () => {
  it("includes every unique built static taxonomy route exactly once", () => {
    const routes = buildTaxonomyRouteIndex([], MODE_TAXONOMY);
    const expectedPaths = Array.from(
      new Set(
        MODE_TAXONOMY.filter(
          (mode) =>
            mode.built &&
            mode.paletteVisible !== false &&
            mode.route &&
            !mode.route.includes(":"),
        ).map((mode) => mode.route!),
      ),
    );

    expect(routes.map((route) => route.path)).toEqual(expectedPaths);
    expect(new Set(routes.map((route) => route.path)).size).toBe(routes.length);
  });

  it("excludes the login route from the authenticated palette", () => {
    const routes = buildTaxonomyRouteIndex([], MODE_TAXONOMY);

    expect(routes.some((route) => route.path === "/login")).toBe(false);
  });

  it("makes the Knowledge Graph a discoverable Research route", () => {
    const graph = buildTaxonomyRouteIndex([], MODE_TAXONOMY).find(
      (route) => route.path === "/knowledge-graph",
    );

    expect(graph).toMatchObject({
      id: "route:knowledge-graph",
      title: "Knowledge graph",
      workflow: "research",
    });
    expect(graph?.subtitle).toMatch(/exact source evidence/i);
  });

  it("uses curated copy only as an override for a taxonomy-owned route", () => {
    const routes = buildTaxonomyRouteIndex(
      [
        {
          kind: "route",
          id: "route:curated",
          title: "Curated title",
          subtitle: "Curated subtitle",
          path: "/knowledge-graph",
        },
        {
          kind: "route",
          id: "route:ghost",
          title: "Ghost",
          subtitle: "Must not survive",
          path: "/not-in-taxonomy",
        },
      ],
      MODE_TAXONOMY,
    );

    expect(routes.find((route) => route.path === "/knowledge-graph")).toMatchObject({
      id: "route:curated",
      title: "Curated title",
      workflow: "research",
    });
    expect(routes.some((route) => route.path === "/not-in-taxonomy")).toBe(false);
  });
});
