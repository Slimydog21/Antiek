import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import { cleanup, fireEvent, render, screen, waitFor } from "@testing-library/react";
import { MemoryRouter, Route, Routes } from "react-router-dom";

/**
 * SpeakIndex.test — the warm one-door home (Product Depth SPR-08 M1).
 *
 * Load-bearing claims:
 *  - the door opens on one warm question ("Who do you want to remember?"),
 *    not a wall of enums — no subject-status / publish-intent select is shown;
 *  - naming a person creates a project and LANDS on it (Speak E1);
 *  - an engine failure shows the honest AIActionFailure, never a fake landing.
 */

const { listPeopleMock, createPersonMock, listPublicFeedMock } = vi.hoisted(() => ({
  listPeopleMock: vi.fn(),
  createPersonMock: vi.fn(),
  listPublicFeedMock: vi.fn(),
}));

vi.mock("../../lib/speakApi", async (orig) => ({
  ...(await orig<typeof import("../../lib/speakApi")>()),
  listPeople: listPeopleMock,
  createPerson: createPersonMock,
  listPublicFeed: listPublicFeedMock,
}));

import SpeakIndex from "./index";

beforeEach(() => {
  listPeopleMock.mockReset().mockResolvedValue([]);
  createPersonMock.mockReset();
  listPublicFeedMock.mockReset().mockResolvedValue([]);
});
afterEach(cleanup);

function mount() {
  return render(
    <MemoryRouter initialEntries={["/speak"]}>
      <Routes>
        <Route path="/speak" element={<SpeakIndex />} />
        <Route path="/speak/:projectId" element={<div>PROJECT PAGE</div>} />
      </Routes>
    </MemoryRouter>,
  );
}

describe("SpeakIndex — the warm door", () => {
  it("opens on one warm question, not a wall of enums", async () => {
    mount();
    expect(await screen.findByText(/who do you want to remember/i)).toBeTruthy();
    // No subject-status / publish-intent selects on the first screen.
    expect(document.querySelectorAll("select").length).toBe(0);
    expect(screen.queryByText(/subject status|publish intent/i)).toBeNull();
  });

  it("renders session thinking brand mark on the Speak door (living-TV densify)", async () => {
    mount();
    await screen.findByText(/who do you want to remember/i);
    expect(screen.getByTestId("speak-home-werner-brand")).toBeTruthy();
  });

  it("naming a person creates a project and lands on it", async () => {
    createPersonMock.mockResolvedValue("proj-abc");
    mount();
    const input = await screen.findByLabelText(/who do you want to remember/i);
    fireEvent.change(input, { target: { value: "my grandmother" } });
    fireEvent.click(screen.getByRole("button", { name: /start their story/i }));
    await waitFor(() => expect(screen.getByText("PROJECT PAGE")).toBeTruthy());
    expect(createPersonMock).toHaveBeenCalledWith("my grandmother");
  });

  it("shows an honest failure (no fake landing) when create fails", async () => {
    createPersonMock.mockRejectedValue(new Error("no provider"));
    mount();
    const input = await screen.findByLabelText(/who do you want to remember/i);
    fireEvent.change(input, { target: { value: "Dad" } });
    fireEvent.click(screen.getByRole("button", { name: /start their story/i }));
    expect(await screen.findByRole("alert")).toBeTruthy();
    expect(screen.queryByText("PROJECT PAGE")).toBeNull();
  });

  // ── SPR-01 M2 — frozen-shell snapshots ──
  // These pin the shipped UI so SPR-02/SPR-03 cannot drift the shell or
  // either lane's body unnoticed. Pure extraction: behavior-preserving.
  describe("frozen-shell snapshots (SPR-01 M2)", () => {
    it("matches the yours-empty snapshot", async () => {
      const { container } = mount();
      expect(await screen.findByText(/no one yet/i)).toBeTruthy();
      expect(container).toMatchSnapshot();
    });

    it("matches the yours-populated snapshot", async () => {
      listPeopleMock.mockResolvedValue([
        { id: "y1", name: "Grandma Rosa", willBePublic: false, voiceCount: 0 },
        { id: "y2", name: "Dad", willBePublic: true, voiceCount: 2 },
      ]);
      const { container } = mount();
      expect(await screen.findByText("Grandma Rosa")).toBeTruthy();
      expect(container).toMatchSnapshot();
    });

    it("matches the public-empty snapshot", async () => {
      const { container } = mount();
      fireEvent.click(screen.getByRole("tab", { name: /public remembrances/i }));
      expect(await screen.findByText(/no public remembrances yet/i)).toBeTruthy();
      expect(container).toMatchSnapshot();
    });
  });

  // ── SPR-04 M1 — private-lane gratitude / impact (no money) ──
  it("shows gratitude/impact on a populated private person, with no money word anywhere in the yours lane", async () => {
    listPeopleMock.mockResolvedValue([
      { id: "y1", name: "Grandma Rosa", willBePublic: false, voiceCount: 0 },
      { id: "y2", name: "Dad", willBePublic: false, voiceCount: 2 },
    ]);
    mount();
    // A person who has had voices shared gets the warm impact line…
    const impact = await screen.findByText(
      /their story is coming together — 2 voices have added a memory\./i,
    );
    expect(impact).toBeTruthy();
    // …and the private lane (YoursLane's own <section>) never speaks money.
    // Scope to YoursLane's output, not the SpeakIndex shell header (which the
    // shell owns and legitimately uses "shares" in its warm intro copy).
    const yoursLane = impact.closest("section");
    expect(yoursLane).not.toBeNull();
    expect(yoursLane?.textContent).not.toMatch(/\$|payout|earn|owed|share|paid/i);
  });

  it("stays honest (no false gratitude) for a private person with no voices yet", async () => {
    listPeopleMock.mockResolvedValue([
      { id: "y1", name: "Grandma Rosa", willBePublic: false, voiceCount: 0 },
    ]);
    mount();
    expect(await screen.findByText("Grandma Rosa")).toBeTruthy();
    expect(screen.queryByText(/their story is coming together/i)).toBeNull();
  });

  // ── M1 — the public/private split ──
  it("has a public-feed tab with an honest empty state and an 'add your memory' entry", async () => {
    mount();
    // Default tab is the private dashboard.
    expect(await screen.findByText(/no one yet/i)).toBeTruthy();
    // Switch to the public feed — empty is honest, not placeholder cards.
    fireEvent.click(screen.getByRole("tab", { name: /public remembrances/i }));
    expect(await screen.findByText(/no public remembrances yet/i)).toBeTruthy();
    // Now a populated feed shows an interview-with / chime-in entry per item.
    listPublicFeedMock.mockResolvedValue([{ id: "p1", name: "Grandma", voiceCount: 3 }]);
    fireEvent.click(screen.getByRole("tab", { name: /people you're remembering/i }));
    fireEvent.click(screen.getByRole("tab", { name: /public remembrances/i }));
    expect(await screen.findByText("Grandma")).toBeTruthy();
    expect(screen.getByRole("button", { name: /add your memory/i })).toBeTruthy();
  });
});
