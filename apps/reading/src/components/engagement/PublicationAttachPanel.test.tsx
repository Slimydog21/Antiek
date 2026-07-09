import { cleanup, fireEvent, render, screen, waitFor } from "@testing-library/react";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";

import { PublicationAttachPanel } from "./PublicationAttachPanel";

const attachSourceRefs = vi.fn();
const hydratePublicationRef = vi.fn();

vi.mock("../../api/engagement", () => ({
  attachSourceRefs: (...args: unknown[]) => attachSourceRefs(...args),
  hydratePublicationRef: (...args: unknown[]) => hydratePublicationRef(...args),
}));

describe("PublicationAttachPanel residual ck", () => {
  afterEach(() => cleanup());
  beforeEach(() => {
    attachSourceRefs.mockReset();
    hydratePublicationRef.mockReset();
  });

  it("attaches refs to spawn and hydrates HTML assets", async () => {
    attachSourceRefs.mockResolvedValue({
      spawn_id: "spn_1",
      source_references: [{ kind: "arxiv", raw: "arxiv:1706.03762" }],
      view_format: "html",
    });
    hydratePublicationRef.mockResolvedValue({
      asset_id: "pub_arxiv_abc",
      ref: { kind: "arxiv", raw: "arxiv:1706.03762" },
      title: "Attention Is All You Need",
      body_text: "…",
      fetched: false,
      view_format: "html",
      notes: [],
      product_panel: "engagement_hydrate",
      source: "test",
      html: "<p>Attention</p>",
    });

    render(<PublicationAttachPanel spawnId="spn_1" />);
    fireEvent.change(screen.getByTestId("publication-attach-input"), {
      target: { value: "arxiv:1706.03762" },
    });
    fireEvent.click(screen.getByTestId("publication-attach-submit"));

    await waitFor(() => {
      expect(attachSourceRefs).toHaveBeenCalledWith("spn_1", [
        "arxiv:1706.03762",
      ]);
    });
    await waitFor(() => {
      expect(hydratePublicationRef).toHaveBeenCalledWith({
        reference: "arxiv:1706.03762",
        include_html: true,
        attach_spawn_id: "spn_1",
      });
    });
    await waitFor(() => {
      expect(screen.getByTestId("publication-attach-result").textContent).toMatch(
        /pub_arxiv_abc/,
      );
    });
    expect(
      screen.getByTestId("publication-attach-panel").getAttribute("data-view-format"),
    ).toBe("html");
  });

  it("surfaces attach failure honestly", async () => {
    attachSourceRefs.mockRejectedValue(new Error("spawn unknown"));
    render(<PublicationAttachPanel spawnId="spn_x" />);
    fireEvent.change(screen.getByTestId("publication-attach-input"), {
      target: { value: "arxiv:1" },
    });
    fireEvent.click(screen.getByTestId("publication-attach-submit"));
    await waitFor(() => {
      expect(screen.getByRole("alert").textContent).toMatch(/spawn unknown/);
    });
  });
});
