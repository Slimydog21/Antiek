/**
 * palette.facet.test.ts — SPR-04 milestone 4 (⌘K workflow facet).
 *
 * Verifies the palette ranking carries + uses the workflow facet:
 *   - a query LEADING with a workflow name floats that workflow's entries
 *     to the top (e.g. "read" surfaces the Read library);
 *   - existing (non-workflow) queries still resolve (no regression);
 *   - the workflow facet is derived from the taxonomy, not hand-typed.
 */
import { describe, it, expect } from "vitest";

import { rankEntries, entryWorkflow, type FacetEntry } from "./paletteFacet";

// A small synthetic entry set spanning workflows + a shared route.
// Typed as FacetEntry (the minimal shape the facet logic needs) + an id
// so the assertions can address rows. This intentionally does NOT import
// CommandPalette.tsx (which would pull in lib/api and leak module mocks
// into other test files).
type Row = FacetEntry & { id: string; path?: string; run?: () => void };
const ENTRIES: Row[] = [
  { kind: "route", id: "r:research", title: "Research workstation", subtitle: "Mode A (/)", path: "/", workflow: "research" },
  { kind: "route", id: "r:wrestle", title: "Document wrestler", subtitle: "Mode B (/wrestle)", path: "/wrestle", workflow: "read" },
  { kind: "route", id: "r:docs", title: "Documents", subtitle: "by tier (/documents)", path: "/documents", workflow: "read" },
  { kind: "route", id: "r:create", title: "Creation studio", subtitle: "Mode C (/create)", path: "/create", workflow: "write" },
  { kind: "route", id: "r:speak", title: "Speak", subtitle: "projects (/speak)", path: "/speak", workflow: "speak" },
  { kind: "route", id: "r:settings", title: "Settings", subtitle: "operator (/settings)", path: "/settings", workflow: "shared" },
  { kind: "action", id: "wf:goto:read", title: "Go to Read", subtitle: "library", run: () => {}, workflow: "read" },
];

describe("palette workflow facet (SPR-04 M4)", () => {
  it("floats a workflow's entries to the top when the query leads with its name", () => {
    const ranked = rankEntries(ENTRIES, "read");
    // The top results must all be Read-workflow entries.
    const topThree = ranked.slice(0, 3).map((e) => entryWorkflow(e));
    expect(topThree.every((w) => w === "read")).toBe(true);
  });

  it("a workflow-lead query matches that workflow even without a text hit", () => {
    // "Documents" has no literal "read" in its title/subtitle, but it is
    // a Read entry → must still surface under "read".
    const ranked = rankEntries(ENTRIES, "read");
    expect(ranked.some((e) => e.id === "r:docs")).toBe(true);
  });

  it("does not pull unrelated workflows up (write stays below read for 'read')", () => {
    const ranked = rankEntries(ENTRIES, "read");
    const readIdx = ranked.findIndex((e) => e.id === "r:wrestle");
    const writeIdx = ranked.findIndex((e) => e.id === "r:create");
    // Write's create may or may not appear; if it does, it's below Read.
    if (writeIdx !== -1) expect(readIdx).toBeLessThan(writeIdx);
  });

  it("existing text queries still resolve (no facet regression)", () => {
    const ranked = rankEntries(ENTRIES, "creation");
    expect(ranked[0]?.id).toBe("r:create");
  });

  it("entryWorkflow infers a facet for substrate kinds", () => {
    expect(
      entryWorkflow({
        kind: "investigation",
        id: "i:1",
        title: "x",
        subtitle: "y",
        path: "/inv/1",
      }),
    ).toBe("research");
    expect(
      entryWorkflow({
        kind: "document",
        id: "d:1",
        title: "x",
        subtitle: "y",
        path: "/wrestle/1",
      }),
    ).toBe("read");
  });
});
