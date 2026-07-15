import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import { act, cleanup, render, screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import type { Editor } from "@tiptap/react";

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

  it("replaces local X-ray authority with the server's stale validity response", async () => {
    await mountWithDraft();
    updateSectionProseMock.mockResolvedValue({
      status: "saved",
      section_id: "sec-1",
      claim_node_id: null,
      claim_event_id: null,
      changed: true,
      prose_text: "Operator-edited paragraph.",
      prose_provenance: null,
      prose_provenance_status: "stale",
      prose_provenance_validity: {
        schema_version: 1,
        prose_sha256: "server",
        status: "stale",
        paragraphs: {
          "0": { text_sha256: "paragraph", status: "stale", origin: "manual" },
        },
      },
    });
    await typeInEditor("Operator-edited paragraph. ");
    await waitFor(() => expect(updateSectionProseMock).toHaveBeenCalled(), { timeout: 3000 });
    await userEvent.click(screen.getByRole("button", { name: /^X-ray$/i }));
    expect(await screen.findByText(/edited since grounding/i)).toBeTruthy();
    expect(screen.queryByText("Capital intensity rises with scale")).toBeTruthy();
  });

  it("serializes overlapping autosaves against the confirmed server baseline", async () => {
    let resolveFirst!: (value: unknown) => void;
    const firstResponse = new Promise((resolve) => { resolveFirst = resolve; });
    updateSectionProseMock
      .mockImplementationOnce(() => firstResponse)
      .mockResolvedValueOnce({
        status: "saved", section_id: "sec-1", claim_node_id: null, claim_event_id: null,
        changed: true, prose_text: "second saved text", prose_provenance: null,
        prose_provenance_status: "ungrounded",
        prose_provenance_validity: {
          schema_version: 1, prose_sha256: "second", status: "ungrounded", paragraphs: {},
        },
      });
    await mountWithDraft();
    await typeInEditor("First edit. ");
    await waitFor(() => expect(updateSectionProseMock).toHaveBeenCalledTimes(1), { timeout: 3000 });
    await typeInEditor("Second edit. ");
    await new Promise((resolve) => setTimeout(resolve, 900));
    expect(updateSectionProseMock).toHaveBeenCalledTimes(1);
    const firstText = updateSectionProseMock.mock.calls[0][1].prose_text;
    resolveFirst({
      status: "saved", section_id: "sec-1", claim_node_id: null, claim_event_id: null,
      changed: true, prose_text: firstText, prose_provenance: null,
      prose_provenance_status: "ungrounded",
      prose_provenance_validity: {
        schema_version: 1, prose_sha256: "first", status: "ungrounded", paragraphs: {},
      },
    });
    await waitFor(() => expect(updateSectionProseMock).toHaveBeenCalledTimes(2));
    expect(updateSectionProseMock.mock.calls[1][1]).toEqual(
      expect.objectContaining({ original_text: firstText }),
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
