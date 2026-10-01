import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import {
  act,
  cleanup,
  fireEvent,
  render,
  screen,
  waitFor,
  within,
} from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { StrictMode } from "react";
import { MemoryRouter } from "react-router-dom";

import { AuthProvider, useAuth, type AuthContextValue } from "../../lib/auth";
import ChatInputArea from "./ChatInputArea";
import { ChatStoryFixture } from "./ChatInputArea.stories";
import {
  useResearchComposer,
  type ResearchComposerProps,
} from "./useResearchComposer";
import {
  useOwnerModelController,
  type OwnerModelController,
} from "../../hooks/useOwnerModelController";

const launchTelemetry = vi.hoisted(() => ({
  enabled: false,
  capture: vi.fn(),
  captureException: vi.fn(),
  identify: vi.fn(),
  reset: vi.fn(),
}));
vi.mock("../../lib/posthogClient", () => ({
  get posthogEnabled() {
    return launchTelemetry.enabled;
  },
  posthog: {
    capture: launchTelemetry.capture,
    captureException: launchTelemetry.captureException,
    identify: launchTelemetry.identify,
    reset: launchTelemetry.reset,
  },
}));

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
 *   2. leaving the root picker unselected blocks a start; the house route
 *      requires explicit selection and sends no saved-model fields;
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
function deferredResponse() {
  let resolve!: (value: Response) => void;
  let reject!: (error: Error) => void;
  const promise = new Promise<Response>((yes, no) => {
    resolve = yes;
    reject = no;
  });
  return { promise, resolve, reject };
}
const receipt = (id: string) =>
  jsonResponse({
    investigation_id: id,
    status: "in_progress",
    start_event_id: `event-${id}`,
  });

beforeEach(() => {
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
});

afterEach(() => {
  vi.unstubAllGlobals();
  cleanup();
});

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

  it("dispatches nothing until an explicit saved or house choice", async () => {
    renderComposer();
    // The picker is present and loaded; it is simply not touched.
    const trigger = await screen.findByRole("button", {
      name: "Model for this research",
    });
    await waitFor(() => expect(trigger.hasAttribute("disabled")).toBe(false));
    await ask("what changed in the margin structure?", 0);
    expect(startBodies).toHaveLength(0);
  });

  it("offers no picker on a chased composer, and starts without one", async () => {
    renderComposer({
      parentInvestigationId: "inv-parent",
      spawnContext: "the passage being chased",
    });
    await waitFor(() =>
      expect(screen.getByRole("button", { name: "Ask" })).toBeTruthy(),
    );
    expect(
      screen.queryByRole("button", { name: "Model for this research" }),
    ).toBeNull();

    await acknowledgePriorLaunches();
    await userEvent.click(screen.getByRole("button", { name: "Ask" }));
    await waitFor(() => expect(startBodies).toHaveLength(1));
    expect(startBodies[0]).not.toHaveProperty("model_choice");
    expect(startBodies[0].parent_investigation_id).toBe("inv-parent");
  });
});

describe("ChatInputArea — the mode survives its navigation (lane A B2-8)", () => {
  it("a research started inside /inv/<id>?m=reading opens at /inv/<new>?m=reading", async () => {
    const { Routes, Route, useLocation } = await import("react-router-dom");
    function Where() {
      const loc = useLocation();
      return <span data-testid="where">{loc.pathname + loc.search}</span>;
    }
    render(
      <AuthProvider>
        <MemoryRouter initialEntries={["/inv/inv-parent?m=reading"]}>
          <Routes>
            <Route
              path="*"
              element={
                <>
                  <Where />
                  <ChatInputArea />
                </>
              }
            />
          </Routes>
        </MemoryRouter>
      </AuthProvider>,
    );
    await waitFor(() =>
      expect(screen.getByRole("button", { name: "Ask" })).toBeTruthy(),
    );
    await chooseDeepSeek();
    await ask("what changed in the margin structure?");
    await waitFor(() =>
      expect(screen.getByTestId("where").textContent).toBe(
        "/inv/inv-started?m=reading",
      ),
    );
  });
});

describe("root admission and exact variant", () => {
  it("displays the selected secondary variant and serializes that same tuple", async () => {
    renderComposer();
    const trigger = await screen.findByRole("button", {
      name: "Model for this research",
    });
    await waitFor(() => expect(trigger.hasAttribute("disabled")).toBe(false));
    await userEvent.click(trigger);
    await userEvent.click(await screen.findByText("deepseek-v4-flash"));
    expect(trigger.textContent).toContain("deepseek-v4-flash");
    await ask("a precise secondary question");
    expect(startBodies[0].model_choice).toMatchObject({
      provider_id: executableModel.id,
      model_id: "deepseek-v4-flash",
    });
  });
  it.each([{ parentInvestigationId: "" }, { spawnContext: "" }])(
    "preserves child admission for present empty fields %j",
    async (props) => {
      renderComposer(props);
      await waitFor(() =>
        expect(screen.getByRole("button", { name: "Ask" })).toBeTruthy(),
      );
      expect(
        screen.queryByRole("button", { name: "Model for this research" }),
      ).toBeNull();
      await acknowledgePriorLaunches();
      await ask("child request with an empty present field");
      expect(startBodies[0]).not.toHaveProperty("model_choice");
      expect(startBodies[0]).not.toHaveProperty("operation_id");
      const field =
        "parentInvestigationId" in props
          ? "parent_investigation_id"
          : "spawn_context";
      expect(startBodies[0][field]).toBe("");
    },
  );
});

