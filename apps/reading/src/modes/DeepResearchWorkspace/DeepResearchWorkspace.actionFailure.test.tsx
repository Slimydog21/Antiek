/**
 * FFX SPR-04 follow-up (F-07 class, in this sprint's DRW file): a failed
 * workspace action (propose, edit, approve, launch, source check) shows
 * describeFailure's plain title and detail, never the raw request line,
 * a status, a path, or the browser's "Failed to fetch".
 */
import { cleanup, fireEvent, render, screen } from "@testing-library/react";
import type { ReactNode } from "react";
import { MemoryRouter } from "react-router-dom";
import { afterEach, describe, expect, it, vi } from "vitest";

import { ApiError } from "../../lib/api";

const api = vi.hoisted(() => ({ createPlan: vi.fn() }));

vi.mock("../../api/research", async (importOriginal) => ({
  ...(await importOriginal<typeof import("../../api/research")>()),
  ...api,
}));
vi.mock("../../api/composerProjection", () => ({ fetchComposerProjection: vi.fn() }));
vi.mock("../../workspace/PanelHost", () => ({
  PanelHost: ({ children }: { children: ReactNode }) => children,
}));

import DeepResearchWorkspace from ".";

const RAW = /\b[1-5]\d\d\b|HTTP|\/research|POST|GET|Failed to fetch/;

afterEach(() => {
  cleanup();
  vi.clearAllMocks();
});

async function proposeAndFail(err: unknown) {
  api.createPlan.mockRejectedValue(err);
  render(
    <MemoryRouter>
      <DeepResearchWorkspace />
    </MemoryRouter>,
  );
  fireEvent.change(screen.getByLabelText("research problem"), {
    target: { value: "How will the grid cope?" },
  });
  fireEvent.click(screen.getByRole("button", { name: "Cascade" }));
  return screen.findByRole("alert");
}

describe("DRW workspace action failures", () => {
  it("a 503 on propose shows the humanised title and no status, method or path", async () => {
    const alert = await proposeAndFail(
      new ApiError("POST /research/plans failed: HTTP 503", 503, "upstream down"),
    );
    expect(alert.textContent).toContain("Couldn't propose a research plan.");
    expect(alert.textContent).toContain("Antiek is busy or restarting.");
    expect(alert.textContent).not.toMatch(RAW);
  });

  it("a network TypeError on propose shows the offline description, not 'Failed to fetch'", async () => {
    const alert = await proposeAndFail(new TypeError("Failed to fetch"));
    expect(alert.textContent).toContain("Couldn't propose a research plan.");
    expect(alert.textContent).toContain("can't be reached");
    expect(alert.textContent).not.toMatch(RAW);
  });
});
