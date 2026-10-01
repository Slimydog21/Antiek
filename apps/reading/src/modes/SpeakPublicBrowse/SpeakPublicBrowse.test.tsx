import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import { cleanup, fireEvent, render, screen } from "@testing-library/react";
import { MemoryRouter } from "react-router-dom";

const { listPublicFeedMock, listPublicOpportunitiesMock } = vi.hoisted(() => ({
  listPublicFeedMock: vi.fn(),
  listPublicOpportunitiesMock: vi.fn(),
}));

vi.mock("../../lib/speakApi", async (orig) => ({
  ...(await orig<typeof import("../../lib/speakApi")>()),
  listPublicFeed: listPublicFeedMock,
  listPublicOpportunities: listPublicOpportunitiesMock,
  getEconomics: vi.fn().mockRejectedValue(new Error("visitor")),
}));

import SpeakPublicBrowse from "./index";
import { GATE_PHRASES, PUBLIC_LANE_LABELS, PUSHES_COPY } from "../../lib/speakVocab";

beforeEach(() => {
  listPublicFeedMock.mockReset().mockResolvedValue([]);
  listPublicOpportunitiesMock.mockReset().mockResolvedValue([]);
});
afterEach(cleanup);

describe("SpeakPublicBrowse — unauth public door", () => {
  it("renders G7 honesty and empty feed without requiring auth", async () => {
    render(
      <MemoryRouter>
        <SpeakPublicBrowse />
      </MemoryRouter>,
    );
    expect(await screen.findByTestId("speak-public-browse")).toBeTruthy();
    expect(screen.getByTestId("browse-g7-banner")).toBeTruthy();
    expect(screen.getAllByText(GATE_PHRASES.publicEcosystem.whenGated).length).toBeGreaterThanOrEqual(1);
    expect(screen.getByText(PUBLIC_LANE_LABELS.browseHeading)).toBeTruthy();
    expect(await screen.findByText(/no public remembrances yet/i)).toBeTruthy();
  });

  it("a failed feed is an unknown, not an empty feed, and can be retried", async () => {
    // Rubric veto: the page printed "Failed to fetch" directly above
    // "No public remembrances yet" — an invented empty from an unknown.
    listPublicFeedMock
      .mockRejectedValueOnce(new TypeError("Failed to fetch"))
      .mockResolvedValueOnce([]);
    render(
      <MemoryRouter>
        <SpeakPublicBrowse />
      </MemoryRouter>,
    );
    expect(
      await screen.findByText("Public remembrances didn't load, so we can't say what's here yet."),
    ).toBeTruthy();
    expect(screen.queryByText(/no public remembrances yet/i)).toBeNull();
    expect(screen.queryByText("Failed to fetch")).toBeNull();
    expect(screen.queryByText(PUSHES_COPY.publicEmpty)).toBeNull();
    fireEvent.click(screen.getByRole("button", { name: "Try again" }));
    expect(await screen.findByText(/no public remembrances yet/i)).toBeTruthy();
    expect(listPublicFeedMock).toHaveBeenCalledTimes(2);
  });

  it("a failed opportunities request does not claim nothing is open", async () => {
    listPublicOpportunitiesMock.mockRejectedValueOnce(new Error("HTTP 502"));
    render(
      <MemoryRouter>
        <SpeakPublicBrowse />
      </MemoryRouter>,
    );
    expect(
      await screen.findByText("Open projects didn't load, so we can't say which are open right now."),
    ).toBeTruthy();
    expect(screen.queryByText(PUSHES_COPY.publicEmpty)).toBeNull();
  });
});

