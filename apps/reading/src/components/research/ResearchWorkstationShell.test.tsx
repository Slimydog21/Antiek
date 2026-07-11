import { afterEach, describe, expect, it } from "vitest";
import { cleanup, render, screen } from "@testing-library/react";
import ResearchWorkstationShell, {
  isResearchSlotFilled,
  validateSessionId,
} from "./ResearchWorkstationShell";

afterEach(() => {
  cleanup();
});

describe("validateSessionId", () => {
  it("requires non-empty", () => {
    expect(() => validateSessionId("  ")).toThrow(/sessionId/);
    expect(validateSessionId(" sess-1 ")).toBe("sess-1");
  });
});

describe("isResearchSlotFilled", () => {
  it("empty vs filled", () => {
    expect(isResearchSlotFilled(false)).toBe(false);
    expect(isResearchSlotFilled("")).toBe(false);
    expect(isResearchSlotFilled(0)).toBe(true);
    expect(isResearchSlotFilled(<span>x</span>)).toBe(true);
    expect(isResearchSlotFilled([])).toBe(false);
    expect(isResearchSlotFilled([""])).toBe(false);
    expect(isResearchSlotFilled([false])).toBe(false);
    expect(isResearchSlotFilled([false, "x"])).toBe(true);
  });
});

describe("ResearchWorkstationShell", () => {
  it("renders session and empty slots honestly", () => {
    render(
      <ResearchWorkstationShell sessionId="sess-1" sessionLabel="Investigate X" />,
    );
    expect(screen.getByTestId("research-workstation-session").textContent).toMatch(
      /sess-1/,
    );
    expect(
      screen
        .getByTestId("research-workstation-slot-source_pack")
        .getAttribute("data-filled"),
    ).toBe("false");
    expect(
      screen.getByTestId("research-workstation-slot-empty-source_pack").textContent,
    ).toMatch(/no invent/i);
  });

  it("renders injected slots", () => {
    render(
      <ResearchWorkstationShell
        sessionId="sess-1"
        slots={{
          source_pack: <div data-testid="injected-pack">Pack</div>,
        }}
        slotOrder={["source_pack", "cascade_launch"]}
      />,
    );
    expect(screen.getByTestId("injected-pack").textContent).toMatch(/Pack/);
    expect(
      screen
        .getByTestId("research-workstation-slot-source_pack")
        .getAttribute("data-filled"),
    ).toBe("true");
    expect(
      screen
        .getByTestId("research-workstation-slot-cascade_launch")
        .getAttribute("data-filled"),
    ).toBe("false");
  });

  it("fails closed on empty session", () => {
    render(<ResearchWorkstationShell sessionId="   " />);
    expect(screen.getByTestId("research-workstation-error").textContent).toMatch(
      /sessionId/,
    );
    expect(screen.queryByTestId("research-workstation-slots")).toBeNull();
  });
});
