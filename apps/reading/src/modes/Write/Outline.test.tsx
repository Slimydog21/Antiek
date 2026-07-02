import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import { cleanup, fireEvent, render, screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";

import { DRAG_MIME } from "../CreationStudio/BlockPalette";
import { ApiError, type SectionResponse } from "../../lib/api";
import type { GenerationResult, OutlineBlockView, RepositoryHit } from "./writeApi";

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
  emitBrainstormBlocksMock,
} = vi.hoisted(() => ({
  getSectionBlocksMock: vi.fn(),
  generateSectionMock: vi.fn(),
  placeBlockMock: vi.fn(),
  moveBlockMock: vi.fn(),
  emitBrainstormBlocksMock: vi.fn(),
}));

vi.mock("./writeApi", async (orig) => ({
  ...(await orig<typeof import("./writeApi")>()),
  getSectionBlocks: getSectionBlocksMock,
  generateSection: generateSectionMock,
  placeBlock: placeBlockMock,
  moveBlock: moveBlockMock,
  emitBrainstormBlocks: emitBrainstormBlocksMock,
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
  emitBrainstormBlocksMock.mockReset().mockResolvedValue({
    block_ids: ["oblk-brainstorm"],
    insight_count: 1,
    question_count: 0,
    data_count: 0,
    skipped_duplicates: 0,
    flagged_unverified: [],
  });
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

  it("drops malformed blocks and trims the valid block before rendering", async () => {
    getSectionBlocksMock.mockResolvedValue([
      block({
        outline_block_id: " oblk-valid ",
        section_id: " sec-1 ",
        content: "  Operator note  ",
        node_label: " ignored label ",
        block_index: "1" as unknown as number,
      }),
      block({
        outline_block_id: " ",
        node_label: "Invisible block",
      }),
    ]);
    const { container } = render(
      <Outline deliverableId="dlv-1" sections={[section({ block_count: 2 })]} onChanged={vi.fn()} />,
    );

    expect(await screen.findByText("Operator note")).toBeTruthy();
    expect(screen.queryByText("Invisible block")).toBeNull();
    expect(container.textContent ?? "").not.toContain(" oblk-valid ");
  });

  it("disables Generate on an empty section with a reason (no hang, no fabrication)", async () => {
    getSectionBlocksMock.mockResolvedValue([]);
    render(<Outline deliverableId="dlv-1" sections={[section()]} onChanged={vi.fn()} />);
    const gen = await screen.findByRole("button", { name: /generate draft/i });
    expect((gen as HTMLButtonElement).disabled).toBe(true);
    expect(screen.getByText(/add at least one block/i)).toBeTruthy();
    expect(generateSectionMock).not.toHaveBeenCalled();
  });

  it("emits brainstorm drivers into the real section and refreshes blocks", async () => {
    getSectionBlocksMock.mockResolvedValue([]);
    const onChanged = vi.fn();
    render(
      <Outline deliverableId="dlv-1" sections={[section()]} onChanged={onChanged} />,
    );

    await userEvent.click(await screen.findByRole("button", { name: /brainstorm blocks/i }));
    await userEvent.type(screen.getAllByPlaceholderText("one per line")[0], "The moat is data");
    await userEvent.click(screen.getByRole("button", { name: /emit lego blocks/i }));

    await waitFor(() =>
      expect(emitBrainstormBlocksMock).toHaveBeenCalledWith({
        section_id: "sec-1",
        deliverable_id: "dlv-1",
        insights: ["The moat is data"],
        questions: [],
        data_points: [],
      }),
    );
    await waitFor(() => expect(onChanged).toHaveBeenCalled());
    expect(screen.getByText(/Placed 1 block/)).toBeTruthy();
  });

  it("places tapped repository claims as claims, not flattened insights", async () => {
    const addHandlerRef: { current: ((hit: RepositoryHit) => void) | null } = { current: null };
    const onChanged = vi.fn();
    render(
      <Outline
        deliverableId="dlv-1"
        sections={[section({ block_count: 3 })]}
        onChanged={onChanged}
        registerAddHandler={(handler) => {
          addHandlerRef.current = handler;
        }}
      />,
    );

    expect(addHandlerRef.current).toBeTruthy();
    addHandlerRef.current?.({
      node_id: "node-claim",
      label: "A sourced claim",
      node_type: "claim",
      source_tier: 1,
      document_id: "doc-1",
      document_title: "Source",
      score: 0.8,
    });

    await waitFor(() => expect(placeBlockMock).toHaveBeenCalled());
    expect(placeBlockMock).toHaveBeenCalledWith(
      expect.objectContaining({
        section_id: "sec-1",
        block_kind: "claim",
        provenance_kind: "graph_node",
        node_id: "node-claim",
        block_index: 3,
        deliverable_id: "dlv-1",
      }),
    );
    await waitFor(() => expect(onChanged).toHaveBeenCalled());
  });

  it("places dropped open questions as open questions, not flattened insights", async () => {
    render(
      <Outline deliverableId="dlv-1" sections={[section()]} onChanged={vi.fn()} />,
    );
    const card = (await screen.findByText("Thesis")).closest("section");
    expect(card).toBeTruthy();

    fireEvent.drop(card!, {
      dataTransfer: {
        getData: (type: string) =>
          type === DRAG_MIME
            ? JSON.stringify({
                from: "palette",
                block_id: "node-question",
                block_kind: "open_question",
                label: "Question to answer",
              })
            : "",
      },
    });

    await waitFor(() => expect(placeBlockMock).toHaveBeenCalled());
    expect(placeBlockMock).toHaveBeenCalledWith(
      expect.objectContaining({
        section_id: "sec-1",
        block_kind: "open_question",
        provenance_kind: "graph_node",
        node_id: "node-question",
        block_index: 0,
        deliverable_id: "dlv-1",
      }),
    );
  });

  it("surfaces AIActionFailure (no fake draft) when generation 503s without keys", async () => {
    getSectionBlocksMock.mockResolvedValue([block()]);
    generateSectionMock.mockRejectedValue(
      new ApiError("generation unavailable", 503, "dispatch provider unavailable"),
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

  it("sanitizes generated prose metadata before editor and X-ray state", async () => {
    getSectionBlocksMock.mockResolvedValue([block()]);
    generateSectionMock.mockResolvedValue({
      status: "generated",
      section_id: " ",
      prose_text: "  Draft paragraph.\n\nSecond paragraph.  ",
      unsupported_paragraphs: ["0", 1.5, -1, Number.NaN],
      fabricated_citations: [" cite-1 ", ""],
      prose_provenance: { " 0 ": [" "], "1": [NODE_ID, " "] },
    });
    const { container } = render(
      <Outline
        deliverableId="dlv-1"
        sections={[section({ block_count: 1 })]}
        onChanged={vi.fn()}
      />,
    );

    await screen.findByText("Capital intensity rises with scale");
    await userEvent.click(screen.getByRole("button", { name: /generate draft/i }));
    await waitFor(() => expect(container.querySelector(".ProseMirror")).toBeTruthy());
    expect(screen.getByText(/1 paragraph\(s\) flagged unsupported/i)).toBeTruthy();
    await userEvent.click(await screen.findByRole("button", { name: /^X-ray$/i }));
    expect(await screen.findByTestId("xray")).toBeTruthy();
    await userEvent.click(screen.getByTestId("xray-paragraph-1").querySelector("button")!);
    expect(await screen.findByTestId("xray-paragraph-blocks-1")).toBeTruthy();
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

  it("X-ray regenerate sends the affected paragraph index to the generate endpoint", async () => {
    getSectionBlocksMock.mockResolvedValue([block()]);
    generateSectionMock.mockResolvedValue({
      status: "generated",
      section_id: "sec-1",
      prose_text: `Prior para [b: ${NODE_ID}].\n\nSharper para [b: ${NODE_ID}].`,
      prose_provenance: { "0": [NODE_ID], "1": [NODE_ID] },
    } satisfies GenerationResult);
    render(
      <Outline
        deliverableId="dlv-1"
        sections={[
          section({
            block_count: 1,
            prose_text: `Prior para [b: ${NODE_ID}].\n\nOld para [b: ${NODE_ID}].`,
            prose_provenance: { "0": [NODE_ID], "1": [NODE_ID] },
          }),
        ]}
        onChanged={vi.fn()}
      />,
    );
    await screen.findByText("Capital intensity rises with scale");
    await userEvent.click(await screen.findByRole("button", { name: /^X-ray$/i }));
    await userEvent.click(screen.getByTestId("xray-paragraph-1").querySelector("button")!);
    await userEvent.click(screen.getByRole("button", { name: /regenerate this paragraph/i }));
    await waitFor(() =>
      expect(generateSectionMock).toHaveBeenCalledWith("sec-1", { paragraphIndex: 1 }),
    );
  });
});
