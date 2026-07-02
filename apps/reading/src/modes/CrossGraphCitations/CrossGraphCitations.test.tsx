import {
  cleanup,
  fireEvent,
  render,
  screen,
  waitFor,
} from "@testing-library/react";
import { MemoryRouter } from "react-router-dom";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";

import CrossGraphCitations from "./index";

const apiFetchMock = vi.hoisted(() => vi.fn());

vi.mock("../../lib/api", async (orig) => {
  const actual = await orig<typeof import("../../lib/api")>();
  return {
    ...actual,
    apiFetch: apiFetchMock,
  };
});

beforeEach(() => {
  apiFetchMock.mockReset();
  apiFetchMock.mockResolvedValue({
    ok: true,
    status: 201,
    json: async () => ({
      reference_id: " ref dirty ",
      referencing_user_id: " operator dirty ",
      referencing_investigation_id: " inv dirty ",
      referenced_user_id: " user dirty ",
      referenced_note_id: " note dirty ",
      federated_substrate_id: " partner dirty ",
      cited_at: " 2026-06-03T12:00:00Z ",
    }),
  });
});

afterEach(() => cleanup());

function renderCitations() {
  return render(
    <MemoryRouter>
      <CrossGraphCitations />
    </MemoryRouter>,
  );
}

describe("CrossGraphCitations", () => {
  it("sanitizes created citations before rendering recent records", async () => {
    renderCitations();

    fireEvent.change(screen.getByDisplayValue("__operator__"), {
      target: { value: " operator input " },
    });
    fireEvent.change(screen.getByPlaceholderText("inv-..."), {
      target: { value: " inv input " },
    });
    fireEvent.change(screen.getByPlaceholderText("user-A"), {
      target: { value: " user input " },
    });
    fireEvent.change(screen.getByPlaceholderText("note-7"), {
      target: { value: " note input " },
    });
    fireEvent.click(screen.getByLabelText(/federation citation/i));
    fireEvent.change(screen.getByPlaceholderText("partner-research-coop"), {
      target: { value: " partner input " },
    });

    fireEvent.click(screen.getByRole("button", { name: "Record citation" }));

    await waitFor(() =>
      expect(apiFetchMock).toHaveBeenCalledWith(
        "/cross-graph/citations",
        expect.objectContaining({ method: "POST" }),
      ),
    );

    const postCall = apiFetchMock.mock.calls[0];
    expect(JSON.parse(String(postCall[1]?.body))).toEqual({
      referencing_user_id: "operator input",
      referencing_investigation_id: "inv input",
      referenced_user_id: "user input",
      referenced_note_id: "note input",
      federated_substrate_id: "partner input",
    });

    expect(await screen.findByText("Recently recorded")).toBeTruthy();
    expect(screen.getByText(/operator dirty\/inv dirty/)).toBeTruthy();
    expect(screen.getByText(/user dirty\/note dirty/)).toBeTruthy();
    expect(
      screen.getByText(
        /ref dirty · 2026-06-03T12:00:00Z · federated: partner dirty/,
      ),
    ).toBeTruthy();
    expect(document.body.textContent).not.toMatch(/ ref dirty | inv dirty /);
  });
});
