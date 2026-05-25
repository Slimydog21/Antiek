import { describe, it, expect } from "vitest";

import {
  WORKFLOW_ROUTES,
  workflowForEntry,
  rankEntries,
  type PaletteEntry,
} from "./CommandPalette";

/**
 * SPR-06 — the palette's workflow facet is testable, not vibes. Each result
 * gets a workflow from what it IS; the four "go to workflow" entries exist;
 * relevance still wins when a query is present.
 */
describe("CommandPalette — workflow facet", () => {
  it("has a 'go to workflow' entry for each of the four workflows", () => {
    expect(WORKFLOW_ROUTES.map((r) => r.path).sort()).toEqual(
      ["/", "/create", "/documents", "/interviews"].sort(),
    );
  });

  it("derives the facet from the entry kind / route", () => {
    expect(workflowForEntry({ kind: "investigation", id: "i", title: "x", subtitle: "", path: "/inv/x" })).toBe("research");
    expect(workflowForEntry({ kind: "parked_question", id: "p", title: "x", subtitle: "", path: "/brainstorm" })).toBe("research");
    expect(workflowForEntry({ kind: "document", id: "d", title: "x", subtitle: "", path: "/wrestle/x" })).toBe("read");
    expect(workflowForEntry({ kind: "notebook", id: "n", title: "x", subtitle: "", path: "/notebook/x" })).toBe("read");
    expect(workflowForEntry({ kind: "route", id: "r", title: "Write", subtitle: "", path: "/create" })).toBe("write");
    expect(workflowForEntry({ kind: "route", id: "r", title: "Speak", subtitle: "", path: "/interviews" })).toBe("speak");
    // shared routes + actions carry no facet
    expect(workflowForEntry({ kind: "route", id: "r", title: "Billing", subtitle: "", path: "/billing" })).toBeNull();
    expect(workflowForEntry({ kind: "action", id: "a", title: "Reset", subtitle: "", run: () => {} })).toBeNull();
  });

  it("ranks by relevance when a query is present (facet does not override text match)", () => {
    const entries: PaletteEntry[] = [
      { kind: "route", id: "a", title: "Roblox memo", subtitle: "", path: "/create" },
      { kind: "investigation", id: "b", title: "Roblox ad-load ceiling", subtitle: "", path: "/inv/b" },
      { kind: "route", id: "c", title: "Pricing", subtitle: "", path: "/pricing" },
    ];
    const ranked = rankEntries(entries, "roblox");
    expect(ranked.map((e) => e.id)).toEqual(["a", "b"]); // both match "roblox"; pricing drops
  });
});
