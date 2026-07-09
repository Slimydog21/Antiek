import { cleanup, fireEvent, render, screen, waitFor } from "@testing-library/react";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";

import { PublicationAttachPanel } from "./PublicationAttachPanel";

const attachSourceRefs = vi.fn();
const hydratePublicationRef = vi.fn();

vi.mock("../../api/engagement", () => ({
  attachSourceRefs: (...args: unknown[]) => attachSourceRefs(...args),
  hydratePublicationRef: (...args: unknown[]) => hydratePublicationRef(...args),
}));

vi.mock("./DecisionTreeDriverBadge", () => ({
  DecisionTreeDriverBadge: (props: {
    researchTier?: string | null;
  }) => (
    <div
      data-testid="decision-tree-driver-badge-stub"
      data-research-tier={props.researchTier || ""}
    >
      driver · tier={props.researchTier || "none"}
    </div>
  ),
}));

describe("PublicationAttachPanel residual ck/ed", () => {
  afterEach(() => cleanup());
  beforeEach(() => {
    attachSourceRefs.mockReset();
    hydratePublicationRef.mockReset();
  });

  it("attaches refs to spawn and hydrates HTML assets", async () => {
    attachSourceRefs.mockResolvedValue({
      spawn_id: "spn_1",
      source_references: [{ kind: "arxiv", raw: "arxiv:1706.03762" }],
      research_tier: "wrestle",
      view_format: "html",
    });
    hydratePublicationRef.mockResolvedValue({
      asset_id: "pub_arxiv_abc",
      ref: { kind: "arxiv", raw: "arxiv:1706.03762" },
      title: "Attention Is All You Need",
      body_text: "…",
      fetched: false,
      offline_honest: true,
      view_format: "html",
      notes: [],
      product_panel: "engagement_hydrate",
      source: "test",
      html: "<p>Attention</p>",
    });

    const onAttached = vi.fn();
    render(
      <PublicationAttachPanel spawnId="spn_1" onAttached={onAttached} />,
    );
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
    // Residual (ia): Settings deep-link for hydrate readiness.
    const settings = screen.getByTestId("publication-attach-settings-link");
    expect(settings.getAttribute("href")).toBe("/settings");
    expect(settings.textContent).toMatch(/hydrate readiness/i);
    // Residual (ed): parent notified so research context can remount.
    await waitFor(() => {
      expect(onAttached).toHaveBeenCalled();
    });
    const payload = onAttached.mock.calls[0][0] as {
      spawnId: string;
      references: string[];
      view_format: string;
      hydrated: Array<{ asset_id: string }>;
    };
    expect(payload.spawnId).toBe("spn_1");
    expect(payload.view_format).toBe("html");
    expect(payload.references).toEqual(["arxiv:1706.03762"]);
    expect(payload.hydrated[0].asset_id).toBe("pub_arxiv_abc");
    // Residual (ef): citation trust honesty after attach.
    expect(
      screen
        .getByTestId("publication-attach-result")
        .getAttribute("data-citation-trust"),
    ).toBe("grounded");
    expect(
      screen.getByTestId("publication-attach-citation-trust").textContent,
    ).toMatch(/grounded/i);
    // Residual (hz): machine-readable attach+hydrate metrics.
    const metrics = screen.getByTestId("publication-attach-metrics");
    expect(metrics.getAttribute("data-attached-count")).toBe("1");
    expect(metrics.getAttribute("data-hydrated-count")).toBe("1");
    // Residual (ko): spawn research_tier from attach-refs response.
    expect(metrics.getAttribute("data-research-tier")).toBe("wrestle");
    expect(
      screen
        .getByTestId("publication-attach-result")
        .getAttribute("data-research-tier"),
    ).toBe("wrestle");
    expect(
      screen.getByTestId("publication-attach-research-tier").textContent,
    ).toMatch(/wrestle/i);
    expect(
      screen.getByTestId("publication-attach-research-tier").textContent,
    ).toMatch(/long-horizon/i);
    expect(metrics.getAttribute("data-offline-honest-count")).toBe("1");
    expect(metrics.getAttribute("data-citation-trust")).toBe("grounded");
    expect(metrics.getAttribute("data-view-format")).toBe("html");
    expect(metrics.textContent).toMatch(/Publication attach/);
    // Residual (hc): offline-honest identity path surfaced.
    expect(
      screen
        .getByTestId("publication-attach-result")
        .getAttribute("data-offline-honest-count"),
    ).toBe("1");
    expect(
      screen.getByTestId("publication-attach-offline-honest").textContent,
    ).toMatch(/offline-honest identity/i);
    expect(
      screen
        .getByTestId("publication-attach-asset-pub_arxiv_abc")
        .getAttribute("data-offline-honest"),
    ).toBe("true");
    expect(
      screen.getByTestId("publication-attach-asset-pub_arxiv_abc").textContent,
    ).toMatch(/offline-honest/);
  });

  it("surfaces injector-backed hydrate as not offline-honest (hc)", async () => {
    attachSourceRefs.mockResolvedValue({
      spawn_id: "spn_2",
      source_references: [{ kind: "arxiv", raw: "arxiv:1706.03762" }],
      view_format: "html",
    });
    hydratePublicationRef.mockResolvedValue({
      asset_id: "pub_arxiv_live",
      ref: { kind: "arxiv", raw: "arxiv:1706.03762" },
      title: "Attention Is All You Need",
      body_text: "We propose the Transformer…",
      fetched: true,
      offline_honest: false,
      view_format: "html",
      notes: ["Body landed via injectable fetch_publication."],
      product_panel: "engagement_hydrate",
      source: "test",
      html: "<p>Transformer</p>",
    });
    render(<PublicationAttachPanel spawnId="spn_2" />);
    fireEvent.change(screen.getByTestId("publication-attach-input"), {
      target: { value: "arxiv:1706.03762" },
    });
    fireEvent.click(screen.getByTestId("publication-attach-submit"));
    await waitFor(() => {
      expect(
        screen.getByTestId("publication-attach-offline-honest").textContent,
      ).toMatch(/injector body landed/i);
    });
    expect(
      screen
        .getByTestId("publication-attach-result")
        .getAttribute("data-offline-honest-count"),
    ).toBe("0");
    expect(
      screen
        .getByTestId("publication-attach-asset-pub_arxiv_live")
        .getAttribute("data-offline-honest"),
    ).toBe("false");
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

  it("mounts driver badge and prefers prop researchTier (lz)", async () => {
    attachSourceRefs.mockResolvedValue({
      spawn_id: "spn_lz",
      source_references: [{ kind: "arxiv", raw: "arxiv:1706.03762" }],
      research_tier: "fast",
      view_format: "html",
    });
    hydratePublicationRef.mockResolvedValue({
      asset_id: "pub_lz",
      ref: { kind: "arxiv", raw: "arxiv:1706.03762" },
      title: "T",
      body_text: "…",
      fetched: false,
      offline_honest: true,
      view_format: "html",
      notes: [],
      product_panel: "engagement_hydrate",
      source: "test",
      html: "<p>t</p>",
    });
    render(
      <PublicationAttachPanel spawnId="spn_lz" researchTier="wrestle" />,
    );
    // Before attach: prop tier on badge.
    expect(
      screen.getByTestId("publication-attach-driver-badge-mount"),
    ).toBeTruthy();
    expect(
      screen
        .getByTestId("decision-tree-driver-badge-stub")
        .getAttribute("data-research-tier"),
    ).toBe("wrestle");
    expect(
      screen
        .getByTestId("publication-attach-panel")
        .getAttribute("data-research-tier"),
    ).toBe("wrestle");
    fireEvent.change(screen.getByTestId("publication-attach-input"), {
      target: { value: "arxiv:1706.03762" },
    });
    fireEvent.click(screen.getByTestId("publication-attach-submit"));
    await waitFor(() => {
      expect(screen.getByTestId("publication-attach-result")).toBeTruthy();
    });
    // Prop still wins over attach response "fast".
    expect(
      screen
        .getByTestId("decision-tree-driver-badge-stub")
        .getAttribute("data-research-tier"),
    ).toBe("wrestle");
    expect(
      screen
        .getByTestId("publication-attach-metrics")
        .getAttribute("data-research-tier"),
    ).toBe("wrestle");
  });

  it("falls back to attach response research_tier when prop absent (lz)", async () => {
    attachSourceRefs.mockResolvedValue({
      spawn_id: "spn_fb",
      source_references: [{ kind: "arxiv", raw: "arxiv:1" }],
      research_tier: "deep",
      view_format: "html",
    });
    hydratePublicationRef.mockResolvedValue({
      asset_id: "pub_fb",
      ref: { kind: "arxiv", raw: "arxiv:1" },
      title: "T",
      body_text: "…",
      fetched: false,
      offline_honest: true,
      view_format: "html",
      notes: [],
      product_panel: "engagement_hydrate",
      source: "test",
      html: "<p>t</p>",
    });
    render(<PublicationAttachPanel spawnId="spn_fb" />);
    fireEvent.change(screen.getByTestId("publication-attach-input"), {
      target: { value: "arxiv:1" },
    });
    fireEvent.click(screen.getByTestId("publication-attach-submit"));
    await waitFor(() => {
      expect(
        screen
          .getByTestId("decision-tree-driver-badge-stub")
          .getAttribute("data-research-tier"),
      ).toBe("deep");
    });
  });
});
