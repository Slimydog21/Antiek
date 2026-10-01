import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import { render, screen, waitFor } from "@testing-library/react";
import { StrictMode } from "react";
import { useAuth } from "../../lib/auth";
import { ChatStoryFixture } from "./ChatInputArea.stories";

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
const { jsonResponse } = fixture;
beforeEach(fixture.setUp);
afterEach(fixture.tearDown);

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
      jsonResponse({ ...fixture.identity, user_id: "external-owner" }),
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
