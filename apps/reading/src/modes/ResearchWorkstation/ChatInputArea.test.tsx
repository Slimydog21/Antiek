import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import { act, fireEvent, render, screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { MemoryRouter } from "react-router-dom";
import { AuthProvider } from "../../lib/auth";
import ChatInputArea from "./ChatInputArea";

const archiveSlot = vi.hoisted(() => ({
  current: null as null | ReturnType<
    typeof import("./rootResearchLaunch").createRootResearchLaunchArchive
  >,
}));
vi.mock("./rootResearchLaunch", async (importOriginal) => {
  const actual = await importOriginal<typeof import("./rootResearchLaunch")>();
  return {
    ...actual,
    get rootResearchLaunchArchive() {
      if (archiveSlot.current === null)
        throw new Error("Chat archive fixture used outside a test");
      return archiveSlot.current;
    },
  };
});

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

import { createChatTestFixture } from "./ChatInputArea.testFixture";

const fixture = createChatTestFixture(archiveSlot);
const {
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
} = fixture;
beforeEach(fixture.setUp);
afterEach(fixture.tearDown);

describe("ChatInputArea — the model driver reaches the request", () => {
  it("sends the chosen model and an operation id in the POST body", async () => {
    renderComposer();
    await chooseDeepSeek();
    await ask("what changed in the margin structure?");

    const body = fixture.startBodies[0];
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
    expect(fixture.startBodies).toHaveLength(0);
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
    await waitFor(() => expect(fixture.startBodies).toHaveLength(1));
    expect(fixture.startBodies[0]).not.toHaveProperty("model_choice");
    expect(fixture.startBodies[0].parent_investigation_id).toBe("inv-parent");
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
    expect(fixture.startBodies[0].model_choice).toMatchObject({
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
      expect(fixture.startBodies[0]).not.toHaveProperty("model_choice");
      expect(fixture.startBodies[0]).not.toHaveProperty("operation_id");
      const field =
        "parentInvestigationId" in props
          ? "parent_investigation_id"
          : "spawn_context";
      expect(fixture.startBodies[0][field]).toBe("");
    },
  );
});

describe("root issued action lifecycle", () => {
  it("requires explicit house and gives a confirmed new identical turn a new operation intent", async () => {
    const onSubmitted = vi.fn();
    renderComposer({ onSubmitted });
    await chooseDeepSeek();
    await ask("identical confirmed question");
    const first = fixture.startBodies[0].operation_id;
    await acknowledgePriorLaunches();
    await userEvent.type(
      screen.getByPlaceholderText("What do you want to research?"),
      "identical confirmed question",
    );
    await userEvent.click(screen.getByRole("button", { name: "Ask" }));
    await waitFor(() => expect(fixture.startBodies).toHaveLength(2));
    expect(fixture.startBodies[1].operation_id).not.toBe(first);
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
    expect(fixture.startBodies[0]).not.toHaveProperty("model_choice");
    expect(fixture.startBodies[0]).not.toHaveProperty("operation_id");
  });
  it("blocks a synchronous double activation of the same logical request", async () => {
    const pending = deferredResponse();
    fixture.startRead = () => pending.promise;
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
    expect(fixture.startBodies).toHaveLength(1);
    await act(async () => pending.resolve(receipt("double-finished")));
  });
  it("retains uncertainty across unmount and starts separately only on an explicit new intent", async () => {
    const first = deferredResponse();
    const onSubmitted = vi.fn();
    fixture.startRead = () => first.promise;
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
    fixture.startRead = null;
    await userEvent.type(
      screen.getByPlaceholderText("What do you want to research?"),
      "a separate new question",
    );
    await userEvent.click(screen.getByRole("button", { name: "Ask" }));
    await waitFor(() => expect(fixture.startBodies).toHaveLength(2));
    expect(fixture.startBodies[1].operation_id).not.toBe(fixture.startBodies[0].operation_id);
    await act(async () => first.resolve(receipt("retired-original")));
    expect(onSubmitted).toHaveBeenCalledTimes(1);
    expect(onSubmitted).toHaveBeenCalledWith("inv-started");
  });
  it("retired pending house cannot navigate or clear a separately issued turn even before another preparation", async () => {
    const pending = deferredResponse();
    const onSubmitted = vi.fn();
    fixture.startRead = () => pending.promise;
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
    fixture.startRead = null;
    await userEvent.click(screen.getByRole("button", { name: "Ask" }));
    await waitFor(() => expect(fixture.startBodies).toHaveLength(2));
    expect(onSubmitted).toHaveBeenCalledTimes(1);
  });
  it("keeps account A results private while account B explicitly starts another research", async () => {
    const a = deferredResponse();
    const b = deferredResponse();
    const onSubmitted = vi.fn();
    fixture.startRead = () => a.promise;
    renderComposer({ onSubmitted });
    await chooseDeepSeek();
    await ask("account A private question");
    fixture.identity = { ...fixture.identity, user_id: "account-b" };
    await act(async () => fixture.auth.refresh());
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
    fixture.startRead = () => b.promise;
    await userEvent.type(
      screen.getByPlaceholderText("What do you want to research?"),
      "account B question",
    );
    await userEvent.click(screen.getByRole("button", { name: "Ask" }));
    await waitFor(() => expect(fixture.startBodies).toHaveLength(2));
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
    fixture.startRead = () => failure.promise;
    renderComposer();
    await chooseDeepSeek();
    await ask("an uncertain question");
    await act(async () => failure.reject(new Error("fixture network failure")));
    await screen.findByText(/Could not confirm the start/);
    expect(
      screen.getByRole("button", { name: "Ask" }).hasAttribute("disabled"),
    ).toBe(true);
    fireEvent.click(screen.getByRole("button", { name: "Ask" }));
    expect(fixture.startBodies).toHaveLength(1);
    await userEvent.click(
      screen.getByRole("button", { name: "Start a separate research" }),
    );
    fixture.startRead = null;
    await userEvent.click(screen.getByRole("button", { name: "Ask" }));
    await waitFor(() => expect(fixture.startBodies).toHaveLength(2));
    expect(fixture.startBodies[1].operation_id).not.toBe(fixture.startBodies[0].operation_id);
  });
});

describe("child immediate lifecycle admission", () => {
  it("refuses child dispatch while verification is pending without requiring root inventory", async () => {
    renderComposer({ parentInvestigationId: "parent-existing" });
    await waitFor(() =>
      expect(fixture.auth.modelExecution.readCurrent().kind).toBe("ready"),
    );
    await acknowledgePriorLaunches();
    fireEvent.change(
      screen.getByPlaceholderText("What do you want to research?"),
      { target: { value: "child pending verification question" } },
    );
    const pending = deferredResponse();
    fixture.authRead = () => pending.promise;
    let refresh!: Promise<void>;
    act(() => {
      refresh = fixture.auth.refresh();
    });
    expect(fixture.auth.modelExecution.readCurrent().kind).not.toBe("ready");
    expect(
      (
        screen.getByPlaceholderText(
          "What do you want to research?",
        ) as HTMLTextAreaElement
      ).disabled,
    ).toBe(true);
    fireEvent.click(screen.getByRole("button", { name: "Ask" }));
    expect(fixture.startBodies).toHaveLength(0);
    await act(async () => {
      pending.resolve(jsonResponse(fixture.identity));
      await refresh;
    });
    fireEvent.change(
      screen.getByPlaceholderText("What do you want to research?"),
      { target: { value: "child pending verification question" } },
    );
    fireEvent.click(screen.getByRole("button", { name: "Ask" }));
    await waitFor(() => expect(fixture.startBodies).toHaveLength(1));
    expect(fixture.startBodies[0]).toEqual({
      question: "child pending verification question",
      parent_investigation_id: "parent-existing",
    });
  });
});

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
        expect(fixture.probedController.inventory.kind).toBe("ready"),
      );
      const oldA = fixture.probedComposer;
      fixture.identity = { ...fixture.identity, user_id: "account-b" };
      await act(async () => fixture.auth.refresh());
      await waitFor(() =>
        expect(fixture.probedController.inventory.kind).toBe("ready"),
      );
      const pendingB = deferredResponse();
      fixture.startRead = () => pendingB.promise;
      act(() => {
        fixture.probedComposer.startSeparate();
        fixture.probedController.select({
          kind: "saved",
          recordId: "um-deepseek-pro",
          modelId: "deepseek-v4-pro",
        });
        fixture.probedComposer.changeQuestion("B pending private question");
      });
      await act(async () => {
        void fixture.probedComposer.submit();
      });
      expect(fixture.startBodies).toHaveLength(1);
      const bOperation = fixture.startBodies[0].operation_id;
      act(() => {
        if (mutator === "changeQuestion")
          oldA.changeQuestion("old A injected question");
        else oldA.startSeparate();
      });
      expect(fixture.probedComposer.question).toBe("B pending private question");
      expect(fixture.probedComposer.busy).toBe(true);
      expect(fixture.probedComposer.submitDisabled).toBe(true);
      await act(async () => {
        void fixture.probedComposer.submit();
      });
      expect(fixture.startBodies).toHaveLength(1);
      expect(fixture.startBodies[0].operation_id).toBe(bOperation);
      fixture.identity = { ...fixture.identity, user_id: "fixture-owner" };
      await act(async () => fixture.auth.refresh());
      await waitFor(() =>
        expect(fixture.probedController.inventory.kind).toBe("ready"),
      );
      const pendingA = deferredResponse();
      fixture.startRead = () => pendingA.promise;
      act(() => {
        fixture.probedComposer.startSeparate();
        fixture.probedController.select({
          kind: "saved",
          recordId: "um-deepseek-pro",
          modelId: "deepseek-v4-pro",
        });
        fixture.probedComposer.changeQuestion("A new epoch private question");
      });
      await act(async () => {
        void fixture.probedComposer.submit();
      });
      expect(fixture.startBodies).toHaveLength(2);
      act(() => {
        if (mutator === "changeQuestion")
          oldA.changeQuestion("old A injected question");
        else oldA.startSeparate();
      });
      expect(fixture.probedComposer.question).toBe("A new epoch private question");
      expect(fixture.probedComposer.busy).toBe(true);
      expect(fixture.probedComposer.submitDisabled).toBe(true);
      await act(async () => {
        void fixture.probedComposer.submit();
      });
      expect(fixture.startBodies).toHaveLength(2);
      await act(async () => {
        pendingB.resolve(receipt("retired-b"));
        pendingA.resolve(receipt("current-a"));
      });
    },
  );
});

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
    expect(fixture.auth.modelExecution.readCurrent().kind).toBe("ready"),
  );
  act(() => fixture.probedComposer.startSeparate());
  act(() => fixture.probedComposer.changeQuestion("unchanged child question"));
  const oldA = fixture.probedComposer;
  fixture.identity = { ...fixture.identity, user_id: "child-account-b" };
  await act(async () => fixture.auth.refresh());
  await waitFor(() =>
    expect(fixture.auth.modelExecution.readCurrent().kind).toBe("ready"),
  );
  expect(fixture.probedComposer.question).toBe("");
  await act(async () => {
    void oldA.submit();
  });
  expect(fixture.startBodies).toHaveLength(0);
  act(() => fixture.probedComposer.startSeparate());
  act(() => fixture.probedComposer.changeQuestion("B deliberate child question"));
  await act(async () => {
    void fixture.probedComposer.submit();
  });
  expect(fixture.startBodies).toEqual([
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
    expect(fixture.auth.modelExecution.readCurrent().kind).toBe("ready"),
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
  await waitFor(() => expect(fixture.startBodies).toHaveLength(1));
  expect(fixture.startBodies[0]).toEqual({
    question: "ready child deliberately typed question",
    parent_investigation_id: "ready-parent",
    spawn_context: "initial passage",
  });
});
