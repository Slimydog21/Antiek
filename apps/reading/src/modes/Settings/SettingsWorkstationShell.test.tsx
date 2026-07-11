import React from "react";
import { afterEach, describe, expect, it } from "vitest";
import { cleanup, render, screen } from "@testing-library/react";
import SettingsWorkstationShell, {
  isSettingsSlotFilled,
  validateSettingsOperatorId,
} from "./SettingsWorkstationShell";

afterEach(() => {
  cleanup();
});

describe("validateSettingsOperatorId", () => {
  it("requires non-empty", () => {
    expect(() => validateSettingsOperatorId("  ")).toThrow(/operatorId/);
    expect(validateSettingsOperatorId(" op-1 ")).toBe("op-1");
  });
});

describe("isSettingsSlotFilled", () => {
  it("empty vs filled", () => {
    expect(isSettingsSlotFilled(false)).toBe(false);
    expect(isSettingsSlotFilled("")).toBe(false);
    expect(isSettingsSlotFilled(0)).toBe(true);
    expect(isSettingsSlotFilled(<span>x</span>)).toBe(true);
    expect(isSettingsSlotFilled([])).toBe(false);
    expect(isSettingsSlotFilled([""])).toBe(false);
    expect(isSettingsSlotFilled([false])).toBe(false);
    expect(isSettingsSlotFilled([false, "x"])).toBe(true);
    expect(isSettingsSlotFilled([[], [false, ""]])).toBe(false);
    expect(isSettingsSlotFilled([[], [false, "ok"]])).toBe(true);
  });

  it("empty Fragment is not filled", () => {
    expect(isSettingsSlotFilled(<></>)).toBe(false);
    expect(isSettingsSlotFilled(<React.Fragment />)).toBe(false);
    expect(isSettingsSlotFilled(<React.Fragment>{""}</React.Fragment>)).toBe(
      false,
    );
    expect(
      isSettingsSlotFilled(
        <React.Fragment>
          <React.Fragment />
        </React.Fragment>,
      ),
    ).toBe(false);
    expect(
      isSettingsSlotFilled(
        <React.Fragment>
          <span>ok</span>
        </React.Fragment>,
      ),
    ).toBe(true);
  });
});

describe("SettingsWorkstationShell", () => {
  it("renders operator and empty slots honestly", () => {
    render(
      <SettingsWorkstationShell
        operatorId="op-1"
        operatorLabel="Primary budget"
      />,
    );
    expect(
      screen.getByTestId("settings-workstation-operator").textContent,
    ).toMatch(/op-1/);
    expect(
      screen
        .getByTestId("settings-workstation-slot-prompt_projection")
        .getAttribute("data-filled"),
    ).toBe("false");
    expect(
      screen.getByTestId(
        "settings-workstation-slot-empty-prompt_projection",
      ).textContent,
    ).toMatch(/no invent/i);
    expect(
      screen
        .getByTestId("settings-workstation-slot-notdiamond_shadow")
        .getAttribute("data-filled"),
    ).toBe("false");
  });

  it("renders injected slots", () => {
    render(
      <SettingsWorkstationShell
        operatorId="op-1"
        slots={{
          prompt_projection: (
            <div data-testid="injected-proj">Projection</div>
          ),
        }}
        slotOrder={["prompt_projection", "decision_tree"]}
      />,
    );
    expect(screen.getByTestId("injected-proj").textContent).toMatch(
      /Projection/,
    );
    expect(
      screen
        .getByTestId("settings-workstation-slot-prompt_projection")
        .getAttribute("data-filled"),
    ).toBe("true");
    expect(
      screen
        .getByTestId("settings-workstation-slot-decision_tree")
        .getAttribute("data-filled"),
    ).toBe("false");
  });

  it("fails closed on empty operator", () => {
    render(<SettingsWorkstationShell operatorId="   " />);
    expect(
      screen.getByTestId("settings-workstation-error").textContent,
    ).toMatch(/operatorId/);
    expect(screen.queryByTestId("settings-workstation-slots")).toBeNull();
  });

  it("treats empty Fragment slot as empty", () => {
    render(
      <SettingsWorkstationShell
        operatorId="op-1"
        slots={{ decision_tree: <></> }}
        slotOrder={["decision_tree"]}
      />,
    );
    expect(
      screen
        .getByTestId("settings-workstation-slot-decision_tree")
        .getAttribute("data-filled"),
    ).toBe("false");
  });
});
