import { createElement } from "react";
import { act, cleanup, render, waitFor } from "@testing-library/react";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
vi.mock("../../lib/posthogClient", () => ({
  posthogEnabled: false,
  posthog: { identify: vi.fn(), reset: vi.fn() },
}));
vi.mock("../../hooks/useReadingState", () => ({
  setReadingStateOwner: vi.fn(),
}));
vi.mock("../Write/sectionProseOwner", () => ({
  setSectionProseOwner: vi.fn(),
  suspendSectionProseDispatch: vi.fn(),
}));
import { AuthProvider, useAuth } from "../../lib/auth";
import {
  useOwnerModelController,
  type OwnerModelController,
} from "../../hooks/useOwnerModelController";
import { createRootResearchLaunchArchive } from "./rootResearchLaunch";
let controller: OwnerModelController;
let modelExecution: ReturnType<typeof useAuth>["modelExecution"];
function ScopeProbe() {
  modelExecution = useAuth().modelExecution;
  return null;
}
function Probe() {
  controller = useOwnerModelController({
    operationPrefix: "fixture",
    policy: "strict-owner",
    allowHouse: true,
  });
  return null;
}
beforeEach(() =>
  vi.stubGlobal(
    "fetch",
    vi.fn(async (input: RequestInfo | URL) => {
      const path = new URL(String(input), "http://fixture").pathname;
      if (path === "/auth/me")
        return new Response(
          JSON.stringify({
            user_id: "fixture",
            email: null,
            auth_method: "antiek_session_cookie",
          }),
        );
      if (path === "/settings/models/user")
        return new Response(
          JSON.stringify({
            models: [],
            count: 0,
            stale_registered: [],
            source: "fixture",
          }),
        );
      throw new Error("fixture route denied");
    }),
  ),
);
afterEach(() => {
  cleanup();
  vi.unstubAllGlobals();
});
async function prepared() {
  render(createElement(AuthProvider, { children: createElement(Probe) }));
  await waitFor(() => expect(controller.inventory.kind).toBe("ready"));
  act(() => controller.select({ kind: "house" }));
  const value = controller.prepareLaunch({
    semanticKey: "fixture-complete-turn",
  });
  if (value.kind === "blocked") throw new Error("blocked");
  return value;
}
async function readyChildScope() {
  render(createElement(AuthProvider, { children: createElement(ScopeProbe) }));
  await waitFor(() => expect(modelExecution.readCurrent().kind).toBe("ready"));
  const scope = modelExecution.readCurrent();
  if (scope.kind !== "ready") throw new Error("missing ready child scope");
  return scope;
}
const receipt = {
  investigation_id: "inv-fixture",
  status: "in_progress",
  start_event_id: "fixture-start",
};
describe("memory-only issued root research continuity", () => {
  it("never implicitly retries unknown or reuses an issued nonce after acceptance", async () => {
    const launch = await prepared();
    const archive = createRootResearchLaunchArchive();
    const intent = archive.createIntent();
    const handle = archive.begin(
      intent,
      { question: "complete fixture question" },
      launch,
    );
    expect(handle).not.toBeNull();
    if (!handle) throw new Error("missing");
    archive.uncertain(handle);
    expect(archive.hasUnresolved()).toBe(true);
    expect(archive.canBegin(intent)).toBe(false);
    expect(archive.canBegin(archive.createIntent())).toBe(false);
    expect(archive.accepted(handle, receipt)).toBe(true);
    expect(archive.hasUnresolved()).toBe(false);
    cleanup();
    expect(archive.accepted(handle, receipt)).toBe(true);
    expect(
      archive.accepted(handle, { ...receipt, investigation_id: "other" }),
    ).toBe(false);
    expect(archive.canBegin(intent)).toBe(false);
    expect(archive.canBegin(archive.createIntent())).toBe(true);
  });
  it("requires an explicit separate intent matching the entire current hold set", async () => {
    const launch = await prepared();
    const archive = createRootResearchLaunchArchive();
    const first = archive.begin(
      archive.createIntent(),
      { question: "first" },
      launch,
    );
    if (!first) throw new Error("missing");
    const stale = archive.createIntent(true);
    const second = archive.begin(
      archive.createIntent(true),
      { question: "second" },
      launch,
    );
    if (!second) throw new Error("missing");
    expect(archive.canBegin(stale)).toBe(false);
    expect(archive.canBegin(archive.createIntent(true))).toBe(true);
    expect(archive.hasUnresolved()).toBe(true);
  });
  it("does not treat malformed start receipts as accepted or release uncertainty", async () => {
    const launch = await prepared();
    const archive = createRootResearchLaunchArchive();
    const handle = archive.begin(
      archive.createIntent(),
      { question: "fixture" },
      launch,
    );
    if (!handle) throw new Error("missing");
    expect(archive.accepted(handle, { investigation_id: "" })).toBe(false);
    archive.uncertain(handle);
    expect(archive.hasUnresolved()).toBe(true);
    expect(archive.canBegin(archive.createIntent())).toBe(false);
  });
});

