import { cleanup, fireEvent, render, screen } from "@testing-library/react";
import { MemoryRouter } from "react-router-dom";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";

import InterviewIndex from "./index";

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
  apiFetchMock.mockImplementation(async (path: string) => {
    if (path === "/interview-projects") {
      return {
        ok: true,
        status: 200,
        json: async () => [
          {
            project_id: " project dirty ",
            title: " Project Dirty ",
            topic_description: " Topic Dirty ",
            deliverable_id: null,
            must_cover: [" Question one ", " ", 42],
            framing: " Framing dirty ",
            interview_count: "3.8",
            completed_count: -1,
            created_at: " 2026-06-04 ",
          },
          {
            project_id: " ",
            title: "Skipped project",
          },
        ],
      } as Response;
    }
    if (path === "/interview-projects/project%20dirty/interviews") {
      return {
        ok: true,
        status: 200,
        json: async () => [
          {
            interview_id: " interview dirty ",
            project_id: " project dirty ",
            informant_handle: " Handle Dirty ",
            informant_email: " informant@example.com ",
            status: " invited ",
            turn_count: "2.9",
          },
          {
            interview_id: " ",
            project_id: "project dirty",
            informant_handle: "Skipped informant",
          },
        ],
      } as Response;
    }
    return { ok: false, status: 404, json: async () => ({}) } as Response;
  });
});

afterEach(() => cleanup());

describe("InterviewIndex", () => {
  it("sanitizes interview projects and expanded interview rows", async () => {
    render(
      <MemoryRouter>
        <InterviewIndex />
      </MemoryRouter>,
    );

    fireEvent.click(await screen.findByText("Project Dirty"));

    expect(await screen.findByText("Question one")).toBeTruthy();
    expect(await screen.findByText("Handle Dirty")).toBeTruthy();
    expect(screen.getByText("0/3 done")).toBeTruthy();
    expect(screen.getByText("invited · 2 turns")).toBeTruthy();
    expect(
      screen.getByRole("link", { name: "Handle Dirty" }).getAttribute("href"),
    ).toBe("/interview/interview%20dirty");
    expect(document.body.textContent).not.toMatch(
      /Skipped|project dirty | interview dirty |NaN|Infinity|-1/,
    );
  });
});
