/**
 * LineupPitch — substitution mechanics, honest states (plain vitest
 * assertions; the repo does not install jest-dom matchers).
 */

import { afterEach, describe, expect, it, vi } from "vitest";
import { cleanup, fireEvent, render, screen } from "@testing-library/react";

afterEach(cleanup);

import LineupPitch, { type LineupPitchProps } from "./LineupPitch";
import type { BenchModelView, RoleView } from "../api/settingsLineup";

const ROLES: RoleView[] = [
  {
    role_id: "writer",
    position: "att",
    label: "Writer",
    blurb: "The striker.",
    discovered: false,
    actions: [],
  },
  {
    role_id: "data_verification",
    position: "gk",
    label: "Data Verification",
    blurb: "The last line.",
    discovered: false,
    actions: [],
  },
  {
    role_id: "critic",
    position: "mid",
    label: "Critic",
    blurb: "The analyst.",
    discovered: true,
    actions: [],
  },
];

const BENCH: BenchModelView[] = [
  { provider_id: "zai", model_id: "glm-5.2", label: "zai/glm-5.2", source: "dispatch", default_tier: "pro" },
  { provider_id: "openai", model_id: "gpt-5.6-luna", label: "GPT-5.6 Luna", source: "preset", default_tier: null },
];

const baseProps: LineupPitchProps = {
  roles: ROLES,
  bench: BENCH,
  assignments: { writer: null, data_verification: null, critic: null },
  selectedRole: null,
  onSelectRole: vi.fn(),
  onAssign: vi.fn(),
  busyRole: null,
};

function renderPitch(overrides: Partial<LineupPitchProps> = {}) {
  const props = { ...baseProps, ...overrides };
  render(<LineupPitch {...props} />);
  return props;
}

describe("LineupPitch", () => {
  it("renders every role position with Auto default", () => {
    renderPitch();
    expect(screen.getByRole("group", { name: /formation/i })).toBeTruthy();
    expect(screen.getByRole("button", { name: /Writer position — Auto/ })).toBeTruthy();
    expect(
      screen.getByRole("button", { name: /Data Verification position — Auto/ }),
    ).toBeTruthy();
  });

  it("selects a position and substitutes a bench model", () => {
    const onAssign = vi.fn();
    const onSelectRole = vi.fn();
    const first = renderPitch({ onAssign, onSelectRole });
    fireEvent.click(screen.getByRole("button", { name: /Writer position — Auto/ }));
    expect(onSelectRole).toHaveBeenCalledWith("writer");
    // re-render as selected to open the substitution bar + bench
    render(
      <LineupPitch
        {...first}
        selectedRole="writer"
        assignments={{ writer: null, data_verification: null, critic: null }}
      />,
    );
    fireEvent.click(screen.getByRole("button", { name: /Substitute ▼/ }));
    fireEvent.click(screen.getByRole("option", { name: /GPT-5.6 Luna/ }));
    expect(onAssign).toHaveBeenCalledWith("writer", {
      provider_id: "openai",
      model_id: "gpt-5.6-luna",
    });
  });

  it("shows the assigned model and tier-strength badge", () => {
    renderPitch({
      assignments: { writer: { provider_id: "zai", model_id: "glm-5.2" }, data_verification: null, critic: null },
    });
    const writer = screen.getByRole("button", { name: /Writer position — zai \/ glm-5.2/ });
    expect(writer).toBeTruthy();
    expect(screen.getByText("8")).toBeTruthy(); // pro tier strength
  });

  it("resets a position to Auto", () => {
    const onAssign = vi.fn();
    renderPitch({
      selectedRole: "writer",
      assignments: { writer: { provider_id: "zai", model_id: "glm-5.2" }, data_verification: null, critic: null },
      onAssign,
    });
    fireEvent.click(screen.getByRole("button", { name: /Reset Writer to Auto/ }));
    expect(onAssign).toHaveBeenCalledWith("writer", null);
  });

  it("renders an honest empty bench state", () => {
    renderPitch({ bench: [], selectedRole: "writer" });
    fireEvent.click(screen.getByRole("button", { name: /Substitute ▼/ }));
    expect(screen.getByText(/The bench is empty/)).toBeTruthy();
  });

  it("flags discovered roles as NEW SIGNING", () => {
    renderPitch({ selectedRole: "critic" });
    expect(screen.getByText("NEW SIGNING")).toBeTruthy();
  });
});
