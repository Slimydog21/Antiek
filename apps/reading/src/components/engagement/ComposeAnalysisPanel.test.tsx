import { afterEach, describe, expect, it, vi } from "vitest";
import { cleanup, fireEvent, render, screen, waitFor } from "@testing-library/react";
import ComposeAnalysisPanel from "./ComposeAnalysisPanel";
import type { ComposeAnalysisResult } from "../../api/twinCompose";

afterEach(() => {
  cleanup();
  vi.restoreAllMocks();
});

const sample: ComposeAnalysisResult = {
  parent_asset_id: "asset-1",
  title: "Combined analysis",
  html: '<article class="antiek-twin-analysis" data-parent="asset-1"><h1>Combined analysis</h1><section><h2>Insights</h2><ul><li>a</li></ul></section></article>',
  twin_ids: ["t1", "t2"],
  insight_count: 1,
  question_count: 0,
};

describe("ComposeAnalysisPanel", () => {
  it("composes analysis via injectable composeFn", async () => {
    const composeFn = vi.fn(async () => sample);
    render(
      <ComposeAnalysisPanel
        composeFn={composeFn}
        initialTwinIds="t1, t2"
        initialTitle="Combined analysis"
        initialParentAssetId="asset-1"
      />,
    );
    fireEvent.click(screen.getByTestId("compose-analysis-run"));
    await waitFor(() => {
      expect(screen.getByTestId("compose-analysis-result")).toBeTruthy();
    });
    expect(composeFn).toHaveBeenCalledWith({
      twin_ids: ["t1", "t2"],
      title: "Combined analysis",
      parent_asset_id: "asset-1",
    });
    expect(screen.getByTestId("compose-analysis-html").textContent).toMatch(
      /antiek-twin-analysis/,
    );
    expect(screen.getByTestId("compose-analysis-meta").textContent).toMatch(
      /parent=asset-1/,
    );
    expect(screen.getByTestId("compose-analysis-title-echo").textContent).toMatch(
      /Combined analysis/,
    );
  });

  it("surfaces errors without rendering a draft result", async () => {
    const composeFn = vi.fn(async () => {
      throw new Error("cross_parent_compose_rejected");
    });
    render(
      <ComposeAnalysisPanel composeFn={composeFn} initialTwinIds="t1, t2" />,
    );
    fireEvent.click(screen.getByTestId("compose-analysis-run"));
    await waitFor(() => {
      expect(screen.getByTestId("compose-analysis-error").textContent).toMatch(
        /cross_parent/,
      );
    });
    expect(screen.queryByTestId("compose-analysis-result")).toBeNull();
  });

  it("does not render result when html validation fails", async () => {
    const composeFn = vi.fn(async () => {
      throw new Error(
        "compose analysis response rejected: html must be non-empty",
      );
    });
    render(<ComposeAnalysisPanel composeFn={composeFn} initialTwinIds="t1" />);
    fireEvent.click(screen.getByTestId("compose-analysis-run"));
    await waitFor(() => {
      expect(screen.getByTestId("compose-analysis-error").textContent).toMatch(
        /html/,
      );
    });
    expect(screen.queryByTestId("compose-analysis-result")).toBeNull();
  });

  it("rejects injectable resolving empty html without rendering success", async () => {
    const composeFn = vi.fn(async () => ({
      ...sample,
      html: "   ",
    }));
    render(<ComposeAnalysisPanel composeFn={composeFn} initialTwinIds="t1" />);
    fireEvent.click(screen.getByTestId("compose-analysis-run"));
    await waitFor(() => {
      expect(screen.getByTestId("compose-analysis-error").textContent).toMatch(
        /html/,
      );
    });
    expect(screen.queryByTestId("compose-analysis-result")).toBeNull();
  });

  it("clears stale HTML immediately when a new compose starts", async () => {
    let resolveFirst!: (v: ComposeAnalysisResult) => void;
    const first = new Promise<ComposeAnalysisResult>((r) => {
      resolveFirst = r;
    });
    const composeFn = vi
      .fn()
      .mockImplementationOnce(() => first)
      .mockImplementationOnce(async () => ({
        ...sample,
        html: "<article>second draft</article>",
        twin_ids: ["t9"],
      }));

    render(
      <ComposeAnalysisPanel composeFn={composeFn} initialTwinIds="t1, t2" />,
    );

    fireEvent.click(screen.getByTestId("compose-analysis-run"));
    resolveFirst(sample);
    await waitFor(() => {
      expect(screen.getByTestId("compose-analysis-html").textContent).toMatch(
        /antiek-twin-analysis/,
      );
    });

    // Start second compose; prior result must vanish before second resolves.
    let resolveSecond!: (v: ComposeAnalysisResult) => void;
    const second = new Promise<ComposeAnalysisResult>((r) => {
      resolveSecond = r;
    });
    composeFn.mockImplementationOnce(() => second);
    fireEvent.click(screen.getByTestId("compose-analysis-run"));
    expect(screen.queryByTestId("compose-analysis-result")).toBeNull();

    resolveSecond({
      ...sample,
      html: "<article>second draft</article>",
      twin_ids: ["t9"],
    });
    await waitFor(() => {
      expect(screen.getByTestId("compose-analysis-html").textContent).toMatch(
        /second draft/,
      );
    });
  });
});
