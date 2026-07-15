import { cleanup, render } from "@testing-library/react";
import { afterEach, beforeAll, describe, expect, it, vi } from "vitest";

vi.mock("../../workspace/PanelLayoutPanel", () => ({ PanelLayoutPanel: () => null }));
vi.mock("./Canvas/Canvas", () => ({ default: () => null }));
vi.mock("./BlockDetail", () => ({ default: () => null }));

const viewport = vi.hoisted(() => ({ tier: "xl" as "xl" | "sm" }));
vi.mock("../../workspace/useViewportTier", () => ({ useViewportTier: () => viewport.tier }));

import { PanelLayout } from "../../workspace/PanelLayout";
import { DeepResearchMissionControlFrame } from ".";

afterEach(cleanup);

beforeAll(() => {
  Object.defineProperty(window, "matchMedia", {
    configurable: true,
    value: () => ({
      matches: false,
      addEventListener: () => {},
      removeEventListener: () => {},
    }),
  });
});

function renderRoute(tier: "xl" | "sm") {
  viewport.tier = tier;
  return render(
    <PanelLayout
      mainSlot={(
        <DeepResearchMissionControlFrame phase="Ready">
          <p>Live research controls</p>
        </DeepResearchMissionControlFrame>
      )}
    />,
  );
}

describe("Deep Research routed landmark", () => {
  it.each(["xl", "sm"] as const)("has exactly one main landmark at the %s tier", (tier) => {
    const { container } = renderRoute(tier);
    expect(container.querySelectorAll("main")).toHaveLength(1);
    expect(container.querySelector("main .deep-research-mission-control")).toBeTruthy();
  });
});
