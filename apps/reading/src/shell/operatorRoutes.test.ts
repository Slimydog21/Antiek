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

  it("groups product routes by workflow instead of the old generic Workstation bucket", () => {
    const byId = new Map(OPERATOR_ROUTES.map((route) => [route.id, route]));

    expect(byId.get("documents")?.group).toBe("Governance");
    expect(byId.get("sources")?.group).toBe("Governance");
    expect(byId.get("skill-rules")?.group).toBe("Governance");

    expect(byId.get("home")?.group).toBe("Home");
    expect(byId.get("research")?.group).toBe("Research");
    expect(byId.get("research")?.title).toBe("Research home");
    expect(byId.get("deep-research")?.group).toBe("Research");
    expect(byId.get("my-research")?.group).toBe("Research");
    expect(byId.get("brainstorm")?.group).toBe("Research");
    expect(byId.get("library")?.group).toBe("Read");
    expect(byId.get("library-browse")?.group).toBe("Read");
    expect(byId.get("wrestle")?.group).toBe("Read");
    expect(byId.get("readings")?.group).toBe("Read");
    expect(byId.get("meta-readings")?.group).toBe("Read");
    expect(byId.get("meta-reading")?.group).toBe("Read");
    expect(byId.get("notebooks")?.group).toBe("Read");
    expect(byId.get("write")?.group).toBe("Write");
    expect(byId.get("create")?.group).toBe("Write");
    expect(byId.get("speak")?.group).toBe("Speak");
    expect(byId.get("biography")?.group).toBe("Speak");
  });
});
