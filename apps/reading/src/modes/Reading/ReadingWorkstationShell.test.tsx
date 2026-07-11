import React from "react";
import { afterEach, describe, expect, it } from "vitest";
import { cleanup, render, screen } from "@testing-library/react";
import ReadingWorkstationShell, {
  isReadingSlotFilled,
  validateReadingAssetId,
} from "./ReadingWorkstationShell";

afterEach(() => {
  cleanup();
});

describe("validateReadingAssetId", () => {
  it("requires non-empty", () => {
    expect(() => validateReadingAssetId("  ")).toThrow(/assetId/);
    expect(validateReadingAssetId(" asset-1 ")).toBe("asset-1");
  });
});

describe("isReadingSlotFilled", () => {
  it("empty vs filled", () => {
    expect(isReadingSlotFilled(false)).toBe(false);
    expect(isReadingSlotFilled("")).toBe(false);
    expect(isReadingSlotFilled(0)).toBe(true);
    expect(isReadingSlotFilled(<span>x</span>)).toBe(true);
    expect(isReadingSlotFilled([])).toBe(false);
    expect(isReadingSlotFilled([""])).toBe(false);
    expect(isReadingSlotFilled([false, "x"])).toBe(true);
    expect(isReadingSlotFilled([[], [false, ""]])).toBe(false);
  });

  it("empty Fragment is not filled", () => {
    expect(isReadingSlotFilled(<></>)).toBe(false);
    expect(isReadingSlotFilled(<React.Fragment />)).toBe(false);
    expect(
      isReadingSlotFilled(
        <React.Fragment>
          <span>ok</span>
        </React.Fragment>,
      ),
    ).toBe(true);
  });
});

describe("ReadingWorkstationShell", () => {
  it("renders asset and empty slots honestly", () => {
    render(
      <ReadingWorkstationShell
        assetId="asset-1"
        assetLabel="Scaling laws paper"
      />,
    );
    expect(
      screen.getByTestId("reading-workstation-asset").textContent,
    ).toMatch(/asset-1/);
    expect(
      screen
        .getByTestId("reading-workstation-slot-floating_deep_research")
        .getAttribute("data-filled"),
    ).toBe("false");
    expect(
      screen.getByTestId(
        "reading-workstation-slot-empty-floating_deep_research",
      ).textContent,
    ).toMatch(/no invent/i);
    expect(
      screen
        .getByTestId("reading-workstation-slot-collective_pack")
        .getAttribute("data-filled"),
    ).toBe("false");
  });

  it("renders injected slots", () => {
    render(
      <ReadingWorkstationShell
        assetId="asset-1"
        slots={{
          floating_deep_research: (
            <div data-testid="injected-float">Float DR</div>
          ),
        }}
        slotOrder={["floating_deep_research", "draft_merge"]}
      />,
    );
    expect(screen.getByTestId("injected-float").textContent).toMatch(/Float DR/);
    expect(
      screen
        .getByTestId("reading-workstation-slot-floating_deep_research")
        .getAttribute("data-filled"),
    ).toBe("true");
    expect(
      screen
        .getByTestId("reading-workstation-slot-draft_merge")
        .getAttribute("data-filled"),
    ).toBe("false");
  });

  it("fails closed on empty asset", () => {
    render(<ReadingWorkstationShell assetId="   " />);
    expect(
      screen.getByTestId("reading-workstation-error").textContent,
    ).toMatch(/assetId/);
    expect(screen.queryByTestId("reading-workstation-slots")).toBeNull();
  });

  it("treats empty Fragment slot as empty", () => {
    render(
      <ReadingWorkstationShell
        assetId="asset-1"
        slots={{ html_reader: <></> }}
        slotOrder={["html_reader"]}
      />,
    );
    expect(
      screen
        .getByTestId("reading-workstation-slot-html_reader")
        .getAttribute("data-filled"),
    ).toBe("false");
  });
});
