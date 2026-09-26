// @vitest-environment node
/**
 * containerVariants.test.ts — cockpit repair round 1, critic H1.
 *
 * The reader's side columns must answer to the reader's own width, not the
 * viewport: in the inset preset a 1024 px viewport gives the reader a
 * ~666 px pane, and viewport breakpoints (md:/lg:) put a 256 px TOC and a
 * 320 px notes column beside ~42 px of text. The reader root is a CSS
 * container (`container-reader`) and its columns use `reader-md:` /
 * `reader-lg:`, which the Tailwind config must compile to real container
 * queries. This runs the project's own Tailwind config over those classes,
 * so a class that compiles to nothing fails here, not on the operator's
 * screen.
 */
import { describe, expect, it } from "vitest";
import postcss from "postcss";
import tailwindcss, { type Config } from "tailwindcss";

/** The project's own (untyped, ESM) Tailwind config. */
const CONFIG_PATH = "../../tailwind.config.js";

async function compile(html: string): Promise<string> {
  const { default: config } = (await import(/* @vite-ignore */ CONFIG_PATH)) as { default: Config };
  const result = await postcss([
    tailwindcss({ ...config, content: [{ raw: html, extension: "html" }] }),
  ]).process("@tailwind utilities;", { from: undefined });
  return result.css.replace(/\s+/g, " ");
}

describe("the reader container variants", () => {
  it("container-reader declares an inline-size container named reader", async () => {
    const css = await compile('<div class="container-reader"></div>');
    expect(css).toMatch(/\.container-reader \{[^}]*container-type: inline-size/);
    expect(css).toMatch(/\.container-reader \{[^}]*container-name: reader/);
  });

  it("reader-md: and reader-lg: compile to container queries at 768 and 1024 px", async () => {
    const css = await compile('<aside class="hidden reader-md:block reader-lg:flex"></aside>');
    expect(css).toContain("@container reader (min-width: 768px)");
    expect(css).toContain("@container reader (min-width: 1024px)");
    expect(css).toMatch(/@container reader \(min-width: 768px\) \{ \.reader-md\\:block \{ display: block/);
    expect(css).toMatch(/@container reader \(min-width: 1024px\) \{ \.reader-lg\\:flex \{ display: flex/);
  });
});
