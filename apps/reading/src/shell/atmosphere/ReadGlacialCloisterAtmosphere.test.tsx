import { readFileSync } from "node:fs";
import { resolve } from "node:path";
import { render } from "@testing-library/react";
import { MemoryRouter } from "react-router-dom";
import { describe, expect, it } from "vitest";

import SceneChrome from "../SceneChrome";
import { MODE_TAXONOMY } from "../workflowTaxonomy";
import { ReadGlacialCloisterAtmosphere } from "./ReadGlacialCloisterAtmosphere";

const readRoutes = MODE_TAXONOMY.filter((mode) => mode.workflow === "read" && mode.route)
  .map((mode) => mode.route!.replace(/:[^/]+/g, "fixture"));

describe("ReadGlacialCloisterAtmosphere (SPR-28)", () => {
  it("is one decorative, pointer-inert image", () => {
    const { container } = render(<ReadGlacialCloisterAtmosphere />);
    const root = container.querySelector("[data-read-glacial-cloister-atmosphere]");
    const image = root?.querySelector("img");
    expect(root?.getAttribute("aria-hidden")).toBe("true");
    expect(root?.className).toContain("pointer-events-none");
    expect(root?.querySelectorAll("img")).toHaveLength(1);
    expect(image?.getAttribute("alt")).toBe("");
    expect(image?.getAttribute("draggable")).toBe("false");
  });

  it("ships a bounded WebP", () => {
    const bytes = readFileSync(resolve("src/shell/atmosphere/read_glacial_cloister_environment_v1.webp"));
    expect(bytes.subarray(0, 4).toString("ascii")).toBe("RIFF");
    expect(bytes.subarray(8, 12).toString("ascii")).toBe("WEBP");
    expect(bytes.byteLength).toBeLessThanOrEqual(128 * 1024);
  });

  it.each(readRoutes)("mounts on taxonomy Read route %s", (route) => {
    const { container } = render(<MemoryRouter initialEntries={[route]}><SceneChrome><p>Read HTML</p></SceneChrome></MemoryRouter>);
    expect(container.querySelector("[data-read-glacial-cloister-atmosphere]")).not.toBeNull();
    expect(container.querySelector("[data-research-observatory-atmosphere]")).toBeNull();
    expect(container.querySelector("[data-write-scriptorium-atmosphere]")).toBeNull();
    expect(container.querySelector("[data-speak-listening-room-atmosphere]")).toBeNull();
  });

  it.each(["/", "/write", "/speak"])("does not mount on non-Read route %s", (route) => {
    const { container } = render(<MemoryRouter initialEntries={[route]}><SceneChrome><p>Other HTML</p></SceneChrome></MemoryRouter>);
    expect(container.querySelector("[data-read-glacial-cloister-atmosphere]")).toBeNull();
  });

  it("keeps real route HTML above the decorative layer", () => {
    const { getByText, container } = render(<MemoryRouter initialEntries={["/library"]}><SceneChrome><button type="button">Open a book</button></SceneChrome></MemoryRouter>);
    expect(getByText("Open a book").closest("[data-scene-chrome-content]")).not.toBeNull();
    const body = container.querySelector("[data-scene-chrome-body]");
    expect(body?.children[0]?.hasAttribute("data-read-glacial-cloister-atmosphere")).toBe(true);
    expect(body?.children[1]?.hasAttribute("data-scene-chrome-content")).toBe(true);
  });
});
