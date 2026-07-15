import { readFileSync } from "node:fs";
import { resolve } from "node:path";
import { render } from "@testing-library/react";
import { MemoryRouter } from "react-router-dom";
import { describe, expect, it } from "vitest";

import SceneChrome from "../SceneChrome";
import { BrainstormFjordAtmosphere } from "./BrainstormFjordAtmosphere";

describe("BrainstormFjordAtmosphere (SPR-38)", () => {
  it("is one decorative, pointer-inert image", () => {
    const { container } = render(<BrainstormFjordAtmosphere />);
    const root = container.querySelector("[data-brainstorm-fjord-atmosphere]");
    const image = root?.querySelector("img");
    expect(root?.getAttribute("aria-hidden")).toBe("true");
    expect(root?.className).toContain("pointer-events-none");
    expect(root?.querySelectorAll("img")).toHaveLength(1);
    expect(image?.getAttribute("alt")).toBe("");
    expect(image?.getAttribute("draggable")).toBe("false");
  });

  it("ships a bounded WebP while retaining the authored master", () => {
    const runtime = readFileSync(
      resolve("src/shell/atmosphere/brainstorm_fjord_idea_coast_v1.webp"),
    );
    const master = readFileSync(
      resolve("src/shell/atmosphere/assets/brainstorm_fjord_idea_coast_v1_master.png"),
    );
    expect(runtime.subarray(0, 4).toString("ascii")).toBe("RIFF");
    expect(runtime.subarray(8, 12).toString("ascii")).toBe("WEBP");
    expect(runtime.byteLength).toBeLessThanOrEqual(128 * 1024);
    expect(master.subarray(1, 4).toString("ascii")).toBe("PNG");
  });

  it("mounts only on Brainstorm while preserving Research atmosphere elsewhere", () => {
    const brainstorm = render(
      <MemoryRouter initialEntries={["/brainstorm"]}>
        <SceneChrome><p>Brainstorm HTML</p></SceneChrome>
      </MemoryRouter>,
    );
    expect(
      brainstorm.container.querySelector("[data-brainstorm-fjord-atmosphere]"),
    ).not.toBeNull();
    expect(
      brainstorm.container.querySelector("[data-research-observatory-atmosphere]"),
    ).toBeNull();
    brainstorm.unmount();

    const research = render(
      <MemoryRouter initialEntries={["/"]}>
        <SceneChrome><p>Research HTML</p></SceneChrome>
      </MemoryRouter>,
    );
    expect(
      research.container.querySelector("[data-research-observatory-atmosphere]"),
    ).not.toBeNull();
    expect(
      research.container.querySelector("[data-brainstorm-fjord-atmosphere]"),
    ).toBeNull();
  });

  it("keeps the real Brainstorm HTML above the decorative layer", () => {
    const { getByRole, container } = render(
      <MemoryRouter initialEntries={["/brainstorm"]}>
        <SceneChrome><button type="button">Begin brainstorming</button></SceneChrome>
      </MemoryRouter>,
    );
    expect(
      getByRole("button", { name: "Begin brainstorming" }).closest(
        "[data-scene-chrome-content]",
      ),
    ).not.toBeNull();
    const body = container.querySelector("[data-scene-chrome-body]");
    expect(body?.children[0]?.hasAttribute("data-brainstorm-fjord-atmosphere")).toBe(true);
    expect(body?.children[1]?.hasAttribute("data-scene-chrome-content")).toBe(true);
    expect(body?.children[1]?.className).toContain("bg-glass");
    expect(body?.children[1]?.className).not.toContain("backdrop-blur-glass");
  });
});