describe("child issued action lifecycle", () => {
  const childProps = {
    parentInvestigationId: "child-lifecycle-parent",
    spawnContext: "",
  };

  async function readyChild(onSubmitted: (id: string) => void) {
    const view = renderComposer({ ...childProps, onSubmitted });
    await waitFor(() =>
      expect(auth.modelExecution.readCurrent().kind).toBe("ready"),
    );
    await acknowledgePriorLaunches();
    return view;
  }

  function childProbeTree(props: ResearchComposerProps) {
    return (
      <AuthProvider>
        <AuthProbe />
        <MemoryRouter>
          <ChildComposerLifecycleProbe {...props} />
        </MemoryRouter>
      </AuthProvider>
    );
  }

  async function readyProbe(props: ResearchComposerProps) {
    const view = render(childProbeTree(props));
    await waitFor(() =>
      expect(auth.modelExecution.readCurrent().kind).toBe("ready"),
    );
    act(() => probedComposer.startSeparate());
    return view;
  }

  it("notifies two mounted root and child composers without dispatch and releases only the matching hold", async () => {
    const rootResponse = deferredResponse();
    const childResponse = deferredResponse();
    const separateRootResponse = deferredResponse();
    const rootSubmitted = vi.fn();
    const childSubmitted = vi.fn();
    const root = renderComposer({ onSubmitted: rootSubmitted });
    await chooseDeepSeek();
    const rootUI = within(root.container);
    const rootField = rootUI.getByPlaceholderText("What do you want to research?");
    fireEvent.change(rootField, { target: { value: "first mounted root question" } });
    const child = renderComposer({ ...childProps, onSubmitted: childSubmitted });
    await waitFor(() => expect(auth.modelExecution.readCurrent().kind).toBe("ready"));
    const childUI = within(child.container);
    const childField = childUI.getByPlaceholderText("What do you want to research?");
    fireEvent.change(childField, { target: { value: "mounted child draft" } });
    expect(childUI.getByRole("button", { name: "Ask" }).hasAttribute("disabled")).toBe(false);
    startRead = () => rootResponse.promise;
    await userEvent.click(rootUI.getByRole("button", { name: "Ask" }));
    await waitFor(() => expect(startBodies).toHaveLength(1));
    expect(childUI.getByRole("button", { name: "Ask" }).hasAttribute("disabled")).toBe(true);
    expect(childUI.getByRole("button", { name: "Start a separate research" })).toBeTruthy();
    expect(childField).toHaveProperty("value", "mounted child draft");
    await act(async () => rootResponse.resolve(receipt("mounted-root")));
    await waitFor(() => expect(childUI.getByRole("button", { name: "Ask" }).hasAttribute("disabled")).toBe(false));
    expect(childUI.queryByRole("button", { name: "Start a separate research" })).toBeNull();
    expect(childField).toHaveProperty("value", "mounted child draft");
    expect(startBodies).toHaveLength(1);
    expect(childSubmitted).not.toHaveBeenCalled();

    startRead = () => childResponse.promise;
    await userEvent.click(childUI.getByRole("button", { name: "Ask" }));
    fireEvent.change(rootField, { target: { value: "separate mounted root draft" } });
    expect(rootUI.getByRole("button", { name: "Ask" }).hasAttribute("disabled")).toBe(true);
    await userEvent.click(rootUI.getByRole("button", { name: "Start a separate research" }));
    startRead = () => separateRootResponse.promise;
    await userEvent.click(rootUI.getByRole("button", { name: "Ask" }));
    expect(startBodies).toHaveLength(3);
    await act(async () => childResponse.resolve(receipt("mounted-child")));
    expect(rootUI.getByRole("button", { name: "…" }).hasAttribute("disabled")).toBe(true);
    expect(rootUI.getByRole("button", { name: "Start a separate research" })).toBeTruthy();
    expect(rootField).toHaveProperty("value", "separate mounted root draft");
    expect(rootSubmitted).toHaveBeenCalledTimes(1);
    expect(childSubmitted).toHaveBeenCalledTimes(1);
    expect(startBodies).toHaveLength(3);
    await act(async () => separateRootResponse.resolve(receipt("mounted-separate-root")));
    expect(rootSubmitted).toHaveBeenCalledTimes(2);
    expect(startBodies).toHaveLength(3);
  });

  it.each(["child", "root"])("reprojects a remounted %s after an old late receipt without navigating or clearing its new draft", async (route) => {
    const pending = deferredResponse();
    const onSubmitted = vi.fn();
    startRead = () => pending.promise;
    const view = route === "child"
      ? await readyChild(onSubmitted)
      : renderComposer({ onSubmitted });
    if (route === "root") await chooseDeepSeek();
    await ask("old child private draft");
    view.unmount();
    renderComposer(route === "child" ? { ...childProps, onSubmitted } : { onSubmitted });
    await waitFor(() =>
      expect(auth.modelExecution.readCurrent().kind).toBe("ready"),
    );
    await screen.findByRole("button", { name: "Start a separate research" });
    if (route === "root") {
      const trigger = await screen.findByRole("button", { name: "Model for this research" });
      await waitFor(() => expect(trigger.hasAttribute("disabled")).toBe(false));
      await userEvent.click(trigger);
      await userEvent.click(await screen.findByText("deepseek-v4-pro"));
    }
    const field = screen.getByPlaceholderText("What do you want to research?");
    fireEvent.change(field, { target: { value: "remounted deliberate draft" } });
    expect(screen.getByRole("button", { name: "Ask" }).hasAttribute("disabled")).toBe(true);

    await act(async () => pending.resolve(receipt("old-child-accepted")));
    await waitFor(() =>
      expect(screen.getByRole("button", { name: "Ask" }).hasAttribute("disabled")).toBe(false),
    );
    expect(screen.queryByRole("button", { name: "Start a separate research" })).toBeNull();
    expect(field).toHaveProperty("value", "remounted deliberate draft");
    expect(onSubmitted).not.toHaveBeenCalled();
    startRead = null;
    await userEvent.click(screen.getByRole("button", { name: "Ask" }));
    await waitFor(() => expect(startBodies).toHaveLength(2));
    if (route === "child") {
      expect(startBodies[1]).toEqual({
        question: "remounted deliberate draft",
        parent_investigation_id: childProps.parentInvestigationId,
        spawn_context: "",
      });
    } else {
      expect(startBodies[1].question).toBe("remounted deliberate draft");
      expect(startBodies[1]).toHaveProperty("model_choice");
      expect(startBodies[1]).toHaveProperty("operation_id");
    }
    await waitFor(() => expect(onSubmitted).toHaveBeenCalledWith("inv-started"));
    expect(onSubmitted).toHaveBeenCalledTimes(1);
  });

  it("dispatches one child DTO for synchronous activation and admits a confirmed identical new turn", async () => {
    const pending = deferredResponse();
    const onSubmitted = vi.fn();
    startRead = () => pending.promise;
    await readyChild(onSubmitted);
    const field = screen.getByPlaceholderText("What do you want to research?");
    fireEvent.change(field, { target: { value: "identical child question" } });
    const button = screen.getByRole("button", { name: "Ask" });
    act(() => {
      fireEvent.click(button);
      fireEvent.click(button);
    });
    expect(startBodies).toEqual([{
      question: "identical child question",
      parent_investigation_id: childProps.parentInvestigationId,
      spawn_context: "",
    }]);
    await act(async () => pending.resolve(receipt("child-first-confirmed")));
    expect(onSubmitted).toHaveBeenCalledWith("child-first-confirmed");
    startRead = null;
    await ask("identical child question", 2);
    expect(startBodies[1]).toEqual(startBodies[0]);
    await waitFor(() => expect(onSubmitted).toHaveBeenCalledTimes(2));
  });

  it("retires a pending child action after explicit separation without clearing the next draft", async () => {
    const pending = deferredResponse();
    const onSubmitted = vi.fn();
    startRead = () => pending.promise;
    await readyChild(onSubmitted);
    await ask("retired pending child question");
    await userEvent.click(screen.getByRole("button", { name: "Start a separate research" }));
    const field = screen.getByPlaceholderText("What do you want to research?");
    fireEvent.change(field, { target: { value: "new separate child draft" } });
    await act(async () => pending.resolve(receipt("retired-child")));
    expect(onSubmitted).not.toHaveBeenCalled();
    expect(field).toHaveProperty("value", "new separate child draft");
    startRead = null;
    await userEvent.click(screen.getByRole("button", { name: "Ask" }));
    await waitFor(() => expect(startBodies).toHaveLength(2));
    expect(startBodies[1].question).toBe("new separate child draft");
    await waitFor(() => expect(onSubmitted).toHaveBeenCalledTimes(1));
  });

  it.each(["root", "child"])("projects a pending %s hold into the other route and requires explicit separation", async (firstRoute) => {
    const old = deferredResponse();
    const next = deferredResponse();
    const oldSubmitted = vi.fn();
    const nextSubmitted = vi.fn();
    startRead = () => old.promise;
    const first = firstRoute === "root"
      ? renderComposer({ onSubmitted: oldSubmitted })
      : renderComposer({ ...childProps, onSubmitted: oldSubmitted });
    await waitFor(() => expect(auth.modelExecution.readCurrent().kind).toBe("ready"));
    if (firstRoute === "root") await chooseDeepSeek();
    else await acknowledgePriorLaunches();
    await ask("first route private question");
    first.unmount();
    renderComposer(firstRoute === "root"
      ? { ...childProps, onSubmitted: nextSubmitted }
      : { onSubmitted: nextSubmitted });
    await waitFor(() => expect(auth.modelExecution.readCurrent().kind).toBe("ready"));
    await screen.findByRole("button", { name: "Start a separate research" });
    expect(document.body.textContent).not.toContain("first route private question");
    fireEvent.change(screen.getByPlaceholderText("What do you want to research?"), {
      target: { value: "other route deliberate question" },
    });
    expect(screen.getByRole("button", { name: "Ask" }).hasAttribute("disabled")).toBe(true);
    fireEvent.click(screen.getByRole("button", { name: "Ask" }));
    expect(startBodies).toHaveLength(1);
    if (firstRoute === "child") await chooseDeepSeek();
    else await acknowledgePriorLaunches();
    startRead = () => next.promise;
    await userEvent.click(screen.getByRole("button", { name: "Ask" }));
    await waitFor(() => expect(startBodies).toHaveLength(2));
    if (firstRoute === "root") {
      expect(startBodies[1]).toEqual({
        question: "other route deliberate question",
        parent_investigation_id: childProps.parentInvestigationId,
        spawn_context: "",
      });
    } else {
      expect(startBodies[1]).toHaveProperty("model_choice");
      expect(startBodies[1]).toHaveProperty("operation_id");
    }
    await act(async () => old.resolve(receipt("old-route-accepted")));
    expect(oldSubmitted).not.toHaveBeenCalled();
    expect(nextSubmitted).not.toHaveBeenCalled();
    expect(screen.getByRole("button", { name: "…" }).hasAttribute("disabled")).toBe(true);
    expect(screen.getByPlaceholderText("What do you want to research?")).toHaveProperty("value", "other route deliberate question");
    await act(async () => next.resolve(receipt("other-route-accepted")));
    expect(nextSubmitted).toHaveBeenCalledWith("other-route-accepted");
    expect(nextSubmitted).toHaveBeenCalledTimes(1);
  });

  it.each(["child", "root"])("keeps a confirmed %s start accepted when onSubmitted throws and permits a deliberate next turn", async (route) => {
    const onSubmitted = vi.fn()
      .mockImplementationOnce(() => { throw new Error("private callback detail"); })
      .mockImplementation(() => {});
    if (route === "child") await readyChild(onSubmitted);
    else {
      renderComposer({ onSubmitted });
      await chooseDeepSeek();
    }
    await ask("confirmed callback failure question");
    await screen.findByText("Research started, but the composer could not open it.");
    expect(onSubmitted).toHaveBeenCalledTimes(1);
    expect(screen.getByPlaceholderText("What do you want to research?")).toHaveProperty("value", "");
    expect(screen.queryByText(/Could not confirm the start/)).toBeNull();
    expect(document.body.textContent).not.toContain("private callback detail");
    expect(startBodies).toHaveLength(1);
    await acknowledgePriorLaunches();
    await ask("deliberate confirmed next turn", 2);
    await waitFor(() => expect(onSubmitted).toHaveBeenCalledTimes(2));
    if (route === "root") {
      expect(startBodies[1].operation_id).not.toBe(startBodies[0].operation_id);
    } else {
      expect(startBodies[1]).toEqual({
        question: "deliberate confirmed next turn",
        parent_investigation_id: childProps.parentInvestigationId,
        spawn_context: "",
      });
    }
  });

  it.each([
    { outcome: "rejected", response: null },
    { outcome: "malformed", response: { investigation_id: "late-incomplete", status: "in_progress" } },
  ])("keeps a late $outcome child hold after its origin unmounts", async ({ outcome, response }) => {
    const pending = deferredResponse();
    const onSubmitted = vi.fn();
    startRead = () => pending.promise;
    const origin = await readyChild(onSubmitted);
    await ask("unmounted unconfirmed child");
    origin.unmount();
    renderComposer({ ...childProps, onSubmitted });
    await waitFor(() => expect(auth.modelExecution.readCurrent().kind).toBe("ready"));
    await screen.findByRole("button", { name: "Start a separate research" });
    const field = screen.getByPlaceholderText("What do you want to research?");
    fireEvent.change(field, { target: { value: "fresh remount child draft" } });
    await act(async () => {
      if (outcome === "rejected") pending.reject(new Error("late fixture failure"));
      else pending.resolve(jsonResponse(response));
    });
    expect(screen.getByRole("button", { name: "Start a separate research" })).toBeTruthy();
    expect(screen.getByRole("button", { name: "Ask" }).hasAttribute("disabled")).toBe(true);
    expect(field).toHaveProperty("value", "fresh remount child draft");
    expect(onSubmitted).not.toHaveBeenCalled();
    fireEvent.click(screen.getByRole("button", { name: "Ask" }));
    expect(startBodies).toHaveLength(1);
    await userEvent.click(screen.getByRole("button", { name: "Start a separate research" }));
    startRead = null;
    await userEvent.click(screen.getByRole("button", { name: "Ask" }));
    await waitFor(() => expect(startBodies).toHaveLength(2));
    await waitFor(() => expect(onSubmitted).toHaveBeenCalledTimes(1));
    expect(startBodies[1]).toEqual({
      question: "fresh remount child draft",
      parent_investigation_id: childProps.parentInvestigationId,
      spawn_context: "",
    });
  });

  it.each([
    { outcome: "rejected", response: null },
    { outcome: "ID-only", response: { investigation_id: "not-a-complete-receipt" } },
    { outcome: "blank-status", response: { investigation_id: "inv", status: "", start_event_id: "event" } },
    { outcome: "missing-event", response: { investigation_id: "inv", status: "in_progress" } },
    { outcome: "blank-event", response: { investigation_id: "inv", status: "in_progress", start_event_id: "" } },
  ])("holds a $outcome child response across the same mount and remount until deliberate separation", async ({ outcome, response }) => {
    const pending = deferredResponse();
    const onSubmitted = vi.fn();
    startRead = () => pending.promise;
    const view = await readyChild(onSubmitted);
    await ask("unconfirmed child question");
    await act(async () => {
      if (outcome === "rejected") pending.reject(new Error("fixture child transport failed"));
      else pending.resolve(jsonResponse(response));
    });
    await screen.findByText(/Could not confirm the start/);
    await screen.findByRole("button", { name: "Start a separate research" });
    expect(onSubmitted).not.toHaveBeenCalled();
    expect(screen.getByRole("button", { name: "Ask" }).hasAttribute("disabled")).toBe(true);
    fireEvent.click(screen.getByRole("button", { name: "Ask" }));
    expect(startBodies).toHaveLength(1);
    view.unmount();

    renderComposer({ ...childProps, onSubmitted });
    await waitFor(() => expect(auth.modelExecution.readCurrent().kind).toBe("ready"));
    await screen.findByRole("button", { name: "Start a separate research" });
    const field = screen.getByPlaceholderText("What do you want to research?");
    expect(field).toHaveProperty("value", "");
    fireEvent.change(field, { target: { value: "deliberate separate child" } });
    fireEvent.click(screen.getByRole("button", { name: "Ask" }));
    expect(startBodies).toHaveLength(1);
    await userEvent.click(screen.getByRole("button", { name: "Start a separate research" }));
    startRead = null;
    await userEvent.click(screen.getByRole("button", { name: "Ask" }));
    await waitFor(() => expect(startBodies).toHaveLength(2));
    expect(startBodies[1]).toEqual({
      question: "deliberate separate child",
      parent_investigation_id: childProps.parentInvestigationId,
      spawn_context: "",
    });
    await waitFor(() => expect(onSubmitted).toHaveBeenCalledWith("inv-started"));
    expect(onSubmitted).toHaveBeenCalledTimes(1);
  });

  it("refuses callable child blind repeats after rejection and remount", async () => {
    const pending = deferredResponse();
    const onSubmitted = vi.fn();
    startRead = () => pending.promise;
    const view = await readyProbe({ ...childProps, onSubmitted });
    act(() => probedComposer.changeQuestion("callable uncertain child"));
    const retained = probedComposer;
    await act(async () => { void probedComposer.submit(); });
    await act(async () => pending.reject(new Error("fixture callable child failure")));
    expect(probedComposer.showUncertainty).toBe(true);
    expect(probedComposer.submitDisabled).toBe(true);
    await act(async () => {
      void retained.submit();
      void probedComposer.submit();
    });
    expect(startBodies).toHaveLength(1);
    view.unmount();
    render(childProbeTree({ ...childProps, onSubmitted }));
    await waitFor(() => expect(auth.modelExecution.readCurrent().kind).toBe("ready"));
    act(() => probedComposer.changeQuestion("remounted callable child"));
    expect(probedComposer.showUncertainty).toBe(true);
    await act(async () => { void probedComposer.submit(); });
    expect(startBodies).toHaveLength(1);
    act(() => probedComposer.startSeparate());
    startRead = null;
    await act(async () => { await probedComposer.submit(); });
    expect(startBodies[1]).toEqual({
      question: "remounted callable child",
      parent_investigation_id: childProps.parentInvestigationId,
      spawn_context: "",
    });
    expect(onSubmitted).toHaveBeenCalledTimes(1);
  });

  it("retires old props callbacks and a late child receipt without mutating the replacement draft", async () => {
    const pending = deferredResponse();
    const oldSubmitted = vi.fn();
    const nextSubmitted = vi.fn();
    startRead = () => pending.promise;
    const view = await readyProbe({
      parentInvestigationId: "old-parent",
      spawnContext: "old caller context",
      onSubmitted: oldSubmitted,
    });
    act(() => probedComposer.changeQuestion("old props child question"));
    const retired = probedComposer;
    await act(async () => { void probedComposer.submit(); });
    view.rerender(childProbeTree({
      parentInvestigationId: "new-parent",
      spawnContext: "new caller context",
      onSubmitted: nextSubmitted,
    }));
    expect(probedComposer.question).toBe("");
    act(() => probedComposer.changeQuestion("new props deliberate draft"));
    await act(async () => { await probedComposer.submit(); });
    expect(startBodies).toHaveLength(1);
    act(() => {
      probedComposer.startSeparate();
      probedComposer.changeQuestion("new props deliberate draft");
    });
    await act(async () => {
      retired.changeQuestion("retired props injected draft");
      retired.startSeparate();
      void retired.submit();
    });
    expect(startBodies).toHaveLength(1);
    expect(probedComposer.question).toBe("new props deliberate draft");
    await act(async () => pending.resolve(receipt("old-props-accepted")));
    expect(oldSubmitted).not.toHaveBeenCalled();
    expect(nextSubmitted).not.toHaveBeenCalled();
    expect(probedComposer.question).toBe("new props deliberate draft");
    act(() => probedComposer.startSeparate());
    startRead = null;
    await act(async () => { await probedComposer.submit(); });
    expect(startBodies[1]).toEqual({
      question: "new props deliberate draft",
      parent_investigation_id: "new-parent",
      spawn_context: "new caller context",
    });
    expect(nextSubmitted).toHaveBeenCalledTimes(1);
  });

  it("retires A child callbacks during B pending and a new A epoch while keeping old receipts private", async () => {
    const oldAResponse = deferredResponse();
    const bResponse = deferredResponse();
    const newAResponse = deferredResponse();
    const onSubmitted = vi.fn();
    startRead = () => oldAResponse.promise;
    await readyProbe({ ...childProps, onSubmitted });
    act(() => probedComposer.changeQuestion("A private original child"));
    const oldA = probedComposer;
    await act(async () => { void probedComposer.submit(); });
    identity = { ...identity, user_id: "child-account-b" };
    await act(async () => auth.refresh());
    expect(probedComposer.question).toBe("");
    expect(probedComposer.showUncertainty).toBe(true);
    expect(document.body.textContent).not.toContain("A private original child");
    act(() => {
      probedComposer.startSeparate();
      probedComposer.changeQuestion("B private child");
    });
    startRead = () => bResponse.promise;
    await act(async () => { void probedComposer.submit(); });
    await act(async () => {
      oldA.changeQuestion("old A injected child");
      oldA.startSeparate();
      void oldA.submit();
    });
    expect(probedComposer.question).toBe("B private child");
    expect(probedComposer.busy).toBe(true);
    expect(startBodies).toHaveLength(2);
    identity = { ...identity, user_id: "fixture-owner" };
    await act(async () => auth.refresh());
    expect(probedComposer.question).toBe("");
    act(() => {
      probedComposer.startSeparate();
      probedComposer.changeQuestion("A new epoch child");
    });
    startRead = () => newAResponse.promise;
    await act(async () => { void probedComposer.submit(); });
    await act(async () => {
      oldA.changeQuestion("old A epoch injected child");
      oldA.startSeparate();
      void oldA.submit();
    });
    expect(probedComposer.question).toBe("A new epoch child");
    expect(probedComposer.busy).toBe(true);
    expect(probedComposer.submitDisabled).toBe(true);
    expect(startBodies).toHaveLength(3);
    await act(async () => {
      oldAResponse.resolve(receipt("old-a-child"));
      bResponse.resolve(receipt("old-b-child"));
    });
    expect(onSubmitted).not.toHaveBeenCalled();
    expect(probedComposer.question).toBe("A new epoch child");
    expect(probedComposer.busy).toBe(true);
    await act(async () => newAResponse.resolve(receipt("new-a-child")));
    expect(onSubmitted).toHaveBeenCalledWith("new-a-child");
    expect(onSubmitted).toHaveBeenCalledTimes(1);
    expect(startBodies).toEqual([
      { question: "A private original child", parent_investigation_id: childProps.parentInvestigationId, spawn_context: "" },
      { question: "B private child", parent_investigation_id: childProps.parentInvestigationId, spawn_context: "" },
      { question: "A new epoch child", parent_investigation_id: childProps.parentInvestigationId, spawn_context: "" },
    ]);
  });
});

