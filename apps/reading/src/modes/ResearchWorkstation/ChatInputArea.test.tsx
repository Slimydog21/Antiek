import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import { cleanup, render, screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { MemoryRouter } from "react-router-dom";

import ChatInputArea from "./ChatInputArea";

/**
 * ChatInputArea.test — the composer's model driver actually drives.
 *
 * The picker here is asserted at the TRANSPORT, not at the API wrapper: the
 * test stubs `fetch` and reads the serialized POST /investigations body. A
 * control that changes state but not the request is the defect this file
 * exists to catch, and only the body proves the difference.
 *
 * Three claims:
 *   1. choosing a model puts `model_choice` AND `operation_id` in the body
 *      (the server rejects one without the other);
 *   2. leaving the picker alone sends neither — the house route stays the
 *      house route, and no half-filled owner launch is invented;
 *   3. a chased composer (a parent or a passage in context) renders NO picker,
 *      because the server refuses an owner-chosen route on a non-root start
 *      (422 owner_model_root_required). An absent control is honest; a
 *      present one that 422s is not.
 */

const executableModel = {
  id: "um-deepseek-pro",
  provider_kind: "openai_compat",
  provider_catalog_id: "deepseek",
  model_id: "deepseek-v4-pro",
  display_name: "DeepSeek V4 Pro",
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
          catalog_id: "deepseek",
          kind: "unavailable",
          balance_usd: null,
          held_cents: 0,
          available_cents: null,
        });
      }
      if (url.endsWith("/investigations")) {
        startBodies.push(JSON.parse(String(init?.body)) as Record<string, unknown>);
        return jsonResponse({
          investigation_id: "inv-started",
          status: "in_progress",
          start_event_id: "ev-1",
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

function renderComposer(props: Record<string, unknown> = {}) {
  return render(
    <MemoryRouter>
      <ChatInputArea onSubmitted={() => {}} {...props} />
    </MemoryRouter>,
  );
}

async function chooseDeepSeek() {
  const trigger = await screen.findByRole("button", { name: "Model for this research" });
  await waitFor(() => expect(trigger.hasAttribute("disabled")).toBe(false));
  await userEvent.click(trigger);
  await userEvent.click(await screen.findByText("DeepSeek V4 Pro"));
}

async function ask(question: string) {
  await userEvent.type(
    screen.getByPlaceholderText("What do you want to research?"),
    question,
  );
  await userEvent.click(screen.getByRole("button", { name: "Ask" }));
  await waitFor(() => expect(startBodies).toHaveLength(1));
}

describe("ChatInputArea — the model driver reaches the request", () => {
  it("sends the chosen model and an operation id in the POST body", async () => {
    renderComposer();
    await chooseDeepSeek();
    await ask("what changed in the margin structure?");

    const body = startBodies[0];
    expect(body.model_choice).toEqual({
      authority: "user_model",
      provider_id: "um-deepseek-pro",
      model_id: "deepseek-v4-pro",
    });
    expect(typeof body.operation_id).toBe("string");
    expect(String(body.operation_id).startsWith("chat-")).toBe(true);
  });

  it("sends neither field when the house route is left in force", async () => {
    renderComposer();
    // The picker is present and loaded; it is simply not touched.
    const trigger = await screen.findByRole("button", { name: "Model for this research" });
    await waitFor(() => expect(trigger.hasAttribute("disabled")).toBe(false));
    await ask("what changed in the margin structure?");

    const body = startBodies[0];
    expect(body).not.toHaveProperty("model_choice");
    expect(body).not.toHaveProperty("operation_id");
  });

  it("offers no picker on a chased composer, and starts without one", async () => {
    renderComposer({
      parentInvestigationId: "inv-parent",
      spawnContext: "the passage being chased",
    });
    await waitFor(() => expect(screen.getByRole("button", { name: "Ask" })).toBeTruthy());
    expect(screen.queryByRole("button", { name: "Model for this research" })).toBeNull();

    await userEvent.click(screen.getByRole("button", { name: "Ask" }));
    await waitFor(() => expect(startBodies).toHaveLength(1));
    expect(startBodies[0]).not.toHaveProperty("model_choice");
    expect(startBodies[0].parent_investigation_id).toBe("inv-parent");
  });
});
