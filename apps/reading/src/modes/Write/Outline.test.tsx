import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import { cleanup, render, screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";

import { ApiError, type SectionResponse } from "../../lib/api";
import type { GenerationResult, OutlineBlockView } from "./writeApi";

/**
 * Outline.test — the outline + generate + real-editor surface (SPR-07
 * M2+M3+M4).
 *
 * Load-bearing claims, mechanically checked:
 *  - blocks render by TEXT + provenance, never an id (no-UUID gate);
 *  - Generate on an EMPTY section is disabled with a reason (no hang, no
 *    fabricated draft);
 *  - Generate without keys (503) surfaces AIActionFailure, never a fake draft;
 *  - a gap outcome is honest;
 *  - a real draft mounts the WriteEditor (the TipTap surface) — the textarea
 *    is retired.
 */

const {
  getSectionBlocksMock,
  generateSectionMock,
  placeBlockMock,
  moveBlockMock,
} = vi.hoisted(() => ({
  getSectionBlocksMock: vi.fn(),
  generateSectionMock: vi.fn(),
  placeBlockMock: vi.fn(),
  moveBlockMock: vi.fn(),
}));

vi.mock("./writeApi", async (orig) => ({
  ...(await orig<typeof import("./writeApi")>()),
  getSectionBlocks: getSectionBlocksMock,
  generateSection: generateSectionMock,
  placeBlock: placeBlockMock,
  moveBlock: moveBlockMock,
}));

// createSection lives on the shared lib/api — keep it inert in these tests.
vi.mock("../../lib/api", async (orig) => ({
  ...(await orig<typeof import("../../lib/api")>()),
  createSection: vi.fn().mockResolvedValue({}),
}));

import Outline from "./Outline";

const NODE_ID = "a1b2c3d4e5f60718293a4b5c6d7e8f90";

function section(over: Partial<SectionResponse> = {}): SectionResponse {
  return {
    section_id: "sec-1",
    deliverable_id: "dlv-1",
    parent_section_id: null,
    section_index: 0,
    title: "Thesis",
    prose_text: null,
    prose_provenance: null,
    block_count: 0,
    ...over,
  };
}

function block(over: Partial<OutlineBlockView> = {}): OutlineBlockView {
  return {
    outline_block_id: "oblk-" + NODE_ID,
    section_id: "sec-1",
    block_kind: "insight",
    provenance_kind: "graph_node",
    node_id: NODE_ID,
    content: null,
    node_label: "Capital intensity rises with scale",
    block_index: 0,
    is_user_originated: false,
    ...over,
  };
}

beforeEach(() => {
  getSectionBlocksMock.mockReset().mockResolvedValue([]);
  generateSectionMock.mockReset();
  placeBlockMock.mockReset().mockResolvedValue("oblk-new");
  moveBlockMock.mockReset().mockResolvedValue(undefined);
});
afterEach(cleanup);

describe("Outline — no id, honest generate, real editor", () => {
  it("renders a block by text + provenance, never an id", async () => {
    getSectionBlocksMock.mockResolvedValue([block()]);
    const { container } = render(
      <Outline deliverableId="dlv-1" sections={[section({ block_count: 1 })]} onChanged={vi.fn()} />,
    );
    expect(await screen.findByText("Capital intensity rises with scale")).toBeTruthy();
    // The node_id / outline_block_id never reach the rendered DOM.
    expect(container.textContent ?? "").not.toContain(NODE_ID);
    expect((container.textContent ?? "").match(/\b[0-9a-f]{32,40}\b/i)).toBeNull();
  });

  it("disables Generate on an empty section with a reason (no hang, no fabrication)", async () => {
    getSectionBlocksMock.mockResolvedValue([]);
    render(<Outline deliverableId="dlv-1" sections={[section()]} onChanged={vi.fn()} />);
    const gen = await screen.findByRole("button", { name: /generate draft/i });
    expect((gen as HTMLButtonElement).disabled).toBe(true);
    expect(screen.getByText(/add at least one block/i)).toBeTruthy();
    expect(generateSectionMock).not.toHaveBeenCalled();
  });

  it("surfaces AIActionFailure (no fake draft) when generation 503s without keys", async () => {
    getSectionBlocksMock.mockResolvedValue([block()]);
    generateSectionMock.mockRejectedValue(
      new ApiError("generation unavailable", 503, "creative_writer not in dispatch config"),
    );
    render(
      <Outline deliverableId="dlv-1" sections={[section({ block_count: 1 })]} onChanged={vi.fn()} />,
    );
    await screen.findByText("Capital intensity rises with scale");
    await userEvent.click(screen.getByRole("button", { name: /generate draft/i }));
    await waitFor(() => expect(screen.getByRole("alert")).toBeTruthy());
    // The honest no-provider sentence — never a fabricated draft.
    expect(screen.getByRole("alert").textContent ?? "").toMatch(/provider isn.t configured/i);
  });

  it("shows an honest gap (not a hang) when generation returns gap", async () => {
    getSectionBlocksMock.mockResolvedValue([block()]);
    const gap: GenerationResult = {
      status: "gap",
      section_id: "sec-1",
      detail: "no blocks attached — left as a gap, not fabricated",
    };
    generateSectionMock.mockResolvedValue(gap);
    render(
      <Outline deliverableId="dlv-1" sections={[section({ block_count: 1 })]} onChanged={vi.fn()} />,
    );
    await screen.findByText("Capital intensity rises with scale");
    await userEvent.click(screen.getByRole("button", { name: /generate draft/i }));
    await waitFor(() => expect(screen.getByText(/left as a gap/i)).toBeTruthy());
  });

  it("mounts the real WriteEditor (TipTap) when a draft generates", async () => {
    getSectionBlocksMock.mockResolvedValue([block()]);
    const generated: GenerationResult = {
      status: "generated",
      section_id: "sec-1",
      prose_text: "The thesis holds because the mechanism is load-bearing.",
    };
    generateSectionMock.mockResolvedValue(generated);
    const { container } = render(
      <Outline deliverableId="dlv-1" sections={[section({ block_count: 1 })]} onChanged={vi.fn()} />,
    );
    await screen.findByText("Capital intensity rises with scale");
    await userEvent.click(screen.getByRole("button", { name: /generate draft/i }));
    // The TipTap editor mounts (ProseMirror contenteditable) — not a textarea.
    await waitFor(() =>
      expect(container.querySelector(".ProseMirror")).toBeTruthy(),
    );
    expect(container.querySelector("textarea")).toBeNull();
  });

  // ── SPR-09 M2→M3 — generation provenance → X-ray (no edit loss on toggle) ──

  it("captures generation provenance and X-rays it (paragraph→blocks)", async () => {
    getSectionBlocksMock.mockResolvedValue([block()]);
    const generated: GenerationResult = {
      status: "generated",
      section_id: "sec-1",
      prose_text: `Para one [b: ${NODE_ID}].\n\nPara two [b: ${NODE_ID}].`,
      // The PERSISTED map the server returned (SECTION_DRAFT_GENERATED).
      prose_provenance: { "0": [NODE_ID], "1": [NODE_ID] },
    };
    generateSectionMock.mockResolvedValue(generated);
    const { container } = render(
      <Outline
        deliverableId="dlv-1"
        sections={[section({ block_count: 1 })]}
        onChanged={vi.fn()}
        investigationId="inv-1"
      />,
    );
    await screen.findByText("Capital intensity rises with scale");
    await userEvent.click(screen.getByRole("button", { name: /generate draft/i }));
    await waitFor(() => expect(container.querySelector(".ProseMirror")).toBeTruthy());
    // The X-ray toggle appears once there's prose; toggling shows the X-ray.
    await userEvent.click(await screen.findByRole("button", { name: /^X-ray$/i }));
    expect(await screen.findByTestId("xray")).toBeTruthy();
    // The first paragraph X-rays back to its driving block (the persisted map).
    await userEvent.click(screen.getByTestId("xray-paragraph-0").querySelector("button")!);
    expect(await screen.findByTestId("xray-paragraph-blocks-0")).toBeTruthy();
  });

  it("X-ray reads back PERSISTED provenance on a reloaded section (no regenerate needed)", async () => {
    getSectionBlocksMock.mockResolvedValue([block()]);
    // The section already carries persisted prose + provenance (read back from
    // GET /deliverables/{id}) — the X-ray works without re-running generate.
    render(
      <Outline
        deliverableId="dlv-1"
        sections={[
          section({
            block_count: 1,
            prose_text: `Prior para [b: ${NODE_ID}].`,
            prose_provenance: { "0": [NODE_ID] },
          }),
        ]}
        onChanged={vi.fn()}
      />,
    );
    await screen.findByText("Capital intensity rises with scale");
    await userEvent.click(await screen.findByRole("button", { name: /^X-ray$/i }));
    expect(await screen.findByTestId("xray")).toBeTruthy();
  });
});
