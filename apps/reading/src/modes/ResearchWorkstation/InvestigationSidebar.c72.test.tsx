import { cleanup, fireEvent, render, screen, waitFor } from "@testing-library/react";
import { MemoryRouter } from "react-router-dom";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";

import InvestigationSidebar from "./InvestigationSidebar";

const navigateMock = vi.fn();
const composeWithETagMock = vi.fn();
const launchMock = vi.fn();

vi.mock("react-router-dom", async (load) => {
  const actual = await load<typeof import("react-router-dom")>();
  return { ...actual, useNavigate: () => navigateMock };
});

vi.mock("../../lib/api", async (load) => {
  const actual = await load<typeof import("../../lib/api")>();
  return {
    ...actual,
    composeResearchArtifactsWithETag: (...args: unknown[]) => composeWithETagMock(...args),
    launchComposition: (...args: unknown[]) => launchMock(...args),
  };
});

vi.mock("../../hooks/useInvestigationList", () => ({
  useInvestigationList: () => ({
    loading: false, error: null, refetch: vi.fn(), investigations: [
      { investigation_id: "inv-a", question: "Alpha", status: "completed", artifact_composable: true, started_at: "2026-01-03", completed_at: "2026-01-03", cost_usd_total: 0, parent_investigation_id: null },
      { investigation_id: "inv-b", question: "Beta", status: "completed", artifact_composable: true, started_at: "2026-01-02", completed_at: "2026-01-02", cost_usd_total: 0, parent_investigation_id: null },
      { investigation_id: "inv-running", question: "Running", status: "in_progress", started_at: "2026-01-01", completed_at: null, cost_usd_total: 0, parent_investigation_id: null },
      { investigation_id: "inv-c", question: "Gamma", status: "completed", artifact_composable: false, started_at: "2026-01-04", completed_at: "2026-01-04", cost_usd_total: 0, parent_investigation_id: null },
    ],
  }),
}));

vi.mock("./TwinNotesPanel", () => ({ default: () => null }));

