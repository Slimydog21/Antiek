import { cleanup, render, screen, waitFor } from "@testing-library/react";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";

import ResearchArtifactHost from "./ResearchArtifactHost";
import { isWindowEligible, openWindow, WINDOW_PAGES } from "./openWindow";
import { useWindows } from "../../workspace/windowsStore";
import * as api from "../../lib/api";

describe("ResearchArtifactHost", () => {
  beforeEach(() => {
    vi.restoreAllMocks();
    vi.unstubAllEnvs();
    useWindows.getState().reset();
  });

  afterEach(cleanup);

  function sendFrom(source: MessageEventSource | null, overrides: Record<string, unknown> = {}, origin = "null") {
    window.dispatchEvent(new MessageEvent("message", {
      origin,
      source,
      data: {
        version: 1,
        type: "antiek.research-artifact.append-note",
        investigation_id: "inv-one",
        note: "persist me",
        expected_content_hash: "a".repeat(64),
        ...overrides,
      },
    }));
  }

  it("hosts the canonical API view with scripts and without same-origin authority", () => {
    render(<ResearchArtifactHost investigation_id="inv / one" content_hash={"a".repeat(64)} view_url="https://evil.invalid/x" />);

    const frame = screen.getByTestId("research-artifact-frame");
    expect(frame.getAttribute("src")).toBe(
      "/research/inv%20%2F%20one/artifact/view",
    );
    expect(frame.getAttribute("src")).not.toContain("evil.invalid");
    expect(frame.getAttribute("sandbox")).toBe("allow-scripts");
    expect(frame.getAttribute("sandbox")).not.toContain("allow-same-origin");
    expect(frame.getAttribute("title")).toContain("inv / one");
  });

  it("fails closed without an investigation identity", () => {
    render(<ResearchArtifactHost investigation_id="   " view_url="/caller/path" />);
    expect(screen.queryByTestId("research-artifact-frame")).toBeNull();
    expect(screen.getByRole("alert").textContent).toMatch(/missing investigation/i);
  });

  it("persists only an exact null-origin message from its iframe and reloads", async () => {
    const append = vi.spyOn(api, "appendResearchArtifactNote").mockResolvedValue({
      investigation_id: "inv-one",
      notes_persisted: 1,
      notes_skipped_duplicate: 0,
      current_content_hash: "b".repeat(64),
      event_pending: false,
    });
    render(<ResearchArtifactHost investigation_id="inv-one" content_hash={"a".repeat(64)} />);
    const frame = screen.getByTestId("research-artifact-frame") as HTMLIFrameElement;

    sendFrom(frame.contentWindow);

    await waitFor(() => expect(append).toHaveBeenCalledWith("inv-one", "persist me", "a".repeat(64)));
    expect(await screen.findByText("Note saved")).toBeTruthy();
  });

  it("surfaces a failed canonical save", async () => {
    vi.spyOn(api, "appendResearchArtifactNote").mockRejectedValue(
      new Error("storage unavailable"),
    );
    render(
      <ResearchArtifactHost
        investigation_id="inv-one"
        content_hash={"a".repeat(64)}
      />,
    );
    const frame = screen.getByTestId(
      "research-artifact-frame",
    ) as HTMLIFrameElement;

    sendFrom(frame.contentWindow);

    expect(await screen.findByText("Note not saved")).toBeTruthy();
  });

  it("rejects hostile windows, origins, identities, malformed hashes, versions, and bounds", () => {
    const append = vi.spyOn(api, "appendResearchArtifactNote").mockResolvedValue({
      investigation_id: "inv-one", notes_persisted: 1, notes_skipped_duplicate: 0,
      current_content_hash: "b".repeat(64),
      event_pending: false,
    });
    render(<ResearchArtifactHost investigation_id="inv-one" content_hash={"a".repeat(64)} />);
    const source = (screen.getByTestId("research-artifact-frame") as HTMLIFrameElement).contentWindow;

    sendFrom(window);
    sendFrom(source, {}, "https://evil.invalid");
    sendFrom(source, { investigation_id: "other" });
    sendFrom(source, { expected_content_hash: "bad" });
    sendFrom(source, { version: 2 });
    sendFrom(source, { type: "other" });
    sendFrom(source, { note: "x".repeat(20_001) });
    sendFrom(source, { note: "   " });

    expect(append).not.toHaveBeenCalled();
  });

  it("is window-native and deduplicates by the per-investigation id", () => {
    expect(isWindowEligible("research_artifact")).toBe(true);
    expect(WINDOW_PAGES.research_artifact?.renderer).toBeTruthy();

    const first = openWindow(
      "research_artifact",
      { investigation_id: "inv-one" },
      { id: "win:research_artifact:inv-one" },
    );
    const second = openWindow(
      "research_artifact",
      { investigation_id: "inv-one" },
      { id: "win:research_artifact:inv-one" },
    );

    expect(second).toBe(first);
    expect(useWindows.getState().order).toEqual([first]);
  });
});
