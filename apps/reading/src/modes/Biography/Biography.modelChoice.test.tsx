import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import { cleanup, render, screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { MemoryRouter } from "react-router-dom";

import Biography from "./index";
import { isDisabled } from "../../test/isDisabled";

/**
 * Biography.modelChoice.test — the gathering runs on the chosen route.
 *
 * "Start a biography" starts a research before it composes anything, so the
 * route that does the gathering is a real spend decision. Asserted at the
 * transport (stubbed `fetch`, serialized POST /investigations body) rather than
 * at the API wrapper, because a picker that never changes the body is exactly
 * the defect worth a test. The sibling Biography.test covers the landing copy
 * and the composition flow.
 */

const executableModel = {
  id: "um-glm",
  provider_kind: "openai_compat",
  provider_catalog_id: "zai",
  model_id: "glm-5.2",
  display_name: "GLM 5.2",
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
/** Flipped by the retry test: the composition call after the start fails once,
 *  which is the path that leaves a claimed operation id behind. */
let composeFails = false;

beforeEach(() => {
  startBodies = [];
  composeFails = false;
  vi.stubGlobal(
    "fetch",
    vi.fn(async (input: RequestInfo | URL, init?: RequestInit) => {
      const url = String(input);
      if (init?.method === "POST" && url.includes("/investigations")) {
        startBodies.push(JSON.parse(String(init.body)) as Record<string, unknown>);
        return jsonResponse({
          investigation_id: `inv-bio-${startBodies.length}`,
          status: "in_progress",
          start_event_id: "ev-1",
        });
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
          catalog_id: "zai",
          kind: "unavailable",
          balance_usd: null,
          held_cents: 0,
          available_cents: null,
        });
      }
      // The composition call that follows the start; its shape is the sibling
      // test's subject, so here it only has to succeed — or fail on demand.
      if (composeFails) {
        composeFails = false;
        return { ok: false, status: 500, json: async () => ({}), text: async () => "" } as unknown as Response;
      }
      return jsonResponse({
        investigation_id: "inv-bio",
        deliverable_id: "dlv-bio",
        project_id: "proj-bio",
      });
    }),
  );
});

afterEach(() => {
  vi.unstubAllGlobals();
  cleanup();
});

async function startBiographyFor(name: string) {
  const expected = startBodies.length + 1;
  await userEvent.type(
    screen.getByLabelText("Whose biography do you want to write?"),
    name,
  );
  await userEvent.click(screen.getByRole("button", { name: "Start a biography" }));
  await waitFor(() => expect(startBodies).toHaveLength(expected));
}

async function chooseGlm() {
  const trigger = await screen.findByRole("button", { name: "Model for the gathering" });
  await waitFor(() => expect(isDisabled(trigger)).toBe(false));
  await userEvent.click(trigger);
  await userEvent.click(await screen.findByText("GLM 5.2"));
}

describe("Biography — the picked model does the gathering", () => {
  it("puts the choice and its operation id in the start body", async () => {
    render(
      <MemoryRouter>
        <Biography />
      </MemoryRouter>,
    );

    const trigger = await screen.findByRole("button", { name: "Model for the gathering" });
    await waitFor(() => expect(isDisabled(trigger)).toBe(false));
    await userEvent.click(trigger);
    await userEvent.click(await screen.findByText("GLM 5.2"));

    await startBiographyFor("my grandmother");

    expect(startBodies[0].model_choice).toEqual({
      authority: "user_model",
      provider_id: "um-glm",
      model_id: "glm-5.2",
    });
    expect(String(startBodies[0].operation_id).startsWith("biography-")).toBe(true);
  });

  it("starts on the house route when the picker is untouched", async () => {
    render(
      <MemoryRouter>
        <Biography />
      </MemoryRouter>,
    );
    const trigger = await screen.findByRole("button", { name: "Model for the gathering" });
    await waitFor(() => expect(isDisabled(trigger)).toBe(false));

    await startBiographyFor("my grandmother");

    expect(startBodies[0]).not.toHaveProperty("model_choice");
    expect(startBodies[0]).not.toHaveProperty("operation_id");
  });

  /**
   * The id names a launch, not a visit to the dropdown. The server claims
   * idempotency on operation_id + a digest of the request, and answers 409
   * owner_model_operation_conflict when the same id returns with a different
   * digest. A first attempt that starts the research and then fails while
   * composing leaves that claim behind, so a retry under an edited name must
   * carry a NEW id — otherwise every later attempt 409s and nothing the user
   * can touch clears it.
   */
  it("mints a new operation id when the retry launches different content", async () => {
    render(
      <MemoryRouter>
        <Biography />
      </MemoryRouter>,
    );
    await chooseGlm();

    composeFails = true;
    await startBiographyFor("my grandmother");
    await screen.findByRole("alert");

    await userEvent.clear(screen.getByLabelText("Whose biography do you want to write?"));
    await startBiographyFor("my grandfather");

    expect(startBodies).toHaveLength(2);
    expect(startBodies[0].question).not.toEqual(startBodies[1].question);
    expect(startBodies[1].model_choice).toEqual(startBodies[0].model_choice);
    expect(startBodies[1].operation_id).not.toEqual(startBodies[0].operation_id);
  });

  it("keeps one id when the identical request is sent again, so the server replays it", async () => {
    render(
      <MemoryRouter>
        <Biography />
      </MemoryRouter>,
    );
    await chooseGlm();

    composeFails = true;
    await startBiographyFor("my grandmother");
    await screen.findByRole("alert");

    await userEvent.click(screen.getByRole("button", { name: "Start a biography" }));
    await waitFor(() => expect(startBodies).toHaveLength(2));
    expect(startBodies[1].question).toEqual(startBodies[0].question);
    expect(startBodies[1].operation_id).toEqual(startBodies[0].operation_id);
  });
});