describe("Cycle 72 collective research composition launch", () => {
  beforeEach(() => {
    composeWithETagMock.mockReset();
    launchMock.mockReset();
    navigateMock.mockReset();
  });
  afterEach(() => cleanup());

  /** Helper: enter select mode, pick investigations, click "Research together". */
  async function enterComposeMode(ids: string[]) {
    render(<MemoryRouter><InvestigationSidebar /></MemoryRouter>);
    fireEvent.click(screen.getByText("Select"));
    for (const id of ids) {
      fireEvent.click(screen.getByLabelText(`Select ${id}`));
    }
    // The "Research together" button in the selection panel (not the confirm button).
    const composeButtons = screen.getAllByText("Research together");
    fireEvent.click(composeButtons[0]);
    const question = await screen.findByLabelText("Follow-up question");
    fireEvent.change(question, { target: { value: "What connects these findings?" } });
  }

  it("enters compose mode and shows ordered selected questions after composing", async () => {
    composeWithETagMock.mockResolvedValue({
      composition: { composition_id: "cmp-aaa", url: "/x", ordered_set_digest: "d", members: [], hash_conflicts: [] },
      etag: '"etag-1"',
    });
    await enterComposeMode(["inv-b", "inv-a"]);
    await waitFor(() => expect(composeWithETagMock).toHaveBeenCalledWith(["inv-b", "inv-a"]));
    // Shows ordered questions (not IDs).
    const items = screen.getAllByRole("listitem");
    const texts = items.map((el) => el.textContent);
    expect(texts).toContain("Beta");
    expect(texts).toContain("Alpha");
    // Follow-up textarea is visible.
    expect(screen.getByLabelText("Follow-up question")).toBeDefined();
    // Confirm button is visible.
    expect(screen.getByText("Research together")).toBeDefined();
  });

  it("synchronously suppresses duplicate compose activation", async () => {
    let resolveCompose!: (value: unknown) => void;
    composeWithETagMock.mockReturnValue(new Promise((resolve) => { resolveCompose = resolve; }));
    render(<MemoryRouter><InvestigationSidebar /></MemoryRouter>);
    fireEvent.click(screen.getByText("Select"));
    fireEvent.click(screen.getByLabelText("Select inv-a"));
    fireEvent.click(screen.getByLabelText("Select inv-b"));
    const button = screen.getAllByText("Research together")[0];
    fireEvent.click(button);
    fireEvent.click(button);
    expect(composeWithETagMock).toHaveBeenCalledTimes(1);
    resolveCompose({
      composition: { composition_id: "cmp-lock", url: "/x", ordered_set_digest: "d", members: [], hash_conflicts: [] },
      etag: '"etag-lock"',
    });
    await screen.findByLabelText("Follow-up question");
  });

  it("calls launchComposition once with If-Match and Idempotency-Key headers", async () => {
    composeWithETagMock.mockResolvedValue({
      composition: { composition_id: "cmp-bbb", url: "/x", ordered_set_digest: "d", members: [], hash_conflicts: [] },
      etag: '"etag-2"',
    });
    launchMock.mockResolvedValue({ investigation_id: "inv-new", status: "started", start_event_id: "evt-1" });
    vi.spyOn(crypto, "randomUUID").mockReturnValue("00000000-0000-4000-8000-000000000072");

    await enterComposeMode(["inv-a", "inv-b"]);
    await waitFor(() => expect(composeWithETagMock).toHaveBeenCalled());

    // Click the confirm button (second "Research together" in the DOM).
    const confirmButtons = screen.getAllByText("Research together");
    fireEvent.click(confirmButtons[confirmButtons.length - 1]);

    await waitFor(() => expect(launchMock).toHaveBeenCalledTimes(1));
    expect(launchMock).toHaveBeenCalledWith(
      "cmp-bbb",
      { question: "What connects these findings?" },
      '"etag-2"',
      "00000000-0000-4000-8000-000000000072",
    );
    // Navigates to the new investigation.
    expect(navigateMock).toHaveBeenCalledWith("/inv/inv-new");
  });

  it("navigates on successful launch", async () => {
    composeWithETagMock.mockResolvedValue({
      composition: { composition_id: "cmp-nav", url: "/x", ordered_set_digest: "d", members: [], hash_conflicts: [] },
      etag: '"etag-nav"',
    });
    launchMock.mockResolvedValue({ investigation_id: "inv-launched", status: "started", start_event_id: "evt-nav" });
    vi.spyOn(crypto, "randomUUID").mockReturnValue("00000000-0000-4000-8000-000000000073");

    await enterComposeMode(["inv-b", "inv-a"]);
    await waitFor(() => expect(composeWithETagMock).toHaveBeenCalled());
    const confirmButtons = screen.getAllByText("Research together");
    fireEvent.click(confirmButtons[confirmButtons.length - 1]);

    await waitFor(() => expect(navigateMock).toHaveBeenCalledWith("/inv/inv-launched"));
  });

  it("reuses the same idempotency key on retry after a failed launch", async () => {
    composeWithETagMock.mockResolvedValue({
      composition: { composition_id: "cmp-retry", url: "/x", ordered_set_digest: "d", members: [], hash_conflicts: [] },
      etag: '"etag-retry"',
    });
    launchMock
      .mockRejectedValueOnce(new Error("server error"))
      .mockResolvedValueOnce({ investigation_id: "inv-recovered", status: "started", start_event_id: "evt-2" });
    vi.spyOn(crypto, "randomUUID").mockReturnValue("00000000-0000-4000-8000-000000000074");

    await enterComposeMode(["inv-a", "inv-b"]);
    await waitFor(() => expect(composeWithETagMock).toHaveBeenCalled());

    // First attempt fails.
    const confirmButtons = screen.getAllByText("Research together");
    fireEvent.click(confirmButtons[confirmButtons.length - 1]);
    await screen.findByText("server error");

    // Retry — should reuse the same idempotency key.
    fireEvent.click(confirmButtons[confirmButtons.length - 1]);
    await waitFor(() => expect(launchMock).toHaveBeenCalledTimes(2));
    expect(launchMock.mock.calls[0][3]).toBe("00000000-0000-4000-8000-000000000074");
    expect(launchMock.mock.calls[1][3]).toBe("00000000-0000-4000-8000-000000000074");
    expect(navigateMock).toHaveBeenCalledWith("/inv/inv-recovered");
  });

  it("locks navigation while launch is pending", async () => {
    composeWithETagMock.mockResolvedValue({
      composition: { composition_id: "cmp-lock", url: "/x", ordered_set_digest: "d", members: [], hash_conflicts: [] },
      etag: '"etag-lock"',
    });
    // Never-resolving launch.
    launchMock.mockReturnValue(new Promise(() => undefined));
    vi.spyOn(crypto, "randomUUID").mockReturnValue("00000000-0000-4000-8000-000000000075");

    await enterComposeMode(["inv-a", "inv-b"]);
    await waitFor(() => expect(composeWithETagMock).toHaveBeenCalled());

    const confirmButtons = screen.getAllByText("Research together");
    fireEvent.click(confirmButtons[confirmButtons.length - 1]);
    await waitFor(() => expect(launchMock).toHaveBeenCalledTimes(1));

    // Checkboxes disabled during pending.
    expect((screen.getByLabelText("Select inv-a") as HTMLInputElement).disabled).toBe(true);
    expect((screen.getByLabelText("Select inv-b") as HTMLInputElement).disabled).toBe(true);
    // "Done" button disabled during pending.
    expect((screen.getByRole("button", { name: "Done" }) as HTMLButtonElement).disabled).toBe(true);
    // Confirm button shows pending state.
    expect(screen.getByText("Launching…")).toBeDefined();
    // "Back" button disabled during pending.
    expect((screen.getByText("Back") as HTMLButtonElement).disabled).toBe(true);
  });

  it("navigates only after the pending launch resolves", async () => {
    composeWithETagMock.mockResolvedValue({
      composition: { composition_id: "cmp-stale", url: "/x", ordered_set_digest: "d", members: [], hash_conflicts: [] },
      etag: '"etag-stale"',
    });
    // Deferred launch — we control when it resolves.
    let resolveLaunch: (v: unknown) => void;
    launchMock.mockReturnValue(new Promise((resolve) => { resolveLaunch = resolve; }));
    vi.spyOn(crypto, "randomUUID").mockReturnValue("00000000-0000-4000-8000-000000000076");

    render(<MemoryRouter><InvestigationSidebar /></MemoryRouter>);
    fireEvent.click(screen.getByText("Select"));
    fireEvent.click(screen.getByLabelText("Select inv-a"));
    fireEvent.click(screen.getByLabelText("Select inv-b"));

    const composeButtons = screen.getAllByText("Research together");
    fireEvent.click(composeButtons[0]);
    await waitFor(() => expect(composeWithETagMock).toHaveBeenCalled());
    fireEvent.change(await screen.findByLabelText("Follow-up question"), {
      target: { value: "What connects these findings?" },
    });

    // Click confirm.
    const confirmButtons = screen.getAllByText("Research together");
    fireEvent.click(confirmButtons[confirmButtons.length - 1]);
    await waitFor(() => expect(launchMock).toHaveBeenCalledTimes(1));

    expect(navigateMock).not.toHaveBeenCalled();
    resolveLaunch!({ investigation_id: "inv-stale", status: "started", start_event_id: "evt-stale" });
    await waitFor(() => expect(navigateMock).toHaveBeenCalledWith("/inv/inv-stale"));
  });

  it("passes the user's follow-up question to launchComposition", async () => {
    composeWithETagMock.mockResolvedValue({
      composition: { composition_id: "cmp-fu", url: "/x", ordered_set_digest: "d", members: [], hash_conflicts: [] },
      etag: '"etag-fu"',
    });
    launchMock.mockResolvedValue({ investigation_id: "inv-fu", status: "started", start_event_id: "evt-fu" });
    vi.spyOn(crypto, "randomUUID").mockReturnValue("00000000-0000-4000-8000-000000000077");

    await enterComposeMode(["inv-a", "inv-b"]);
    await waitFor(() => expect(composeWithETagMock).toHaveBeenCalled());

    // Type a follow-up question.
    fireEvent.change(screen.getByLabelText("Follow-up question"), {
      target: { value: "What patterns connect these findings?" },
    });

    const confirmButtons = screen.getAllByText("Research together");
    fireEvent.click(confirmButtons[confirmButtons.length - 1]);

    await waitFor(() => expect(launchMock).toHaveBeenCalledTimes(1));
    expect(launchMock).toHaveBeenCalledWith(
      "cmp-fu",
      { question: "What patterns connect these findings?" },
      '"etag-fu"',
      "00000000-0000-4000-8000-000000000077",
    );
  });

  it("exits compose mode on Back and resets state", async () => {
    composeWithETagMock.mockResolvedValue({
      composition: { composition_id: "cmp-back", url: "/x", ordered_set_digest: "d", members: [], hash_conflicts: [] },
      etag: '"etag-back"',
    });
    await enterComposeMode(["inv-a", "inv-b"]);
    await waitFor(() => expect(composeWithETagMock).toHaveBeenCalled());

    // Click Back.
    fireEvent.click(screen.getByText("Back"));
    // Should be back to the selection panel with action buttons.
    expect(screen.getByText("Open HTML")).toBeDefined();
    expect(screen.getByText("Create review draft")).toBeDefined();
  });

  it("shows launch error and allows recovery", async () => {
    composeWithETagMock.mockResolvedValue({
      composition: { composition_id: "cmp-err", url: "/x", ordered_set_digest: "d", members: [], hash_conflicts: [] },
      etag: '"etag-err"',
    });
    launchMock.mockRejectedValue(new Error("stale ETag"));
    vi.spyOn(crypto, "randomUUID").mockReturnValue("00000000-0000-4000-8000-000000000078");

    await enterComposeMode(["inv-a", "inv-b"]);
    await waitFor(() => expect(composeWithETagMock).toHaveBeenCalled());

    const confirmButtons = screen.getAllByText("Research together");
    fireEvent.click(confirmButtons[confirmButtons.length - 1]);
    expect((await screen.findByRole("alert")).textContent).toContain("stale ETag");
  });

  it("does not call launchComposition on compose or Open HTML", async () => {
    composeWithETagMock.mockResolvedValue({
      composition: { composition_id: "cmp-nolaunch", url: "/x", ordered_set_digest: "d", members: [], hash_conflicts: [] },
      etag: '"etag-nl"',
    });
    await enterComposeMode(["inv-a", "inv-b"]);
    await waitFor(() => expect(composeWithETagMock).toHaveBeenCalled());
    // Just entering compose mode should NOT trigger launch.
    expect(launchMock).not.toHaveBeenCalled();
  });

  it("disables checkboxes for non-composable investigations", async () => {
    render(<MemoryRouter><InvestigationSidebar /></MemoryRouter>);
    fireEvent.click(screen.getByText("Select"));
    // inv-running: in_progress → not composable
    expect((screen.getByLabelText("Select inv-running") as HTMLInputElement).disabled).toBe(true);
    // inv-c: artifact_composable=false → not composable
    expect((screen.getByLabelText("Select inv-c") as HTMLInputElement).disabled).toBe(true);
    // inv-a: composable → enabled
    expect((screen.getByLabelText("Select inv-a") as HTMLInputElement).disabled).toBe(false);
  });
});
