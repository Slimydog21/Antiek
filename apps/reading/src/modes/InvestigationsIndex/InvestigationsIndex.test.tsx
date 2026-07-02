import { cleanup, fireEvent, render, screen, waitFor } from "@testing-library/react";
import { afterEach, describe, expect, it, vi } from "vitest";
import { MemoryRouter } from "react-router-dom";

import { apiFetch } from "../../lib/api";
import InvestigationsIndex from "./index";

const { navigateMock } = vi.hoisted(() => ({
  navigateMock: vi.fn(),
}));

vi.mock("../../lib/api", () => ({
  apiFetch: vi.fn(),
}));

vi.mock("react-router-dom", async (orig) => {
  const actual = await orig<typeof import("react-router-dom")>();
  return { ...actual, useNavigate: () => navigateMock };
});

const apiFetchMock = vi.mocked(apiFetch);

afterEach(() => {
  cleanup();
  vi.clearAllMocks();
});

function renderIndex() {
  return render(
    <MemoryRouter>
      <InvestigationsIndex />
    </MemoryRouter>,
  );
}

describe("InvestigationsIndex", () => {
  it("sanitizes malformed investigation costs", async () => {
    apiFetchMock.mockResolvedValueOnce({
      ok: true,
      json: async () => ({
        count: 4,
        investigations: [
          row("inv-valid", "Valid cost", 0.0123),
          row("inv-nan", "Malformed cost A", Number.NaN),
          row("inv-inf", "Malformed cost B", Number.POSITIVE_INFINITY),
          row("inv-neg", "Malformed cost C", -1),
        ],
      }),
    } as Response);

    renderIndex();

    expect(await screen.findByText("Valid cost")).toBeTruthy();
    expect(screen.getByText("4 shown · $0.01 total cost")).toBeTruthy();
    expect(screen.getByText("$0.0123")).toBeTruthy();
    expect(screen.getAllByText("$0.0000").length).toBeGreaterThanOrEqual(3);
    expect(document.body.textContent).not.toMatch(/NaN|Infinity|\$-/);
  });

  it("accepts numeric-string costs from the investigations API", async () => {
    apiFetchMock.mockResolvedValueOnce({
      ok: true,
      json: async () => ({
        count: 2,
        investigations: [
          row("inv-string-a", "String cost A", "0.0123"),
          row("inv-string-b", "String cost B", "0.0077"),
        ],
      }),
    } as Response);

    renderIndex();

    expect(await screen.findByText("String cost A")).toBeTruthy();
    expect(screen.getByText("2 shown · $0.02 total cost")).toBeTruthy();
    expect(screen.getByText("$0.0123")).toBeTruthy();
    expect(screen.getByText("$0.0077")).toBeTruthy();
  });

  it("sanitizes investigation list rows before rendering links", async () => {
    apiFetchMock.mockResolvedValueOnce({
      ok: true,
      json: async () => ({
        count: 2,
        investigations: [
          {
            investigation_id: " inv dirty ",
            question: " ",
            status: " completed ",
            started_at: " 2026-07-01T04:00:00Z ",
            completed_at: " ",
            cost_usd_total: "0.5",
            parent_investigation_id: " parent dirty ",
          },
          {
            investigation_id: " ",
            question: "Skipped investigation",
            status: "completed",
          },
        ],
      }),
    } as Response);

    renderIndex();

    expect(await screen.findByText("inv dirty")).toBeTruthy();
    expect(screen.queryByText("Skipped investigation")).toBeNull();
    expect(screen.getByText("1 shown · $0.50 total cost")).toBeTruthy();
    expect(screen.getAllByText("completed").length).toBeGreaterThanOrEqual(2);
    expect(screen.getByText("$0.5000")).toBeTruthy();
    expect(screen.getByText("started 2026-07-01T04:00:00Z")).toBeTruthy();

    expect(
      screen
        .getByRole("link", { name: /inv dirty.*parent: parent dirty/i })
        .getAttribute("href"),
    ).toBe("/inv/inv%20dirty");
    expect(screen.getByRole("link", { name: /replay/i }).getAttribute("href")).toBe(
      "/replay/inv%20dirty",
    );
  });

  it("clamps malformed max sub-question input before submitting", async () => {
    apiFetchMock
      .mockResolvedValueOnce({
        ok: true,
        json: async () => ({ count: 0, investigations: [] }),
      } as Response)
      .mockResolvedValueOnce({
        ok: true,
        status: 200,
        json: async () => ({ investigation_id: " inv-created " }),
      } as Response);

    renderIndex();

    await screen.findByText("No investigations match this filter.");
    fireEvent.change(screen.getByPlaceholderText("What's the question? (≥ 3 chars)"), {
      target: { value: "What should we research next?" },
    });
    fireEvent.change(screen.getByLabelText("Max sub-questions (1-20)"), {
      target: { value: "" },
    });
    fireEvent.click(screen.getByRole("button", { name: "Start investigation" }));

    await waitFor(() => expect(navigateMock).toHaveBeenCalledWith("/inv/inv-created"));
    const [, init] = apiFetchMock.mock.calls[1];
    expect(JSON.parse(init?.body as string)).toMatchObject({
      max_sub_questions: 1,
    });
  });

  it("surfaces malformed created investigation ids instead of navigating", async () => {
    apiFetchMock
      .mockResolvedValueOnce({
        ok: true,
        json: async () => ({ count: 0, investigations: [] }),
      } as Response)
      .mockResolvedValueOnce({
        ok: true,
        status: 200,
        json: async () => ({ investigation_id: " " }),
      } as Response);

    renderIndex();

    await screen.findByText("No investigations match this filter.");
    fireEvent.change(screen.getByPlaceholderText("What's the question? (≥ 3 chars)"), {
      target: { value: "What should we research next?" },
    });
    fireEvent.click(screen.getByRole("button", { name: "Start investigation" }));

    expect(await screen.findByText("investigation_id must be a non-empty string")).toBeTruthy();
    expect(navigateMock).not.toHaveBeenCalled();
  });
});

function row(id: string, question: string, cost: unknown) {
  return {
    investigation_id: id,
    question,
    status: "completed",
    started_at: null,
    completed_at: null,
    cost_usd_total: cost,
    parent_investigation_id: null,
  };
}
