import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import { act, cleanup, fireEvent, render, screen, waitFor } from "@testing-library/react";
import { MemoryRouter, Route, Routes } from "react-router-dom";
import type { Editor } from "@tiptap/react";

import { setSectionProseOwner } from "./sectionProse";

/**
 * Outline.race.test — CR-F1: the writing save-race (R11 no-edit-loss).
 *
 * The flagship trust contract, reproduced against the REAL Outline (and the
 * real WriteHome Canvas↔Outline toggle), not a hand-rolled queue:
 *
 *   an older editor mount's PATCH must never overwrite a newer draft after
 *   unmount/remount, even when the older request COMPLETES LAST. The operator
 *   must never see "Saved" for prose that a stale request then replaces.
 *
 * The server stand-in is last-completed-write-wins and is settled LIFO (the
 * newest in-flight request completes first) — the adversarial completion
 * order under which any reintroduced race loses the newer draft.
 *
 * ── MUTATION THAT REINTRODUCES THE RACE (this file goes red) ──────────────
 * In `sectionProse.ts`, drop the per-section shared handle so every mount
 * builds its own writer (the pre-seam SectionCard shape):
 *
 *   export function sectionProse(deliverableId, sectionId, prose, provenance) {
 *     const key = JSON.stringify([deliverableId, sectionId]);
 *     // const existing = sections.get(key);        ← DELETE this lookup
 *     // if (existing) { ...; return existing; }    ← DELETE this return
 *     const session = new SectionProse(key, sectionId, prose, provenance);
 *     ...
 *   }
 *
 * Two writers then own one section: the old mount's in-flight PATCH lands
 * after the new mount's save and stored prose reverts to the older edit.
 * Verified red on this mutation (4 failed):
 *
 *   expected ' Older mount edit.Saved prose.' to be ' Newer mount edit.Saved prose.'
 *
 * — the exact F1 symptom (the older mount's edit wins the server). A second
 * red mutation: in SectionProse.subscribe's cleanup, remove the
 * `if (this.timer !== null) void this.flush();` unmount flush — the pending
 * edit is then lost on leaving the piece before the 800 ms debounce.
 */

const {
  getSectionBlocksMock,
  updateSectionProseMock,
  postTypedEventMock,
  getDeliverableMock,
  editorHolder,
} = vi.hoisted(() => ({
  getSectionBlocksMock: vi.fn(),
  updateSectionProseMock: vi.fn(),
  postTypedEventMock: vi.fn(),
  getDeliverableMock: vi.fn(),
  editorHolder: { current: null as { editor: unknown } | null },
}));

vi.mock("./writeApi", async (orig) => ({
  ...(await orig<typeof import("./writeApi")>()),
  getSectionBlocks: getSectionBlocksMock,
  searchRepository: vi.fn(async () => []),
  listFolders: vi.fn(async () => ({ folders: [] })),
  placeBlock: vi.fn(async () => "oblk-new"),
  moveBlock: vi.fn(async () => undefined),
  generateSection: vi.fn(async () => ({ status: "gap", section_id: "sec-1", detail: "no blocks" })),
}));

vi.mock("../../lib/api", async (orig) => ({
  ...(await orig<typeof import("../../lib/api")>()),
  getDeliverable: getDeliverableMock,
  listDeliverables: vi.fn(async () => ({ count: 0, deliverables: [] })),
  listInvestigations: vi.fn(async () => ({ count: 0, investigations: [] })),
  createSection: vi.fn(async () => ({})),
  updateSectionProse: updateSectionProseMock,
  postTypedEvent: postTypedEventMock,
  apiFetch: vi.fn(async () => ({ ok: false, status: 404, json: async () => ({}), text: async () => "" })),
}));

// Capture the REAL TipTap editor (the Outline→WriteEditor mount stays real)
// so a test drives genuine ProseMirror transactions into the save path.
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

// The imported SPR-03 Canvas is not under test; the toggle's UNMOUNT of the
// Outline is. A marker element is enough — and honest about that boundary.
vi.mock("../DeepResearchWorkspace/Canvas/Canvas", () => ({
  default: ({ investigationId }: { investigationId: string }) => (
    <div data-testid="research-canvas-stand-in">{investigationId}</div>
  ),
}));

