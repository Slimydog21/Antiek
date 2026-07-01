import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import { cleanup, render, screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { MemoryRouter, useLocation } from "react-router-dom";

import type { ParkedQuestionEntry } from "../lib/api";
import CommandPalette from "./CommandPalette";
import {
  getBrainstormQuestionSelection,
  resetBrainstormQuestionSelection,
} from "../modes/BrainstormStation/WatchForLaterPanel";

const apiFetchMock = vi.hoisted(() => vi.fn());

vi.mock("../lib/api", async (orig) => ({
  ...(await orig<typeof import("../lib/api")>()),
  apiFetch: apiFetchMock,
}));

const QUESTION: ParkedQuestionEntry = {
  question_id: "q-palette-1",
  question_text: "How should memory retrieval become a writing block?",
  source_investigation_id: "inv-palette",
  source_document_id: "doc-palette",
  anchor_region_id: "region-palette",
  parked_at: "2026-07-01T00:00:00Z",
  parent_event_id: "event-palette",
};

function LocationProbe() {
  const location = useLocation();
  return <div data-testid="location">{location.pathname}</div>;
}

function renderPalette() {
  return render(
    <MemoryRouter initialEntries={["/"]}>
      <CommandPalette />
      <LocationProbe />
    </MemoryRouter>,
  );
}

beforeEach(() => {
  apiFetchMock.mockReset().mockImplementation(async (path: string) => {
    if (path === "/watch-for-later") {
      return {
        ok: true,
        json: async () => ({ count: 1, questions: [QUESTION] }),
      };
    }
    return {
      ok: true,
      json: async () => ({}),
    };
  });
});

afterEach(() => {
  cleanup();
  resetBrainstormQuestionSelection();
});

describe("CommandPalette", () => {
  it("describes trust and privacy routes without raw implementation labels", async () => {
    renderPalette();

    window.dispatchEvent(new Event("antiek:palette:toggle"));
    await userEvent.type(await screen.findByRole("textbox"), "privacy");

    expect(await screen.findByText("Privacy dashboard")).toBeTruthy();
    expect(screen.getByText("Privacy budgets and deletion controls")).toBeTruthy();
    expect(screen.queryByText(/ε exposure/i)).toBeNull();
    expect(screen.queryByText(/delete-all/i)).toBeNull();
    expect(screen.queryByText(/\(\/privacy\)/i)).toBeNull();

    await userEvent.clear(screen.getByRole("textbox"));
    await userEvent.type(screen.getByRole("textbox"), "trust");

    expect(await screen.findByText("Trust Center")).toBeTruthy();
    expect(
      screen.getByText("Published privacy, deletion, and training commitments"),
    ).toBeTruthy();
    expect(screen.queryByText(/deletion SLA/i)).toBeNull();
    expect(screen.queryByText(/\(\/trust\)/i)).toBeNull();
  });

  it("labels the meta-reading generator as proposed before navigation", async () => {
    renderPalette();

    window.dispatchEvent(new Event("antiek:palette:toggle"));
    await userEvent.type(await screen.findByRole("textbox"), "meta-reading");

    expect(await screen.findByText("Meta-reading")).toBeTruthy();
    expect(screen.getByText("Proposed — sign-off pending (/read/meta-reading)")).toBeTruthy();
  });

  it("finds governance routes from the shared operator registry", async () => {
    renderPalette();

    window.dispatchEvent(new Event("antiek:palette:toggle"));
    await userEvent.type(await screen.findByRole("textbox"), "cross-graph citations");

    expect(await screen.findByText("Cross-graph citations")).toBeTruthy();
    expect(screen.getByText("Record citations + rev-share (/cross-graph/citations)")).toBeTruthy();
  });

  it("opens a parked question in Brainstorm with the thought-partner selection seeded", async () => {
    renderPalette();

    window.dispatchEvent(new Event("antiek:palette:toggle"));
    await userEvent.type(
      await screen.findByRole("textbox"),
      "memory retrieval writing block",
    );

    await userEvent.click(await screen.findByText(QUESTION.question_text));

    expect(screen.getByTestId("location").textContent).toBe("/brainstorm");
    await waitFor(() => {
      expect(getBrainstormQuestionSelection()).toEqual(QUESTION);
    });
  });
});