describe("research launch telemetry boundary", () => {
  beforeEach(() => {
    launchTelemetry.enabled = false;
    launchTelemetry.capture.mockReset();
    launchTelemetry.captureException.mockReset();
  });
  afterEach(() => {
    launchTelemetry.enabled = false;
    launchTelemetry.capture.mockReset();
    launchTelemetry.captureException.mockReset();
    launchTelemetry.identify.mockClear();
    launchTelemetry.reset.mockClear();
  });

  async function readyTelemetryComposer(
    route: string,
    onSubmitted: (id: string) => void,
  ) {
    renderComposer(route === "root"
      ? { onSubmitted }
      : { parentInvestigationId: "telemetry-child-parent", spawnContext: "", onSubmitted });
    await waitFor(() => expect(auth.modelExecution.readCurrent().kind).toBe("ready"));
    if (route === "root") await chooseDeepSeek();
    else await acknowledgePriorLaunches();
  }

  async function askWithFailingTelemetry(question: string) {
    await userEvent.type(
      screen.getByPlaceholderText("What do you want to research?"),
      question,
    );
    launchTelemetry.enabled = true;
    launchTelemetry.capture.mockImplementation(() => {
      throw new Error("fixture success telemetry failure");
    });
    launchTelemetry.captureException.mockImplementation(() => {
      throw new Error("fixture exception telemetry failure");
    });
    await userEvent.click(screen.getByRole("button", { name: "Ask" }));
    await waitFor(() => expect(startBodies).toHaveLength(1));
  }

  it.each(["root", "child"])("finishes a confirmed %s receipt when both telemetry methods throw", async (route) => {
    const onSubmitted = vi.fn();
    await readyTelemetryComposer(route, onSubmitted);
    await askWithFailingTelemetry("confirmed telemetry boundary question");
    await waitFor(() => expect(onSubmitted).toHaveBeenCalledWith("inv-started"));
    expect(onSubmitted).toHaveBeenCalledTimes(1);
    expect(screen.getByPlaceholderText("What do you want to research?")).toHaveProperty("value", "");
    expect(launchTelemetry.capture).toHaveBeenCalledWith("investigation_started", {
      question_length: "confirmed telemetry boundary question".length,
      has_parent: route === "child",
      has_spawn_context: route === "child",
    });
    expect(launchTelemetry.capture).toHaveBeenCalledTimes(1);
    expect(launchTelemetry.captureException).not.toHaveBeenCalled();
    expect(screen.queryByText(/Research started, but/)).toBeNull();
    expect(screen.queryByText(/Could not confirm the start/)).toBeNull();
    expect(screen.getByRole("button", { name: "Ask" }).hasAttribute("disabled")).toBe(true);
    fireEvent.click(screen.getByRole("button", { name: "Ask" }));
    expect(startBodies).toHaveLength(1);
    if (route === "child") {
      expect(startBodies[0]).toEqual({
        question: "confirmed telemetry boundary question",
        parent_investigation_id: "telemetry-child-parent",
        spawn_context: "",
      });
    } else {
      expect(startBodies[0]).toHaveProperty("model_choice");
      expect(startBodies[0]).toHaveProperty("operation_id");
    }
  });

  it.each(["root", "child"])("shows a known %s start when its callback and exception reporting both throw", async (route) => {
    const privateCallbackError = new Error("private callback failure");
    const onSubmitted = vi.fn(() => { throw privateCallbackError; });
    await readyTelemetryComposer(route, onSubmitted);
    await askWithFailingTelemetry("known start callback telemetry question");
    await screen.findByText("Research started, but the composer could not open it.");
    expect(onSubmitted).toHaveBeenCalledWith("inv-started");
    expect(onSubmitted).toHaveBeenCalledTimes(1);
    expect(launchTelemetry.capture).toHaveBeenCalledTimes(1);
    expect(launchTelemetry.captureException).toHaveBeenCalledWith(
      new Error("Research start completion callback failed."),
    );
    expect(launchTelemetry.captureException).toHaveBeenCalledTimes(1);
    expect(launchTelemetry.captureException).not.toHaveBeenCalledWith(privateCallbackError);
    expect(screen.queryByText(/Could not confirm the start/)).toBeNull();
    expect(document.body.textContent).not.toContain("private callback failure");
    expect(document.body.textContent).not.toContain("fixture exception telemetry failure");
    expect(screen.getByPlaceholderText("What do you want to research?")).toHaveProperty("value", "");
    expect(screen.getByRole("button", { name: "Ask" }).hasAttribute("disabled")).toBe(true);
    fireEvent.click(screen.getByRole("button", { name: "Ask" }));
    expect(startBodies).toHaveLength(1);
  });

  it.each(["root", "child"])("keeps a rejected %s start unknown when exception reporting throws", async (route) => {
    const pending = deferredResponse();
    const privateTransportError = new Error("private transport failure");
    const onSubmitted = vi.fn();
    startRead = () => pending.promise;
    await readyTelemetryComposer(route, onSubmitted);
    await askWithFailingTelemetry("unknown telemetry boundary question");
    await act(async () => pending.reject(privateTransportError));
    await screen.findByText(/Could not confirm the start/);
    expect(screen.getByRole("button", { name: "Start a separate research" })).toBeTruthy();
    expect(screen.getByRole("button", { name: "Ask" }).hasAttribute("disabled")).toBe(true);
    expect(screen.getByPlaceholderText("What do you want to research?")).toHaveProperty("value", "unknown telemetry boundary question");
    expect(launchTelemetry.capture).not.toHaveBeenCalled();
    expect(launchTelemetry.captureException).toHaveBeenCalledWith(
      new Error("Research start could not be confirmed."),
    );
    expect(launchTelemetry.captureException).toHaveBeenCalledTimes(1);
    expect(launchTelemetry.captureException).not.toHaveBeenCalledWith(privateTransportError);
    expect(onSubmitted).not.toHaveBeenCalled();
    expect(document.body.textContent).not.toContain("private transport failure");
    expect(document.body.textContent).not.toContain("fixture exception telemetry failure");
    fireEvent.click(screen.getByRole("button", { name: "Ask" }));
    expect(startBodies).toHaveLength(1);
  });
});

