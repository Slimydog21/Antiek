import { afterEach, describe, expect, it, vi } from "vitest";
import { cleanup, render, screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";

import type { OutlineBlockView } from "./writeApi";
import Xray, { splitParagraphs } from "./Xray";
import type { ParagraphProvenanceStatus, ProseProvenanceValidity } from "../../lib/api";

/**
 * Xray.test — the paragraph ↔ blocks provenance view (SPR-09 M3).
 *
 * Mechanically checked:
 *  - paragraph → its blocks (click a paragraph, see its driving blocks);
 *  - block → every paragraph using it (rigor #3b: one block in MANY paragraphs,
 *    the "click block → uses" list is complete);
 *  - a paragraph with ZERO blocks is flagged unsupported, never silently
 *    presented as sourced (rigor #3a — §9 no-fabrication carried into the X-ray);
 *  - the drag-in-X-ray / regenerate gesture hands the host the affected
 *    paragraph's index (the host re-drafts that paragraph's SECTION — scope is
 *    the host's concern; here we verify only the index contract, not the scope).
 */

// getTraceTarget is the only writeApi call Xray makes (block → source chain).
vi.mock("./writeApi", async (orig) => ({
  ...(await orig<typeof import("./writeApi")>()),
  getTraceTarget: vi.fn().mockResolvedValue({
    kind: "document", full_text_allowed: true, document_id: "doc-1",
    document_title: "Source Book", chunk_ids: ["c1"], servability_status: "servable", detail: null,
  }),
}));

const NODE = "a1b2c3d4e5f60718293a4b5c6d7e8f90";

function block(over: Partial<OutlineBlockView> = {}): OutlineBlockView {
  return {
    outline_block_id: "oblk-1", section_id: "sec-1", block_kind: "insight",
    provenance_kind: "graph_node", node_id: NODE, content: null,
    node_label: "Capital intensity rises with scale", block_index: 0,
    is_user_originated: false, ...over,
  };
}

function validity(...statuses: ParagraphProvenanceStatus[]): ProseProvenanceValidity {
  return {
    schema_version: 1,
    prose_sha256: "test",
    status: statuses.every((status) => status === "current") ? "current" : "partial",
    paragraphs: Object.fromEntries(
      statuses.map((status, index) => [
        String(index),
        { text_sha256: `p${index}`, status, origin: "generated" },
      ]),
    ),
  };
}

afterEach(cleanup);

describe("Xray — paragraph↔blocks over persisted provenance", () => {
  it("splits prose the substrate's way (blank line)", () => {
    expect(splitParagraphs("a\n\nb\n\n\nc")).toEqual(["a", "b", "c"]);
  });

  it("click a paragraph → shows its driving blocks", async () => {
    render(
      <Xray
        proseText={`First para [b: ${NODE}].\n\nSecond para.`}
        proseProvenance={{ "0": [NODE] }}
        proseValidity={validity("current", "ungrounded")}
        blocks={[block()]}
      />,
    );
    await userEvent.click(screen.getByTestId("xray-paragraph-0").querySelector("button")!);
    expect(await screen.findByTestId("xray-paragraph-blocks-0")).toBeTruthy();
    expect(screen.getAllByText("Capital intensity rises with scale").length).toBeGreaterThan(0);
  });

  it("rigor #3b — one block in MANY paragraphs: click block → all uses listed", async () => {
    render(
      <Xray
        proseText={`Para one [b: ${NODE}].\n\nPara two [b: ${NODE}].\n\nPara three [b: ${NODE}].`}
        proseProvenance={{ "0": [NODE], "1": [NODE], "2": [NODE] }}
        proseValidity={validity("current", "current", "current")}
        blocks={[block()]}
      />,
    );
    // Open paragraph 0, click its block.
    await userEvent.click(screen.getByTestId("xray-paragraph-0").querySelector("button")!);
    const blockBtn = screen
      .getByTestId("xray-paragraph-blocks-0")
      .querySelector("button")!;
    await userEvent.click(blockBtn);
    const uses = await screen.findByTestId("xray-block-uses");
    // The inversion is COMPLETE — all three paragraphs (1,2,3) are listed.
    expect(uses.textContent).toMatch(/1, 2, 3/);
  });

  it("rigor #3a — a paragraph with ZERO blocks is flagged unsupported, not faked", async () => {
    render(
      <Xray
        proseText={`Cited para [b: ${NODE}].\n\nAn orphan paragraph with no recorded blocks at all.`}
        proseProvenance={{ "0": [NODE] }}
        proseValidity={validity("current", "unsupported")}
        blocks={[block()]}
      />,
    );
    await userEvent.click(screen.getByTestId("xray-paragraph-1").querySelector("button")!);
    expect(await screen.findByText(/no support was established/i)).toBeTruthy();
  });

  it("regenerate gesture hands the host the affected paragraph's index (1, not 0)", async () => {
    const onRegen = vi.fn();
    render(
      <Xray
        proseText={`P0 [b: ${NODE}].\n\nP1 [b: ${NODE}].`}
        proseProvenance={{ "0": [NODE], "1": [NODE] }}
        proseValidity={validity("current", "current")}
        blocks={[block()]}
        onRegenerateParagraph={onRegen}
      />,
    );
    await userEvent.click(screen.getByTestId("xray-paragraph-1").querySelector("button")!);
    await userEvent.click(screen.getByRole("button", { name: /regenerate this section/i }));
    // The host receives the affected paragraph's index (1) — it re-drafts that
    // paragraph's section. We assert the index contract, not the regen scope.
    await waitFor(() => expect(onRegen).toHaveBeenCalledWith(1));
    expect(onRegen).not.toHaveBeenCalledWith(0);
  });

  it("never exposes stale paragraph mappings as current trace controls", async () => {
    render(
      <Xray
        proseText="Edited paragraph."
        proseProvenance={{ "0": [NODE] }}
        proseValidity={validity("stale")}
        blocks={[block()]}
      />,
    );
    await userEvent.click(screen.getByTestId("xray-paragraph-0").querySelector("button")!);
    expect(await screen.findByText(/edited since grounding/i)).toBeTruthy();
    expect(screen.queryByText("Capital intensity rises with scale")).toBeNull();
  });
});
