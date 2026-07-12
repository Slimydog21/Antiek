import { cleanup, fireEvent, render, screen } from "@testing-library/react";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";

import CanonicalResearch from "./index";

const { getCanonicalMergeHtml, navigate, route } = vi.hoisted(() => ({
  getCanonicalMergeHtml: vi.fn(),
  navigate: vi.fn(),
  route: { deliverableId: "project/a %?#/مرحبا" },
}));

vi.mock("../../../api/engagement", () => ({
  getCanonicalMergeHtml,
}));

vi.mock("react-router-dom", () => ({
  useNavigate: () => navigate,
  useParams: () => ({ deliverableId: route.deliverableId }),
}));

vi.mock("../../../components/engagement/TwinNotesPanel", () => ({
  TwinNotesPanel: (props: {
    assetId: string;
    autoLoad?: boolean;
    autoPromoteAfterLoad?: boolean;
    onPromoted?: () => void;
  }) => (
    <button
      type="button"
      data-testid="canonical-twins-stub"
      data-asset-id={props.assetId}
      data-auto-load={String(props.autoLoad)}
      data-auto-promote={String(props.autoPromoteAfterLoad)}
      onClick={() => props.onPromoted?.()}
    >
      promote twins
    </button>
  ),
}));

vi.mock("../../../components/engagement/ResearchContextPanel", () => ({
  ResearchContextPanel: (props: { assetId: string; autoLoad?: boolean }) => (
    <div
      data-testid="canonical-context-stub"
      data-asset-id={props.assetId}
      data-auto-load={String(props.autoLoad)}
    />
  ),
}));

beforeEach(() => {
  getCanonicalMergeHtml.mockResolvedValue({
    deliverable_id: route.deliverableId,
    section_id: "sec-canonical",
    revision: "b".repeat(64),
    draft_sha256: "a".repeat(64),
    twin_note_count: 2,
    view_format: "html",
    html: "<article><p>Exact canonical research</p><script>bad()</script></article>",
  });
});

afterEach(() => {
  cleanup();
  vi.clearAllMocks();
});

describe("CanonicalResearch", () => {
  it("reloads exact canonical HTML authority and opens the same deliverable in Write", async () => {
    render(<CanonicalResearch />);
    const authority = await screen.findByTestId("canonical-research-authority");
    expect(getCanonicalMergeHtml).toHaveBeenCalledWith(route.deliverableId);
    expect(authority.textContent).toContain("a".repeat(64));
    expect(authority.textContent).toContain("b".repeat(64));
    const html = screen.getByTestId("canonical-research-html");
    expect(html.textContent).toContain("Exact canonical research");
    expect(html.innerHTML).not.toContain("<script");
    const twins = screen.getByTestId("canonical-twins-stub");
    const context = screen.getByTestId("canonical-context-stub");
    expect(twins.getAttribute("data-asset-id")).toBe(route.deliverableId);
    expect(twins.getAttribute("data-auto-load")).toBe("true");
    expect(twins.getAttribute("data-auto-promote")).toBe("true");
    expect(context.getAttribute("data-asset-id")).toBe(route.deliverableId);
    expect(context.getAttribute("data-auto-load")).toBe("true");
    expect(
      screen.getByTestId("canonical-research-context-mount").getAttribute(
        "data-refresh-key",
      ),
    ).toBe("0");
    fireEvent.click(twins);
    expect(
      screen.getByTestId("canonical-research-context-mount").getAttribute(
        "data-refresh-key",
      ),
    ).toBe("1");
    fireEvent.click(screen.getByRole("button", { name: /open canonical in write/i }));
    expect(navigate).toHaveBeenCalledWith(
      `/write/${encodeURIComponent(route.deliverableId)}`,
    );
  });

  it("surfaces reload failure without fallback HTML", async () => {
    getCanonicalMergeHtml.mockRejectedValueOnce(
      new Error("engagement API 409: canonical reviewed research has drifted"),
    );
    render(<CanonicalResearch />);
    expect((await screen.findByRole("alert")).textContent).toMatch(/409.*drifted/i);
    expect(screen.queryByTestId("canonical-research-html")).toBeNull();
    expect(screen.queryByTestId("canonical-twins-stub")).toBeNull();
    expect(screen.queryByTestId("canonical-context-stub")).toBeNull();
  });
});
