import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import {
  act,
  cleanup,
  fireEvent,
  render,
  screen,
  waitFor,
} from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { MemoryRouter } from "react-router-dom";

import { AuthProvider, useAuth, type AuthContextValue } from "../../lib/auth";
import ChatInputArea from "./ChatInputArea";
import { useResearchComposer } from "./useResearchComposer";
import {
  useOwnerModelController,
  type OwnerModelController,
} from "../../hooks/useOwnerModelController";

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

describe("root issued action lifecycle", () => {
  it("requires explicit house and gives a confirmed new identical turn a new operation intent", async () => {
    const onSubmitted = vi.fn();
    renderComposer({ onSubmitted });
    await chooseDeepSeek();
    await ask("identical confirmed question");
    const first = startBodies[0].operation_id;
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

function ChildComposerLifecycleProbe() {
  probedComposer = useResearchComposer({
    parentInvestigationId: "child-existing-parent",
    onSubmitted: probeSubmitted,
  });
  return null;
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
