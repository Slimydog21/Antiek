/**
 * proseLayer.test.tsx — one prose layer for the three long-form surfaces
 * (design spec §3, audit-type-copy T2/T3/T4).
 *
 * Before this layer, Tailwind's preflight erased every heading, paragraph
 * gap and list marker in the Notebook editor, the Write editor and the
 * sanitized-HTML reader: h1 rendered at 16px/400 like body text and lists
 * had no markers. Lines ran 85-142 characters.
 *
 * jsdom does no layout, so this suite pins the WIRING and the RULES; the
 * rendered result (heading sizes, list markers, characters per line) is
 * measured in Chromium by the wave's rendered proof.
 */
import { readFileSync } from "node:fs";
import { dirname, join } from "node:path";
import { fileURLToPath } from "node:url";
import { afterEach, describe, expect, it, vi } from "vitest";
import { cleanup, render, waitFor } from "@testing-library/react";

vi.mock("../../lib/api", async (orig) => ({
  ...(await orig<typeof import("../../lib/api")>()),
  postTypedEvent: vi.fn().mockResolvedValue(undefined),
}));

import { WriteEditor } from "../../modes/Write/Editor/Editor";
import ReadingColumn from "./ReadingColumn";

const here = dirname(fileURLToPath(import.meta.url));
const css = readFileSync(join(here, "..", "..", "index.css"), "utf8").replace(/\/\*[\s\S]*?\*\//g, "");

/** Every declaration block whose selector list mentions `.prose-antiek` and `needle`. */
function rules(needle: RegExp): string[] {
  return [...css.matchAll(/([^{}]+)\{([^{}]*)\}/g)]
    .filter((m) => m[1].includes(".prose-antiek") && needle.test(m[1]))
    .map((m) => m[2]);
}
const decl = (body: string, prop: string) =>
  body.match(new RegExp(`(?:^|;|\\s)${prop}\\s*:\\s*([^;]+)`))?.[1].trim();

afterEach(() => cleanup());

describe("prose layer rules (index.css)", () => {
  it("caps the line at a 60-72 character measure", () => {
    // Charter's average glyph is 0.44em (measured in Chromium on the reader
    // route), so 60-72 characters is 26.4em-31.7em. The rendered proof
    // measures the characters per line directly.
    const root = rules(/\.prose-antiek\s*$/).join(";");
    const measure = decl(root, "max-width");
    expect(measure).toMatch(/^[\d.]+em$/);
    const em = parseFloat(measure!);
    expect(em * (1 / 0.44)).toBeGreaterThanOrEqual(60);
    expect(em * (1 / 0.44)).toBeLessThanOrEqual(72);
  });

  it("gives h1-h4 a real, descending scale above the body size", () => {
    const size = (h: string) => {
      const body = rules(new RegExp(`\\b${h}\\b`)).map((b) => decl(b, "font-size")).find(Boolean);
      expect(body, `${h} needs a font-size`).toBeTruthy();
      return parseFloat(body!);
    };
    const [h1, h2, h3, h4] = ["h1", "h2", "h3", "h4"].map(size);
    expect(h1).toBeGreaterThan(h2);
    expect(h2).toBeGreaterThan(h3);
    expect(h3).toBeGreaterThanOrEqual(h4);
    expect(h4).toBeGreaterThanOrEqual(1);
    const weight = rules(/h1/).map((b) => decl(b, "font-weight")).find(Boolean);
    expect(Number(weight)).toBeGreaterThanOrEqual(600);
  });

  it("restores list markers, paragraph rhythm, blockquote and code", () => {
    expect(rules(/\bul\b/).map((b) => decl(b, "list-style")).find(Boolean)).toMatch(/disc/);
    expect(rules(/\bol\b/).map((b) => decl(b, "list-style")).find(Boolean)).toMatch(/decimal/);
    expect(rules(/\+/).map((b) => decl(b, "margin-top")).find(Boolean)).toMatch(/em$/);
    expect(rules(/blockquote/).map((b) => decl(b, "border-left")).find(Boolean)).toBeTruthy();
    expect(rules(/\bcode\b/).map((b) => decl(b, "font-family")).find(Boolean)).toMatch(/JetBrains Mono/);
  });

  it("draws the editor placeholder the Placeholder extension asks for", () => {
    expect(rules(/is-editor-empty/).map((b) => decl(b, "content")).find(Boolean)).toBe("attr(data-placeholder)");
  });
});

describe("ReadingColumn — markdown heading level n renders as h(n+1)", () => {
  it("maps #, ## and ### to h2, h3 and h4 under the page's h1", () => {
    const { container } = render(
      <ReadingColumn assetId="doc-1" text={"# Book\n\nOne.\n\n## Chapter\n\nTwo.\n\n### Section\n\nThree."} />,
    );
    const tags = [...container.querySelectorAll("h1,h2,h3,h4,h5,h6")].map((h) => h.tagName.toLowerCase());
    expect(tags).toEqual(["h2", "h3", "h4"]);
  });

  it("sets both the markdown and the sanitized-HTML body in the prose layer", () => {
    const { container, rerender } = render(<ReadingColumn assetId="doc-1" text="Body." />);
    expect(container.querySelector("article")!.classList.contains("prose-antiek")).toBe(true);
    rerender(<ReadingColumn assetId={null} text="<h2>Imported</h2><p>Body.</p>" contentFormat="html" />);
    expect(container.querySelector("[data-antiek-html-body]")!.closest(".prose-antiek")).toBeTruthy();
  });
});

describe("the editors opt in", () => {
  it("the Write editor's editable root carries the prose layer", async () => {
    const { container } = render(
      <WriteEditor deliverableId="d-1" sectionId="s-1" initialContent="<h2>Draft</h2><p>Words.</p>" />,
    );
    await waitFor(() => expect(container.querySelector(".ProseMirror")).toBeTruthy());
    expect(container.querySelector(".ProseMirror")!.classList.contains("prose-antiek")).toBe(true);
  });

  it("the Notebook editor's editable root carries the prose layer", () => {
    const src = readFileSync(join(here, "..", "..", "modes", "Notebook", "Editor.tsx"), "utf8");
    const cls = src.match(/editorProps:\s*{\s*attributes:\s*{\s*class:\s*([^}]+)}/)?.[1] ?? "";
    expect(cls).toContain("prose-antiek");
    // The layer owns face, size and colour; the old ad-hoc body classes go.
    expect(cls).not.toMatch(/text-base|leading-relaxed/);
  });
});
