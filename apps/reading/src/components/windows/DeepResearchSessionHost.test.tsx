import { cleanup, render, screen } from "@testing-library/react";
import { afterEach, describe, expect, it, vi } from "vitest";

import { DEEP_RESEARCH_WINDOW_KIND } from "../../workspace/deepResearchWindow";
import DeepResearchSessionHost from "./DeepResearchSessionHost";
import HostedHtmlDocumentHost from "./HostedHtmlDocumentHost";
import { WINDOW_PAGES, isWindowEligible } from "./openWindow";

vi.mock("./windowHostContext", () => ({ useInWindow: () => undefined }));
vi.mock("../engagement/TwinNotesPanel", () => ({
  TwinNotesPanel: ({ assetId }: { assetId: string }) => (
    <div data-testid="twin-notes-stub">{assetId}</div>
  ),
}));
vi.mock("../engagement/SpawnMergePanel", () => ({
  SpawnMergePanel: ({ spawnId, parentAssetId }: { spawnId: string; parentAssetId: string }) => (
    <div data-testid="spawn-merge-stub">{spawnId}→{parentAssetId}</div>
  ),
}));

describe("DeepResearchSessionHost", () => {
  afterEach(cleanup);

  it("keeps linked session, parent, selection, twin, and merge surfaces together", () => {
    render(<DeepResearchSessionHost session_id="fsess_1" spawn_id="spn_1"
      investigation_id="inv_1" parent_asset_id="book-1"
      selection_text="Selected reader passage" status="reserved" view_format="html" />);
    expect(screen.getByText("fsess_1")).toBeTruthy();
    expect(screen.getAllByText("book-1").length).toBeGreaterThan(0);
    expect(screen.getByTestId("deep-research-selection").textContent).toContain("Selected");
    expect(screen.getByTestId("twin-notes-stub").textContent).toBe("book-1");
    expect(screen.getByTestId("spawn-merge-stub").textContent).toBe("spn_1→book-1");
  });

  it("is registered as a stable window-native page", () => {
    expect(isWindowEligible(DEEP_RESEARCH_WINDOW_KIND)).toBe(true);
    expect(WINDOW_PAGES[DEEP_RESEARCH_WINDOW_KIND]?.renderer).toBeTruthy();
    expect(isWindowEligible("hosted_html_document")).toBe(true);
  });

  it("leaves missing identity visible instead of replacing the host", () => {
    render(<DeepResearchSessionHost view_format="html" />);
    expect(screen.getByText("(missing session)")).toBeTruthy();
    expect(screen.getByText("(missing parent)")).toBeTruthy();
  });
});

describe("HostedHtmlDocumentHost", () => {
  afterEach(cleanup);

  it("isolates hosted HTML in a script-disabled frame", () => {
    render(
      <HostedHtmlDocumentHost
        document_id="draft_1"
        title="Draft"
        html={'<script>window.top.pwned=true</script><p>Safe prose</p>'}
        view_format="html"
      />,
    );
    const frame = screen.getByTestId("hosted-html-body");
    expect(frame.getAttribute("sandbox")).toBe("");
    expect(frame.getAttribute("srcdoc")).toContain("Safe prose");
  });

  it("rejects non-HTML formats", () => {
    render(<HostedHtmlDocumentHost html="body" view_format="pdf" />);
    expect(screen.getByRole("alert").textContent).toMatch(/must be html/);
    expect(screen.queryByTestId("hosted-html-body")).toBeNull();
  });
});
