import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import { act, fireEvent, render, screen, waitFor, within } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { MemoryRouter } from "react-router-dom";
import { AuthProvider } from "../../lib/auth";
import type { ResearchComposerProps } from "./useResearchComposer";

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
  ChildComposerLifecycleProbe,
  renderComposer,
  chooseDeepSeek,
  ask,
  acknowledgePriorLaunches,
  deferredResponse,
  receipt,
  jsonResponse,
} = fixture;
beforeEach(fixture.setUp);
afterEach(fixture.tearDown);

describe("child issued action lifecycle", () => {
  const childProps = {
    parentInvestigationId: "child-lifecycle-parent",
    spawnContext: "",
  };

  async function readyChild(onSubmitted: (id: string) => void) {
    const view = renderComposer({ ...childProps, onSubmitted });
    await waitFor(() =>
      expect(fixture.auth.modelExecution.readCurrent().kind).toBe("ready"),
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
      expect(fixture.auth.modelExecution.readCurrent().kind).toBe("ready"),
    );
    act(() => fixture.probedComposer.startSeparate());
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
    await waitFor(() => expect(fixture.auth.modelExecution.readCurrent().kind).toBe("ready"));
    const childUI = within(child.container);
    const childField = childUI.getByPlaceholderText("What do you want to research?");
    fireEvent.change(childField, { target: { value: "mounted child draft" } });
    expect(childUI.getByRole("button", { name: "Ask" }).hasAttribute("disabled")).toBe(false);
    fixture.startRead = () => rootResponse.promise;
    await userEvent.click(rootUI.getByRole("button", { name: "Ask" }));
    await waitFor(() => expect(fixture.startBodies).toHaveLength(1));
    expect(childUI.getByRole("button", { name: "Ask" }).hasAttribute("disabled")).toBe(true);
    expect(childUI.getByRole("button", { name: "Start a separate research" })).toBeTruthy();
    expect(childField).toHaveProperty("value", "mounted child draft");
    await act(async () => rootResponse.resolve(receipt("mounted-root")));
    await waitFor(() => expect(childUI.getByRole("button", { name: "Ask" }).hasAttribute("disabled")).toBe(false));
    expect(childUI.queryByRole("button", { name: "Start a separate research" })).toBeNull();
    expect(childField).toHaveProperty("value", "mounted child draft");
    expect(fixture.startBodies).toHaveLength(1);
    expect(childSubmitted).not.toHaveBeenCalled();

    fixture.startRead = () => childResponse.promise;
    await userEvent.click(childUI.getByRole("button", { name: "Ask" }));
    fireEvent.change(rootField, { target: { value: "separate mounted root draft" } });
    expect(rootUI.getByRole("button", { name: "Ask" }).hasAttribute("disabled")).toBe(true);
    await userEvent.click(rootUI.getByRole("button", { name: "Start a separate research" }));
    fixture.startRead = () => separateRootResponse.promise;
    await userEvent.click(rootUI.getByRole("button", { name: "Ask" }));
    expect(fixture.startBodies).toHaveLength(3);
    await act(async () => childResponse.resolve(receipt("mounted-child")));
    expect(rootUI.getByRole("button", { name: "…" }).hasAttribute("disabled")).toBe(true);
    expect(rootUI.getByRole("button", { name: "Start a separate research" })).toBeTruthy();
    expect(rootField).toHaveProperty("value", "separate mounted root draft");
    expect(rootSubmitted).toHaveBeenCalledTimes(1);
    expect(childSubmitted).toHaveBeenCalledTimes(1);
    expect(fixture.startBodies).toHaveLength(3);
    await act(async () => separateRootResponse.resolve(receipt("mounted-separate-root")));
    expect(rootSubmitted).toHaveBeenCalledTimes(2);
    expect(fixture.startBodies).toHaveLength(3);
  });

  it.each(["child", "root"])("reprojects a remounted %s after an old late receipt without navigating or clearing its new draft", async (route) => {
    const pending = deferredResponse();
    const onSubmitted = vi.fn();
    fixture.startRead = () => pending.promise;
    const view = route === "child"
      ? await readyChild(onSubmitted)
      : renderComposer({ onSubmitted });
    if (route === "root") await chooseDeepSeek();
    await ask("old child private draft");
    view.unmount();
    renderComposer(route === "child" ? { ...childProps, onSubmitted } : { onSubmitted });
    await waitFor(() =>
      expect(fixture.auth.modelExecution.readCurrent().kind).toBe("ready"),
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
    fixture.startRead = null;
    await userEvent.click(screen.getByRole("button", { name: "Ask" }));
    await waitFor(() => expect(fixture.startBodies).toHaveLength(2));
    if (route === "child") {
      expect(fixture.startBodies[1]).toEqual({
        question: "remounted deliberate draft",
        parent_investigation_id: childProps.parentInvestigationId,
        spawn_context: "",
      });
    } else {
      expect(fixture.startBodies[1].question).toBe("remounted deliberate draft");
      expect(fixture.startBodies[1]).toHaveProperty("model_choice");
      expect(fixture.startBodies[1]).toHaveProperty("operation_id");
    }
    await waitFor(() => expect(onSubmitted).toHaveBeenCalledWith("inv-started"));
    expect(onSubmitted).toHaveBeenCalledTimes(1);
  });

  it("dispatches one child DTO for synchronous activation and admits a confirmed identical new turn", async () => {
    const pending = deferredResponse();
    const onSubmitted = vi.fn();
    fixture.startRead = () => pending.promise;
    await readyChild(onSubmitted);
    const field = screen.getByPlaceholderText("What do you want to research?");
    fireEvent.change(field, { target: { value: "identical child question" } });
    const button = screen.getByRole("button", { name: "Ask" });
    act(() => {
      fireEvent.click(button);
      fireEvent.click(button);
    });
    expect(fixture.startBodies).toEqual([{
      question: "identical child question",
      parent_investigation_id: childProps.parentInvestigationId,
      spawn_context: "",
    }]);
    await act(async () => pending.resolve(receipt("child-first-confirmed")));
    expect(onSubmitted).toHaveBeenCalledWith("child-first-confirmed");
    fixture.startRead = null;
    await ask("identical child question", 2);
    expect(fixture.startBodies[1]).toEqual(fixture.startBodies[0]);
    await waitFor(() => expect(onSubmitted).toHaveBeenCalledTimes(2));
  });

  it("retires a pending child action after explicit separation without clearing the next draft", async () => {
    const pending = deferredResponse();
    const onSubmitted = vi.fn();
    fixture.startRead = () => pending.promise;
    await readyChild(onSubmitted);
    await ask("retired pending child question");
    await userEvent.click(screen.getByRole("button", { name: "Start a separate research" }));
    const field = screen.getByPlaceholderText("What do you want to research?");
    fireEvent.change(field, { target: { value: "new separate child draft" } });
    await act(async () => pending.resolve(receipt("retired-child")));
    expect(onSubmitted).not.toHaveBeenCalled();
    expect(field).toHaveProperty("value", "new separate child draft");
    fixture.startRead = null;
    await userEvent.click(screen.getByRole("button", { name: "Ask" }));
    await waitFor(() => expect(fixture.startBodies).toHaveLength(2));
    expect(fixture.startBodies[1].question).toBe("new separate child draft");
    await waitFor(() => expect(onSubmitted).toHaveBeenCalledTimes(1));
  });

  it.each(["root", "child"])("projects a pending %s hold into the other route and requires explicit separation", async (firstRoute) => {
    const old = deferredResponse();
    const next = deferredResponse();
    const oldSubmitted = vi.fn();
    const nextSubmitted = vi.fn();
    fixture.startRead = () => old.promise;
    const first = firstRoute === "root"
      ? renderComposer({ onSubmitted: oldSubmitted })
      : renderComposer({ ...childProps, onSubmitted: oldSubmitted });
    await waitFor(() => expect(fixture.auth.modelExecution.readCurrent().kind).toBe("ready"));
    if (firstRoute === "root") await chooseDeepSeek();
    else await acknowledgePriorLaunches();
    await ask("first route private question");
    first.unmount();
    renderComposer(firstRoute === "root"
      ? { ...childProps, onSubmitted: nextSubmitted }
      : { onSubmitted: nextSubmitted });
    await waitFor(() => expect(fixture.auth.modelExecution.readCurrent().kind).toBe("ready"));
    await screen.findByRole("button", { name: "Start a separate research" });
    expect(document.body.textContent).not.toContain("first route private question");
    fireEvent.change(screen.getByPlaceholderText("What do you want to research?"), {
      target: { value: "other route deliberate question" },
    });
    expect(screen.getByRole("button", { name: "Ask" }).hasAttribute("disabled")).toBe(true);
    fireEvent.click(screen.getByRole("button", { name: "Ask" }));
    expect(fixture.startBodies).toHaveLength(1);
    if (firstRoute === "child") await chooseDeepSeek();
    else await acknowledgePriorLaunches();
    fixture.startRead = () => next.promise;
    await userEvent.click(screen.getByRole("button", { name: "Ask" }));
    await waitFor(() => expect(fixture.startBodies).toHaveLength(2));
    if (firstRoute === "root") {
      expect(fixture.startBodies[1]).toEqual({
        question: "other route deliberate question",
        parent_investigation_id: childProps.parentInvestigationId,
        spawn_context: "",
      });
    } else {
      expect(fixture.startBodies[1]).toHaveProperty("model_choice");
      expect(fixture.startBodies[1]).toHaveProperty("operation_id");
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
    expect(fixture.startBodies).toHaveLength(1);
    await acknowledgePriorLaunches();
    await ask("deliberate confirmed next turn", 2);
    await waitFor(() => expect(onSubmitted).toHaveBeenCalledTimes(2));
    if (route === "root") {
      expect(fixture.startBodies[1].operation_id).not.toBe(fixture.startBodies[0].operation_id);
    } else {
      expect(fixture.startBodies[1]).toEqual({
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
    fixture.startRead = () => pending.promise;
    const origin = await readyChild(onSubmitted);
    await ask("unmounted unconfirmed child");
    origin.unmount();
    renderComposer({ ...childProps, onSubmitted });
    await waitFor(() => expect(fixture.auth.modelExecution.readCurrent().kind).toBe("ready"));
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
    expect(fixture.startBodies).toHaveLength(1);
    await userEvent.click(screen.getByRole("button", { name: "Start a separate research" }));
    fixture.startRead = null;
    await userEvent.click(screen.getByRole("button", { name: "Ask" }));
    await waitFor(() => expect(fixture.startBodies).toHaveLength(2));
    await waitFor(() => expect(onSubmitted).toHaveBeenCalledTimes(1));
    expect(fixture.startBodies[1]).toEqual({
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
    fixture.startRead = () => pending.promise;
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
    expect(fixture.startBodies).toHaveLength(1);
    view.unmount();

    renderComposer({ ...childProps, onSubmitted });
    await waitFor(() => expect(fixture.auth.modelExecution.readCurrent().kind).toBe("ready"));
    await screen.findByRole("button", { name: "Start a separate research" });
    const field = screen.getByPlaceholderText("What do you want to research?");
    expect(field).toHaveProperty("value", "");
    fireEvent.change(field, { target: { value: "deliberate separate child" } });
    fireEvent.click(screen.getByRole("button", { name: "Ask" }));
    expect(fixture.startBodies).toHaveLength(1);
    await userEvent.click(screen.getByRole("button", { name: "Start a separate research" }));
    fixture.startRead = null;
    await userEvent.click(screen.getByRole("button", { name: "Ask" }));
    await waitFor(() => expect(fixture.startBodies).toHaveLength(2));
    expect(fixture.startBodies[1]).toEqual({
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
    fixture.startRead = () => pending.promise;
    const view = await readyProbe({ ...childProps, onSubmitted });
    act(() => fixture.probedComposer.changeQuestion("callable uncertain child"));
    const retained = fixture.probedComposer;
    await act(async () => { void fixture.probedComposer.submit(); });
    await act(async () => pending.reject(new Error("fixture callable child failure")));
    expect(fixture.probedComposer.showUncertainty).toBe(true);
    expect(fixture.probedComposer.submitDisabled).toBe(true);
    await act(async () => {
      void retained.submit();
      void fixture.probedComposer.submit();
    });
    expect(fixture.startBodies).toHaveLength(1);
    view.unmount();
    render(childProbeTree({ ...childProps, onSubmitted }));
    await waitFor(() => expect(fixture.auth.modelExecution.readCurrent().kind).toBe("ready"));
    act(() => fixture.probedComposer.changeQuestion("remounted callable child"));
    expect(fixture.probedComposer.showUncertainty).toBe(true);
    await act(async () => { void fixture.probedComposer.submit(); });
    expect(fixture.startBodies).toHaveLength(1);
    act(() => fixture.probedComposer.startSeparate());
    fixture.startRead = null;
    await act(async () => { await fixture.probedComposer.submit(); });
    expect(fixture.startBodies[1]).toEqual({
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
    fixture.startRead = () => pending.promise;
    const view = await readyProbe({
      parentInvestigationId: "old-parent",
      spawnContext: "old caller context",
      onSubmitted: oldSubmitted,
    });
    act(() => fixture.probedComposer.changeQuestion("old props child question"));
    const retired = fixture.probedComposer;
    await act(async () => { void fixture.probedComposer.submit(); });
    view.rerender(childProbeTree({
      parentInvestigationId: "new-parent",
      spawnContext: "new caller context",
      onSubmitted: nextSubmitted,
    }));
    expect(fixture.probedComposer.question).toBe("");
    act(() => fixture.probedComposer.changeQuestion("new props deliberate draft"));
    await act(async () => { await fixture.probedComposer.submit(); });
    expect(fixture.startBodies).toHaveLength(1);
    act(() => {
      fixture.probedComposer.startSeparate();
      fixture.probedComposer.changeQuestion("new props deliberate draft");
    });
    await act(async () => {
      retired.changeQuestion("retired props injected draft");
      retired.startSeparate();
      void retired.submit();
    });
    expect(fixture.startBodies).toHaveLength(1);
    expect(fixture.probedComposer.question).toBe("new props deliberate draft");
    await act(async () => pending.resolve(receipt("old-props-accepted")));
    expect(oldSubmitted).not.toHaveBeenCalled();
    expect(nextSubmitted).not.toHaveBeenCalled();
    expect(fixture.probedComposer.question).toBe("new props deliberate draft");
    act(() => fixture.probedComposer.startSeparate());
    fixture.startRead = null;
    await act(async () => { await fixture.probedComposer.submit(); });
    expect(fixture.startBodies[1]).toEqual({
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
    fixture.startRead = () => oldAResponse.promise;
    await readyProbe({ ...childProps, onSubmitted });
    act(() => fixture.probedComposer.changeQuestion("A private original child"));
    const oldA = fixture.probedComposer;
    await act(async () => { void fixture.probedComposer.submit(); });
    fixture.identity = { ...fixture.identity, user_id: "child-account-b" };
    await act(async () => fixture.auth.refresh());
    expect(fixture.probedComposer.question).toBe("");
    expect(fixture.probedComposer.showUncertainty).toBe(true);
    expect(document.body.textContent).not.toContain("A private original child");
    act(() => {
      fixture.probedComposer.startSeparate();
      fixture.probedComposer.changeQuestion("B private child");
    });
    fixture.startRead = () => bResponse.promise;
    await act(async () => { void fixture.probedComposer.submit(); });
    await act(async () => {
      oldA.changeQuestion("old A injected child");
      oldA.startSeparate();
      void oldA.submit();
    });
    expect(fixture.probedComposer.question).toBe("B private child");
    expect(fixture.probedComposer.busy).toBe(true);
    expect(fixture.startBodies).toHaveLength(2);
    fixture.identity = { ...fixture.identity, user_id: "fixture-owner" };
    await act(async () => fixture.auth.refresh());
    expect(fixture.probedComposer.question).toBe("");
    act(() => {
      fixture.probedComposer.startSeparate();
      fixture.probedComposer.changeQuestion("A new epoch child");
    });
    fixture.startRead = () => newAResponse.promise;
    await act(async () => { void fixture.probedComposer.submit(); });
    await act(async () => {
      oldA.changeQuestion("old A epoch injected child");
      oldA.startSeparate();
      void oldA.submit();
    });
    expect(fixture.probedComposer.question).toBe("A new epoch child");
    expect(fixture.probedComposer.busy).toBe(true);
    expect(fixture.probedComposer.submitDisabled).toBe(true);
    expect(fixture.startBodies).toHaveLength(3);
    await act(async () => {
      oldAResponse.resolve(receipt("old-a-child"));
      bResponse.resolve(receipt("old-b-child"));
    });
    expect(onSubmitted).not.toHaveBeenCalled();
    expect(fixture.probedComposer.question).toBe("A new epoch child");
    expect(fixture.probedComposer.busy).toBe(true);
    await act(async () => newAResponse.resolve(receipt("new-a-child")));
    expect(onSubmitted).toHaveBeenCalledWith("new-a-child");
    expect(onSubmitted).toHaveBeenCalledTimes(1);
    expect(fixture.startBodies).toEqual([
      { question: "A private original child", parent_investigation_id: childProps.parentInvestigationId, spawn_context: "" },
      { question: "B private child", parent_investigation_id: childProps.parentInvestigationId, spawn_context: "" },
      { question: "A new epoch child", parent_investigation_id: childProps.parentInvestigationId, spawn_context: "" },
    ]);
  });
});