describe("root issued action lifecycle", () => {
  it("requires explicit house and gives a confirmed new identical turn a new operation intent", async () => {
    const onSubmitted = vi.fn();
    renderComposer({ onSubmitted });
    await chooseDeepSeek();
    await ask("identical confirmed question");
    const first = startBodies[0].operation_id;
    await acknowledgePriorLaunches();
    await userEvent.type(
      screen.getByPlaceholderText("What do you want to research?"),
      "identical confirmed question",
    );
    await userEvent.click(screen.getByRole("button", { name: "Ask" }));
    await waitFor(() => expect(startBodies).toHaveLength(2));
    expect(startBodies[1].operation_id).not.toBe(first);
    expect(onSubmitted).toHaveBeenCalledTimes(2);
  });
  it("sends explicit house without inventing saved model fields", async () => {
    renderComposer();
    await chooseDeepSeek();
    await userEvent.click(
      screen.getByRole("button", { name: "Model for this research" }),
    );
    await userEvent.click(await screen.findByText("Default (house route)"));
    await ask("a deliberate house question");
    expect(startBodies[0]).not.toHaveProperty("model_choice");
    expect(startBodies[0]).not.toHaveProperty("operation_id");
  });
  it("blocks a synchronous double activation of the same logical request", async () => {
    const pending = deferredResponse();
    startRead = () => pending.promise;
    renderComposer();
    await chooseDeepSeek();
    fireEvent.change(
      screen.getByPlaceholderText("What do you want to research?"),
      { target: { value: "synchronous double question" } },
    );
    const button = screen.getByRole("button", { name: "Ask" });
    act(() => {
      fireEvent.click(button);
      fireEvent.click(button);
    });
    expect(startBodies).toHaveLength(1);
    await act(async () => pending.resolve(receipt("double-finished")));
  });
  it("retains uncertainty across unmount and starts separately only on an explicit new intent", async () => {
    const first = deferredResponse();
    const onSubmitted = vi.fn();
    startRead = () => first.promise;
    const view = renderComposer({ onSubmitted });
    await chooseDeepSeek();
    await ask("a prior private question");
    view.unmount();
    renderComposer({ onSubmitted });
    await screen.findByRole("button", { name: "Start a separate research" });
    expect(
      (
        screen.getByPlaceholderText(
          "What do you want to research?",
        ) as HTMLTextAreaElement
      ).value,
    ).toBe("");
    await chooseDeepSeek();
    startRead = null;
    await userEvent.type(
      screen.getByPlaceholderText("What do you want to research?"),
      "a separate new question",
    );
    await userEvent.click(screen.getByRole("button", { name: "Ask" }));
    await waitFor(() => expect(startBodies).toHaveLength(2));
    expect(startBodies[1].operation_id).not.toBe(startBodies[0].operation_id);
    await act(async () => first.resolve(receipt("retired-original")));
    expect(onSubmitted).toHaveBeenCalledTimes(1);
    expect(onSubmitted).toHaveBeenCalledWith("inv-started");
  });
  it("retired pending house cannot navigate or clear a separately issued turn even before another preparation", async () => {
    const pending = deferredResponse();
    const onSubmitted = vi.fn();
    startRead = () => pending.promise;
    renderComposer({ onSubmitted });
    await chooseDeepSeek();
    await userEvent.click(
      screen.getByRole("button", { name: "Model for this research" }),
    );
    await userEvent.click(await screen.findByText("Default (house route)"));
    await ask("same house question");
    await userEvent.click(
      screen.getByRole("button", { name: "Start a separate research" }),
    );
    await act(async () => pending.resolve(receipt("retired-house")));
    expect(onSubmitted).not.toHaveBeenCalled();
    expect(
      (
        screen.getByPlaceholderText(
          "What do you want to research?",
        ) as HTMLTextAreaElement
      ).value,
    ).toBe("same house question");
    await acknowledgePriorLaunches();
    startRead = null;
    await userEvent.click(screen.getByRole("button", { name: "Ask" }));
    await waitFor(() => expect(startBodies).toHaveLength(2));
    expect(onSubmitted).toHaveBeenCalledTimes(1);
  });
  it("keeps account A results private while account B explicitly starts another research", async () => {
    const a = deferredResponse();
    const b = deferredResponse();
    const onSubmitted = vi.fn();
    startRead = () => a.promise;
    renderComposer({ onSubmitted });
    await chooseDeepSeek();
    await ask("account A private question");
    identity = { ...identity, user_id: "account-b" };
    await act(async () => auth.refresh());
    await screen.findByRole("button", { name: "Start a separate research" });
    expect(
      (
        screen.getByPlaceholderText(
          "What do you want to research?",
        ) as HTMLTextAreaElement
      ).value,
    ).toBe("");
    expect(document.body.textContent).not.toContain(
      "account A private question",
    );
    await chooseDeepSeek();
    startRead = () => b.promise;
    await userEvent.type(
      screen.getByPlaceholderText("What do you want to research?"),
      "account B question",
    );
    await userEvent.click(screen.getByRole("button", { name: "Ask" }));
    await waitFor(() => expect(startBodies).toHaveLength(2));
    await act(async () => a.resolve(receipt("private-a-accepted")));
    expect(onSubmitted).not.toHaveBeenCalled();
    expect(
      screen.getByRole("button", { name: "…" }).hasAttribute("disabled"),
    ).toBe(true);
    await act(async () => b.resolve(receipt("b-accepted")));
    expect(onSubmitted).toHaveBeenCalledWith("b-accepted");
    expect(onSubmitted).toHaveBeenCalledTimes(1);
  });
  it("does not turn a failed request into a blind retry or erase the private hold", async () => {
    const failure = deferredResponse();
    startRead = () => failure.promise;
    renderComposer();
    await chooseDeepSeek();
    await ask("an uncertain question");
    await act(async () => failure.reject(new Error("fixture network failure")));
    await screen.findByText(/Could not confirm the start/);
    expect(
      screen.getByRole("button", { name: "Ask" }).hasAttribute("disabled"),
    ).toBe(true);
    fireEvent.click(screen.getByRole("button", { name: "Ask" }));
    expect(startBodies).toHaveLength(1);
    await userEvent.click(
      screen.getByRole("button", { name: "Start a separate research" }),
    );
    startRead = null;
    await userEvent.click(screen.getByRole("button", { name: "Ask" }));
    await waitFor(() => expect(startBodies).toHaveLength(2));
    expect(startBodies[1].operation_id).not.toBe(startBodies[0].operation_id);
  });
});

