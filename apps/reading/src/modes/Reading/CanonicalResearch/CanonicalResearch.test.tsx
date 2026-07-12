import { cleanup, fireEvent, render, screen } from "@testing-library/react";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";

import CanonicalResearch from "./index";

const { getCanonicalMergeHtml, navigate } = vi.hoisted(() => ({
  getCanonicalMergeHtml: vi.fn(),
  navigate: vi.fn(),
}));

vi.mock("../../../api/engagement", () => ({
  getCanonicalMergeHtml,
}));

vi.mock("react-router-dom", () => ({
  useNavigate: () => navigate,
  useParams: () => ({ deliverableId: "dlv-canonical-reading" }),
}));

beforeEach(() => {
  getCanonicalMergeHtml.mockResolvedValue({
    deliverable_id: "dlv-canonical-reading",
    section_id: "sec-canonical",
    revision: "b".repeat(64),
    draft_sha256: "a".repeat(64),
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
    expect(getCanonicalMergeHtml).toHaveBeenCalledWith("dlv-canonical-reading");
    expect(authority.textContent).toContain("a".repeat(64));
    expect(authority.textContent).toContain("b".repeat(64));
    const html = screen.getByTestId("canonical-research-html");
    expect(html.textContent).toContain("Exact canonical research");
    expect(html.innerHTML).not.toContain("<script");
    fireEvent.click(screen.getByRole("button", { name: /open canonical in write/i }));
    expect(navigate).toHaveBeenCalledWith("/write/dlv-canonical-reading");
  });

  it("surfaces reload failure without fallback HTML", async () => {
    getCanonicalMergeHtml.mockRejectedValueOnce(
      new Error("engagement API 409: canonical reviewed research has drifted"),
    );
    render(<CanonicalResearch />);
    expect((await screen.findByRole("alert")).textContent).toMatch(/409.*drifted/i);
    expect(screen.queryByTestId("canonical-research-html")).toBeNull();
  });
});
