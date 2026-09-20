/**
 * LineupPanel — data flow: load, formation substitution, advanced
 * per-action override, error + retry (plain vitest assertions; the repo
 * does not install jest-dom matchers).
 */

import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import { cleanup, fireEvent, render, screen, waitFor, within } from "@testing-library/react";

afterEach(cleanup);

import LineupPanel from "./LineupPanel";
import { fetchLineup, saveLineup } from "../../api/settingsLineup";

vi.mock("../../api/settingsLineup", async (importOriginal) => ({
  ...(await importOriginal<typeof import("../../api/settingsLineup")>()),
  fetchLineup: vi.fn(),
  saveLineup: vi.fn(),
}));

const LINEUP = {
  version: 1,
  general: [
    {
      role_id: "writer",
      position: "att",
      label: "Writer",
      blurb: "The striker.",
      discovered: false,
      actions: [
        {
          action_id: "research_synthesis",
          role_id: "writer",
          label: "Research synthesis",
          blurb: "The final synthesis.",
          dispatch_role: "synthesizer",
          default_tier: "synthesis",
          kind: "llm",
        },
      ],
    },
    {
      role_id: "critic",
      position: "mid",
      label: "Critic",
      blurb: "The analyst.",
      discovered: true,
      actions: [],
    },
  ],
  advanced: [
    {
      action_id: "research_synthesis",
      role_id: "writer",
      label: "Research synthesis",
      blurb: "The final synthesis.",
      dispatch_role: "synthesizer",
      default_tier: "synthesis",
      kind: "llm",
    },
  ],
  bench: [
    { provider_id: "zai", model_id: "glm-5.2", label: "zai/glm-5.2", source: "dispatch", default_tier: "pro" },
    { provider_id: "openai", model_id: "gpt-5.6-luna", label: "GPT-5.6 Luna", source: "preset", default_tier: null },
  ],
  assignments: { general: { writer: null, critic: null }, advanced: { research_synthesis: null } },
  updated_at: "2026-08-12T19:00:00Z",
};

describe("LineupPanel", () => {
  beforeEach(() => {
    vi.mocked(fetchLineup).mockResolvedValue(LINEUP as never);
    vi.mocked(saveLineup).mockResolvedValue({
      ...LINEUP,
      assignments: {
        general: { writer: { provider_id: "openai", model_id: "gpt-5.6-luna" }, critic: null },
        advanced: { research_synthesis: null },
      },
      updated_at: "2026-08-12T19:01:00Z",
    } as never);
  });

  it("loads and renders the formation plus the tactics board", async () => {
    render(<LineupPanel />);
    expect(await screen.findByText("Formation — general selector")).toBeTruthy();
    expect(screen.getByText("Tactics — advanced selector")).toBeTruthy();
    expect(screen.getByRole("button", { name: /Writer position — Auto/ })).toBeTruthy();
    // advanced default role = writer, so its action is visible
    expect(await screen.findByText("Research synthesis")).toBeTruthy();
    expect(screen.getByText(/dispatch_role=synthesizer/)).toBeTruthy();
  });

  it("persists a formation substitution via PUT", async () => {
    render(<LineupPanel />);
    await screen.findByText("Formation — general selector");
    fireEvent.click(screen.getByRole("button", { name: /Writer position — Auto/ }));
    fireEvent.click(screen.getByRole("button", { name: /Substitute ▼/ }));
    const bench = screen.getByRole("listbox", { name: /Bench substitutes/ });
    fireEvent.click(within(bench).getByRole("option", { name: /GPT-5.6 Luna/ }));
    await waitFor(() =>
      expect(saveLineup).toHaveBeenCalledWith({
        general: { writer: { provider_id: "openai", model_id: "gpt-5.6-luna" }, critic: null },
        advanced: { research_synthesis: null },
      }),
    );
    await waitFor(() =>
      expect(screen.getByText(/Last saved 2026-08-12T19:01:00Z/)).toBeTruthy(),
    );
  });

  it("persists an advanced per-action override", async () => {
    render(<LineupPanel />);
    await screen.findByText("Formation — general selector");
    const select = screen.getByLabelText("Research synthesis model");
    fireEvent.change(select, { target: { value: "openai:gpt-5.6-luna" } });
    await waitFor(() =>
      expect(saveLineup).toHaveBeenCalledWith({
        general: { writer: null, critic: null },
        advanced: { research_synthesis: { provider_id: "openai", model_id: "gpt-5.6-luna" } },
      }),
    );
  });

  it("shows an honest error state and recovers on retry", async () => {
    vi.mocked(fetchLineup).mockRejectedValueOnce(new Error("boom"));
    render(<LineupPanel />);
    expect(await screen.findByText(/Lineup unavailable · boom/)).toBeTruthy();
    fireEvent.click(screen.getByRole("button", { name: /Retry/ }));
    expect(await screen.findByText("Formation — general selector")).toBeTruthy();
  });

  it("flags discovered roles in the tactics role switcher", async () => {
    render(<LineupPanel />);
    await screen.findByText("Formation — general selector");
    expect(screen.getByRole("button", { name: "CriticNEW" })).toBeTruthy();
  });
});
