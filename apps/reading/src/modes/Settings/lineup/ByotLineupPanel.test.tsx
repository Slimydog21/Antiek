import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import { cleanup, render, screen, within } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import ByotLineupPanel from "./ByotLineupPanel";
import { fetchUserModels } from "../../../api/settingsModels";
import { GENERAL_SLOTS } from "./inventory";

const inventory = {
  models: [
    {
      id: "user-sol",
      provider_kind: "openai_compat" as const,
      provider_catalog_id: "openai",
      model_id: "gpt-5.6-sol",
      display_name: "Sol",
      base_url: "https://api.openai.com",
      enabled: true,
      key_present: true,
      registered: true,
      route_eligible: true,
      pricing_status: "known" as const,
      hard_ceiling_eligible: false,
      execution_status: "blocked_idempotency_unproven" as const,
      rate_snapshot: "sol",
    },
    {
      id: "user-luna",
      provider_kind: "openai_compat" as const,
      provider_catalog_id: "openai",
      model_id: "gpt-5.6-luna",
      display_name: "Luna",
      base_url: "https://api.openai.com",
      enabled: true,
      key_present: true,
      registered: true,
      route_eligible: true,
      pricing_status: "known" as const,
      hard_ceiling_eligible: false,
      execution_status: "blocked_idempotency_unproven" as const,
      rate_snapshot: "luna",
    },
    {
      id: "user-sonnet",
      provider_kind: "anthropic" as const,
      provider_catalog_id: "anthropic",
      model_id: "claude-sonnet-5",
      display_name: "Sonnet",
      base_url: "https://api.anthropic.com",
      enabled: true,
      key_present: true,
      registered: true,
      route_eligible: true,
      pricing_status: "known" as const,
      hard_ceiling_eligible: false,
      execution_status: "blocked_idempotency_unproven" as const,
      rate_snapshot: "sonnet",
    },
    {
      id: "user-terra",
      provider_kind: "openai_compat" as const,
      provider_catalog_id: "openai",
      model_id: "gpt-5.6-terra",
      display_name: "Terra",
      base_url: "https://api.openai.com",
      enabled: true,
      key_present: true,
      registered: true,
      route_eligible: true,
      pricing_status: "known" as const,
      hard_ceiling_eligible: false,
      execution_status: "blocked_idempotency_unproven" as const,
      rate_snapshot: "terra",
    },
    {
      id: "user-haiku",
      provider_kind: "anthropic" as const,
      provider_catalog_id: "anthropic",
      model_id: "claude-haiku-4-5",
      display_name: "Haiku",
      base_url: "https://api.anthropic.com",
      enabled: true,
      key_present: true,
      registered: true,
      route_eligible: true,
      pricing_status: "known" as const,
      hard_ceiling_eligible: false,
      execution_status: "blocked_idempotency_unproven" as const,
      rate_snapshot: "haiku",
    },
  ],
  count: 5,
  stale_registered: [],
  source: "test",
};

vi.mock("../../../api/settingsModels", () => ({
  fetchUserModels: vi.fn(),
}));

describe("ByotLineupPanel", () => {
  beforeEach(() => {
    window.localStorage.clear();
    vi.mocked(fetchUserModels).mockResolvedValue(inventory);
  });

  afterEach(() => {
    cleanup();
  });

  it("renders the four general position names on the pitch", async () => {
    render(<ByotLineupPanel />);
    expect(await screen.findByTestId("byot-pitch")).toBeTruthy();
    for (const slot of GENERAL_SLOTS) {
      expect(screen.getByTestId(`lineup-slot-${slot}`).textContent).toContain(
        slot,
      );
    }
  });

  it("substitutes a bench card into a named starter slot", async () => {
    const user = userEvent.setup();
    render(<ByotLineupPanel />);
    await screen.findByTestId("lineup-card-user-sol");

    await user.click(screen.getByTestId("lineup-empty-writer"));
    await user.click(screen.getByTestId("lineup-card-user-sol"));

    const writer = screen.getByTestId("lineup-slot-writer");
    expect(within(writer).getByTestId("lineup-card-user-sol")).toBeTruthy();
    expect(screen.getByTestId("byot-bench").textContent).not.toContain("Sol");
  });

  it("enumerates advanced extras that are not the four general names", async () => {
    const user = userEvent.setup();
    render(<ByotLineupPanel />);
    await screen.findByTestId("byot-advanced-toggle");
    await user.click(screen.getByTestId("byot-advanced-toggle"));
    expect(screen.getByTestId("advanced-slot-thought_partner")).toBeTruthy();
    expect(screen.getByTestId("advanced-slot-interviewer")).toBeTruthy();
    expect(screen.getByTestId("advanced-slot-wrestler")).toBeTruthy();
    expect(screen.getByTestId("advanced-slot-rlm_orchestrator")).toBeTruthy();
    expect(screen.getByTestId("advanced-slot-visual")).toBeTruthy();
    expect(screen.getByTestId("advanced-slot-transcription")).toBeTruthy();
    expect(screen.getByTestId("advanced-slot-tts")).toBeTruthy();
    expect(screen.getByTestId("advanced-slot-synthesizer")).toBeTruthy();
  });
});
