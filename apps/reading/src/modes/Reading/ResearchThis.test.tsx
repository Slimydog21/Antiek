import { cleanup, fireEvent, render, screen, waitFor } from "@testing-library/react";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import { MemoryRouter } from "react-router-dom";

import ResearchThis from "./ResearchThis";

const launchFloatingDeepResearch = vi.fn();
const spinResearch = vi.fn();
const navigate = vi.fn();
const hydratePublicationRefs = vi.fn();
const parsePublicationRefs = vi.fn();

vi.mock("./launchFloatingDeepResearch", () => ({
  launchFloatingDeepResearch: (...args: unknown[]) =>
    launchFloatingDeepResearch(...args),
}));

vi.mock("../ResearchWorkstation/publicationRefs", () => ({
  parsePublicationRefs: (...args: unknown[]) => parsePublicationRefs(...args),
  hydratePublicationRefs: (...args: unknown[]) => hydratePublicationRefs(...args),
  questionWithPublicationRefs: (q: string) => q,
}));

vi.mock("../../api/books", () => ({
  spinResearch: (...args: unknown[]) => spinResearch(...args),
}));

vi.mock("../../components/engagement/ResearchLaunchBudgetPanel", () => ({
  ResearchLaunchBudgetPanel: (props: {
    promptText: string;
    researchTier: string;
  }) => (
    <div
      data-testid="research-launch-budget-panel-stub"
      data-prompt-len={String(props.promptText.length)}
      data-research-tier={props.researchTier}
    >
      budget stub
    </div>
  ),
}));

vi.mock("react-router-dom", async (importOriginal) => {
  const actual = await importOriginal<typeof import("react-router-dom")>();
  return {
    ...actual,
    useNavigate: () => navigate,
  };
});

vi.mock("../../lib/analytics", () => ({
  track: vi.fn(),
}));

describe("ResearchThis residual cc/cu/cx", () => {
  beforeEach(() => {
    launchFloatingDeepResearch.mockReset();
    spinResearch.mockReset();
    navigate.mockReset();
    hydratePublicationRefs.mockReset();
    parsePublicationRefs.mockReset();
    parsePublicationRefs.mockReturnValue([]);
  });

  afterEach(() => cleanup());

  it("mounts budget projection panel before float open (cx)", () => {
    render(
      <MemoryRouter>
        <ResearchThis
          documentId="doc-1"
          pageIndex={0}
          passageText="Attention is content-addressable memory."
        />
      </MemoryRouter>,
    );
    const mount = screen.getByTestId("research-this-budget-mount");
    expect(mount).toBeTruthy();
    expect(mount.getAttribute("data-view-format")).toBe("html");
    const stub = screen.getByTestId("research-launch-budget-panel-stub");
    expect(stub.getAttribute("data-research-tier")).toBe("deep");
    expect(Number(stub.getAttribute("data-prompt-len"))).toBeGreaterThan(3);
  });

  it("opens floating deep research window from passage", async () => {
    launchFloatingDeepResearch.mockResolvedValue({
      session_id: "fsess_1",
      spawn_id: "spn_1",
      investigation_id: "inv_1",
      parent_asset_id: "doc-1",
      window_id: "wdr_fsess_1",
      view_format: "html",
      view_mode: "floating",
      status: "reserved",
    });

    render(
      <MemoryRouter>
        <ResearchThis
          documentId="doc-1"
          pageIndex={0}
          passageText="Attention is content-addressable memory."
        />
      </MemoryRouter>,
    );

    fireEvent.click(screen.getByTestId("research-this-floating"));
    await waitFor(() => {
      expect(launchFloatingDeepResearch).toHaveBeenCalled();
    });
    const call = launchFloatingDeepResearch.mock.calls.at(-1)?.[0] as {
      asset_id: string;
      selection_text: string;
      view_mode: string;
    };
    expect(call.asset_id).toBe("doc-1");
    expect(call.selection_text).toMatch(/Attention/);
    expect(call.view_mode).toBe("floating");
    await waitFor(() => {
      expect(screen.getByTestId("research-this-window-id").textContent).toMatch(
        /wdr_fsess_1/,
      );
    });
  });

  it("hydrates pub refs and passes references to floating launch (cu)", async () => {
    parsePublicationRefs.mockReturnValue(["arxiv:1706.03762"]);
    hydratePublicationRefs.mockResolvedValue({
      ok: [{ asset_id: "pub_1", view_format: "html" }],
      failed: [],
      view_format: "html",
    });
    launchFloatingDeepResearch.mockResolvedValue({
      session_id: "fsess_2",
      spawn_id: "spn_2",
      investigation_id: "inv_2",
      parent_asset_id: "doc-1",
      window_id: "wdr_fsess_2",
      view_format: "html",
      view_mode: "floating",
      status: "reserved",
    });

    render(
      <MemoryRouter>
        <ResearchThis documentId="doc-1" pageIndex={0} passageText="hello world" />
      </MemoryRouter>,
    );
    expect(screen.getByTestId("research-this-pub-refs")).toBeTruthy();
    fireEvent.change(screen.getByTestId("research-this-refs-input"), {
      target: { value: "arxiv:1706.03762" },
    });
    fireEvent.click(screen.getByTestId("research-this-floating"));
    await waitFor(() => {
      expect(hydratePublicationRefs).toHaveBeenCalledWith(["arxiv:1706.03762"]);
    });
    await waitFor(() => {
      expect(launchFloatingDeepResearch).toHaveBeenCalledWith(
        expect.objectContaining({
          references: ["arxiv:1706.03762"],
          view_mode: "floating",
        }),
      );
    });
    await waitFor(() => {
      expect(screen.getByTestId("research-this-refs-status").textContent).toMatch(
        /Hydrated 1/,
      );
    });
  });

  it("full workstation path still navigates via spinResearch", async () => {
    spinResearch.mockResolvedValue({ investigation_id: "inv_full" });
    render(
      <MemoryRouter>
        <ResearchThis documentId="doc-1" pageIndex={0} passageText="hello world" />
      </MemoryRouter>,
    );
    fireEvent.click(screen.getByTestId("research-this-full"));
    await waitFor(() => {
      expect(spinResearch).toHaveBeenCalledWith("doc-1", 0, "hello world");
    });
    expect(navigate).toHaveBeenCalledWith("/inv/inv_full");
  });
});
