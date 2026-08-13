/**
 * paletteFacet.test.ts — the state-filter facet (herdr transfer P0-5).
 * Pure logic, no React, no data layer (same isolation rule as the module).
 */
import { describe, expect, it } from "vitest";

import {
  entryMatchesStateFilter,
  isStateFilter,
  leadingStateFilter,
  rankEntries,
  type FacetEntry,
} from "./paletteFacet";

function inv(state: "blocked" | "working" | "done", unseen = false, title = "x"): FacetEntry {
  return { kind: "investigation", title, subtitle: "s", state, unseen };
}

const noState: FacetEntry = { kind: "route", title: "Home", subtitle: "go" };

describe("leadingStateFilter", () => {
  it("parses a leading state: word", () => {
    expect(leadingStateFilter("state:blocked")).toBe("blocked");
    expect(leadingStateFilter("state:blocked openai")).toBe("blocked");
    expect(leadingStateFilter("state:unseen")).toBe("unseen");
  });

  it("rejects unknown state words and non-leading positions", () => {
    expect(leadingStateFilter("state:bogus")).toBeNull();
    expect(leadingStateFilter("openai state:blocked")).toBeNull();
    expect(leadingStateFilter("research")).toBeNull();
    expect(leadingStateFilter("")).toBeNull();
  });
});

describe("isStateFilter", () => {
  it("accepts exactly the chip vocabulary", () => {
    expect(isStateFilter("blocked")).toBe(true);
    expect(isStateFilter("working")).toBe(true);
    expect(isStateFilter("done")).toBe(true);
    expect(isStateFilter("unseen")).toBe(true);
    expect(isStateFilter("stopped")).toBe(false);
    expect(isStateFilter("all")).toBe(false);
  });
});

describe("entryMatchesStateFilter", () => {
  it("matches research states exactly", () => {
    expect(entryMatchesStateFilter(inv("blocked"), "blocked")).toBe(true);
    expect(entryMatchesStateFilter(inv("working"), "blocked")).toBe(false);
  });

  it("unseen matches only unseen completions", () => {
    expect(entryMatchesStateFilter(inv("done", true), "unseen")).toBe(true);
    expect(entryMatchesStateFilter(inv("done", false), "unseen")).toBe(false);
    expect(entryMatchesStateFilter(inv("working", true), "unseen")).toBe(false);
  });

  it("stateless entries match no state filter", () => {
    expect(entryMatchesStateFilter(noState, "blocked")).toBe(false);
    expect(entryMatchesStateFilter(noState, "unseen")).toBe(false);
  });
});

describe("rankEntries with state filters", () => {
  const entries = [
    inv("blocked", false, "alice"),
    inv("working", false, "bob"),
    inv("done", true, "carol"),
    inv("done", false, "dave"),
    noState,
  ];

  it("state:blocked keeps only blocked entries", () => {
    const out = rankEntries(entries, "state:blocked");
    expect(out.map((e) => e.title)).toEqual(["alice"]);
  });

  it("state:unseen keeps only unseen completions", () => {
    const out = rankEntries(entries, "state:unseen");
    expect(out.map((e) => e.title)).toEqual(["carol"]);
  });

  it("a state filter still lets the rest of the query search text", () => {
    const out = rankEntries(entries, "state:done carol");
    expect(out.map((e) => e.title)).toEqual(["carol"]);
  });

  it("state-only queries keep every matching entry (no text drop)", () => {
    const out = rankEntries(entries, "state:done");
    expect(out.map((e) => e.title).sort()).toEqual(["carol", "dave"]);
  });

  it("empty query is unchanged (no regression)", () => {
    expect(rankEntries(entries, "")).toHaveLength(entries.length);
  });

  it("non-state queries behave exactly as before (no regression)", () => {
    const out = rankEntries(entries, "carol");
    expect(out[0].title).toBe("carol");
  });
});