import Outline from "./Outline";
import WriteHome from "./WriteHome";

function editor(): Editor {
  if (!editorHolder.current) throw new Error("editor not mounted");
  return editorHolder.current.editor as Editor;
}

/** A genuine manual prose edit on the live editor (jsdom cannot type into
 *  ProseMirror; a real transaction fires the real onUpdate → onContentChange). */
async function typeInEditor(text: string): Promise<void> {
  await act(async () => {
    editor().commands.insertContent(text);
  });
}

/**
 * Last-completed-write-wins server, settled LIFO (newest request first) so a
 * stale request that is still in flight is the one that lands last.
 */
function racingServer() {
  const saves: { text: string; done: boolean; complete: () => void }[] = [];
  let stored = "Saved prose.";
  updateSectionProseMock.mockImplementation(
    (_id: string, body: { prose_text: string }) =>
      new Promise<void>((resolve) => {
        const entry: { text: string; done: boolean; complete: () => void } = {
          text: body.prose_text,
          done: false,
          complete: () => {
            entry.done = true;
            stored = body.prose_text;
            resolve();
          },
        };
        saves.push(entry);
      }),
  );
  const pending = () => saves.filter((s) => !s.done);
  /** Release every outstanding save in LIFO order, letting new saves issue. */
  async function settleAllLifo(): Promise<void> {
    for (let guard = 0; guard < 12; guard++) {
      const open = pending();
      if (open.length === 0) break;
      open[open.length - 1].complete();
      await act(async () => {
        await Promise.resolve();
        await Promise.resolve();
      });
    }
  }
  return { saves, pending, settleAllLifo, stored: () => stored };
}

const DETAIL = {
  deliverable_id: "dlv-1",
  title: "Why the finches matter",
  deliverable_kind: "general_essay",
  status: "draft",
  investigation_root_id: "inv-1",
  created_at: null,
  updated_at: null,
  section_count: 1,
  sections: [
    {
      section_id: "sec-1",
      deliverable_id: "dlv-1",
      parent_section_id: null,
      section_index: 0,
      title: "Thesis",
      prose_text: "Saved prose.",
      prose_provenance: null,
      block_count: 1,
    },
  ],
};

function section(over: Record<string, unknown> = {}) {
  return {
    section_id: "sec-1",
    deliverable_id: "dlv-1",
    parent_section_id: null,
    section_index: 0,
    title: "Thesis",
    prose_text: "Saved prose.",
    prose_provenance: null,
    block_count: 1,
    ...over,
  };
}

beforeEach(() => {
  setSectionProseOwner(null);
  setSectionProseOwner("race-test-owner");
  getSectionBlocksMock.mockReset().mockResolvedValue([]);
  updateSectionProseMock.mockReset();
  postTypedEventMock.mockReset().mockResolvedValue({});
  getDeliverableMock.mockReset().mockResolvedValue(DETAIL);
  editorHolder.current = null;
  Object.defineProperty(window, "matchMedia", {
    writable: true,
    configurable: true,
    value: (query: string) => ({
      matches: false,
      media: query,
      onchange: null,
      addEventListener: () => {},
      removeEventListener: () => {},
      addListener: () => {},
      removeListener: () => {},
      dispatchEvent: () => false,
    }),
  });
});
afterEach(() => {
  cleanup();
  setSectionProseOwner(null);
  vi.useRealTimers();
});

async function mountOutline() {
  const view = render(
    <Outline deliverableId="dlv-1" sections={[section()]} onChanged={vi.fn()} />,
  );
  await waitFor(() => expect(editorHolder.current).toBeTruthy());
  return view;
}

async function mountPiece() {
  const view = render(
    <MemoryRouter initialEntries={["/write/dlv-1"]}>
      <Routes>
        <Route path="/write/:deliverableId" element={<WriteHome />} />
      </Routes>
    </MemoryRouter>,
  );
  await screen.findByRole("heading", { name: "Why the finches matter" });
  await waitFor(() => expect(editorHolder.current).toBeTruthy());
  return view;
}

