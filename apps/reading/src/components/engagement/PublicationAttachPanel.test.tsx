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
    // Residual (agx): knowledge-dense quick-call presets insert without hydrate.
    const panel = screen.getByTestId("publication-attach-panel");
    expect(panel.getAttribute("data-seamless-pub-quick-call")).toBe("true");
    expect(Number(panel.getAttribute("data-knowledge-dense-presets"))).toBeGreaterThanOrEqual(
      4,
    );
    const presets = screen.getByTestId("publication-quick-call-presets");
    expect(presets.getAttribute("data-auto-hydrate")).toBe("false");
    expect(presets.getAttribute("data-seamless-pub-quick-call")).toBe("true");
    expect(
      screen.getByTestId("publication-preset-attention-is-all-you-need"),
    ).toBeTruthy();
    fireEvent.click(
      screen.getByTestId("publication-preset-attention-is-all-you-need"),
    );
    expect(
      (screen.getByTestId("publication-attach-input") as HTMLTextAreaElement)
        .value,
    ).toMatch(/arxiv:1706\.03762/);
    // Preset click must not auto-hydrate.
    expect(attachSourceRefs).not.toHaveBeenCalled();
    expect(hydratePublicationRef).not.toHaveBeenCalled();
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
    // Residual (rc): Open Write twin_seed from hydrated publications.
    const write = screen.getByTestId("publication-attach-open-write");
    const href = write.getAttribute("href") || "";
    expect(href).toMatch(/^\/write\?twin_seed=antiek\.twin_write_seed\./);
    expect(href).not.toMatch(/html_draft=/);
    expect(write.getAttribute("data-has-twin-seed")).toBe("1");
    expect(write.getAttribute("data-hydrated-count")).toBe("1");
    // Residual (acs): body_text/HTML body → has-body true.
    expect(write.getAttribute("data-write-seed-has-body")).toBe("true");
    expect(
      screen.getByTestId("publication-attach-panel").getAttribute("data-view-format"),
    ).toBe("html");
    // Residual (ia): Settings deep-link for hydrate readiness.
    const settings = screen.getByTestId("publication-attach-settings-link");
    expect(settings.getAttribute("href")).toBe("/settings#hydrate-live-status");
    expect(settings.textContent).toMatch(/hydrate readiness/i);
    // Residual (mj): dual-gate checklist link (prep only; never enables injectors).
    const dual = screen.getByTestId("publication-attach-dual-gate-checklist-link");
    // Residual (xc): L1 arxiv checklist section deep-link.
    expect(dual.getAttribute("href")).toMatch(/DUAL-GATE-L1-L4.*#l1-arxiv/);
    expect(dual.textContent).toMatch(/L1 arxiv checklist/i);
    // Residual (aap): L2 Substack checklist (parity aal–aao).
    const dualL2 = screen.getByTestId("publication-attach-dual-gate-l2-link");
    expect(dualL2.getAttribute("href")).toMatch(/DUAL-GATE-L1-L4.*#l2-substack/);
    expect(dualL2.textContent).toMatch(/L2 Substack checklist/i);
    // Residual (ajc): knowledge-dense attach → competitive DR honesty map.
    expect(
      screen
        .getByTestId("publication-attach-competitive-scorecard-link")
        .getAttribute("href"),
    ).toBe("/settings#settings-competitive-dr-scorecard");
    expect(
      screen
        .getByTestId("publication-attach-competitive-dr-future-agent-link")
        .getAttribute("href") || "",
    ).toMatch(/FUTURE-AGENT-SPEC-competitive-deep-research-quality/);
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
    const trust = screen.getByTestId("publication-attach-citation-trust");
    expect(trust.textContent).toMatch(/grounded/i);
    // Residual (vb): grounded attach still deep-links hydrate maintain-prep.
    expect(trust.getAttribute("data-citation-trust")).toBe("grounded");
    expect(trust.getAttribute("data-offline-hydrate-default")).toBe("true");
    expect(
      screen
        .getByTestId("publication-attach-hydrate-settings-link")
        .getAttribute("href"),
    ).toBe("/settings#hydrate-live-status");
    expect(
      screen
        .getByTestId("publication-attach-hydrate-dual-gate-link")
        .getAttribute("href") || "",
    ).toMatch(/DUAL-GATE-L1-L4.*#l1-arxiv/);
    expect(
      screen
        .getByTestId("publication-attach-hydrate-dual-gate-l2-link")
        .getAttribute("href") || "",
    ).toMatch(/DUAL-GATE-L1-L4.*#l2-substack/);
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

  it("surfaces hydrate prep links when attach ungrounded (uq)", async () => {
    attachSourceRefs.mockResolvedValue({
      spawn_id: "spn_ug",
      source_references: [{ kind: "arxiv", raw: "arxiv:broken" }],
      research_tier: "deep",
      view_format: "html",
    });
    hydratePublicationRef.mockRejectedValue(new Error("hydrate failed"));
    render(<PublicationAttachPanel spawnId="spn_ug" />);
    fireEvent.change(screen.getByTestId("publication-attach-input"), {
      target: { value: "arxiv:broken" },
    });
    fireEvent.click(screen.getByTestId("publication-attach-submit"));
    await waitFor(() => {
      expect(screen.getByTestId("publication-attach-result")).toBeTruthy();
    });
    const trust = screen.getByTestId("publication-attach-citation-trust");
    expect(trust.getAttribute("data-citation-trust")).toBe("ungrounded");
    expect(trust.getAttribute("data-offline-hydrate-default")).toBe("true");
    expect(trust.textContent).toMatch(/ungrounded/i);
    expect(
      screen
        .getByTestId("publication-attach-hydrate-settings-link")
        .getAttribute("href"),
    ).toBe("/settings#hydrate-live-status");
    expect(
      screen
        .getByTestId("publication-attach-hydrate-dual-gate-link")
        .getAttribute("href") || "",
    ).toMatch(/DUAL-GATE-L1-L4/);
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
