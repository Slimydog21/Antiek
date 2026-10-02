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
  renderComposer,
  chooseDeepSeek,
  ask,
  acknowledgePriorLaunches,
  deferredResponse,
  receipt,
  executableModel,
} = fixture;
beforeEach(fixture.setUp);
afterEach(fixture.tearDown);

describe("callback-only composer rerender", () => {
  const childProps = {
    parentInvestigationId: "callback-stable-parent",
    spawnContext: "",
  };

  function composerTree(route: string, onSubmitted: (id: string) => void) {
    return (
      <AuthProvider>
        <AuthProbe />
        <MemoryRouter>
          <ChatInputArea {...(route === "child" ? childProps : {})} onSubmitted={onSubmitted} />
        </MemoryRouter>
      </AuthProvider>
    );
  }

  async function readyComposer(route: string, onSubmitted: (id: string) => void) {
    const view = render(composerTree(route, onSubmitted));
    await waitFor(() => expect(fixture.auth.modelExecution.readCurrent().kind).toBe("ready"));
    if (route === "root") await chooseDeepSeek();
    else await acknowledgePriorLaunches();
    return view;
  }

  function probeTree(route: string, onSubmitted: (id: string) => void) {
    return (
      <AuthProvider>
        <AuthProbe />
        <MemoryRouter>
          {route === "root"
            ? <ComposerLifecycleProbe onSubmitted={onSubmitted} />
            : <ChildComposerLifecycleProbe {...childProps} onSubmitted={onSubmitted} />}
        </MemoryRouter>
      </AuthProvider>
    );
  }

  async function readyProbe(route: string, onSubmitted: (id: string) => void) {
    const view = render(probeTree(route, onSubmitted));
    await waitFor(() => expect(fixture.auth.modelExecution.readCurrent().kind).toBe("ready"));
    if (route === "root") {
      await waitFor(() => expect(fixture.probedController.inventory.kind).toBe("ready"));
      act(() => fixture.probedController.select({ kind: "saved", recordId: executableModel.id, modelId: "deepseek-v4-pro" }));
    }
    act(() => fixture.probedComposer.startSeparate());
    return view;
  }

  function expectExactWire(route: string, body: Record<string, unknown>, question: string) {
    expect(body).toEqual(route === "child"
      ? { question, parent_investigation_id: childProps.parentInvestigationId, spawn_context: "" }
      : {
          question,
          model_choice: { authority: "user_model", provider_id: executableModel.id, model_id: "deepseek-v4-pro" },
          operation_id: expect.any(String),
        });
  }

  it.each(["root", "child"])("preserves an unsent %s draft and sends it through only the current callback", async (route) => {
    const oldSubmitted = vi.fn();
    const currentSubmitted = vi.fn();
    const view = await readyComposer(route, oldSubmitted);
    const scope = fixture.auth.modelExecution.readCurrent();
    const field = screen.getByPlaceholderText("What do you want to research?");
    await userEvent.type(field, "unsent callback stable question");
    view.rerender(composerTree(route, currentSubmitted));
    expect(fixture.auth.modelExecution.readCurrent()).toBe(scope);
    expect(field).toHaveProperty("value", "unsent callback stable question");
    expect(fixture.startBodies).toHaveLength(0);
    await userEvent.click(screen.getByRole("button", { name: "Ask" }));
    await waitFor(() => expect(currentSubmitted).toHaveBeenCalledWith("inv-started"));
    expect(currentSubmitted).toHaveBeenCalledTimes(1);
    expect(oldSubmitted).not.toHaveBeenCalled();
    expect(fixture.startBodies).toHaveLength(1);
    expectExactWire(route, fixture.startBodies[0], "unsent callback stable question");
    expect(field).toHaveProperty("value", "");
  });

  it.each(["root", "child"])("keeps a pending %s draft private from both retired and replacement delivery callbacks", async (route) => {
    const pending = deferredResponse();
    const oldSubmitted = vi.fn();
    const currentSubmitted = vi.fn();
    fixture.startRead = () => pending.promise;
    const view = await readyComposer(route, oldSubmitted);
    await ask("pending callback stable question");
    const scope = fixture.auth.modelExecution.readCurrent();
    const field = screen.getByPlaceholderText("What do you want to research?");
    view.rerender(composerTree(route, currentSubmitted));
    expect(fixture.auth.modelExecution.readCurrent()).toBe(scope);
    expect(field).toHaveProperty("value", "pending callback stable question");
    expect(screen.getByRole("button", { name: /^(Ask|…)$/ }).hasAttribute("disabled")).toBe(true);
    await act(async () => pending.resolve(receipt("retired-callback-receipt")));
    expect(oldSubmitted).not.toHaveBeenCalled();
    expect(currentSubmitted).not.toHaveBeenCalled();
    expect(field).toHaveProperty("value", "pending callback stable question");
    expect(screen.getByRole("button", { name: "Ask" }).hasAttribute("disabled")).toBe(true);
    expect(fixture.startBodies).toHaveLength(1);
    await userEvent.click(screen.getByRole("button", { name: "Start a separate research" }));
    fireEvent.change(field, { target: { value: "separate current callback question" } });
    fixture.startRead = null;
    await userEvent.click(screen.getByRole("button", { name: "Ask" }));
    await waitFor(() => expect(currentSubmitted).toHaveBeenCalledWith("inv-started"));
    expect(currentSubmitted).toHaveBeenCalledTimes(1);
    expect(oldSubmitted).not.toHaveBeenCalled();
    expect(fixture.startBodies).toHaveLength(2);
    expectExactWire(route, fixture.startBodies[1], "separate current callback question");
    if (route === "root") expect(fixture.startBodies[1].operation_id).not.toBe(fixture.startBodies[0].operation_id);
  });

  it.each(["root", "child"])("denies retained %s mutators after callback churn while a current separate action stays pending", async (route) => {
    const oldResponse = deferredResponse();
    const currentResponse = deferredResponse();
    const oldSubmitted = vi.fn();
    const currentSubmitted = vi.fn();
    fixture.startRead = () => oldResponse.promise;
    const view = await readyProbe(route, oldSubmitted);
    act(() => fixture.probedComposer.changeQuestion("retained callback private question"));
    const retired = fixture.probedComposer;
    await act(async () => { void fixture.probedComposer.submit(); });
    const scope = fixture.auth.modelExecution.readCurrent();
    view.rerender(probeTree(route, currentSubmitted));
    expect(fixture.auth.modelExecution.readCurrent()).toBe(scope);
    expect(fixture.probedComposer.question).toBe("retained callback private question");
    await act(async () => {
      retired.changeQuestion("retired injected question");
      retired.startSeparate();
      void retired.submit();
      void fixture.probedComposer.submit();
    });
    expect(fixture.startBodies).toHaveLength(1);
    expect(fixture.probedComposer.question).toBe("retained callback private question");
    expect(fixture.probedComposer.submitDisabled).toBe(true);
    act(() => {
      fixture.probedComposer.startSeparate();
      fixture.probedComposer.changeQuestion("current callback pending question");
    });
    fixture.startRead = () => currentResponse.promise;
    await act(async () => { void fixture.probedComposer.submit(); });
    expect(fixture.startBodies).toHaveLength(2);
    expectExactWire(route, fixture.startBodies[1], "current callback pending question");
    await act(async () => {
      retired.changeQuestion("retired later injected question");
      retired.startSeparate();
      void retired.submit();
      oldResponse.resolve(receipt("old-callback-private"));
    });
    expect(fixture.probedComposer.question).toBe("current callback pending question");
    expect(fixture.probedComposer.busy).toBe(true);
    expect(fixture.probedComposer.submitDisabled).toBe(true);
    expect(fixture.startBodies).toHaveLength(2);
    expect(oldSubmitted).not.toHaveBeenCalled();
    expect(currentSubmitted).not.toHaveBeenCalled();
    await act(async () => currentResponse.resolve(receipt("current-callback-accepted")));
    expect(currentSubmitted).toHaveBeenCalledWith("current-callback-accepted");
    expect(currentSubmitted).toHaveBeenCalledTimes(1);
    expect(oldSubmitted).not.toHaveBeenCalled();
  });

  it.each(["root", "child"])("preserves %s validation error and draft across callback-only churn", async (route) => {
    const oldSubmitted = vi.fn();
    const currentSubmitted = vi.fn();
    const view = await readyProbe(route, oldSubmitted);
    act(() => fixture.probedComposer.changeQuestion("x"));
    await act(async () => { await fixture.probedComposer.submit(); });
    expect(fixture.probedComposer.error).toBe("Question is too short. At least 3 characters.");
    view.rerender(probeTree(route, currentSubmitted));
    expect(fixture.probedComposer.question).toBe("x");
    expect(fixture.probedComposer.error).toBe("Question is too short. At least 3 characters.");
    expect(fixture.startBodies).toHaveLength(0);
    expect(oldSubmitted).not.toHaveBeenCalled();
    expect(currentSubmitted).not.toHaveBeenCalled();
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
    await waitFor(() => expect(fixture.auth.modelExecution.readCurrent().kind).toBe("ready"));
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
    await waitFor(() => expect(fixture.startBodies).toHaveLength(1));
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
    expect(fixture.startBodies).toHaveLength(1);
    if (route === "child") {
      expect(fixture.startBodies[0]).toEqual({
        question: "confirmed telemetry boundary question",
        parent_investigation_id: "telemetry-child-parent",
        spawn_context: "",
      });
    } else {
      expect(fixture.startBodies[0]).toHaveProperty("model_choice");
      expect(fixture.startBodies[0]).toHaveProperty("operation_id");
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
    expect(fixture.startBodies).toHaveLength(1);
  });

  it.each(["root", "child"])("keeps a rejected %s start unknown when exception reporting throws", async (route) => {
    const pending = deferredResponse();
    const privateTransportError = new Error("private transport failure");
    const onSubmitted = vi.fn();
    fixture.startRead = () => pending.promise;
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
    expect(fixture.startBodies).toHaveLength(1);
  });
});
