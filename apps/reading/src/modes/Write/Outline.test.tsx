import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import { act, cleanup, fireEvent, render, screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import type { Editor } from "@tiptap/react";

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
  updateSectionProseMock,
  postTypedEventMock,
  editorHolder,
} = vi.hoisted(() => ({
  getSectionBlocksMock: vi.fn(),
  generateSectionMock: vi.fn(),
  placeBlockMock: vi.fn(),
  moveBlockMock: vi.fn(),
  updateSectionProseMock: vi.fn(),
  postTypedEventMock: vi.fn(),
  // Holds the REAL TipTap editor instance (captured, not replaced) so a test
  // can drive a genuine ProseMirror transaction — jsdom cannot deliver an edit
  // through typing (its DOM mutation never reaches ProseMirror's observer).
  editorHolder: { current: null as { editor: unknown } | null },
}));

vi.mock("./writeApi", async (orig) => ({
  ...(await orig<typeof import("./writeApi")>()),
  getSectionBlocks: getSectionBlocksMock,
  generateSection: generateSectionMock,
  placeBlock: placeBlockMock,
  moveBlock: moveBlockMock,
}));

// createSection lives on the shared lib/api — keep it inert in these tests.
// updateSectionProse is the persistence call this sprint wires; postTypedEvent
// is the (best-effort) edit.captured telemetry the editor already fires — both
// are stubbed so the SPR-02 tests are hermetic (no real network).
vi.mock("../../lib/api", async (orig) => ({
  ...(await orig<typeof import("../../lib/api")>()),
  createSection: vi.fn().mockResolvedValue({}),
  updateSectionProse: updateSectionProseMock,
  postTypedEvent: postTypedEventMock,
}));

// Capture the REAL editor instance without changing its behavior. We wrap
// TipTap's useEditor, store the returned editor, and return it untouched — the
// Outline→WriteEditor mount stays real (rigor #1: no hand-rolled editor).
vi.mock("@tiptap/react", async (orig) => {
  const actual = await orig<typeof import("@tiptap/react")>();
  return {
    ...actual,
    useEditor: (options: unknown, deps?: unknown) => {
      const ed = (actual.useEditor as (o: unknown, d?: unknown) => unknown)(
        options,
        deps,
      );
      if (ed) editorHolder.current = { editor: ed };
      return ed;
    },
  };
});

/** The captured real editor, typed for command access. */
function editor(): Editor {
  if (!editorHolder.current) throw new Error("editor not mounted");
  return editorHolder.current.editor as Editor;
}

/** Simulate a genuine manual prose edit: a real ProseMirror transaction on the
 * live editor, which fires the editor's real onUpdate → onContentChange. */
async function typeInEditor(text: string): Promise<void> {
  await act(async () => {
    editor().commands.insertContent(text);
  });
}

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
  updateSectionProseMock
    .mockReset()
    .mockResolvedValue({ status: "saved", section_id: "sec-1", claim_node_id: null, claim_event_id: null });
  postTypedEventMock.mockReset().mockResolvedValue({});
  editorHolder.current = null;
});
afterEach(cleanup);

