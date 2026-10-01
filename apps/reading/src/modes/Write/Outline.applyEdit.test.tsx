import { setSectionProseOwner } from "./sectionProse";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import { act, cleanup, render, screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import type { Editor } from "@tiptap/react";

import type { SectionResponse } from "../../lib/api";
import type { OutlineBlockView } from "./writeApi";

/**
 * Outline.applyEdit — the Cmd+K selection edit (CK-5) lands IN the editor.
 *
 * The model's edited span must become a real editor transaction: the editor
 * shows it, and the autosave persists it (the same path a keystroke takes).
 * Splicing it into the X-ray's prose only (the pre-R3 behaviour) left the
 * editor without the edit and the server without it, so a reload lost it and
 * the next keystroke overwrote it.
 *
 * The shared FloatMenu and its selection hook are stubbed here (jsdom cannot
 * make a DOM selection reach them); the editor is the real TipTap one.
 */

const {
  getSectionBlocksMock,
  updateSectionProseMock,
  editorHolder,
  selectionHolder,
} = vi.hoisted(() => ({
  getSectionBlocksMock: vi.fn(),
  updateSectionProseMock: vi.fn(),
  editorHolder: { current: null as { editor: unknown } | null },
  selectionHolder: { current: null as { text: string; rect: object; provenance: object } | null },
}));

vi.mock("./writeApi", async (orig) => ({
  ...(await orig<typeof import("./writeApi")>()),
  getSectionBlocks: getSectionBlocksMock,
  generateSection: vi.fn(),
  placeBlock: vi.fn(),
  moveBlock: vi.fn(),
}));

vi.mock("../../lib/api", async (orig) => ({
  ...(await orig<typeof import("../../lib/api")>()),
  createSection: vi.fn().mockResolvedValue({}),
  updateSectionProse: updateSectionProseMock,
  postTypedEvent: vi.fn().mockResolvedValue({}),
}));

vi.mock("../shared/FloatMenu/useFloatMenuSelection", () => ({
  useFloatMenuSelection: () => selectionHolder.current,
}));

vi.mock("../shared/FloatMenu/FloatMenu", () => ({
  default: (props: { onApplyEdit?: (t: string) => void }) => (
    <button type="button" onClick={() => props.onApplyEdit?.("Sharper sentence.")}>
      apply model edit
    </button>
  ),
}));

vi.mock("@tiptap/react", async (orig) => {
  const actual = await orig<typeof import("@tiptap/react")>();
  return {
    ...actual,
    useEditor: (options: unknown, deps?: unknown) => {
      const ed = (actual.useEditor as (o: unknown, d?: unknown) => unknown)(options, deps);
      if (ed) editorHolder.current = { editor: ed };
      return ed;
    },
  };
});

import Outline from "./Outline";
import { toast } from "../../components/lemon/LemonToast";

function editor(): Editor {
  if (!editorHolder.current) throw new Error("editor not mounted");
  return editorHolder.current.editor as Editor;
}

function section(prose: string): SectionResponse {
  return {
    section_id: "sec-1",
    deliverable_id: "dlv-1",
    parent_section_id: null,
    section_index: 0,
    title: "Thesis",
    prose_text: prose,
    prose_provenance: {},
    block_count: 1,
  };
}

const BLOCK: OutlineBlockView = {
  outline_block_id: "oblk-1",
  section_id: "sec-1",
  block_kind: "insight",
  provenance_kind: "graph_node",
  node_id: "n1",
  content: null,
  node_label: "Capital intensity rises with scale",
  block_index: 0,
  is_user_originated: false,
};

beforeEach(() => {
  setSectionProseOwner(null);
  setSectionProseOwner("writing-test-owner");
  getSectionBlocksMock.mockReset().mockResolvedValue([BLOCK]);
  updateSectionProseMock
    .mockReset()
    .mockResolvedValue({ status: "saved", section_id: "sec-1", claim_node_id: null, claim_event_id: null });
  editorHolder.current = null;
  selectionHolder.current = null;
});
afterEach(() => { cleanup(); setSectionProseOwner(null); });

const text = (c: HTMLElement) => c.querySelector(".ProseMirror")?.textContent ?? "";

describe("Outline — Cmd+K apply edit lands in the editor (cockpit R3)", () => {
  it("the edited span replaces the selection in the editor and is persisted", async () => {
    selectionHolder.current = { text: "Weak sentence.", rect: { top: 0, left: 0, width: 1, height: 1 }, provenance: {} };
    const { container } = render(
      <Outline deliverableId="dlv-1" sections={[section("Weak sentence. Second sentence.")]} onChanged={vi.fn()} />,
    );
    await waitFor(() => expect(editorHolder.current).toBeTruthy());
    await userEvent.click(screen.getByRole("button", { name: "apply model edit" }));
    expect(text(container)).toBe("Sharper sentence. Second sentence.");
    await waitFor(() => expect(updateSectionProseMock).toHaveBeenCalled(), { timeout: 3000 });
    const [, req] = updateSectionProseMock.mock.calls.at(-1)!;
    const r = req as { prose_text: string; original_text?: string };
    expect(r.prose_text).toBe("Sharper sentence. Second sentence.");
    expect(r.original_text).toBe("Weak sentence. Second sentence.");
  });

  it("replaces the occurrence the editor has selected, not the first match", async () => {
    selectionHolder.current = { text: "Same words.", rect: { top: 0, left: 0, width: 1, height: 1 }, provenance: {} };
    const { container } = render(
      <Outline deliverableId="dlv-1" sections={[section("Same words.\n\nSame words.")]} onChanged={vi.fn()} />,
    );
    await waitFor(() => expect(editorHolder.current).toBeTruthy());
    // The operator selected the SECOND paragraph (positions 14..25).
    const doc = editor().state.doc;
    const second = doc.child(0).nodeSize + 1;
    await act(async () => {
      editor().commands.setTextSelection({ from: second, to: second + "Same words.".length });
    });
    await userEvent.click(screen.getByRole("button", { name: "apply model edit" }));
    const ps = [...container.querySelectorAll(".ProseMirror p")].map((p) => p.textContent);
    expect(ps).toEqual(["Same words.", "Sharper sentence."]);
  });

  it("a selection that is no longer in the editor changes nothing and says so", async () => {
    selectionHolder.current = { text: "Gone text.", rect: { top: 0, left: 0, width: 1, height: 1 }, provenance: {} };
    const { container } = render(
      <Outline deliverableId="dlv-1" sections={[section("Present text.")]} onChanged={vi.fn()} />,
    );
    await waitFor(() => expect(editorHolder.current).toBeTruthy());
    const warn = vi.spyOn(toast, "warn");
    await userEvent.click(screen.getByRole("button", { name: "apply model edit" }));
    expect(text(container)).toBe("Present text.");
    await new Promise((r) => setTimeout(r, 900));
    expect(updateSectionProseMock).not.toHaveBeenCalled();
    expect(warn).toHaveBeenCalled();
    warn.mockRestore();
  });
});
