import { afterEach, describe, expect, it } from "vitest";
import { cleanup, render, screen } from "@testing-library/react";
import MidnightOilWorkstationShell, {
  isMoSlotFilled,
  validateOperatorId,
} from "./MidnightOilWorkstationShell";

afterEach(() => {
  cleanup();
});

describe("validateOperatorId", () => {
  it("requires non-empty", () => {
    expect(() => validateOperatorId("  ")).toThrow(/operatorId/);
    expect(validateOperatorId(" op-1 ")).toBe("op-1");
  });
});

describe("isMoSlotFilled", () => {
  it("empty vs filled", () => {
    expect(isMoSlotFilled(false)).toBe(false);
    expect(isMoSlotFilled([])).toBe(false);
    expect(isMoSlotFilled([false, ""])).toBe(false);
    expect(isMoSlotFilled(0)).toBe(true);
    expect(isMoSlotFilled(<div>x</div>)).toBe(true);
  });
});

describe("MidnightOilWorkstationShell", () => {
  it("renders operator and empty slots", () => {
    render(<MidnightOilWorkstationShell operatorId="op-1" />);
    expect(screen.getByTestId("mo-workstation-operator").textContent).toMatch(
      /op-1/,
    );
    expect(screen.getByTestId("mo-workstation-live").textContent).toMatch(
      /false/,
    );
    expect(
      screen.getByTestId("mo-workstation-slot-launch_gate").getAttribute("data-filled"),
    ).toBe("false");
  });

  it("renders injected slots", () => {
    render(
      <MidnightOilWorkstationShell
        operatorId="op-1"
        slots={{
          price_ceiling: <div data-testid="inj-ceiling">Ceiling</div>,
        }}
        slotOrder={["price_ceiling", "launch_gate"]}
      />,
    );
    expect(screen.getByTestId("inj-ceiling").textContent).toMatch(/Ceiling/);
    expect(
      screen.getByTestId("mo-workstation-slot-price_ceiling").getAttribute("data-filled"),
    ).toBe("true");
  });

  it("fails closed on empty operator", () => {
    render(<MidnightOilWorkstationShell operatorId="   " />);
    expect(screen.getByTestId("mo-workstation-error").textContent).toMatch(
      /operatorId/,
    );
  });
});
