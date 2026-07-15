import { cleanup, fireEvent, render, screen, waitFor } from "@testing-library/react";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";

import TwinNotesPanel, { absoluteApiUrl } from "./TwinNotesPanel";

const A2 = `tnr-${"a".repeat(32)}`;
const A1 = `tnr-${"1".repeat(32)}`;
const B1 = `tnr-${"b".repeat(32)}`;
const C1 = `tnc-${"c".repeat(32)}`;

const listMock = vi.fn();
const historyMock = vi.fn();
const composeMock = vi.fn();
vi.mock("../../api/research", async (load) => {
  const actual = await load<typeof import("../../api/research")>();
  return {
    ...actual,
    listTwinNotes: (...args: unknown[]) => listMock(...args),
    getTwinNoteHistory: (...args: unknown[]) => historyMock(...args),
    composeTwinNotes: (...args: unknown[]) => composeMock(...args),
  };
});

const revision = (revision_id: string, asset_id: string) => ({
  revision_id, asset_id, note_count: 2, source_count: 3,
});

describe("Cycle 48 twin notes", () => {
  beforeEach(() => {
    listMock.mockReset().mockResolvedValue({ assets: [
      { asset_id: "asset-a", asset_label: "Alpha", current_revision: revision(A2, "asset-a"), revision_count: 2 },
      { asset_id: "asset-b", asset_label: "Beta", current_revision: revision(B1, "asset-b"), revision_count: 1 },
    ] });
    historyMock.mockReset().mockResolvedValue({ asset_id: "asset-a", revisions: [revision(A2, "asset-a"), revision(A1, "asset-a")] });
    composeMock.mockReset();
  });
  afterEach(() => { cleanup(); vi.restoreAllMocks(); });

  it("resolves empty, relative, and absolute API bases and rejects hostile URLs", () => {
    const path = `/research/twin-notes/revisions/${A2}`;
    expect(absoluteApiUrl(path, "")).toBe(`${window.location.origin}${path}`);
    expect(absoluteApiUrl(path, "/api")).toBe(`${window.location.origin}/api${path}`);
    expect(absoluteApiUrl(path, "https://api.example.test/api")).toBe(`https://api.example.test/api${path}`);
    expect(() => absoluteApiUrl("https://evil.example/research/twin-notes/revisions/tnr-" + "e".repeat(32))).toThrow();
    expect(() => absoluteApiUrl("/not-twin-notes/tnr-" + "e".repeat(32))).toThrow();
  });

  it("loads metadata, discloses history, and opens an exact backend URL safely", async () => {
    const replace = vi.fn();
    const popup = { opener: window, close: vi.fn(), location: { replace } };
    vi.spyOn(window, "open").mockReturnValue(popup as unknown as Window);
    render(<TwinNotesPanel />);
    expect(await screen.findByText("2 notes · 3 sources · 2 revisions")).toBeTruthy();
    fireEvent.click(screen.getAllByText("History")[0]);
    expect(await screen.findByLabelText(`Select revision ${A1}`)).toBeTruthy();
    fireEvent.click(screen.getAllByText("Open exact")[1]);
    expect(popup.opener).toBeNull();
    expect(replace).toHaveBeenCalledWith(expect.stringContaining(`/research/twin-notes/revisions/${A1}`));
  });

  it("opens current exactly and reports a blocked exact-history popup without navigating", async () => {
    const replace = vi.fn();
    const popup = { opener: window, close: vi.fn(), location: { replace } };
    const open = vi.spyOn(window, "open").mockReturnValueOnce(popup as unknown as Window).mockReturnValueOnce(null);
    render(<TwinNotesPanel />);
    await screen.findByText("Alpha");
    fireEvent.click(screen.getAllByText("Open current")[0]);
    expect(popup.opener).toBeNull();
    expect(replace).toHaveBeenCalledWith(expect.stringContaining(`/research/twin-notes/revisions/${A2}`));
    fireEvent.click(screen.getAllByText("History")[0]);
    await screen.findByLabelText(`Select revision ${A1}`);
    fireEvent.click(screen.getAllByText("Open exact")[1]);
    expect(open).toHaveBeenCalledTimes(2);
    expect((await screen.findByRole("alert")).textContent).toContain("Allow pop-ups");
    expect(replace).toHaveBeenCalledTimes(1);
  });

  it("preserves click order, supports tray movement/removal, and composes exact revisions", async () => {
    composeMock.mockResolvedValue({ composition_id: C1, url: `/research/twin-notes/compositions/${C1}`, members: [] });
    const replace = vi.fn();
    vi.spyOn(window, "open").mockReturnValue({ opener: null, close: vi.fn(), location: { replace } } as unknown as Window);
    render(<TwinNotesPanel />);
    await screen.findByText("Alpha");
    fireEvent.click(screen.getByLabelText("Select current Beta"));
    fireEvent.click(screen.getByLabelText("Select current Alpha"));
    fireEvent.click(screen.getByLabelText(`Move ${A2} up`));
    fireEvent.click(screen.getByText("Compose twin notes"));
    await waitFor(() => expect(composeMock).toHaveBeenCalledWith([A2, B1]));
    expect(replace).toHaveBeenCalledWith(expect.stringContaining(`/research/twin-notes/compositions/${C1}`));
  });

  it("removes tray members and enforces the actual twenty-revision cap", async () => {
    listMock.mockResolvedValueOnce({ assets: Array.from({ length: 21 }, (_, index) => ({
      asset_id: `asset-${index}`,
      asset_label: `Asset ${index}`,
      current_revision: revision(`tnr-${index.toString(16).padStart(32, "0")}`, `asset-${index}`),
      revision_count: 1,
    })) });
    render(<TwinNotesPanel />);
    await screen.findByText("Asset 0");
    for (let index = 0; index < 20; index += 1) {
      fireEvent.click(screen.getByLabelText(`Select current Asset ${index}`));
    }
    expect(screen.getByText("20/20 selected")).toBeTruthy();
    expect((screen.getByLabelText("Select current Asset 20") as HTMLInputElement).disabled).toBe(true);
    fireEvent.click(screen.getByLabelText(`Remove tnr-${"0".repeat(31)}7`));
    expect(screen.getByText("19/20 selected")).toBeTruthy();
    expect((screen.getByLabelText("Select current Asset 7") as HTMLInputElement).checked).toBe(false);
    expect((screen.getByLabelText("Select current Asset 20") as HTMLInputElement).disabled).toBe(false);
  });

  it("freezes controls pending and retains the exact order for a value-free retry", async () => {
    let rejectFirst: ((reason?: unknown) => void) | undefined;
    composeMock.mockImplementationOnce(() => new Promise((_resolve, reject) => { rejectFirst = reject; }))
      .mockResolvedValueOnce({ composition_id: C1, url: `/research/twin-notes/compositions/${C1}`, members: [] });
    const close = vi.fn();
    vi.spyOn(window, "open").mockReturnValue({ opener: null, close, location: { replace: vi.fn() } } as unknown as Window);
    render(<TwinNotesPanel />);
    await screen.findByText("Alpha");
    fireEvent.click(screen.getByLabelText("Select current Alpha"));
    fireEvent.click(screen.getByLabelText("Select current Beta"));
    fireEvent.click(screen.getByText("Compose twin notes"));
    await waitFor(() => expect(composeMock).toHaveBeenCalledTimes(1));
    expect((screen.getByLabelText(`Remove ${A2}`) as HTMLButtonElement).disabled).toBe(true);
    expect((screen.getByLabelText(`Move ${B1} up`) as HTMLButtonElement).disabled).toBe(true);
    expect((screen.getByLabelText("Select current Alpha") as HTMLInputElement).disabled).toBe(true);
    expect((screen.getAllByText("Open current")[0] as HTMLButtonElement).disabled).toBe(true);
    expect((screen.getAllByText("History")[0] as HTMLButtonElement).disabled).toBe(true);
    expect((screen.getByLabelText("Refresh twin notes") as HTMLButtonElement).disabled).toBe(true);
    expect((screen.getByText("Composing…") as HTMLButtonElement).disabled).toBe(true);
    rejectFirst?.(new Error("/secret/path account-123 hash-deadbeef"));
    expect((await screen.findByRole("alert")).textContent).not.toContain("secret");
    expect(close).toHaveBeenCalled();
    fireEvent.click(screen.getByText("Compose twin notes"));
    await waitFor(() => expect(composeMock).toHaveBeenCalledTimes(2));
    expect(composeMock.mock.calls[1]).toEqual(composeMock.mock.calls[0]);
  });

  it("freezes the load-error retry while composition is pending", async () => {
    listMock.mockRejectedValueOnce(new Error("offline"));
    composeMock.mockReturnValue(new Promise(() => undefined));
    vi.spyOn(window, "open").mockReturnValue({ opener: null, close: vi.fn(), location: { replace: vi.fn() } } as unknown as Window);
    render(<TwinNotesPanel />);
    const retry = await screen.findByText("Try again");
    expect((retry as HTMLButtonElement).disabled).toBe(false);

    // A retained asset list can coexist with a later refresh error. Reload the
    // component with that sequence so composition remains available.
    cleanup();
    listMock.mockReset()
      .mockResolvedValueOnce({ assets: [
        { asset_id: "asset-a", asset_label: "Alpha", current_revision: revision(A2, "asset-a"), revision_count: 1 },
        { asset_id: "asset-b", asset_label: "Beta", current_revision: revision(B1, "asset-b"), revision_count: 1 },
      ] })
      .mockRejectedValueOnce(new Error("offline"));
    render(<TwinNotesPanel />);
    await screen.findByText("Alpha");
    fireEvent.click(screen.getByLabelText("Refresh twin notes"));
    await screen.findByText("Try again");
    fireEvent.click(screen.getByLabelText("Select current Alpha"));
    fireEvent.click(screen.getByLabelText("Select current Beta"));
    fireEvent.click(screen.getByText("Compose twin notes"));
    await waitFor(() => expect(composeMock).toHaveBeenCalledTimes(1));
    expect((screen.getByText("Try again") as HTMLButtonElement).disabled).toBe(true);
  });

  it("does not submit when a popup is blocked", async () => {
    vi.spyOn(window, "open").mockReturnValue(null);
    render(<TwinNotesPanel />);
    await screen.findByText("Alpha");
    fireEvent.click(screen.getByLabelText("Select current Alpha"));
    fireEvent.click(screen.getByLabelText("Select current Beta"));
    fireEvent.click(screen.getByText("Compose twin notes"));
    expect((await screen.findByRole("alert")).textContent).toContain("Allow pop-ups");
    expect(composeMock).not.toHaveBeenCalled();
  });

  it("closes the popup and shows no returned value when composition URL is hostile", async () => {
    composeMock.mockResolvedValue({ composition_id: C1, url: "https://evil.example/secret", members: [] });
    const close = vi.fn();
    const replace = vi.fn();
    vi.spyOn(window, "open").mockReturnValue({ opener: null, close, location: { replace } } as unknown as Window);
    render(<TwinNotesPanel />);
    await screen.findByText("Alpha");
    fireEvent.click(screen.getByLabelText("Select current Alpha"));
    fireEvent.click(screen.getByLabelText("Select current Beta"));
    fireEvent.click(screen.getByText("Compose twin notes"));
    expect(await screen.findByRole("alert")).toBeTruthy();
    expect(close).toHaveBeenCalled();
    expect(replace).not.toHaveBeenCalled();
    expect(screen.getByRole("alert").textContent).not.toContain("evil");
  });
});
