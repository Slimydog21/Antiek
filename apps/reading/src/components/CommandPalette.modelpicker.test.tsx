import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import { cleanup, fireEvent, render, screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { MemoryRouter } from "react-router-dom";

// SPR-03 Task 3 — the driver dropdown on the CommandPalette. The palette's
// index loads are best-effort and answered with 404 here; only the user-model
// inventory is served, so the picker has one key to offer.
vi.mock("../lib/api", async (orig) => ({
  ...(await orig<typeof import("../lib/api")>()),
  apiFetch: vi.fn(),
}));

import { apiFetch } from "../lib/api";
import CommandPalette from "./CommandPalette";
import { THOUGHT_PARTNER_SEED_EVENT, type ThoughtPartnerSeedDetail } from "./ai/thoughtPartnerSeed";

const apiFetchMock = apiFetch as unknown as ReturnType<typeof vi.fn>;

const inventory = {
  models: [
    {
      id: "um-1",
      provider_kind: "openai_compat",
      provider_catalog_id: "deepseek",
      model_id: "deepseek-reasoner",
      model_ids: ["deepseek-reasoner", "deepseek-chat"],
      display_name: "My DeepSeek",
      base_url: "https://api.deepseek.com",
      enabled: true,
      key_present: true,
      registered: true,
      route_eligible: true,
      pricing_status: "known",
      hard_ceiling_eligible: true,
      execution_status: "executable",
      rate_snapshot: "deepseek-v4-pro-2026-08-spec",
    },
  ],
  count: 1,
  stale_registered: [],
  source: "test",
};

function openPalette(): void {
  // The workspace shortcuts module owns ⌘K and dispatches this event; the
  // palette also keeps its own ⌘K fallback. Either path sets open=true.
  fireEvent(window, new Event("antiek:palette:toggle"));
}

describe("CommandPalette driver dropdown (SPR-03 Task 3)", () => {
  beforeEach(() => {
    apiFetchMock.mockReset();
    apiFetchMock.mockImplementation((url: string) => {
      if (typeof url === "string" && url.endsWith("/settings/models/user")) {
        return Promise.resolve({ ok: true, status: 200, json: async () => inventory });
      }
      return Promise.resolve({ ok: false, status: 404 });
    });
  });
  afterEach(cleanup);

  it("mounts the ModelUsagePicker in the open palette's tree", async () => {
    render(
      <MemoryRouter>
        <CommandPalette />
      </MemoryRouter>,
    );
    expect(screen.queryByRole("dialog")).toBeNull();
    openPalette();
    const dialog = await screen.findByRole("dialog", { name: "Command palette" });
    const trigger = await screen.findByLabelText("Driver model for the AI sidecar");
    expect(dialog.contains(trigger)).toBe(true);
    await waitFor(() => expect(trigger.textContent).toContain("Default"));
  });

  it("broadcasts the chosen key and variant on the thought-partner seed bus and mirrors it on the trigger", async () => {
    const user = userEvent.setup();
    const seeds: ThoughtPartnerSeedDetail[] = [];
    const onSeed = (ev: Event) => seeds.push((ev as CustomEvent<ThoughtPartnerSeedDetail>).detail);
    window.addEventListener(THOUGHT_PARTNER_SEED_EVENT, onSeed);
    try {
      render(
        <MemoryRouter>
          <CommandPalette />
        </MemoryRouter>,
      );
      openPalette();
      await screen.findByRole("dialog", { name: "Command palette" });
      const trigger = await screen.findByLabelText("Driver model for the AI sidecar");
      await waitFor(() => expect(trigger.textContent).toContain("Default"));
      await waitFor(() =>
        expect(apiFetchMock.mock.calls.some(([u]) => String(u).endsWith("/settings/models/user"))).toBe(true),
      );
      await user.click(trigger);
      const flash = await waitFor(() => {
        const el = Array.from(document.querySelectorAll("button")).find((b) =>
          (b.textContent || "").includes("deepseek-chat"),
        );
        expect(el).toBeTruthy();
        return el as HTMLElement;
      });
      await user.click(flash);

      expect(seeds).toEqual([{ owner_model: { row_id: "um-1", model_id: "deepseek-chat" } }]);
      await waitFor(() => expect(trigger.textContent).toContain("My DeepSeek · deepseek-chat"));
      // Choosing a driver does not close the palette.
      expect(screen.getByRole("dialog", { name: "Command palette" })).toBeTruthy();
    } finally {
      window.removeEventListener(THOUGHT_PARTNER_SEED_EVENT, onSeed);
    }
  });
});
