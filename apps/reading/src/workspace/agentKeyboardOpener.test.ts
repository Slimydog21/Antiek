import { waitFor } from "@testing-library/react";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import {
  awaitWorkspaceOwnerSession,
  resumeWorkspaceOwner,
  setWorkspaceOwner,
  suspendWorkspaceOwner,
  workspaceOwnerSession,
} from "../lib/accountWorkspaceOwner";
import { createActionHandlers } from "./shortcuts";
import { tabTreeHandle } from "./tabTreeHandle";
import { useTabTrees } from "./tabTreeStore";

const { open } = vi.hoisted(() => ({ open: vi.fn() }));
vi.mock("./agent/openAgentPane", () => ({
  openAgentPane: open,
  openAgentPaneFromKey: () => open({ scope: "project", projectId: useTabTrees.getState().projectId }),
}));

// Synthetic UNIT ownership and a controlled lazy opener; no account/server admission.
beforeEach(async () => {
  setWorkspaceOwner(null);
  setWorkspaceOwner("unit-keyboard-A");
  await awaitWorkspaceOwnerSession(workspaceOwnerSession());
  useTabTrees.getState().resetTabTrees();
  useTabTrees.getState().selectProject("unit-project-A");
  window.history.replaceState({}, "", "/read/unit-document");
  open.mockReset();
  open.mockReturnValue({ ok: true, viewId: "agent:pane:p:unit-project-A", agentId: "p:unit-project-A", reused: false });
});

afterEach(async () => {
  tabTreeHandle.store = useTabTrees;
  setWorkspaceOwner(null);
  await vi.dynamicImportSettled();
  useTabTrees.getState().resetTabTrees();
  window.history.replaceState({}, "", "/");
});

function pressAgentKey() {
  return createActionHandlers(vi.fn())["agent.openPane"]();
}

async function expectRetired() {
  await vi.dynamicImportSettled();
  expect(open).not.toHaveBeenCalled();
}

describe("agent keyboard originating context", () => {
  it("opens the captured current project after loading the companion chunk", async () => {
    expect(pressAgentKey()).toBe(true);
    await waitFor(() => expect(open).toHaveBeenCalledExactlyOnceWith({ scope: "project", projectId: "unit-project-A" }));
  });

  it("retires an A action when the account becomes B during lazy loading", async () => {
    pressAgentKey();
    setWorkspaceOwner("unit-keyboard-B");
    await expectRetired();
  });

  it("retires A-B-A account reuse rather than renewing the original admission", async () => {
    pressAgentKey();
    setWorkspaceOwner("unit-keyboard-B");
    setWorkspaceOwner("unit-keyboard-A");
    await expectRetired();
  });

  it("retires a project switch during lazy loading", async () => {
    pressAgentKey();
    useTabTrees.getState().selectProject("unit-project-B");
    await expectRetired();
  });

  it("retires project A-B-A reuse by the actual store context epoch", async () => {
    pressAgentKey();
    useTabTrees.getState().selectProject("unit-project-B");
    useTabTrees.getState().selectProject("unit-project-A");
    await expectRetired();
  });

  it("retires a reset even when the project ID remains the same", async () => {
    pressAgentKey();
    useTabTrees.getState().resetTabTrees();
    useTabTrees.getState().selectProject("unit-project-A");
    await expectRetired();
  });

  it("keeps benign same-context store publication eligible", async () => {
    pressAgentKey();
    useTabTrees.setState({ treePanelOpen: !useTabTrees.getState().treePanelOpen });
    await waitFor(() => expect(open).toHaveBeenCalledExactlyOnceWith({ scope: "project", projectId: "unit-project-A" }));
  });

  it("holds through same-token suspension and opens once after confirmation", async () => {
    pressAgentKey();
    const owner = workspaceOwnerSession();
    suspendWorkspaceOwner();
    await expectRetired();
    expect(resumeWorkspaceOwner(owner)).toBe(true);
    await waitFor(() => expect(open).toHaveBeenCalledExactlyOnceWith({ scope: "project", projectId: "unit-project-A" }));
  });

  it("retires replacement while the originating owner is suspended", async () => {
    pressAgentKey();
    suspendWorkspaceOwner();
    setWorkspaceOwner("unit-keyboard-B");
    await expectRetired();
  });

  it("does not take the writing outline after the route changes during lazy loading", async () => {
    pressAgentKey();
    window.history.replaceState({}, "", "/write/unit-piece");
    await expectRetired();
  });

  it("does not open without a canonical owner", async () => {
    setWorkspaceOwner(null);
    pressAgentKey();
    await expectRetired();
  });

  it("does not adopt a later tree store when none existed at the keystroke", async () => {
    tabTreeHandle.store = null;
    pressAgentKey();
    tabTreeHandle.store = useTabTrees;
    await expectRetired();
  });
});
