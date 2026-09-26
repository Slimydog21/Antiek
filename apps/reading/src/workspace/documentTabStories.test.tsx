/**
 * The document-strip stories mount and show what each claims: every story in
 * DocumentTabStrip.stories.tsx is rendered here with its own args, so a story
 * that throws, or drifts from its caption, fails the suite (Storybook itself
 * is not in the test run).
 */
import { afterEach, describe, expect, it } from "vitest";
import { cleanup, render } from "@testing-library/react";

import * as stories from "./DocumentTabStrip.stories";
import { StoryStrip } from "./documentTabStories";

type StoryModule = typeof stories;
type Args = Parameters<typeof StoryStrip>[0];

afterEach(() => {
  cleanup();
  document.body.innerHTML = "";
});

function mount(name: keyof StoryModule) {
  const story = stories[name] as { args?: Partial<Args> };
  const args = { ...stories.default.args, ...story.args } as Args;
  return render(<StoryStrip {...args} />);
}

const q = (sel: string) => document.querySelectorAll(sel);

describe("DocumentTabStrip stories", () => {
  const names = Object.keys(stories).filter((k) => k !== "default") as (keyof StoryModule)[];

  it("every story mounts", () => {
    expect(names.length).toBeGreaterThanOrEqual(19);
    for (const name of names) {
      mount(name);
      expect(document.querySelector("[data-document-strip]"), String(name)).toBeTruthy();
      cleanup();
    }
  });

  it("depth 1: no path header, three top-level tabs, a ↳2 chip", () => {
    mount("Depth1Day");
    expect(q("[data-tab-path]")).toHaveLength(0);
    expect(q("[role='tab']")).toHaveLength(3);
    expect(document.querySelector("[data-children-chip]")!.textContent).toContain("2");
  });

  it("depth 4: the whole path; depth 12 and 40 compress in the middle", () => {
    mount("Depth4Day");
    expect(q("[data-tab-path] [data-crumb]")).toHaveLength(4);
    cleanup();
    for (const name of ["Depth12Night", "Depth40Day"] as const) {
      mount(name);
      expect(q("[data-tab-path] [data-crumb]"), name).toHaveLength(3);
      expect(document.querySelector("[data-crumb-ellipsis]")!.getAttribute("aria-label")).toMatch(/\d+ tabs/);
      cleanup();
    }
  });

  it("no story label is a raw ref", () => {
    for (const name of ["Depth40Day", "Siblings174Day", "TreePanelDepth40Night"] as const) {
      mount(name);
      const text = document.querySelector("[data-document-strip]")!.textContent!;
      expect(text, name).not.toMatch(/\/inv\/|book-\d|cite-\d|\/write\//);
      cleanup();
    }
  });

  it("174 siblings: all in the tablist, the active one selected", () => {
    mount("Siblings174Night");
    const tabs = q("[role='tablist'] [role='tab']");
    expect(tabs).toHaveLength(174);
    expect(q("[role='tab'][aria-selected='true']")).toHaveLength(1);
  });

  it("the depth-40 panel caps the indent and badges depth; the 174 panel is windowed", () => {
    mount("TreePanelDepth40Night");
    const badges = Array.from(q("[data-depth-badge]")).map((b) => b.textContent);
    expect(badges.length).toBeGreaterThan(0);
    expect(badges.every((b) => /^d([7-9]|[1-9]\d)$/.test(b ?? ""))).toBe(true);
    cleanup();
    mount("TreePanelSiblings174Day");
    const rows = q("[role='treeitem']");
    expect(rows.length).toBeLessThan(80);
    expect(rows[1].getAttribute("aria-setsize")).toBe("174");
  });

  it("a Write section tab is named by its heading and never 'opens as window'", () => {
    for (const name of ["WriteSectionDay", "WriteSectionNight"] as const) {
      mount(name);
      const strip = document.querySelector<HTMLElement>("[data-document-strip]")!;
      expect(strip.querySelector("[role='tab'][aria-selected='true']")!.textContent, name).toContain("What Lack measured");
      expect(strip.querySelector("[data-tab-bridge]"), name).toBeNull();
      expect(strip.textContent, name).not.toMatch(/opens as window|section:/);
      cleanup();
    }
  });

  it("loading, error and empty render the shared primitives", () => {
    mount("LoadingDay");
    expect(document.querySelector("[data-document-strip] [role='status']")!.textContent).toMatch(/Opening your tabs/);
    cleanup();
    mount("ErrorNight");
    const alert = document.querySelector("[data-document-strip] [role='alert']")!;
    expect(alert.textContent).toContain("Try again");
    expect(alert.textContent).not.toContain("HTTP 503");
    cleanup();
    mount("EmptyPanelDay");
    expect(document.querySelector("[data-tab-tree-panel] .st")!.textContent).toContain("No open tabs");
  });
});
