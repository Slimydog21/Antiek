import { afterEach, describe, expect, it } from "vitest";
import { cleanup, render, screen } from "@testing-library/react";
import LibraryWorkstationShell, {
  isLibrarySlotFilled,
  validateLibraryOperatorId,
} from "./LibraryWorkstationShell";

afterEach(() => {
  cleanup();
});

describe("validateLibraryOperatorId", () => {
  it("requires non-empty", () => {
    expect(() => validateLibraryOperatorId("  ")).toThrow(/operatorId/);
    expect(validateLibraryOperatorId(" op-1 ")).toBe("op-1");
  });
});

describe("isLibrarySlotFilled", () => {
  it("empty vs filled", () => {
    expect(isLibrarySlotFilled(false)).toBe(false);
    expect(isLibrarySlotFilled([])).toBe(false);
    expect(isLibrarySlotFilled([[], [false, ""]])).toBe(false);
    expect(isLibrarySlotFilled(0)).toBe(true);
    expect(isLibrarySlotFilled(<span>x</span>)).toBe(true);
  });
});

describe("LibraryWorkstationShell", () => {
  it("renders operator and empty slots", () => {
    render(<LibraryWorkstationShell operatorId="op-1" />);
    expect(screen.getByTestId("library-workstation-operator").textContent).toMatch(
      /op-1/,
    );
    expect(screen.getByTestId("library-workstation-doctrine").textContent).toMatch(
      /HTML-native/,
    );
    expect(
      screen
        .getByTestId("library-workstation-slot-html_host")
        .getAttribute("data-filled"),
    ).toBe("false");
  });

  it("renders injected slots", () => {
    render(
      <LibraryWorkstationShell
        operatorId="op-1"
        slots={{
          free_copy: <div data-testid="inj-free">Free</div>,
        }}
        slotOrder={["free_copy", "purchase_gate"]}
      />,
    );
    expect(screen.getByTestId("inj-free").textContent).toMatch(/Free/);
    expect(
      screen
        .getByTestId("library-workstation-slot-free_copy")
        .getAttribute("data-filled"),
    ).toBe("true");
  });

  it("fails closed on empty operator", () => {
    render(<LibraryWorkstationShell operatorId="   " />);
    expect(screen.getByTestId("library-workstation-error").textContent).toMatch(
      /operatorId/,
    );
  });
});