describe("CR-F1 — an older mount's save never overwrites a newer draft", () => {
  it("unmount/remount: the older in-flight save completing LAST does not win (F1)", async () => {
    const server = racingServer();
    const first = await mountOutline();
    await typeInEditor(" Older mount edit.");
    const older = editor().getText();
    // Leaving before the debounce: the flush is immediate (not 800 ms later).
    first.unmount();
    await act(async () => {});
    expect(server.saves).toHaveLength(1);
    expect(server.saves[0].text).toBe(older);

    // A new mount of the same section.
    editorHolder.current = null;
    await mountOutline();
    await typeInEditor(" Newer mount edit.");
    const newest = editor().getText();
    expect(newest).not.toBe(older);

    // Let every debounce fire. The pipeline must stay serialized behind the
    // in-flight save (under the fix only one request exists at a time; a
    // reintroduced race shows two parallel requests here).
    await act(async () => {
      await new Promise((resolve) => setTimeout(resolve, 850));
    });

    // Adversarial completion order (LIFO): whatever is outstanding settles
    // newest-first. Under the fix the follow-up send carries the LATEST
    // text; under the race the older request completes last and wins.
    await server.settleAllLifo();
    expect(server.stored()).toBe(newest);
    expect(editor().getText()).toBe(newest);
    await screen.findByText(/^Saved\./);
  });

  it("Canvas↔Outline toggle: the older in-flight save completing LAST does not win (F1)", async () => {
    const server = racingServer();
    await mountPiece();
    await typeInEditor(" Older mount edit.");
    const older = editor().getText();

    // Toggle to the research canvas: Outline (and its editor) UNMOUNTS for
    // real — the WriteHome pieceView swap at WriteHome.tsx:440-456.
    const toCanvas = screen.getByRole("button", { name: "research canvas" });
    act(() => {
      fireEvent.click(toCanvas);
    });
    await screen.findByTestId("research-canvas-stand-in");
    await act(async () => {});
    // Immediate unmount flush — no debounce wait.
    expect(server.saves).toHaveLength(1);
    expect(server.saves[0].text).toBe(older);

    // Toggle back: a NEW Outline instance mounts from the same section.
    act(() => {
      fireEvent.click(screen.getByRole("button", { name: "outline" }));
    });
    await waitFor(() => expect(editorHolder.current).toBeTruthy());
    await typeInEditor(" Newer mount edit.");
    const newest = editor().getText();
    expect(newest).not.toBe(older);

    // Let every debounce fire (serialization holds the request count at one
    // under the fix; a reintroduced race issues a parallel save here).
    await act(async () => {
      await new Promise((resolve) => setTimeout(resolve, 850));
    });

    await server.settleAllLifo();
    expect(server.stored()).toBe(newest);
    expect(editor().getText()).toBe(newest);
    await screen.findByText(/^Saved\./);
  });

  it("the remounted editor retains the local draft across unmount/remount", async () => {
    const server = racingServer();
    const first = await mountOutline();
    await typeInEditor(" Older mount edit.");
    const older = editor().getText();
    first.unmount();
    await act(async () => {});
    editorHolder.current = null;
    await mountOutline();
    // Same mutation lifetime: the retained local draft, not fresh server prose.
    expect(editor().getText()).toBe(older);
    expect(server.saves[0].text).toBe(older);
  });

  it("unmount flush is immediate (no 800 ms debounce wait) and a failed flush retains the text in a designed failure state", async () => {
    const first = await mountOutline();
    vi.useFakeTimers();
    await typeInEditor(" Keep this through the failure.");
    const text = editor().getText();
    const failing = Promise.reject(new Error("offline"));
    // Swallow the rejection for the unhandled-rejection detector; the
    // session's catch turns it into the designed error state.
    failing.catch(() => {});
    updateSectionProseMock.mockReturnValueOnce(failing);
    first.unmount();
    await act(async () => {
      await Promise.resolve();
    });
    // Issued synchronously on unmount — NOT after the 800 ms debounce
    // (fake timers have advanced 0 ms).
    expect(updateSectionProseMock).toHaveBeenCalledTimes(1);
    vi.useRealTimers();

    editorHolder.current = null;
    await mountOutline();
    // Text retained; designed failure state ("Couldn't save" + Retry).
    expect(editor().getText()).toBe(text);
    expect(screen.getByText(/couldn.t save/i)).toBeTruthy();
    expect(screen.getByRole("button", { name: /retry/i })).toBeTruthy();
  });
});
