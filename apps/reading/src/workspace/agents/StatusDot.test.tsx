/**
 * StatusDot.test.tsx — SPR-10 M3: colour + word, never colour alone; every
 * state differs by SHAPE where the word is hidden; the accessible name is
 * announced once; tokens resolve only through --state-* and the island
 * ring token (no hex, no --sun).
 */
import { afterEach, describe, expect, it } from "vitest";
import { cleanup, render } from "@testing-library/react";

import { AGENT_STATUSES, type AgentStatus } from "./agentStatus";
import { ISLAND_RING_TOKEN, STATUS_WORD, StatusDot } from "./StatusDot";

afterEach(cleanup);

const VARIANTS = ["dot", "symbol"] as const;
const GROUNDS = ["paper", "island"] as const;

function mount(status: AgentStatus, variant: (typeof VARIANTS)[number], ground: (typeof GROUNDS)[number], word: "visible" | "sr" = "sr", reason?: string) {
  const { container } = render(<StatusDot status={status} variant={variant} ground={ground} word={word} reason={reason} />);
  const root = container.querySelector('[role="img"]') as HTMLElement;
  const glyph = root.firstElementChild as HTMLElement;
  const wordEl = root.lastElementChild as HTMLElement;
  return { root, glyph, wordEl };
}

describe("every state × variant × ground", () => {
  for (const status of AGENT_STATUSES) for (const variant of VARIANTS) for (const ground of GROUNDS) {
    it(`${status}/${variant}/${ground}: role img, aria-label is the word, the word is in the DOM once, no duplicated accessible text`, () => {
      const { root, glyph, wordEl } = mount(status, variant, ground, "sr");
      expect(root.getAttribute("aria-label")).toBe(STATUS_WORD[status]);
      expect(glyph.getAttribute("aria-hidden")).toBe("true");
      expect(wordEl.textContent).toBe(STATUS_WORD[status]);
      expect(wordEl.className).toContain("sr-only");
      expect(root.textContent?.split(STATUS_WORD[status]).length).toBe(2);
      // With the word visible it is still hidden from the accessible name (announced once).
      const vis = mount(status, variant, ground, "visible");
      expect(vis.wordEl.getAttribute("aria-hidden")).toBe("true");
      expect(vis.wordEl.className).not.toContain("sr-only");
      expect(vis.root.getAttribute("aria-label")).toBe(STATUS_WORD[status]);
    });
  }

  it("a reason joins the accessible name once: 'idle, stopped'", () => {
    const { root } = mount("idle", "dot", "paper", "sr", "stopped");
    expect(root.getAttribute("aria-label")).toBe("idle, stopped");
  });
});

describe("shape, not hue or motion", () => {
  it("working and done differ by shape in the dot variant (hollow ring vs solid) and in the symbol variant (◐ vs ✓)", () => {
    const w = mount("working", "dot", "paper");
    const d = mount("done", "dot", "paper");
    expect(w.glyph.className).toContain("border-2");
    expect(w.glyph.className).toContain("bg-transparent");
    expect(d.glyph.className).toContain("bg-[var(--state-done)]");
    expect(d.glyph.className).not.toContain("bg-transparent");
    expect(mount("working", "symbol", "paper").glyph.textContent).toBe("◐");
    expect(mount("done", "symbol", "paper").glyph.textContent).toBe("✓");
    expect(mount("blocked", "symbol", "paper").glyph.textContent).toBe("×");
    expect(mount("idle", "symbol", "paper").glyph.textContent).toBe("○");
    expect(mount("unknown", "symbol", "paper").glyph.textContent).toBe("·");
  });

  it("every state has a distinct shape signature where the word is hidden", () => {
    const sig = (s: AgentStatus) => {
      const g = mount(s, "dot", "paper").glyph.className;
      return [/border-2/.test(g), /bg-transparent/.test(g), /ring-2/.test(g), /w-1\b|w-\[4px\]/.test(g)].join(",");
    };
    const sigs = AGENT_STATUSES.map(sig);
    expect(new Set(sigs).size).toBe(AGENT_STATUSES.length - 1);
    // blocked and done are both solid; done wears the halo (ring-2), blocked does not.
    expect(sig("blocked")).not.toBe(sig("done"));
    expect(mount("blocked", "dot", "paper").glyph.className).not.toContain("ring-2");
    expect(mount("done", "dot", "paper").glyph.className).toContain("ring-2");
  });

  it("under prefers-reduced-motion the working node's animation class is neutralised (motion-reduce:animate-none) and the shape still differs", () => {
    const w = mount("working", "dot", "paper").glyph.className;
    expect(w).toContain("animate-pulse");
    expect(w).toContain("motion-reduce:animate-none");
    const ws = mount("working", "symbol", "paper").glyph.className;
    expect(ws).toContain("animate-spin");
    expect(ws).toContain("motion-reduce:animate-none");
    for (const s of AGENT_STATUSES.filter((x) => x !== "working")) {
      expect(mount(s, "dot", "paper").glyph.className).not.toMatch(/animate-(pulse|spin)/);
    }
  });

  it("tokens resolve only through --state-* and the island ring token: no hex, no --sun, no text-2/success", () => {
    for (const status of AGENT_STATUSES) for (const variant of VARIANTS) for (const ground of GROUNDS) {
      const cls = mount(status, variant, ground).glyph.className;
      expect(cls).not.toMatch(/#[0-9a-fA-F]{3,8}/);
      expect(cls).not.toMatch(/--sun\b|--sun\)|--success|--text-2|--text-3/);
      for (const v of cls.match(/var\(--[a-z0-9-]+\)/g) ?? []) {
        expect(v === `var(${ISLAND_RING_TOKEN})` || /^var\(--state-(blocked|working|done|stopped|muted)\)$/.test(v), v).toBe(true);
      }
    }
    expect(ISLAND_RING_TOKEN).toBe("--fixed-paper");
    expect(mount("blocked", "dot", "island").glyph.className).toContain(`ring-[var(${ISLAND_RING_TOKEN})]`);
    expect(mount("blocked", "dot", "paper").glyph.className).not.toContain(ISLAND_RING_TOKEN);
  });
});