describe("child immediate lifecycle admission", () => {
  it("refuses child dispatch while verification is pending without requiring root inventory", async () => {
    renderComposer({ parentInvestigationId: "parent-existing" });
    await waitFor(() =>
      expect(auth.modelExecution.readCurrent().kind).toBe("ready"),
    );
    await acknowledgePriorLaunches();
    fireEvent.change(
      screen.getByPlaceholderText("What do you want to research?"),
      { target: { value: "child pending verification question" } },
    );
    const pending = deferredResponse();
    authRead = () => pending.promise;
    let refresh!: Promise<void>;
    act(() => {
      refresh = auth.refresh();
    });
    expect(auth.modelExecution.readCurrent().kind).not.toBe("ready");
    expect(
      (
        screen.getByPlaceholderText(
          "What do you want to research?",
        ) as HTMLTextAreaElement
      ).disabled,
    ).toBe(true);
    fireEvent.click(screen.getByRole("button", { name: "Ask" }));
    expect(startBodies).toHaveLength(0);
    await act(async () => {
      pending.resolve(jsonResponse(identity));
      await refresh;
    });
    fireEvent.change(
      screen.getByPlaceholderText("What do you want to research?"),
      { target: { value: "child pending verification question" } },
    );
    fireEvent.click(screen.getByRole("button", { name: "Ask" }));
    await waitFor(() => expect(startBodies).toHaveLength(1));
    expect(startBodies[0]).toEqual({
      question: "child pending verification question",
      parent_investigation_id: "parent-existing",
    });
  });
});

