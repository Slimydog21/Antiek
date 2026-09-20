import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import { cleanup, render, screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";

import ConnectResearch from "./ConnectResearch";

/**
 * ConnectResearch.modelChoice.test — the backing folder runs on the chosen
 * route.
 *
 * "Start without a project" spawns a real research, so it spends. This file
 * asserts the choice at the transport: `fetch` is stubbed and the serialized
 * POST /investigations body is read back. The sibling ConnectResearch.test
 * covers the connect/spawn behaviour itself and mocks the API wrapper; this
 * one deliberately does not, because the body is the only place a decorative
 * picker shows up as decorative.
 */

const executableModel = {
  id: "um-kimi",
  provider_kind: "openai_compat",
  provider_catalog_id: "moonshot",
  model_id: "kimi-k2.5",
  display_name: "Kimi K2.5",
  base_url: null,
  enabled: true,
  key_present: true,
  registered: true,
  route_eligible: true,
  pricing_status: "known",
  hard_ceiling_eligible: true,
  execution_status: "executable",
  rate_snapshot: null,
};

function jsonResponse(payload: unknown): Response {
  return {
    ok: true,
    status: 200,
    json: async () => payload,
    text: async () => JSON.stringify(payload),
  } as unknown as Response;
}

let startBodies: Record<string, unknown>[] = [];

beforeEach(() => {
  startBodies = [];
  vi.stubGlobal(
    "fetch",
    vi.fn(async (input: RequestInfo | URL, init?: RequestInit) => {
      const url = String(input);
      if (init?.method === "POST" && url.includes("/investigations")) {
        startBodies.push(JSON.parse(String(init.body)) as Record<string, unknown>);
        return jsonResponse({
          investigation_id: "inv-spawned",
          status: "in_progress",
          start_event_id: "ev-1",
        });
      }
      if (url.includes("/investigations")) {
        return jsonResponse({ count: 0, investigations: [] });
      }
      if (url.includes("/settings/models")) {
        return jsonResponse({
          models: [executableModel],
          count: 1,
          stale_registered: [],
          source: "test",
        });
      }
      if (url.includes("/settings/usage")) return jsonResponse({ keys: [], count: 0 });
      if (url.includes("/settings/balance/")) {
        return jsonResponse({
          api_key_id: executableModel.id,
          catalog_id: "moonshot",
          kind: "unavailable",
          balance_usd: null,
          held_cents: 0,
          available_cents: null,
        });
      }
      throw new Error(`unexpected fetch in test: ${url}`);
    }),
  );
});

afterEach(() => {
  vi.unstubAllGlobals();
  cleanup();
});

describe("ConnectResearch — the picked model backs the spawned folder", () => {
  it("puts the choice and its operation id in the spawn body", async () => {
    render(<ConnectResearch pieceTitle="My memo" onConnect={() => {}} />);

    const trigger = await screen.findByRole("button", {
      name: "Model for the backing research",
    });
    await waitFor(() => expect(trigger.hasAttribute("disabled")).toBe(false));
    await userEvent.click(trigger);
    await userEvent.click(await screen.findByText("Kimi K2.5"));

    await userEvent.click(await screen.findByText(/start without a project/i));
    await waitFor(() => expect(startBodies).toHaveLength(1));

    expect(startBodies[0].model_choice).toEqual({
      authority: "user_model",
      provider_id: "um-kimi",
      model_id: "kimi-k2.5",
    });
    expect(String(startBodies[0].operation_id).startsWith("connect-")).toBe(true);
  });

  it("spawns on the house route when the picker is untouched", async () => {
    render(<ConnectResearch pieceTitle="My memo" onConnect={() => {}} />);
    const trigger = await screen.findByRole("button", {
      name: "Model for the backing research",
    });
    await waitFor(() => expect(trigger.hasAttribute("disabled")).toBe(false));

    await userEvent.click(await screen.findByText(/start without a project/i));
    await waitFor(() => expect(startBodies).toHaveLength(1));

    expect(startBodies[0]).not.toHaveProperty("model_choice");
    expect(startBodies[0]).not.toHaveProperty("operation_id");
  });
});
