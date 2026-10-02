import { expect, vi } from "vitest";
import { act, cleanup, render, screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { MemoryRouter } from "react-router-dom";
import { AuthProvider, useAuth, type AuthContextValue } from "../../lib/auth";
import ChatInputArea from "./ChatInputArea";
import {
  useResearchComposer,
  type ResearchComposerProps,
} from "./useResearchComposer";
import {
  useOwnerModelController,
  type OwnerModelController,
} from "../../hooks/useOwnerModelController";
import { createRootResearchLaunchArchive } from "./rootResearchLaunch";

export function createChatTestFixture(archiveSlot: {
  current: ReturnType<typeof createRootResearchLaunchArchive> | null;
}) {
  const executableModel = {
    id: "um-deepseek-pro",
    provider_kind: "openai_compat",
    provider_catalog_id: "deepseek",
    model_id: "deepseek-v4-pro",
    model_ids: ["deepseek-v4-pro", "deepseek-v4-flash"],
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
  let identity = {
    user_id: "fixture-owner",
    email: null,
    auth_method: "antiek_session_cookie",
  };
  let auth: AuthContextValue;
  let authRead: (() => Promise<Response>) | null = null;
  let startRead: ((body: Record<string, unknown>) => Promise<Response>) | null =
    null;
  function AuthProbe() {
    auth = useAuth();
    return null;
  }
  const unsettledResponses = new Set<Promise<Response>>();
  function deferredResponse() {
    let resolve!: (value: Response) => void;
    let reject!: (error: Error) => void;
    const promise = new Promise<Response>((yes, no) => {
      resolve = yes;
      reject = no;
    });
    unsettledResponses.add(promise);
    return {
      promise,
      resolve(value: Response) {
        unsettledResponses.delete(promise);
        resolve(value);
      },
      reject(error: Error) {
        unsettledResponses.delete(promise);
        reject(error);
      },
    };
  }
  const receipt = (id: string) =>
    jsonResponse({
      investigation_id: id,
      status: "in_progress",
      start_event_id: `event-${id}`,
    });

  function setUp() {
    if (archiveSlot.current !== null)
      throw new Error("prior Chat archive fixture not cleaned up");
    archiveSlot.current = createRootResearchLaunchArchive();
    startBodies = [];
    authRead = null;
    startRead = null;
    identity = {
      user_id: "fixture-owner",
      email: null,
      auth_method: "antiek_session_cookie",
    };
    vi.stubGlobal(
      "fetch",
      vi.fn(async (input: RequestInfo | URL, init?: RequestInit) => {
        const url = String(input);
        if (url.endsWith("/auth/me"))
          return authRead ? authRead() : jsonResponse(identity);
        if (url.includes("/settings/models")) {
          return jsonResponse({
            models: [executableModel],
            count: 1,
            stale_registered: [],
            source: "test",
          });
        }
        if (url.includes("/settings/usage"))
          return jsonResponse({ keys: [], count: 0 });
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
          const body = JSON.parse(String(init?.body)) as Record<string, unknown>;
          startBodies.push(body);
          if (startRead) return startRead(body);
          return jsonResponse({
            investigation_id: "inv-started",
            status: "in_progress",
            start_event_id: "ev-1",
          });
        }
        throw new Error(`unexpected fetch in test: ${url}`);
      }),
    );
  }

  async function tearDown() {
    cleanup();
    await act(async () => {});
    if (unsettledResponses.size > 0)
      throw new Error("Chat archive fixture has unresolved deferred responses");
    archiveSlot.current = null;
    vi.unstubAllGlobals();
  }

  function renderComposer(props: Record<string, unknown> = {}) {
    return render(
      <AuthProvider>
        <AuthProbe />
        <MemoryRouter>
          <ChatInputArea onSubmitted={() => {}} {...props} />
        </MemoryRouter>
      </AuthProvider>,
    );
  }

  async function chooseDeepSeek() {
    const separate = screen.queryByRole("button", {
      name: "Start a separate research",
    });
    if (separate) await userEvent.click(separate);
    const trigger = await screen.findByRole("button", {
      name: "Model for this research",
    });
    await waitFor(() => expect(trigger.hasAttribute("disabled")).toBe(false));
    await userEvent.click(trigger);
    await userEvent.click(await screen.findByText("deepseek-v4-pro"));
  }

  async function ask(question: string, expected = 1) {
    await userEvent.type(
      screen.getByPlaceholderText("What do you want to research?"),
      question,
    );
    await userEvent.click(screen.getByRole("button", { name: "Ask" }));
    await waitFor(() => expect(startBodies).toHaveLength(expected));
  }

  async function acknowledgePriorLaunches() {
    const separate = screen.queryByRole("button", {
      name: "Start a separate research",
    });
    if (separate) await userEvent.click(separate);
  }

  let probedComposer: ReturnType<typeof useResearchComposer>;
  let probedController: OwnerModelController;
  const probeSubmitted = () => {};
  function ComposerLifecycleProbe({ onSubmitted = probeSubmitted }: Pick<ResearchComposerProps, "onSubmitted">) {
    probedController = useOwnerModelController({
      operationPrefix: "probe",
      policy: "strict-owner",
      allowHouse: true,
    });
    probedComposer = useResearchComposer({
      controller: probedController,
      onSubmitted,
    });
    return (
      <output data-testid="probed-question">{probedComposer.question}</output>
    );
  }

  function ChildComposerLifecycleProbe(props: ResearchComposerProps) {
    probedComposer = useResearchComposer({
      parentInvestigationId: "child-existing-parent",
      onSubmitted: probeSubmitted,
      ...props,
    });
    return (
      <output data-testid="child-probed-question">{probedComposer.question}</output>
    );
  }

  return {
    setUp,
    tearDown,
    AuthProbe,
    ComposerLifecycleProbe,
    ChildComposerLifecycleProbe,
    probeSubmitted,
    renderComposer,
    chooseDeepSeek,
    ask,
    acknowledgePriorLaunches,
    deferredResponse,
    receipt,
    jsonResponse,
    executableModel,
    get auth() { return auth; },
    get startBodies() { return startBodies; },
    get probedComposer() { return probedComposer; },
    get probedController() { return probedController; },
    get identity() { return identity; },
    set identity(value: typeof identity) { identity = value; },
    get authRead() { return authRead; },
    set authRead(value: typeof authRead) { authRead = value; },
    get startRead() { return startRead; },
    set startRead(value: typeof startRead) { startRead = value; },
  };
}
