import { readFileSync } from "node:fs";
import { resolve } from "node:path";
import { render } from "@testing-library/react";
import { MemoryRouter } from "react-router-dom";
import { describe, expect, it } from "vitest";

import SceneChrome from "../SceneChrome";
import { MODE_TAXONOMY } from "../workflowTaxonomy";
import { ResearchObservatoryAtmosphere } from "./ResearchObservatoryAtmosphere";

const researchRoutes = [
  "/",
  ...MODE_TAXONOMY.filter((mode) => mode.workflow === "research" && mode.route)
    .map((mode) => mode.route!.replace(/:[^/]+/g, "fixture")),
].filter(
  (route, index, routes) =>
    route !== "/brainstorm" && routes.indexOf(route) === index,
);

describe("ResearchObservatoryAtmosphere (SPR-25)", () => {
  it("is one decorative, pointer-inert image", () => {
    const { container } = render(<ResearchObservatoryAtmosphere />);
    const root = container.querySelector("[data-research-observatory-atmosphere]");
    const image = root?.querySelector("img");
    expect(root?.getAttribute("aria-hidden")).toBe("true");
    expect(root?.className).toContain("pointer-events-none");
    expect(root?.querySelectorAll("img")).toHaveLength(1);
    expect(image?.getAttribute("alt")).toBe("");
    expect(image?.getAttribute("draggable")).toBe("false");
  });

  it("ships a bounded WebP rather than the 2.1 MB provenance PNG", () => {
    const bytes = readFileSync(
      resolve("src/shell/atmosphere/research_observatory_environment_v1.webp"),
    );
    expect(bytes.subarray(0, 4).toString("ascii")).toBe("RIFF");
    expect(bytes.subarray(8, 12).toString("ascii")).toBe("WEBP");
    expect(bytes.byteLength).toBeLessThanOrEqual(128 * 1024);
  });

  it.each(researchRoutes)(
    "mounts on the Research taxonomy route %s",
    (route) => {
      const { container } = render(
        <MemoryRouter initialEntries={[route]}>
          <SceneChrome><p>Research HTML</p></SceneChrome>
        </MemoryRouter>,
      );
      expect(
        container.querySelector("[data-research-observatory-atmosphere]"),
      ).not.toBeNull();
    },
  );

  it("leaves shared routes bare", () => {
    const { getByText } = render(
      <MemoryRouter initialEntries={["/settings"]}>
        <SceneChrome><p>Shared HTML</p></SceneChrome>
      </MemoryRouter>,
    );
    expect(getByText("Shared HTML").parentElement?.className).toBe("");
  });

  it("keeps the real route HTML above the decorative layer", () => {
    const { getByText, container } = render(
      <MemoryRouter initialEntries={["/"]}>
        <SceneChrome><button type="button">Start research</button></SceneChrome>
      </MemoryRouter>,
    );
    expect(getByText("Start research").closest("[data-scene-chrome-content]")).not.toBeNull();
    const body = container.querySelector("[data-scene-chrome-body]");
    expect(body?.children[0]?.hasAttribute("data-research-observatory-atmosphere")).toBe(true);
    expect(body?.children[1]?.hasAttribute("data-scene-chrome-content")).toBe(true);
  });
});
