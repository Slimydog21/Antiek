import { readFileSync } from "node:fs";
import { dirname, join } from "node:path";
import { fileURLToPath } from "node:url";
import { cleanup, fireEvent, render, screen } from "@testing-library/react";
import { afterEach, describe, expect, it, vi } from "vitest";

import type { MultimediaAssetList } from "../../api/multimedia";
import Multimedia from "./index";

const css = readFileSync(
  join(
    dirname(fileURLToPath(import.meta.url)),
    "multimedia-production-bay.css",
  ),
  "utf8",
);
const emptyList: MultimediaAssetList = { assets: [], count: 0 };

afterEach(cleanup);

describe("Multimedia production bay shell", () => {
  it("renders one landmark plus real inert decorative layers", async () => {
    render(<Multimedia loadAssets={async () => emptyList} />);

    expect(screen.getAllByRole("main")).toHaveLength(1);
    const environment = document.querySelector<HTMLImageElement>(
      ".multimedia-production-bay__environment",
    );
    expect(environment?.alt).toBe("");
    expect(environment?.getAttribute("aria-hidden")).toBe("true");
    expect(
      document.querySelector(".multimedia-production-bay__veil"),
    ).not.toBeNull();
    expect(css).toMatch(
      /\.multimedia-production-bay__environment,[\s\S]*?pointer-events:\s*none/,
    );
  });

  it("uses the injected list transport at mount without calling fetch", async () => {
    const loadAssets = vi.fn(async () => emptyList);
    const fetchSpy = vi.spyOn(globalThis, "fetch");

    render(<Multimedia loadAssets={loadAssets} />);

    expect(await screen.findByText("No plan reviewed yet")).toBeTruthy();
    expect(loadAssets).toHaveBeenCalledTimes(1);
    expect(fetchSpy).not.toHaveBeenCalled();
    fetchSpy.mockRestore();
  });

  it("keeps review fixtures inert when a reviewer tries an execution control", async () => {
    const fetchSpy = vi.spyOn(globalThis, "fetch");

    render(
      <Multimedia
        loadAssets={async () => emptyList}
        executionEnabled={false}
      />,
    );

    const review = await screen.findByRole("button", { name: "Review plan" });
    expect((review as HTMLButtonElement).disabled).toBe(true);
    fireEvent.click(review);
    expect(fetchSpy).not.toHaveBeenCalled();
    fetchSpy.mockRestore();
  });

  it("keeps a safe, actionable surface when the list transport fails", async () => {
    render(
      <Multimedia
        loadAssets={async () => {
          throw new Error("fixture transport unavailable");
        }}
      />,
    );

    expect((await screen.findByRole("alert")).textContent).toContain(
      "assets will not persist",
    );
    expect(screen.getByRole("button", { name: "Review plan" })).toBeTruthy();
  });

  it("declares narrow and reduced-motion containment without hiding content", () => {
    expect(css).toMatch(/@media \(max-width:\s*767px\)/);
    expect(css).toMatch(/overflow-wrap:\s*anywhere/);
    expect(css).toMatch(/@media \(prefers-reduced-motion:\s*reduce\)/);
    expect(css).not.toMatch(/display:\s*none/);
  });
});
