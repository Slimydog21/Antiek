import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import { cleanup, render, screen } from "@testing-library/react";
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
import { GATE_PHRASES, PUBLIC_LANE_LABELS } from "../../lib/speakVocab";

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
});