describe("memory-only issued child research continuity", () => {
  it("records a pending child once and retains its unknown hold until a complete receipt", async () => {
    const scope = await readyChildScope();
    const archive = createRootResearchLaunchArchive();
    const intent = archive.createIntent();
    const handle = archive.beginChild(
      intent,
      { question: "child question", parent_investigation_id: "", spawn_context: "" },
      scope,
    );
    if (!handle) throw new Error("missing child handle");
    expect(archive.hasUnresolved()).toBe(true);
    expect(archive.beginChild(intent, { question: "blind repeat" }, scope)).toBeNull();
    expect(archive.canBegin(archive.createIntent())).toBe(false);
    archive.uncertain(handle);
    expect(archive.hasUnresolved()).toBe(true);
    cleanup();
    expect(archive.accepted(handle, receipt)).toBe(true);
    expect(archive.hasUnresolved()).toBe(false);
    expect(archive.accepted(handle, receipt)).toBe(true);
    expect(archive.accepted(handle, { ...receipt, start_event_id: "other" })).toBe(false);
    expect(archive.canBegin(intent)).toBe(false);
    expect(archive.canBegin(archive.createIntent())).toBe(true);
  });

  it.each([
    null,
    {},
    { investigation_id: "inv-only" },
    { ...receipt, investigation_id: " " },
    { ...receipt, status: "" },
    { ...receipt, status: " " },
    { ...receipt, start_event_id: "" },
    { ...receipt, start_event_id: " " },
    { ...receipt, start_event_id: 12 },
  ])("retains child uncertainty for malformed receipt %j", async (response) => {
    const scope = await readyChildScope();
    const archive = createRootResearchLaunchArchive();
    const handle = archive.beginChild(
      archive.createIntent(),
      { question: "child malformed receipt" },
      scope,
    );
    if (!handle) throw new Error("missing child handle");
    const version = archive.getVersion();
    expect(archive.accepted(handle, response)).toBe(false);
    expect(archive.getVersion()).toBe(version);
    archive.uncertain(handle);
    expect(archive.hasUnresolved()).toBe(true);
    expect(archive.canBegin(archive.createIntent())).toBe(false);
  });

  it("shares root and child holds and rejects a stale separate acknowledgment", async () => {
    const launch = await prepared();
    const archive = createRootResearchLaunchArchive();
    const root = archive.begin(archive.createIntent(), { question: "root" }, launch);
    if (!root) throw new Error("missing root handle");
    const stale = archive.createIntent(true);
    expect(archive.beginChild(archive.createIntent(), { question: "child" }, launch.scope)).toBeNull();
    const child = archive.beginChild(archive.createIntent(true), { question: "child" }, launch.scope);
    if (!child) throw new Error("missing child handle");
    expect(archive.canBegin(stale)).toBe(false);
    const bothHolds = archive.createIntent(true);
    expect(archive.accepted(root, receipt)).toBe(true);
    expect(archive.hasUnresolved()).toBe(true);
    expect(archive.canBegin(bothHolds)).toBe(false);
    expect(archive.begin(archive.createIntent(), { question: "blocked root" }, launch)).toBeNull();
    const separateRoot = archive.begin(archive.createIntent(true), { question: "separate root" }, launch);
    if (!separateRoot) throw new Error("missing separate root handle");
    expect(archive.accepted(child, { ...receipt, investigation_id: "inv-child" })).toBe(true);
    expect(archive.hasUnresolved()).toBe(true);
    expect(archive.accepted(separateRoot, { ...receipt, investigation_id: "inv-separate" })).toBe(true);
    expect(archive.hasUnresolved()).toBe(false);
  });

  it("publishes scalar changes for issue, uncertainty and late acceptance, but not duplicate receipts", async () => {
    const scope = await readyChildScope();
    const archive = createRootResearchLaunchArchive();
    const versions: number[] = [];
    const unsubscribe = archive.subscribe(() => versions.push(archive.getVersion()));
    const handle = archive.beginChild(archive.createIntent(), { question: "late child" }, scope);
    if (!handle) throw new Error("missing child handle");
    archive.uncertain(handle);
    archive.uncertain(handle);
    expect(versions).toEqual([1, 2]);
    cleanup();
    expect(archive.accepted(handle, receipt)).toBe(true);
    expect(versions).toEqual([1, 2, 3]);
    expect(archive.accepted(handle, receipt)).toBe(true);
    expect(archive.accepted(handle, { ...receipt, status: "conflicting" })).toBe(false);
    expect(versions).toEqual([1, 2, 3]);
    unsubscribe();
    archive.beginChild(archive.createIntent(), { question: "next child" }, scope);
    expect(versions).toEqual([1, 2, 3]);
    expect(archive.getVersion()).toBe(4);
  });
});
