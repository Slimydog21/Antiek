import { afterEach, describe, expect, it, vi } from "vitest";
import { cleanup, fireEvent, render, screen, waitFor } from "@testing-library/react";
import DraftMergePanel from "./DraftMergePanel";
import type { DraftMergeResult } from "../../api/draftMerge";

afterEach(() => {
  cleanup();
  vi.restoreAllMocks();
});

const sample: DraftMergeResult = {
  draft_id: "draft-xyz",
  parent_asset_id: "parent-1",
  provisional: true,
  html: '<article data-provisional="true">combined</article>',
  twin_ids: ["t1", "t2"],
  insight_count: 2,
  question_count: 1,
  created_at: 42,
  notes: [],
};

describe("DraftMergePanel", () => {
  it("builds provisional draft via injectable draftFn", async () => {
    const draftFn = vi.fn(async () => sample);
    render(
      <DraftMergePanel
        draftFn={draftFn}
        initialParentId="parent-1"
        initialTwinIds="t1, t2"
        initialParentHtml="<p>body</p>"
      />,
    );

    fireEvent.click(screen.getByTestId("draft-merge-build"));

    await waitFor(() => {
      expect(screen.getByTestId("draft-merge-result")).toBeTruthy();
    });
    expect(draftFn).toHaveBeenCalledWith({
      parent_asset_id: "parent-1",
      parent_html: "<p>body</p>",
      twin_ids: ["t1", "t2"],
      title: "Draft merge",
    });
    expect(screen.getByTestId("draft-merge-provisional").textContent).toMatch(
      /PROVISIONAL/i,
    );
    expect(screen.getByTestId("draft-merge-draft-id").textContent).toMatch(
      /draft-xyz/,
    );
    expect(screen.getByTestId("draft-merge-twins").textContent).toMatch(
      /2 twins/,
    );
    expect(screen.getByTestId("draft-merge-html").textContent).toMatch(
      /combined/,
    );
  });

  it("surfaces cross-parent rejection honesty", async () => {
    const { DraftMergeHttpError } = await import("../../api/draftMerge");
    const draftFn = vi.fn(async () => {
      throw new DraftMergeHttpError(
        409,
        JSON.stringify({
          detail: { code: "cross_parent_draft_merge_rejected" },
        }),
        "cross_parent_draft_merge_rejected",
      );
    });
    render(
      <DraftMergePanel
        draftFn={draftFn}
        initialParentId="p"
        initialTwinIds="t1"
      />,
    );
    fireEvent.click(screen.getByTestId("draft-merge-build"));
    await waitFor(() => {
      expect(screen.getByTestId("draft-merge-error")).toBeTruthy();
    });
    const el = screen.getByTestId("draft-merge-error");
    expect(el.getAttribute("data-cross-parent")).toBe("true");
    expect(el.textContent).toMatch(/Cross-parent/i);
    expect(screen.queryByTestId("draft-merge-result")).toBeNull();
  });

  it("does not render result when draftFn rejects non-provisional body", async () => {
    const draftFn = vi.fn(async () => {
      throw new Error(
        "draft-merge response rejected: provisional must be true (not final merge)",
      );
    });
    render(
      <DraftMergePanel
        draftFn={draftFn}
        initialParentId="p"
        initialTwinIds="t1"
      />,
    );
    fireEvent.click(screen.getByTestId("draft-merge-build"));
    await waitFor(() => {
      expect(screen.getByTestId("draft-merge-error").textContent).toMatch(
        /provisional must be true/,
      );
    });
    expect(screen.queryByTestId("draft-merge-result")).toBeNull();
  });

  it("shows generic error without cross-parent flag", async () => {
    const draftFn = vi.fn(async () => {
      throw new Error("network down");
    });
    render(
      <DraftMergePanel
        draftFn={draftFn}
        initialParentId="p"
        initialTwinIds="t1"
      />,
    );
    fireEvent.click(screen.getByTestId("draft-merge-build"));
    await waitFor(() => {
      expect(screen.getByTestId("draft-merge-error").textContent).toMatch(
        /network down/,
      );
    });
    expect(
      screen.getByTestId("draft-merge-error").getAttribute("data-cross-parent"),
    ).toBe("false");
  });
});
