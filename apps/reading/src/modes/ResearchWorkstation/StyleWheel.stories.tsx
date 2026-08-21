import type { Meta, StoryObj } from "@storybook/react";
import { expect, fn, userEvent, within } from "@storybook/test";
import StyleWheel from "./StyleWheel";

const originalFetch = window.fetch;

const meta = {
  title: "Research/StyleWheel",
  component: StyleWheel,
  parameters: { layout: "padded" },
  beforeEach: () => {
    window.fetch = fn(async (input: RequestInfo | URL, init?: RequestInit) => {
      const url = String(input);
      if (url.endsWith("/styles")) return new Response(JSON.stringify({ styles: [
        { name: "antiek", label: "Antiek", description: "A quiet, source-first reading surface.", builtin: true, source_fidelity: true, theme_css: "" },
        { name: "folio", label: "Folio", description: "More editorial space for long-form reading.", builtin: true, source_fidelity: false, theme_css: "" },
        { name: "field-notes", label: "Field notes", description: "A personal fork for working copies.", builtin: false, source_fidelity: true, theme_css: "" },
      ] }), { headers: { "Content-Type": "application/json" } });
      if (url.includes("/render")) {
        const style = new URL(url, window.location.origin).searchParams.get("style") ?? "antiek";
        return new Response("<!doctype html><html><body><main><h1>Research artifact</h1><p>Evidence remains readable inside the isolated preview.</p></main></body></html>", { headers: { "Content-Type": "text/html", "X-Artifact-ID": "artifact-story", "X-Artifact-Style": style, "X-Artifact-Version": init?.method === "POST" ? "4" : "preview", "X-Content-SHA256": "5".repeat(64), "X-Source-SHA256": "6".repeat(64) } });
      }
      return new Response("not found", { status: 404 });
    }) as typeof window.fetch;
    return () => { window.fetch = originalFetch; };
  },
} satisfies Meta<typeof StyleWheel>;

export default meta;
type Story = StoryObj<typeof meta>;

export const Ready: Story = {
  args: { artifactId: "artifact-story", investigationId: "investigation-story" },
  play: async ({ canvasElement }) => {
    const canvas = within(canvasElement);
    await expect(await canvas.findByRole("option", { name: /Antiek/ })).toHaveAttribute("aria-selected", "true");
    await userEvent.click(canvas.getByRole("option", { name: /Folio/ }));
    await expect(canvas.getByRole("option", { name: /Folio/ })).toHaveAttribute("aria-selected", "true");
  },
};
