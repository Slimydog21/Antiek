import { describe, expect, it, vi, afterEach, beforeEach } from "vitest";
import { cleanup, fireEvent, render, screen, waitFor } from "@testing-library/react";

import HostedHtmlDocumentHost, {
  resolveHostedResearchSelection,
} from "./HostedHtmlDocumentHost";

const launchFloatingDeepResearch = vi.fn();

vi.mock("./windowHostContext", () => ({
  useInWindow: () => undefined,
}));

vi.mock("../../modes/Reading/launchFloatingDeepResearch", () => ({
  launchFloatingDeepResearch: (...args: unknown[]) =>
    launchFloatingDeepResearch(...args),
}));

vi.mock("../engagement/TwinNotesPanel", () => ({
  TwinNotesPanel: (props: { assetId: string }) => (
    <div data-testid="twin-notes-panel-stub">{props.assetId}</div>
  ),
}));

vi.mock("../engagement/ResearchContextPanel", () => ({
  ResearchContextPanel: (props: { assetId: string; autoLoad?: boolean }) => (
    <div data-testid="research-context-panel-stub">
      {props.assetId}:auto={String(Boolean(props.autoLoad))}
    </div>
  ),
}));

vi.mock("../engagement/ResearchLaunchBudgetPanel", () => {
  const React = require("react") as typeof import("react");
  return {
    ResearchLaunchBudgetPanel: (props: {
      promptText: string;
      researchTier: string;
      onProjectionChange?: (p: {
        wouldExceedBudget: boolean | null;
        pricingKnown: boolean;
        estimatedUsdHigh: number | null;
        remainingUsd: number | null;
        modelId: string | null;
      }) => void;
    }) => {
      React.useEffect(() => {
        props.onProjectionChange?.({
          wouldExceedBudget: false,
          pricingKnown: true,
          estimatedUsdHigh: 0.1,
          remainingUsd: 5,
          modelId: null,
        });
      }, [props.onProjectionChange]);
      return (
        <div
          data-testid="research-launch-budget-panel-stub"
          data-research-tier={props.researchTier}
          data-prompt-len={String(props.promptText.length)}
        >
          budget
        </div>
      );
    },
  };
});

vi.mock("../engagement/DecisionTreeDriverBadge", () => ({
  DecisionTreeDriverBadge: () => (
    <div data-testid="decision-tree-driver-badge-stub">driver</div>
  ),
}));

