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

const { listPeopleMock, createPersonMock } = vi.hoisted(() => ({
  listPeopleMock: vi.fn(),
  createPersonMock: vi.fn(),
}));

vi.mock("../../lib/speakApi", async (orig) => ({
  ...(await orig<typeof import("../../lib/speakApi")>()),
  listPeople: listPeopleMock,
  createPerson: createPersonMock,
}));

import SpeakIndex from "./index";

beforeEach(() => {
  listPeopleMock.mockReset().mockResolvedValue([]);
  createPersonMock.mockReset();
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
});
