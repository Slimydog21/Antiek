/**
 * modeNavigation.test.ts — lane A stage B2-8: a research spun from a reader
 * lives at /inv/<id>?m=reading, and every in-app navigation made from inside
 * it keeps that mode. One helper decides (inMode); the ResearchWorkstation
 * surfaces route their navigations through it (useModeNavigate, ModeLink, ModeNavLink).
 */
import { readFileSync } from "node:fs";
import { dirname, join } from "node:path";
import { fileURLToPath } from "node:url";

import { describe, expect, it } from "vitest";

import { inMode } from "./mothershipForPath";

describe("inMode: the one mode-preserving path helper", () => {
  it("carries the selected project through mode links without replacing an explicit target selection", () => {
    expect(inMode("/inv/thread", "?project=chosen", "/read/doc")).toBe("/inv/thread?project=chosen&m=reading");
    expect(inMode("/read/doc#page", "?project=chosen", "/read/source")).toBe("/read/doc?project=chosen#page");
    expect(inMode("/inv/thread?project=other", "?project=chosen", "/inv/source")).toBe("/inv/thread?project=other");
  });
  it("carries ?m to a route whose own mode differs", () => {
    expect(inMode("/inv/child-1", "?m=reading")).toBe("/inv/child-1?m=reading");
    expect(inMode("/notebook/auto/inv-1", "?m=writing")).toBe("/notebook/auto/inv-1?m=writing");
  });

  it("leaves a route alone when its own mode already matches, or no mode is pinned", () => {
    expect(inMode("/read/doc-2", "?m=reading")).toBe("/read/doc-2");
    expect(inMode("/inv/child-1", "?m=research")).toBe("/inv/child-1");
    // Neither a pinned mode nor a page path: nothing to keep.
    expect(inMode("/inv/child-1", "")).toBe("/inv/child-1");
    expect(inMode("/inv/child-1", "?talk=1")).toBe("/inv/child-1");
  });

  it("without a pinned ?m, the page's own path decides its mode (R2-H1)", () => {
    // From a reader with no ?m, a research opens in reading, never by
    // switching the operator into the research tree.
    expect(inMode("/inv/child-1", "", "/read/origin-of-species")).toBe("/inv/child-1?m=reading");
    expect(inMode("/inv/child-1", "", "/inv/parent")).toBe("/inv/child-1");
    expect(inMode("/inv/child-1", "?m=writing", "/read/doc")).toBe("/inv/child-1?m=writing");
  });

  it("merges with a query the target already has, and never overrides an explicit ?m", () => {
    expect(inMode("/inv/c?x=1", "?m=reading")).toBe("/inv/c?x=1&m=reading");
    expect(inMode("/read/d?m=research", "?m=writing")).toBe("/read/d?m=research");
  });

  it("keeps a hash", () => {
    expect(inMode("/inv/c#top", "?m=reading")).toBe("/inv/c?m=reading#top");
  });
});

describe("the ResearchWorkstation's in-page surfaces navigate through it", () => {
  const here = dirname(fileURLToPath(import.meta.url));
  const files = [
    "index.tsx",
    "SuggestedResearch.tsx",
    "ChatInputArea.tsx",
    "InvestigationSidebar.tsx",
    "ChaseSlideOver.tsx",
    "ChaseThread.tsx",
    "DistillView.tsx",
    "StartResearch.tsx",
  ];
  it.each(files)("%s uses no raw useNavigate or <Link to>", (file) => {
    const src = readFileSync(join(here, "../modes/ResearchWorkstation", file), "utf8");
    expect(src).not.toMatch(/\buseNavigate\s*\(/);
    expect(src).not.toMatch(/<(Nav)?Link\b/);
  });
});
