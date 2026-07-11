import { afterEach, describe, expect, it, vi } from "vitest";
import { cleanup, fireEvent, render, screen, waitFor } from "@testing-library/react";
import TwinSearchPanel from "./TwinSearchPanel";

afterEach(() => {
  cleanup();
  vi.restoreAllMocks();
});

describe("TwinSearchPanel", () => {
  it("searches via injectable searchFn and lists hits", async () => {
    const searchFn = vi.fn(async () => ({
      query: "scaling",
      count: 1,
      hits: [
        {
          twin_id: "t1",
          parent_asset_id: "p1",
          score: 2,
          matched_insights: ["scaling laws"],
          matched_questions: [],
          source_label: null,
        },
      ],
    }));
    render(
      <TwinSearchPanel searchFn={searchFn} initialQuery="scaling" />,
    );
    fireEvent.click(screen.getByTestId("twin-search-run"));
    await waitFor(() => {
      expect(screen.getByTestId("twin-search-result")).toBeTruthy();
    });
    expect(searchFn).toHaveBeenCalledWith({
      q: "scaling",
      parent_asset_id: null,
    });
    expect(screen.getByTestId("twin-search-hit-t1").textContent).toMatch(
      /scaling laws/,
    );
  });

  it("shows empty match honesty", async () => {
    const searchFn = vi.fn(async () => ({
      query: "zzz",
      count: 0,
      hits: [],
    }));
    render(<TwinSearchPanel searchFn={searchFn} initialQuery="zzz" />);
    fireEvent.click(screen.getByTestId("twin-search-run"));
    await waitFor(() => {
      expect(screen.getByTestId("twin-search-empty").textContent).toMatch(
        /No twins matched/i,
      );
    });
  });

  it("surfaces empty-query errors without inventing hits", async () => {
    const searchFn = vi.fn(async () => {
      throw new Error("q must be non-empty");
    });
    render(<TwinSearchPanel searchFn={searchFn} initialQuery="  " />);
    fireEvent.click(screen.getByTestId("twin-search-run"));
    await waitFor(() => {
      expect(screen.getByTestId("twin-search-error").textContent).toMatch(
        /q must be non-empty/,
      );
    });
    expect(screen.queryByTestId("twin-search-result")).toBeNull();
  });
});
