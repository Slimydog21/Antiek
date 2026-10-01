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
import { AuthProvider } from "../../lib/auth";
import {
  useOwnerModelController,
  type OwnerModelController,
} from "../../hooks/useOwnerModelController";
import { createRootResearchLaunchArchive } from "./rootResearchLaunch";
let controller: OwnerModelController;
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
