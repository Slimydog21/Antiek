import { StrictMode, type ReactNode } from "react";
import { cleanup, fireEvent, render, screen } from "@testing-library/react";
import { afterEach, describe, expect, it, vi } from "vitest";
import { MemoryRouter, Route, Routes } from "react-router-dom";

import type { ParkedQuestionEntry, StartInvestigationResponse } from "../../lib/api";
import BrainstormStation, { type BrainstormStationProps } from "./index";

vi.mock("../../lib/analytics", () => ({ track: vi.fn() }));
vi.mock("../../workspace/PanelHost", () => ({
  PanelHost: ({ children }: { children: ReactNode }) => children,
}));

const firstQuestion: ParkedQuestionEntry = {
  question_id: "q-aurora",
  question_text: "Which assumptions would reverse the deployment thesis?",
  source_investigation_id: "inv-aurora",
  source_document_id: "doc-7",
  anchor_region_id: "region-3",
  parked_at: "2026-07-15T18:00:00Z",
  parent_event_id: "event-1",
};

const secondQuestion: ParkedQuestionEntry = {
  ...firstQuestion,
  question_id: "q-orbit",
  question_text: "What evidence would make the market map obsolete?",
};

const successfulLaunch: StartInvestigationResponse = {
  investigation_id: "inv-child",
  status: "in_progress",
  start_event_id: "event-child",
};

afterEach(cleanup);

function mount(props: BrainstormStationProps = {}) {
  return render(
    <MemoryRouter initialEntries={["/brainstorm"]}>
      <Routes>
        <Route path="/brainstorm" element={<BrainstormStation withWorkspacePanels={false} {...props} />} />
        <Route path="/inv/:id" element={<div>Research destination</div>} />
      </Routes>
    </MemoryRouter>,
  );
}

describe("Curiosity Observatory", () => {
  it("selects the first authoritative parked question and keeps semantics out of the raster", async () => {
    mount({
      loadQuestions: vi.fn(async () => ({ count: 2, questions: [firstQuestion, secondQuestion] })),
    });
    expect((await screen.findAllByText(firstQuestion.question_text)).length).toBeGreaterThan(0);
    const environment = screen.getByTestId("curiosity-observatory-environment");
    expect(environment.getAttribute("alt")).toBe("");
    expect(environment.getAttribute("aria-hidden")).toBe("true");
    expect(environment.className).toContain("pointer-events-none");
    expect(environment.getAttribute("src")).toContain("curiosity_observatory_environment_v1");
    expect(environment.closest("main")?.className).not.toContain("curiosity-observatory--still");
    expect(screen.getByLabelText("2 parked questions")).toBeTruthy();
  });

  it("renders an authored empty state only after an empty response", async () => {
    mount({ loadQuestions: vi.fn(async () => ({ count: 0, questions: [] })) });
    expect(await screen.findByTestId("curiosity-observatory-empty")).toBeTruthy();
    expect(screen.queryByText(/Listening for unfinished/)).toBeNull();
  });

  it("does not leak a private list failure and retries", async () => {
    const loadQuestions = vi
      .fn()
      .mockRejectedValueOnce(new Error("private backend trace"))
      .mockResolvedValueOnce({ count: 1, questions: [firstQuestion] });
    mount({ loadQuestions });
    const alert = await screen.findByRole("alert");
    expect(alert.textContent).toMatch(/could not refresh/);
    expect(alert.textContent).not.toMatch(/private backend trace/);
    fireEvent.click(screen.getByRole("button", { name: "Try again" }));
    expect((await screen.findAllByText(firstQuestion.question_text)).length).toBeGreaterThan(0);
    expect(loadQuestions).toHaveBeenCalledTimes(2);
  });

  it("ignores a superseded list response", async () => {
    let resolveOld!: (value: { count: number; questions: ParkedQuestionEntry[] }) => void;
    const oldLoader = vi.fn(() => new Promise<{ count: number; questions: ParkedQuestionEntry[] }>((resolve) => { resolveOld = resolve; }));
    const currentLoader = vi.fn(async () => ({ count: 1, questions: [secondQuestion] }));
    const view = mount({ loadQuestions: oldLoader });
    view.rerender(
      <MemoryRouter initialEntries={["/brainstorm"]}>
        <BrainstormStation withWorkspacePanels={false} loadQuestions={currentLoader} />
      </MemoryRouter>,
    );
    expect((await screen.findAllByText(secondQuestion.question_text)).length).toBeGreaterThan(0);
    resolveOld({ count: 1, questions: [firstQuestion] });
    await Promise.resolve();
    expect(screen.queryByText(firstQuestion.question_text)).toBeNull();
  });

  it("loads under React StrictMode effect replay", async () => {
    const loadQuestions = vi.fn(async () => ({ count: 1, questions: [firstQuestion] }));
    render(
      <StrictMode>
        <MemoryRouter><BrainstormStation withWorkspacePanels={false} loadQuestions={loadQuestions} /></MemoryRouter>
      </StrictMode>,
    );
    expect((await screen.findAllByText(firstQuestion.question_text)).length).toBeGreaterThan(0);
  });

  it("allows only one launch in flight and navigates after authoritative success", async () => {
    let resolveLaunch!: (value: StartInvestigationResponse) => void;
    const launchQuestion = vi.fn(() => new Promise<StartInvestigationResponse>((resolve) => { resolveLaunch = resolve; }));
    const loadQuestions = vi
      .fn()
      .mockResolvedValueOnce({ count: 1, questions: [firstQuestion] })
      .mockResolvedValueOnce({ count: 0, questions: [] });
    mount({ loadQuestions, launchQuestion });
    const launch = await screen.findByRole("button", { name: "Launch investigation" });
    fireEvent.click(launch);
    fireEvent.click(launch);
    expect(launchQuestion).toHaveBeenCalledTimes(1);
    resolveLaunch(successfulLaunch);
    expect(await screen.findByText("Research destination")).toBeTruthy();
  });

  it("navigates after launch success even when the presentation refresh fails", async () => {
    const loadQuestions = vi
      .fn()
      .mockResolvedValueOnce({ count: 1, questions: [firstQuestion] })
      .mockRejectedValueOnce(new Error("refresh unavailable"));
    mount({ loadQuestions, launchQuestion: vi.fn(async () => successfulLaunch) });
    fireEvent.click(await screen.findByRole("button", { name: "Launch investigation" }));
    expect(await screen.findByText("Research destination")).toBeTruthy();
    expect(loadQuestions).toHaveBeenCalledTimes(2);
  });

  it("keeps a question parked and hides private launch failures", async () => {
    mount({
      loadQuestions: vi.fn(async () => ({ count: 1, questions: [firstQuestion] })),
      launchQuestion: vi.fn(async () => { throw new Error("provider credential trace"); }),
    });
    fireEvent.click(await screen.findByRole("button", { name: "Launch investigation" }));
    const alert = await screen.findByRole("alert");
    expect(alert.textContent).toMatch(/stayed parked/);
    expect(alert.textContent).not.toMatch(/provider credential trace/);
    expect(screen.getAllByText(firstQuestion.question_text).length).toBeGreaterThan(0);
  });
});
