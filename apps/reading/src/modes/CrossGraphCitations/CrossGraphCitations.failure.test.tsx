/**
 * FFX SPR-03 (F-08): a failed citation POST rendered
 * "POST /cross-graph/citations: HTTP n — <response body>". The failure must be
 * plain copy with no status, no path and no body.
 */
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import { cleanup, render, screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { MemoryRouter } from "react-router-dom";

import CrossGraphCitations from "./index";

const fetchMock = vi.fn();

beforeEach(() => {
  fetchMock.mockReset();
  vi.stubGlobal("fetch", fetchMock);
});
afterEach(() => {
  cleanup();
  vi.unstubAllGlobals();
});

/** The `what` passed to describeFailure is plain words, so the title is
 *  "Couldn't <what>." and not the "That didn't work." fallback (#3538). */
function expectPlainTitle(text: string) {
  expect(text).toMatch(/^Couldn't [a-z][a-z ']*\./i);
}

function expectHonest(text: string) {
  expect(text).not.toMatch(/\b[45]\d\d\b/);
  expect(text).not.toMatch(/\/[a-z-]+/);
  expect(text).not.toContain("Failed to fetch");
  expect(text).not.toContain("HTTP");
  expect(text).not.toContain("detail");
}

async function fillAndSubmit() {
  const inputs = screen.getAllByRole("textbox");
  // referencing user is prefilled; fill investigation, referenced user, note.
  await userEvent.type(inputs[1], "inv-1");
  await userEvent.type(inputs[2], "user-A");
  await userEvent.type(inputs[3], "note-7");
  await userEvent.click(screen.getByRole("button", { name: "Record citation" }));
}

function renderPage() {
  return render(
    <MemoryRouter>
      <CrossGraphCitations />
    </MemoryRouter>,
  );
}

describe("CrossGraphCitations — honest failure", () => {
  it("a 503 with a body shows plain copy; Try again re-sends the same request", async () => {
    fetchMock
      .mockResolvedValueOnce(new Response(JSON.stringify({ detail: "x" }), { status: 503 }))
      .mockResolvedValueOnce(
        new Response(
          JSON.stringify({
            reference_id: "ref-1",
            referencing_user_id: "__operator__",
            referencing_investigation_id: "inv-1",
            referenced_user_id: "user-A",
            referenced_note_id: "note-7",
            federated_substrate_id: null,
            cited_at: "2026-09-27",
          }),
          { status: 201 },
        ),
      );
    renderPage();
    await fillAndSubmit();
    const alert = await screen.findByRole("alert");
    expectHonest(alert.textContent ?? "");
    expectPlainTitle(alert.textContent ?? "");
    expect(alert.textContent).toContain("Couldn't record the citation.");
    await userEvent.click(screen.getByRole("button", { name: "Try again" }));
    await waitFor(() => expect(screen.queryByRole("alert")).toBeNull());
    expect(fetchMock).toHaveBeenCalledTimes(2);
    expect(fetchMock.mock.calls[1][1]?.body).toBe(fetchMock.mock.calls[0][1]?.body);
    expect(await screen.findByText("Recently recorded")).toBeTruthy();
  });

  it("a network TypeError never shows 'Failed to fetch', and the page shows no path anywhere", async () => {
    fetchMock.mockRejectedValue(new TypeError("Failed to fetch"));
    renderPage();
    await fillAndSubmit();
    const alert = await screen.findByRole("alert");
    expectHonest(alert.textContent ?? "");
    expectPlainTitle(alert.textContent ?? "");
    // The header's federation link read "/federation" (M7 crawl); written after the fix.
    expectHonest(document.body.textContent ?? "");
  });

  it("a 422 whose detail is a snake_case code is not echoed", async () => {
    fetchMock.mockResolvedValue(
      new Response(JSON.stringify({ detail: "referenced_note_not_public" }), { status: 422 }),
    );
    renderPage();
    await fillAndSubmit();
    const alert = await screen.findByRole("alert");
    expectHonest(alert.textContent ?? "");
    expectPlainTitle(alert.textContent ?? "");
    expect(alert.textContent).not.toContain("referenced_note_not_public");
  });
});
