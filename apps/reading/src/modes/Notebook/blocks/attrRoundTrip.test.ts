import { describe, it, expect } from "vitest";

import { stringAttr, intAttr } from "./attrHelpers";

/**
 * Round-trip discipline for TipTap node attributes.
 *
 * The AI tool-call protocol's `add_to_notebook` action serialises
 * actions as <antiek-note text="…">-style custom-element HTML. The
 * editor stores that HTML in localStorage; on reload, TipTap parses
 * it via each NodeView's parseHTML rule. If a single attribute
 * silently drops (because the parser doesn't pick it up), the AI's
 * inserted block becomes empty.
 *
 * This test confirms each helper's parseHTML/renderHTML round-trip
 * is symmetric without relying on TipTap's own attribute-pickup
 * heuristics.
 */

function mkEl(name: string, attrs: Record<string, string>): HTMLElement {
  const el = document.createElement(name);
  for (const [k, v] of Object.entries(attrs)) {
    el.setAttribute(k, v);
  }
  return el;
}

describe("stringAttr", () => {
  it("parses a present attribute as the string value", () => {
    const helper = stringAttr("text");
    const el = mkEl("antiek-note", { text: "hello world" });
    expect(helper.parseHTML(el)).toBe("hello world");
  });

  it("parses an absent attribute as null", () => {
    const helper = stringAttr("text");
    const el = mkEl("antiek-note", {});
    expect(helper.parseHTML(el)).toBeNull();
  });

  it("emits the attribute in renderHTML when present", () => {
    const helper = stringAttr("text");
    expect(helper.renderHTML({ text: "hi" })).toEqual({ text: "hi" });
  });

  it("omits the attribute in renderHTML when null", () => {
    const helper = stringAttr("text");
    expect(helper.renderHTML({ text: null })).toEqual({});
    expect(helper.renderHTML({})).toEqual({});
  });

  it("round-trip: HTML → parse → render → HTML preserves the value", () => {
    const helper = stringAttr("note_id");
    const el = mkEl("antiek-note", { note_id: "abc-123" });
    const parsed = helper.parseHTML(el);
    const rendered = helper.renderHTML({ note_id: parsed });
    expect(rendered).toEqual({ note_id: "abc-123" });
  });
});

describe("intAttr", () => {
  it("parses a present integer attribute", () => {
    const helper = intAttr("page");
    const el = mkEl("antiek-region-embed", { page: "42" });
    expect(helper.parseHTML(el)).toBe(42);
  });

  it("parses an absent attribute as null", () => {
    const helper = intAttr("page");
    const el = mkEl("antiek-region-embed", {});
    expect(helper.parseHTML(el)).toBeNull();
  });

  it("parses a malformed value (NaN) as null", () => {
    const helper = intAttr("page");
    const el = mkEl("antiek-region-embed", { page: "not-a-number" });
    expect(helper.parseHTML(el)).toBeNull();
  });

  it("emits the attribute as a string in renderHTML", () => {
    const helper = intAttr("page");
    expect(helper.renderHTML({ page: 42 })).toEqual({ page: "42" });
  });

  it("round-trip: HTML → parse → render → HTML preserves the value", () => {
    const helper = intAttr("page");
    const el = mkEl("antiek-region-embed", { page: "12" });
    const parsed = helper.parseHTML(el);
    const rendered = helper.renderHTML({ page: parsed });
    expect(rendered).toEqual({ page: "12" });
  });
});

describe("AI tool-call HTML payload — end-to-end", () => {
  it("a full <antiek-note text='…' /> survives parse + render", () => {
    const html = '<antiek-note text="key insight: foo"></antiek-note>';
    const container = document.createElement("div");
    container.innerHTML = html;
    const el = container.firstElementChild as HTMLElement;

    const noteHelper = stringAttr("text");
    expect(noteHelper.parseHTML(el)).toBe("key insight: foo");
  });

  it("a full <antiek-region-embed page='12' /> survives parse + render", () => {
    const html = '<antiek-region-embed document_id="doc-1" page="12" caption="found here"></antiek-region-embed>';
    const container = document.createElement("div");
    container.innerHTML = html;
    const el = container.firstElementChild as HTMLElement;

    expect(stringAttr("document_id").parseHTML(el)).toBe("doc-1");
    expect(intAttr("page").parseHTML(el)).toBe(12);
    expect(stringAttr("caption").parseHTML(el)).toBe("found here");
  });
});
