import { afterEach, describe, expect, it } from "vitest";
import { cleanup, render, screen } from "@testing-library/react";
import TwinWorkstationShell, {
  isSlotFilled,
  validateParentAssetId,
} from "./TwinWorkstationShell";

afterEach(() => {
  cleanup();
});

describe("validateParentAssetId", () => {
  it("requires non-empty", () => {
    expect(() => validateParentAssetId("  ")).toThrow(/parentAssetId/);
    expect(validateParentAssetId(" asset-1 ")).toBe("asset-1");
  });
});

describe("TwinWorkstationShell", () => {
  it("renders parent context and empty slots honestly", () => {
    render(<TwinWorkstationShell parentAssetId="asset-1" parentLabel="Paper A" />);
    expect(screen.getByTestId("twin-workstation-parent").textContent).toMatch(
      /asset-1/,
    );
    expect(screen.getByTestId("twin-workstation-parent").textContent).toMatch(
      /Paper A/,
    );
    expect(
      screen.getByTestId("twin-workstation-slot-notes").getAttribute("data-filled"),
    ).toBe("false");
    expect(
      screen.getByTestId("twin-workstation-slot-empty-notes").textContent,
    ).toMatch(/no invent/i);
  });

  it("renders injected slots", () => {
    render(
      <TwinWorkstationShell
        parentAssetId="asset-1"
        slots={{
          search: <div data-testid="injected-search">Search panel</div>,
          compose: <div data-testid="injected-compose">Compose panel</div>,
        }}
        slotOrder={["search", "compose", "notes"]}
      />,
    );
    expect(screen.getByTestId("injected-search").textContent).toMatch(
      /Search panel/,
    );
    expect(
      screen.getByTestId("twin-workstation-slot-search").getAttribute("data-filled"),
    ).toBe("true");
    expect(
      screen.getByTestId("twin-workstation-slot-notes").getAttribute("data-filled"),
    ).toBe("false");
  });

  it("fails closed on empty parent", () => {
    render(<TwinWorkstationShell parentAssetId="   " />);
    expect(screen.getByTestId("twin-workstation-error").textContent).toMatch(
      /parentAssetId/,
    );
    expect(screen.queryByTestId("twin-workstation-slots")).toBeNull();
  });

  it("treats false and empty string slots as empty (no invent filled)", () => {
    expect(isSlotFilled(false)).toBe(false);
    expect(isSlotFilled("")).toBe(false);
    expect(isSlotFilled("  ")).toBe(false);
    expect(isSlotFilled(0)).toBe(true);
    expect(isSlotFilled(Number.NaN)).toBe(true);
    expect(isSlotFilled(Number.POSITIVE_INFINITY)).toBe(true);
    expect(isSlotFilled(<span>x</span>)).toBe(true);
    render(
      <TwinWorkstationShell
        parentAssetId="asset-1"
        slots={{
          search: false,
          compose: "",
        }}
        slotOrder={["search", "compose"]}
      />,
    );
    expect(
      screen.getByTestId("twin-workstation-slot-search").getAttribute("data-filled"),
    ).toBe("false");
    expect(
      screen.getByTestId("twin-workstation-slot-empty-search"),
    ).toBeTruthy();
    expect(
      screen.getByTestId("twin-workstation-slot-compose").getAttribute("data-filled"),
    ).toBe("false");
  });
});