describe("HostedHtmlDocumentHost residual bt/bw/cv/da", () => {
  afterEach(() => cleanup());
  beforeEach(() => {
    launchFloatingDeepResearch.mockReset();
  });

  it("renders HTML body for hosted book", () => {
    render(
      <HostedHtmlDocumentHost
        document_id="doc_abc"
        title="Attention Is All You Need"
        view_format="html"
        license_class="public_domain"
        html="<article><h1>Attention</h1><p>Transformers.</p></article>"
      />,
    );
    expect(screen.getByTestId("hosted-html-document-host").getAttribute(
      "data-view-format",
    )).toBe("html");
    expect(screen.getByTestId("hosted-html-body").innerHTML).toMatch(
      /Attention/,
    );
    expect(screen.getByTestId("hosted-html-document-host").textContent).toMatch(
      /not PDF/,
    );
  });

  it("mounts twin notes + research context for document_id (bw/cv)", () => {
    render(
      <HostedHtmlDocumentHost
        document_id="hdoc_xyz"
        title="Pride"
        view_format="html"
        html="<p>It is a truth</p>"
      />,
    );
    expect(screen.getByTestId("hosted-html-twins-mount")).toBeTruthy();
    expect(screen.getByTestId("twin-notes-panel-stub").textContent).toMatch(
      /hdoc_xyz/,
    );
    expect(screen.getByTestId("hosted-html-context-mount")).toBeTruthy();
    expect(screen.getByTestId("research-context-panel-stub").textContent).toMatch(
      /hdoc_xyz:auto=true/,
    );
  });

  it("mounts driver badge + budget + deep research launch (da)", async () => {
    launchFloatingDeepResearch.mockResolvedValue({
      session_id: "fsess_h",
      spawn_id: "spn_h",
      investigation_id: "inv_h",
      parent_asset_id: "doc_host",
      window_id: "wdr_host_1",
      view_format: "html",
      view_mode: "floating",
      status: "reserved",
      model_id: "claude-opus-4-8",
    });

    render(
      <HostedHtmlDocumentHost
        document_id="doc_host"
        title="Hosted Book"
        view_format="html"
        html="<p>Body</p>"
      />,
    );

    expect(screen.getByTestId("decision-tree-driver-badge-stub")).toBeTruthy();
    const launch = screen.getByTestId("hosted-html-research-launch");
    expect(launch.getAttribute("data-view-format")).toBe("html");
    const budget = screen.getByTestId("research-launch-budget-panel-stub");
    expect(budget.getAttribute("data-research-tier")).toBe("deep");
    expect(Number(budget.getAttribute("data-prompt-len"))).toBeGreaterThan(3);

    fireEvent.click(screen.getByTestId("hosted-html-deep-research"));
    await waitFor(() => {
      expect(launchFloatingDeepResearch).toHaveBeenCalledWith(
        expect.objectContaining({
          asset_id: "doc_host",
          view_mode: "floating",
        }),
      );
    });
    const call = launchFloatingDeepResearch.mock.calls.at(-1)?.[0] as {
      selection_text: string;
      goal_hint: string;
    };
    expect(call.selection_text).toMatch(/Hosted Book/);
    expect(call.goal_hint).toMatch(/Hosted Book/);
    await waitFor(() => {
      expect(
        screen.getByTestId("hosted-html-research-window-id").textContent,
      ).toMatch(/wdr_host_1/);
    });
  });

  it("rejects non-html view_format", () => {
    render(
      <HostedHtmlDocumentHost
        document_id="doc_x"
        view_format="pdf"
        html="%PDF-1.4"
      />,
    );
    expect(screen.getByTestId("hosted-html-reject-pdf")).toBeTruthy();
    expect(screen.queryByTestId("hosted-html-research-launch")).toBeNull();
  });

  it("resolveHostedResearchSelection prefers highlight (en)", () => {
    const hit = resolveHostedResearchSelection({
      title: "Book",
      assetId: "doc_1",
      fallbackDocId: "doc_1",
      highlightText: "  attention is all you need  ",
    });
    expect(hit.from_highlight).toBe(true);
    expect(hit.selection_text).toBe("attention is all you need");
    const miss = resolveHostedResearchSelection({
      title: "Book",
      assetId: "doc_1",
      fallbackDocId: "doc_1",
      highlightText: "   ",
    });
    expect(miss.from_highlight).toBe(false);
    expect(miss.selection_text).toMatch(/Deep-research hosted document: Book/);
  });

  it("uses window selection for deep research when highlighted (en)", async () => {
    launchFloatingDeepResearch.mockResolvedValue({
      session_id: "fsess_sel",
      spawn_id: "spn_sel",
      investigation_id: "inv_sel",
      parent_asset_id: "doc_sel",
      window_id: "wdr_sel",
      view_format: "html",
      view_mode: "floating",
      status: "reserved",
      model_id: null,
    });
    const getSelection = vi.fn(() => ({
      toString: () => "Transformers changed NLP forever",
    }));
    vi.stubGlobal("getSelection", getSelection);

    render(
      <HostedHtmlDocumentHost
        document_id="doc_sel"
        title="Attention"
        view_format="html"
        html="<p>Transformers changed NLP forever in 2017.</p>"
      />,
    );

    expect(
      screen.getByTestId("hosted-html-research-launch").getAttribute(
        "data-from-highlight",
      ),
    ).toBe("false");

    fireEvent.mouseUp(screen.getByTestId("hosted-html-body"));
    await waitFor(() => {
      expect(
        screen.getByTestId("hosted-html-selection-preview").getAttribute(
          "data-from-highlight",
        ),
      ).toBe("true");
    });
    expect(screen.getByTestId("hosted-html-selection-text").textContent).toMatch(
      /Transformers changed NLP forever/,
    );

    fireEvent.click(screen.getByTestId("hosted-html-deep-research"));
    await waitFor(() => {
      expect(launchFloatingDeepResearch).toHaveBeenCalledWith(
        expect.objectContaining({
          asset_id: "doc_sel",
          selection_text: "Transformers changed NLP forever",
          view_mode: "floating",
        }),
      );
    });
    const call = launchFloatingDeepResearch.mock.calls.at(-1)?.[0] as {
      goal_hint: string;
    };
    expect(call.goal_hint).toMatch(/highlighted passage/i);

    fireEvent.click(screen.getByTestId("hosted-html-clear-highlight"));
    await waitFor(() => {
      expect(
        screen.getByTestId("hosted-html-selection-preview").getAttribute(
          "data-from-highlight",
        ),
      ).toBe("false");
    });

    vi.unstubAllGlobals();
  });
});
