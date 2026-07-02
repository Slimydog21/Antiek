import { afterEach, describe, expect, it, vi } from "vitest";
import { cleanup, render, screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";

import { getTraceTarget } from "./writeApi";
import type { OutlineBlockView } from "./writeApi";
import Xray, { splitParagraphs, traceSourceLabel } from "./Xray";

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
 *    paragraph's index.
 */

// getTraceTarget is the only writeApi call Xray makes (block → source chain).
vi.mock("./writeApi", async (orig) => ({
  ...(await orig<typeof import("./writeApi")>()),
  getTraceTarget: vi.fn().mockResolvedValue({
    kind: "document", full_text_allowed: true, document_id: "doc-1",
    document_title: "Source Book", chunk_ids: ["c1"],
    primary_chunk_index: 0, primary_section_path: "Page 1",
    servability_status: "servable", detail: null,
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

afterEach(cleanup);

describe("Xray — paragraph↔blocks over persisted provenance", () => {
  it("splits prose the substrate's way (blank line)", () => {
    expect(splitParagraphs("a\n\nb\n\n\nc")).toEqual(["a", "b", "c"]);
  });

  it("labels traced source locators without inventing a region", () => {
    expect(traceSourceLabel({
      documentTitle: "Source Book",
      primarySectionPath: "Page 3",
      primaryChunkIndex: 2,
    })).toBe("Source: Source Book · Page 3");
    expect(traceSourceLabel({
      documentTitle: "Source Book",
      primarySectionPath: null,
      primaryChunkIndex: 2,
    })).toBe("Source: Source Book · chunk 3");
  });

  it("click a paragraph → shows its driving blocks", async () => {
    render(
      <Xray
        proseText={`First para [b: ${NODE}].\n\nSecond para.`}
        proseProvenance={{ "0": [NODE] }}
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

  it("drops malformed persisted provenance keys from the block use inversion", async () => {
    render(
      <Xray
        proseText={`Para one [b: ${NODE}].\n\nPara two [b: ${NODE}].`}
        proseProvenance={{
          "0": [NODE],
          "1": [NODE],
          "2": [NODE],
          "1junk": [NODE],
          "9007199254740992": [NODE],
        }}
        blocks={[block()]}
      />,
    );
    await userEvent.click(screen.getByTestId("xray-paragraph-0").querySelector("button")!);
    await userEvent.click(screen.getByTestId("xray-paragraph-blocks-0").querySelector("button")!);
    const uses = await screen.findByTestId("xray-block-uses");
    expect(uses.textContent).toMatch(/1, 2/);
    expect(uses.textContent).not.toContain("3");
    expect(uses.textContent).not.toContain("NaN");
    expect(uses.textContent).not.toContain("9007199254740993");
  });

  it("drops malformed persisted provenance values instead of fabricating blocks", async () => {
    render(
      <Xray
        proseText={`Para one.\n\nPara two [b: ${NODE}].`}
        proseProvenance={{
          "0": "not-an-array" as unknown as string[],
          "1": [NODE, "", 42 as unknown as string],
        }}
        blocks={[block()]}
      />,
    );

    await userEvent.click(screen.getByTestId("xray-paragraph-0").querySelector("button")!);
    expect(await screen.findByText(/no blocks recorded.*unsupported/i)).toBeTruthy();

    await userEvent.click(screen.getByTestId("xray-paragraph-1").querySelector("button")!);
    await userEvent.click(screen.getByTestId("xray-paragraph-blocks-1").querySelector("button")!);
    const uses = await screen.findByTestId("xray-block-uses");
    expect(uses.textContent).toMatch(/Used in paragraph\(s\): 2/);
    expect(uses.textContent).not.toContain("NaN");
    expect(uses.textContent).not.toContain("42");
  });

  it("does not render gated trace locator metadata even if the API sends it", async () => {
    vi.mocked(getTraceTarget).mockResolvedValueOnce({
      kind: "servable_snippet",
      full_text_allowed: false,
      document_id: "doc-gated",
      document_title: "Gated Book",
      chunk_ids: ["c-gated"],
      primary_chunk_index: 8,
      primary_section_path: "Restricted appendix",
      servability_status: "restricted_pending_opt_in",
      detail: "gated source — metadata only",
    });
    render(
      <Xray
        proseText={`Para one [b: ${NODE}].`}
        proseProvenance={{ "0": [NODE] }}
        blocks={[block()]}
      />,
    );
    await userEvent.click(screen.getByTestId("xray-paragraph-0").querySelector("button")!);
    await userEvent.click(screen.getByTestId("xray-paragraph-blocks-0").querySelector("button")!);
    const uses = await screen.findByTestId("xray-block-uses");
    expect(uses.textContent).toContain("gated source");
    expect(uses.textContent).not.toContain("Restricted appendix");
    expect(uses.textContent).not.toContain("chunk 9");
  });

  it("sanitizes malformed allowed trace metadata before source labeling", async () => {
    vi.mocked(getTraceTarget).mockResolvedValueOnce({
      kind: "",
      full_text_allowed: true,
      document_id: " doc-1 ",
      document_title: "  Source Book  ",
      chunk_ids: [" c1 ", "", 42 as unknown as string],
      primary_chunk_index: "2" as unknown as number,
      primary_section_path: " ",
      servability_status: "",
      detail: "",
    });
    render(
      <Xray
        proseText={`Para one [b: ${NODE}].`}
        proseProvenance={{ "0": [NODE] }}
        blocks={[block()]}
      />,
    );
    await userEvent.click(screen.getByTestId("xray-paragraph-0").querySelector("button")!);
    await userEvent.click(screen.getByTestId("xray-paragraph-blocks-0").querySelector("button")!);
    const uses = await screen.findByTestId("xray-block-uses");
    expect(uses.textContent).toContain("Source: Source Book · chunk 3");
    expect(uses.textContent).not.toContain("  Source Book  ");
  });

  it("treats allowed traces without a usable document title as unresolved", async () => {
    vi.mocked(getTraceTarget).mockResolvedValueOnce({
      kind: "document",
      full_text_allowed: true,
      document_id: "doc-1",
      document_title: " ",
      chunk_ids: ["c1"],
      primary_chunk_index: 0,
      primary_section_path: "Page 1",
      servability_status: "servable",
      detail: "",
    });
    render(
      <Xray
        proseText={`Para one [b: ${NODE}].`}
        proseProvenance={{ "0": [NODE] }}
        blocks={[block()]}
      />,
    );
    await userEvent.click(screen.getByTestId("xray-paragraph-0").querySelector("button")!);
    await userEvent.click(screen.getByTestId("xray-paragraph-blocks-0").querySelector("button")!);
    const uses = await screen.findByTestId("xray-block-uses");
    expect(uses.textContent).toContain("Resolving source");
    expect(uses.textContent).not.toContain("Page 1");
  });

  it("rigor #3a — a paragraph with ZERO blocks is flagged unsupported, not faked", async () => {
    render(
      <Xray
        proseText={`Cited para [b: ${NODE}].\n\nAn orphan paragraph with no recorded blocks at all.`}
        proseProvenance={{ "0": [NODE] }}
        blocks={[block()]}
      />,
    );
    await userEvent.click(screen.getByTestId("xray-paragraph-1").querySelector("button")!);
    expect(await screen.findByText(/no blocks recorded.*unsupported/i)).toBeTruthy();
  });

  it("regenerate gesture hands the host the affected paragraph's index (1, not 0)", async () => {
    const onRegen = vi.fn();
    render(
      <Xray
        proseText={`P0 [b: ${NODE}].\n\nP1 [b: ${NODE}].`}
        proseProvenance={{ "0": [NODE], "1": [NODE] }}
        blocks={[block()]}
        onRegenerateParagraph={onRegen}
      />,
    );
    await userEvent.click(screen.getByTestId("xray-paragraph-1").querySelector("button")!);
    await userEvent.click(screen.getByRole("button", { name: /regenerate this paragraph/i }));
    // The host receives the affected paragraph's index (1) — it re-drafts that
    // paragraph via the shipped generate path.
    await waitFor(() => expect(onRegen).toHaveBeenCalledWith(1));
    expect(onRegen).not.toHaveBeenCalledWith(0);
  });
});
