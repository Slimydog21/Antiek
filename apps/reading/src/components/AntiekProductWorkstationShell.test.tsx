import React from "react";
import { afterEach, describe, expect, it } from "vitest";
import { cleanup, render, screen } from "@testing-library/react";
import AntiekProductWorkstationShell, {
  isProductSlotFilled,
  validateProductOperatorId,
} from "./AntiekProductWorkstationShell";

afterEach(() => {
  cleanup();
});

describe("validateProductOperatorId", () => {
  it("requires non-empty", () => {
    expect(() => validateProductOperatorId("  ")).toThrow(/operatorId/);
    expect(validateProductOperatorId(" op-1 ")).toBe("op-1");
  });
});

describe("isProductSlotFilled", () => {
  it("empty vs filled including Fragment", () => {
    expect(isProductSlotFilled(false)).toBe(false);
    expect(isProductSlotFilled("")).toBe(false);
    expect(isProductSlotFilled([])).toBe(false);
    expect(isProductSlotFilled(<></>)).toBe(false);
    expect(isProductSlotFilled(<React.Fragment />)).toBe(false);
    expect(isProductSlotFilled(<span>x</span>)).toBe(true);
    expect(
      isProductSlotFilled(
        <React.Fragment>
          <span>ok</span>
        </React.Fragment>,
      ),
    ).toBe(true);
  });
});

describe("AntiekProductWorkstationShell", () => {
  it("renders operator and empty slots honestly", () => {
    render(
      <AntiekProductWorkstationShell
        operatorId="op-1"
        operatorLabel="Primary"
      />,
    );
    expect(
      screen.getByTestId("antiek-product-workstation-operator").textContent,
    ).toMatch(/op-1/);
    expect(
      screen
        .getByTestId("antiek-product-workstation-slot-research")
        .getAttribute("data-filled"),
    ).toBe("false");
    expect(
      screen.getByTestId(
        "antiek-product-workstation-slot-empty-midnight_oil",
      ).textContent,
    ).toMatch(/no invent/i);
  });

  it("renders injected slots", () => {
    render(
      <AntiekProductWorkstationShell
        operatorId="op-1"
        slots={{
          reading: <div data-testid="injected-reading">Reading shell</div>,
        }}
        slotOrder={["reading", "settings"]}
      />,
    );
    expect(screen.getByTestId("injected-reading").textContent).toMatch(
      /Reading shell/,
    );
    expect(
      screen
        .getByTestId("antiek-product-workstation-slot-reading")
        .getAttribute("data-filled"),
    ).toBe("true");
    expect(
      screen
        .getByTestId("antiek-product-workstation-slot-settings")
        .getAttribute("data-filled"),
    ).toBe("false");
  });

  it("fails closed on empty operator", () => {
    render(<AntiekProductWorkstationShell operatorId="   " />);
    expect(
      screen.getByTestId("antiek-product-workstation-error").textContent,
    ).toMatch(/operatorId/);
    expect(
      screen.queryByTestId("antiek-product-workstation-slots"),
    ).toBeNull();
  });
});