describe("Outline — no id, honest generate, real editor", () => {
  it("places selected repository evidence at the exact chosen seam", async () => {
    getSectionBlocksMock.mockResolvedValue([block()]);
    const done = vi.fn();
    render(
      <Outline
        deliverableId="dlv-1"
        sections={[section({ block_count: 1 })]}
        onChanged={vi.fn()}
        pendingRepositoryHit={{
          node_id: "node-new",
          label: "Demand compounds across cycles",
          node_type: "insight",
          document_title: "Research memo",
          document_id: "doc-new",
          source_tier: 1,
          score: 0.91,
        }}
        onRepositoryPlacementDone={done}
      />,
    );
    await screen.findByText("Capital intensity rises with scale");
    await userEvent.click(screen.getByRole("button", { name: /place before capital intensity/i }));
    await waitFor(() =>
      expect(placeBlockMock).toHaveBeenCalledWith({
        section_id: "sec-1",
        block_kind: "insight",
        provenance_kind: "graph_node",
        node_id: "node-new",
        block_index: 0,
        deliverable_id: "dlv-1",
      }),
    );
    expect(done).toHaveBeenCalledTimes(1);
  });

  it.each([
    [/place between blocks 1 and 2/i, 1],
    [/place after the last block/i, 2],
  ])("places repository evidence at another populated seam: %s", async (seamName, index) => {
    getSectionBlocksMock.mockResolvedValue([
      block({ outline_block_id: "oblk-a", node_label: "Evidence A", block_index: 0 }),
      block({ outline_block_id: "oblk-b", node_label: "Evidence B", block_index: 1 }),
    ]);
    render(
      <Outline
        deliverableId="dlv-1" sections={[section({ block_count: 2 })]} onChanged={vi.fn()}
        pendingRepositoryHit={{
          node_id: "node-new", label: "New evidence", node_type: "insight",
          document_title: null, document_id: null, source_tier: null, score: 0.8,
        }}
      />,
    );
    await screen.findByText("Evidence B");
    await userEvent.click(screen.getByRole("button", { name: seamName }));
    await waitFor(() => expect(placeBlockMock).toHaveBeenCalledWith(
      expect.objectContaining({ block_index: index }),
    ));
  });

  it("keeps a failed placement selected and exposes a truthful retry seam", async () => {
    getSectionBlocksMock.mockResolvedValue([]);
    placeBlockMock.mockRejectedValue(new Error("write refused"));
    render(
      <Outline
        deliverableId="dlv-1"
        sections={[section()]}
        onChanged={vi.fn()}
        pendingRepositoryHit={{
          node_id: "node-new",
          label: "Demand compounds across cycles",
          node_type: "insight",
          document_title: null,
          document_id: null,
          source_tier: null,
          score: 0.91,
        }}
      />,
    );
    const seam = await screen.findByRole("button", { name: /place as the first block/i });
    await userEvent.click(seam);
    expect((await screen.findByRole("alert")).textContent ?? "").toMatch(
      /not placed.*write refused/i,
    );
    expect(screen.getByRole("button", { name: /place as the first block/i })).toBeTruthy();
  });

  it("retries the same seam successfully and preserves question semantics", async () => {
    placeBlockMock
      .mockRejectedValueOnce(new Error("temporary lock"))
      .mockResolvedValueOnce("oblk-retried");
    const done = vi.fn();
    render(
      <Outline
        deliverableId="dlv-1"
        sections={[section()]}
        onChanged={vi.fn()}
        pendingRepositoryHit={{
          node_id: "question-new", label: "What survives?", node_type: "open_question",
          document_title: null, document_id: null, source_tier: null, score: 0.8,
        }}
        onRepositoryPlacementDone={done}
      />,
    );
    const seam = await screen.findByRole("button", { name: /place as the first block/i });
    await userEvent.click(seam);
    await screen.findByRole("alert");
    await userEvent.click(seam);
    await waitFor(() => expect(done).toHaveBeenCalledTimes(1));
    expect(placeBlockMock).toHaveBeenLastCalledWith(expect.objectContaining({
      block_kind: "open_question", node_id: "question-new", block_index: 0,
    }));
  });

  it("coalesces rapid seam activation and ignores Escape while the write is pending", async () => {
    let resolveWrite!: (value: string) => void;
    placeBlockMock.mockReturnValue(new Promise<string>((resolve) => { resolveWrite = resolve; }));
    const cancel = vi.fn();
    const done = vi.fn();
    render(
      <Outline
        deliverableId="dlv-1" sections={[section()]} onChanged={vi.fn()}
        pendingRepositoryHit={{
          node_id: "claim-new", label: "Costs remain", node_type: "claim",
          document_title: null, document_id: null, source_tier: null, score: 0.8,
        }}
        onRepositoryPlacementDone={done}
        onRepositoryPlacementCancel={cancel}
      />,
    );
    const seam = await screen.findByRole("button", { name: /place as the first block/i });
    fireEvent.click(seam);
    fireEvent.click(seam);
    fireEvent.keyDown(window, { key: "Escape" });
    expect(placeBlockMock).toHaveBeenCalledTimes(1);
    expect(placeBlockMock).toHaveBeenCalledWith(expect.objectContaining({ block_kind: "claim" }));
    expect(cancel).not.toHaveBeenCalled();
    resolveWrite("oblk-new");
    await waitFor(() => expect(done).toHaveBeenCalledTimes(1));
  });

  it("keeps desktop tap committed when its parent refresh rejects", async () => {
    let add!: (hit: RepositoryHit) => void;
    const onChanged = vi.fn().mockRejectedValue(new Error("refresh offline"));
    render(
      <Outline
        deliverableId="dlv-1" sections={[section()]} onChanged={onChanged}
        registerAddHandler={(handler) => { add = handler; }}
      />,
    );
    await waitFor(() => expect(add).toBeTypeOf("function"));
    add({
      node_id: "claim-tap", label: "Tap claim", node_type: "claim",
      document_title: null, document_id: null, source_tier: null, score: 0.7,
    });
    await waitFor(() => expect(placeBlockMock).toHaveBeenCalledTimes(1));
    await waitFor(() => expect(onChanged).toHaveBeenCalledTimes(1));
    expect(placeBlockMock).toHaveBeenCalledWith(expect.objectContaining({ block_kind: "claim" }));
  });

  it("preserves native drag kind and does not retry a commit when refresh rejects", async () => {
    const onChanged = vi.fn().mockRejectedValue(new Error("refresh offline"));
    const { container } = render(
      <Outline deliverableId="dlv-1" sections={[section()]} onChanged={onChanged} />,
    );
    const card = container.querySelector("section")!;
    const payload = JSON.stringify({
      from: "palette", block_kind: "open_question", block_id: "question-drag", label: "Why?",
    });
    fireEvent.drop(card, {
      dataTransfer: { getData: () => payload, types: ["application/x-antiek-block"] },
    });
    await waitFor(() => expect(placeBlockMock).toHaveBeenCalledTimes(1));
    await waitFor(() => expect(onChanged).toHaveBeenCalledTimes(1));
    expect(placeBlockMock).toHaveBeenCalledWith(expect.objectContaining({
      block_kind: "open_question", node_id: "question-drag",
    }));
  });

  it("keeps native reorder committed when the parent refresh rejects", async () => {
    getSectionBlocksMock.mockResolvedValue([block()]);
    const onChanged = vi.fn().mockRejectedValue(new Error("refresh offline"));
    render(
      <Outline
        deliverableId="dlv-1" sections={[section({ block_count: 1 })]} onChanged={onChanged}
      />,
    );
    const row = await screen.findByTitle("Drag to reorder");
    fireEvent.drop(row, {
      dataTransfer: {
        getData: (type: string) =>
          type === "application/x-antiek-outline-block" ? "oblk-native" : "",
        types: ["application/x-antiek-outline-block"],
      },
    });
    await waitFor(() => expect(moveBlockMock).toHaveBeenCalledTimes(1));
    await waitFor(() => expect(onChanged).toHaveBeenCalledTimes(1));
    expect(moveBlockMock).toHaveBeenCalledWith("oblk-native", "sec-1", 0);
  });

  it("moves an existing block through the same keyboard-operable seams", async () => {
    getSectionBlocksMock.mockResolvedValue([block()]);
    render(
      <Outline deliverableId="dlv-1" sections={[section({ block_count: 1 })]} onChanged={vi.fn()} />,
    );
    await userEvent.click(
      await screen.findByRole("button", { name: /move capital intensity rises with scale/i }),
    );
    await userEvent.click(screen.getByRole("button", { name: /place after the last block/i }));
    await waitFor(() => expect(moveBlockMock).toHaveBeenCalledWith("oblk-" + NODE_ID, "sec-1", 1));
  });

  it.each([
    [/place before evidence a/i, 0],
    [/place between blocks 1 and 2/i, 1],
  ])("moves populated evidence to a first/middle seam: %s", async (seamName, index) => {
    getSectionBlocksMock.mockResolvedValue([
      block({ outline_block_id: "oblk-a", node_label: "Evidence A", block_index: 0 }),
      block({ outline_block_id: "oblk-b", node_label: "Evidence B", block_index: 1 }),
      block({ outline_block_id: "oblk-c", node_label: "Evidence C", block_index: 2 }),
    ]);
    render(
      <Outline deliverableId="dlv-1" sections={[section({ block_count: 3 })]} onChanged={vi.fn()} />,
    );
    await userEvent.click(await screen.findByRole("button", { name: /move evidence c/i }));
    await userEvent.click(screen.getByRole("button", { name: seamName }));
    await waitFor(() => expect(moveBlockMock).toHaveBeenCalledWith("oblk-c", "sec-1", index));
  });

  it("moves evidence across sections without exposing its identifier", async () => {
    getSectionBlocksMock.mockImplementation(async (sectionId: string) =>
      sectionId === "sec-1" ? [block()] : [],
    );
    const second = section({
      section_id: "sec-2",
      section_index: 1,
      title: "Counterargument",
      block_count: 0,
    });
    const { container } = render(
      <Outline
        deliverableId="dlv-1"
        sections={[section({ block_count: 1 }), second]}
        onChanged={vi.fn()}
      />,
    );
    await userEvent.click(
      await screen.findByRole("button", { name: /move capital intensity rises with scale/i }),
    );
    await userEvent.click(screen.getByRole("button", { name: /place as the first block/i }));
    await waitFor(() => expect(moveBlockMock).toHaveBeenCalledWith("oblk-" + NODE_ID, "sec-2", 0));
    expect(container.textContent ?? "").not.toContain("oblk-");
  });

  it("cancels field-kit placement with Escape without writing", async () => {
    const cancel = vi.fn();
    render(
      <Outline
        deliverableId="dlv-1"
        sections={[section()]}
        onChanged={vi.fn()}
        pendingRepositoryHit={{
          node_id: "node-new",
          label: "Demand compounds across cycles",
          node_type: "insight",
          document_title: null,
          document_id: null,
          source_tier: null,
          score: 0.91,
        }}
        onRepositoryPlacementCancel={cancel}
      />,
    );
    fireEvent.keyDown(window, { key: "Escape" });
    expect(cancel).toHaveBeenCalledTimes(1);
    expect(placeBlockMock).not.toHaveBeenCalled();
  });

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

// ── SPR-02 — manual /write edits persist to prose_text ────────────────────────
//
// The gap: Outline mounts the real WriteEditor with NO onContentChange, so a
// manual prose edit fires edit.captured telemetry (swallowed) but never reaches
// deliverable_sections.prose_text — export (app.py:2890) and reload (app.py:2573)
// both read that column, so the edit is silently discarded despite the footer
// promising "saved as you write". These tests drive a REAL editor transaction
// through the REAL mount and assert the persistence call + an honest indicator.

/** Mount Outline, generate a draft (so the real WriteEditor mounts), and wait
 * until the live editor is captured. Returns the render result. */
async function mountWithDraft(over: Partial<SectionResponse> = {}) {
  getSectionBlocksMock.mockResolvedValue([block()]);
  generateSectionMock.mockResolvedValue({
    status: "generated",
    section_id: "sec-1",
    prose_text: "Draft prose written from the blocks.",
  } satisfies GenerationResult);
  const utils = render(
    <Outline
      deliverableId="dlv-1"
      sections={[section({ block_count: 1, ...over })]}
      onChanged={vi.fn()}
    />,
  );
  await screen.findByText("Capital intensity rises with scale");
  await userEvent.click(screen.getByRole("button", { name: /generate draft/i }));
  await waitFor(() => expect(utils.container.querySelector(".ProseMirror")).toBeTruthy());
  await waitFor(() => expect(editorHolder.current).toBeTruthy());
  return utils;
}

describe("Outline — manual /write edit persistence (SPR-02)", () => {
  it("persists a manual edit to prose_text via updateSectionProse (RED on main — no onContentChange wired)", async () => {
    await mountWithDraft();
    updateSectionProseMock.mockClear();

    await typeInEditor("Sharpened by the operator. ");

    // The debounced autosave must reach the persistence API with the edited
    // prose. On main the mount passes no onContentChange, so this never fires —
    // the dropped edit, proven.
    await waitFor(
      () => expect(updateSectionProseMock).toHaveBeenCalled(),
      { timeout: 3000 },
    );
    expect(updateSectionProseMock).toHaveBeenCalledWith(
      "sec-1",
      expect.objectContaining({
        prose_text: expect.stringContaining("Sharpened by the operator"),
        promote_to_graph: false,
      }),
    );
  });

  it("edit → reload re-fetch shows the edited prose (round-trip, reload direction)", async () => {
    await mountWithDraft();
    await typeInEditor("Reloaded edit body kept. ");
    await waitFor(
      () => expect(updateSectionProseMock).toHaveBeenCalled(),
      { timeout: 3000 },
    );
    const [, req] = updateSectionProseMock.mock.calls.at(-1)!;
    const persisted = (req as { prose_text: string }).prose_text;

    // A reload calls GET /deliverables/{id}, which reads the SAME prose_text
    // column (app.py:2573) that updateSectionProse just wrote (app.py:2801).
    // Re-mount with that persisted value standing in for the re-fetched section.
    cleanup();
    editorHolder.current = null;
    getSectionBlocksMock.mockResolvedValue([block()]);
    render(
      <Outline
        deliverableId="dlv-1"
        sections={[section({ block_count: 1, prose_text: persisted, prose_provenance: {} })]}
        onChanged={vi.fn()}
      />,
    );
    await screen.findByText("Capital intensity rises with scale");
    // The reloaded section carries the edit — the X-ray reads it back.
    await userEvent.click(await screen.findByRole("button", { name: /^X-ray$/i }));
    const xray = await screen.findByTestId("xray");
    expect(xray.textContent ?? "").toContain("Reloaded edit body kept");
  });

  it("shows 'Saved' only after a confirmed persistence, never before", async () => {
    await mountWithDraft();
    // Before an edit there is nothing pending — no false "Saved".
    expect(screen.queryByText(/^Saved\b/i)).toBeNull();

    await typeInEditor("Body worth saving. ");
    await waitFor(
      () => expect(updateSectionProseMock).toHaveBeenCalled(),
      { timeout: 3000 },
    );
    // "Saved" appears only after the persistence resolves.
    await waitFor(() => expect(screen.getByText(/^Saved\b/i)).toBeTruthy());
  });

  it("never shows 'saved' over a failed save — surfaces the error, does not swallow it", async () => {
    updateSectionProseMock.mockRejectedValue(
      new ApiError("PATCH /sections/{id}/prose failed: HTTP 500", 500, "boom"),
    );
    await mountWithDraft();

    await typeInEditor("An edit whose save will fail. ");

    // The failure is surfaced (unlike the edit.captured .catch(()=>{})).
    await waitFor(
      () => expect(screen.getByText(/couldn.t save/i)).toBeTruthy(),
      { timeout: 3000 },
    );
    // And the optimistic "saved as you write" / "Saved" copy is NOT shown over
    // the failed save.
    expect(screen.queryByText(/saved as you write/i)).toBeNull();
    expect(screen.queryByText(/^Saved\b/i)).toBeNull();
  });
});
