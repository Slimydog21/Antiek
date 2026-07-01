import { describe, expect, it } from "vitest";

import {
  OPERATOR_ROUTE_GROUP_ORDER,
  OPERATOR_ROUTES,
  operatorRouteGroups,
} from "./operatorRoutes";

describe("operator route registry", () => {
  it("has stable unique ids and paths", () => {
    const ids = OPERATOR_ROUTES.map((route) => route.id);
    const paths = OPERATOR_ROUTES.map((route) => route.path);

    expect(new Set(ids).size).toBe(ids.length);
    expect(new Set(paths).size).toBe(paths.length);
  });

  it("groups every registered route exactly once in display order", () => {
    const grouped = operatorRouteGroups();
    const groupedRoutes = grouped.flatMap((group) => group.routes);

    expect(grouped.map((group) => group.title)).toEqual(OPERATOR_ROUTE_GROUP_ORDER);
    expect(groupedRoutes.map((route) => route.id)).toEqual(
      OPERATOR_ROUTES.map((route) => route.id),
    );
  });
});