let probedComposer: ReturnType<typeof useResearchComposer>;
let probedController: OwnerModelController;
const probeSubmitted = () => {};
function ComposerLifecycleProbe() {
  probedController = useOwnerModelController({
    operationPrefix: "probe",
    policy: "strict-owner",
    allowHouse: true,
  });
  probedComposer = useResearchComposer({
    controller: probedController,
    onSubmitted: probeSubmitted,
  });
  return (
    <output data-testid="probed-question">{probedComposer.question}</output>
  );
}
describe("retained composer mutators", () => {
  it.each(["changeQuestion", "startSeparate"] as const)(
    "rejects old A %s during B pending and an A-B-A new epoch",
    async (mutator) => {
      render(
        <AuthProvider>
          <AuthProbe />
          <MemoryRouter>
            <ComposerLifecycleProbe />
          </MemoryRouter>
        </AuthProvider>,
      );
      await waitFor(() =>
        expect(probedController.inventory.kind).toBe("ready"),
      );
      const oldA = probedComposer;
      identity = { ...identity, user_id: "account-b" };
      await act(async () => auth.refresh());
      await waitFor(() =>
        expect(probedController.inventory.kind).toBe("ready"),
      );
      const pendingB = deferredResponse();
      startRead = () => pendingB.promise;
      act(() => {
        probedComposer.startSeparate();
        probedController.select({
          kind: "saved",
          recordId: "um-deepseek-pro",
          modelId: "deepseek-v4-pro",
        });
        probedComposer.changeQuestion("B pending private question");
      });
      await act(async () => {
        void probedComposer.submit();
      });
      expect(startBodies).toHaveLength(1);
      const bOperation = startBodies[0].operation_id;
      act(() => {
        if (mutator === "changeQuestion")
          oldA.changeQuestion("old A injected question");
        else oldA.startSeparate();
      });
      expect(probedComposer.question).toBe("B pending private question");
      expect(probedComposer.busy).toBe(true);
      expect(probedComposer.submitDisabled).toBe(true);
      await act(async () => {
        void probedComposer.submit();
      });
      expect(startBodies).toHaveLength(1);
      expect(startBodies[0].operation_id).toBe(bOperation);
      identity = { ...identity, user_id: "fixture-owner" };
      await act(async () => auth.refresh());
      await waitFor(() =>
        expect(probedController.inventory.kind).toBe("ready"),
      );
      const pendingA = deferredResponse();
      startRead = () => pendingA.promise;
      act(() => {
        probedComposer.startSeparate();
        probedController.select({
          kind: "saved",
          recordId: "um-deepseek-pro",
          modelId: "deepseek-v4-pro",
        });
        probedComposer.changeQuestion("A new epoch private question");
      });
      await act(async () => {
        void probedComposer.submit();
      });
      expect(startBodies).toHaveLength(2);
      act(() => {
        if (mutator === "changeQuestion")
          oldA.changeQuestion("old A injected question");
        else oldA.startSeparate();
      });
      expect(probedComposer.question).toBe("A new epoch private question");
      expect(probedComposer.busy).toBe(true);
      expect(probedComposer.submitDisabled).toBe(true);
      await act(async () => {
        void probedComposer.submit();
      });
      expect(startBodies).toHaveLength(2);
      await act(async () => {
        pendingB.resolve(receipt("retired-b"));
        pendingA.resolve(receipt("current-a"));
      });
    },
  );
});

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
it("rejects a retained child A submit under B while preserving the admitted child DTO", async () => {
  render(
    <AuthProvider>
      <AuthProbe />
      <MemoryRouter>
        <ChildComposerLifecycleProbe />
      </MemoryRouter>
    </AuthProvider>,
  );
  await waitFor(() =>
    expect(auth.modelExecution.readCurrent().kind).toBe("ready"),
  );
  act(() => probedComposer.startSeparate());
  act(() => probedComposer.changeQuestion("unchanged child question"));
  const oldA = probedComposer;
  identity = { ...identity, user_id: "child-account-b" };
  await act(async () => auth.refresh());
  await waitFor(() =>
    expect(auth.modelExecution.readCurrent().kind).toBe("ready"),
  );
  expect(probedComposer.question).toBe("");
  await act(async () => {
    void oldA.submit();
  });
  expect(startBodies).toHaveLength(0);
  act(() => probedComposer.startSeparate());
  act(() => probedComposer.changeQuestion("B deliberate child question"));
  await act(async () => {
    void probedComposer.submit();
  });
  expect(startBodies).toEqual([
    {
      question: "B deliberate child question",
      parent_investigation_id: "child-existing-parent",
    },
  ]);
});

it("admits child editing when mounted into an already-ready real provider", async () => {
  const view = render(
    <AuthProvider>
      <AuthProbe />
      <MemoryRouter />
    </AuthProvider>,
  );
  await waitFor(() =>
    expect(auth.modelExecution.readCurrent().kind).toBe("ready"),
  );
  view.rerender(
    <AuthProvider>
      <AuthProbe />
      <MemoryRouter>
        <ChatInputArea
          parentInvestigationId="ready-parent"
          spawnContext="initial passage"
          onSubmitted={probeSubmitted}
        />
      </MemoryRouter>
    </AuthProvider>,
  );
  const field = screen.getByPlaceholderText(
    "What do you want to research?",
  ) as HTMLTextAreaElement;
  expect(field.disabled).toBe(false);
  expect(field.value).toBe("initial passage");
  await acknowledgePriorLaunches();
  fireEvent.change(field, {
    target: { value: "ready child deliberately typed question" },
  });
  fireEvent.click(screen.getByRole("button", { name: "Ask" }));
  await waitFor(() => expect(startBodies).toHaveLength(1));
  expect(startBodies[0]).toEqual({
    question: "ready child deliberately typed question",
    parent_investigation_id: "ready-parent",
    spawn_context: "initial passage",
  });
});

describe("ChatInputArea story fixture fetch lifetime", () => {
  function StoryAuthProbe({ name }: { name: string }) {
    const { state } = useAuth();
    return (
      <output data-testid={name}>
        {state.status === "authenticated" ? state.identity.user_id : state.status}
      </output>
    );
  }

  function renderStoryFixture(name: string) {
    return render(
      <ChatStoryFixture>
        <StoryAuthProbe name={name} />
      </ChatStoryFixture>,
    );
  }

  async function expectStoryIdentity(name: string) {
    await waitFor(() =>
      expect(screen.getByTestId(name).textContent).toBe("story-fixture"),
    );
  }

  it.each([
    { order: "non-LIFO", removeFirstMounted: true },
    { order: "LIFO", removeFirstMounted: false },
  ])(
    "restores the original after two owners unmount in $order order",
    async ({ removeFirstMounted }) => {
      const original = globalThis.fetch;
      const first = renderStoryFixture("first-story-owner");
      const firstInstalled = globalThis.fetch;
      const second = renderStoryFixture("second-story-owner");
      const installed = globalThis.fetch;
      await expectStoryIdentity("first-story-owner");
      await expectStoryIdentity("second-story-owner");
      expect(original).not.toHaveBeenCalled();

      const retired = removeFirstMounted ? first : second;
      const survivor = removeFirstMounted ? second : first;
      const survivorName = removeFirstMounted
        ? "second-story-owner"
        : "first-story-owner";
      retired.unmount();
      expect(globalThis.fetch).toBe(installed);
      await expectStoryIdentity(survivorName);
      expect(await (await globalThis.fetch("/auth/me")).json()).toMatchObject({
        user_id: "story-fixture",
      });

      survivor.unmount();
      expect(globalThis.fetch).toBe(original);
      expect(await (await globalThis.fetch("/auth/me")).json()).toMatchObject({
        user_id: "fixture-owner",
      });
      expect(installed).toBe(firstInstalled);
    },
  );

  it("restores a single owner's original fetch", async () => {
    const original = globalThis.fetch;
    const view = renderStoryFixture("single-story-owner");
    expect(globalThis.fetch).not.toBe(original);
    await expectStoryIdentity("single-story-owner");

    view.unmount();
    expect(globalThis.fetch).toBe(original);
  });

  it("keeps a survivor's fixture through StrictMode replay and repeated unmount", async () => {
    const original = globalThis.fetch;
    const survivor = renderStoryFixture("surviving-story-owner");
    const installed = globalThis.fetch;
    const replayed = render(
      <StrictMode>
        <ChatStoryFixture>
          <StoryAuthProbe name="strict-story-owner" />
        </ChatStoryFixture>
      </StrictMode>,
    );
    await expectStoryIdentity("surviving-story-owner");
    await expectStoryIdentity("strict-story-owner");
    expect(globalThis.fetch).toBe(installed);

    replayed.unmount();
    replayed.unmount();
    expect(globalThis.fetch).toBe(installed);
    survivor.unmount();
    expect(globalThis.fetch).toBe(original);
  });

  it("preserves an external replacement and captures it for a fresh generation", async () => {
    const first = renderStoryFixture("replaced-first-owner");
    const second = renderStoryFixture("replaced-second-owner");
    await expectStoryIdentity("replaced-first-owner");
    await expectStoryIdentity("replaced-second-owner");
    const replacement = vi.fn(async () =>
      jsonResponse({ ...identity, user_id: "external-owner" }),
    );
    vi.stubGlobal("fetch", replacement);
    const installedReplacement = globalThis.fetch;

    first.unmount();
    expect(globalThis.fetch).toBe(installedReplacement);
    second.unmount();
    expect(globalThis.fetch).toBe(installedReplacement);

    const next = renderStoryFixture("fresh-story-owner");
    await expectStoryIdentity("fresh-story-owner");
    expect(globalThis.fetch).not.toBe(installedReplacement);
    expect(replacement).not.toHaveBeenCalled();
    next.unmount();
    expect(globalThis.fetch).toBe(installedReplacement);
    expect(await (await globalThis.fetch("/auth/me")).json()).toMatchObject({
      user_id: "external-owner",
    });
  });
});
