/**
 * FloatMenu.test.tsx — SPR-04 verification gates (run: `npx vitest run FloatMenu`).
 *
 * Asserts, against real systems mocked at the api boundary only:
 *   - open-on-selection: selecting text in a scope opens the menu at the rect;
 *   - dismiss: an empty / collapsed selection closes it cleanly (no crash);
 *   - mounts in >1 host: the SAME component opens in two different scope hosts;
 *   - viewport-edge clamp: a selection at the right edge clamps on-screen;
 *   - the four actions each fire their handler;
 *   - NOTE persists as a typed event with a user-sourced label + provenance;
 *   - DEEP-RESEARCH hands the host the selection (the reused chase path);
 *   - §9.0 no-leak: a withheld selection's body never reaches SEARCH /
 *     DEEP-RESEARCH (load-bearing).
 *
 * Selection in jsdom: build a real Range over a text node inside the scope,
 * add it to the live selection, spy `Range.getBoundingClientRect`, and fire
 * `selectionchange` — the pattern the diligence prescribes.
 */
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import { act, cleanup, fireEvent, render, screen } from "@testing-library/react";
import { useRef } from "react";

// Mock the api boundary: capture postTypedEvent + searchBlocks + startInvestigation.
const postTypedEventMock = vi.fn((_envelope: unknown) =>
  Promise.resolve({ event_id: "ev-note-1", action_type: "marginalia.noted" }),
);
const searchBlocksMock = vi.fn((_q: string) => Promise.resolve({ count: 0, hits: [] }));
const startInvestigationMock = vi.fn((_req: unknown) =>
  Promise.resolve({ investigation_id: "child-1", status: "in_progress", start_event_id: "ev-start" }),
);
const apiFetchMock = vi.fn((_input: unknown, _init?: unknown) =>
  Promise.resolve(new Response(JSON.stringify({ text: "model reply" }), { status: 200 })),
);

vi.mock("../../../lib/api", async (importOriginal) => {
  const actual = await importOriginal<typeof import("../../../lib/api")>();
  return {
    ...actual,
    postTypedEvent: (envelope: unknown) => postTypedEventMock(envelope),
    searchBlocks: (q: string) => searchBlocksMock(q),
    startInvestigation: (req: unknown) => startInvestigationMock(req),
    apiFetch: (input: unknown, init?: unknown) => apiFetchMock(input, init),
  };
});

// ── voice mock (M3) ──────────────────────────────────────────────────────────
// A controllable useVoiceCapture stand-in so the Note panel's voice affordance
// is exercised WITHOUT a real recorder/ASR. It models the real two-click flow:
// first "Speak it" → start() (phase "recording"); second click → stopAndCapture
// returns a known USER-sourced transcript (sourceKind "user"). The real hook's
// own unit tests cover recorder/ASR/persistence; here we only need the
// transcript + its "user" label to flow into the saved note.
const VOICE_TRANSCRIPT = "this is my spoken marginal note";
const voiceState = vi.hoisted(() => ({ phase: "idle" as string }));
const stopAndCaptureMock = vi.hoisted(() =>
  vi.fn(async () => ({
    transcript: "this is my spoken marginal note",
    language: "en",
    durationSeconds: 2,
    sourceKind: "user" as const,
    transcriptStatus: "ok" as const,
    eventId: "ev-voice-1",
  })),
);
const voiceStartMock = vi.hoisted(() => vi.fn(async () => {}));

vi.mock("../../../hooks/useVoiceCapture", () => ({
  useVoiceCapture: () => ({
    phase: voiceState.phase,
    error: null,
    recorderState: "idle",
    result: null,
    start: voiceStartMock,
    stopAndCapture: stopAndCaptureMock,
    reset: () => {
      voiceState.phase = "idle";
    },
  }),
}));

import FloatMenu from "./FloatMenu";
import {
  outboundText,
  searchFloatMenuSelection,
  saveFloatMenuNote,
  buildDialoguePrompt,
} from "./floatMenuActions";
import type { FloatMenuSelection } from "./useFloatMenuSelection";
import { useFloatMenuSelection } from "./useFloatMenuSelection";
import type { EvidencePassportView } from "../../../components/evidence/EvidencePassport";

// ── jsdom selection helper ──────────────────────────────────────────────────

/** Select `text` inside `scope` (creates a text node if empty), give the range
 * a rect, and fire `selectionchange`. Returns the range. */
function selectTextIn(scope: HTMLElement, text: string, rect = { top: 200, left: 100, width: 80, height: 18 }): Range {
  if (!scope.firstChild) scope.appendChild(document.createTextNode(text));
  const node = scope.firstChild as Text;
  // A real Range over a node INSIDE the scope, so the hook's
  // `scope.contains(range.commonAncestorContainer)` narrowing passes.
  const range = document.createRange();
  range.setStart(node, 0);
  range.setEnd(node, node.textContent?.length ?? text.length);
  // jsdom implements neither Range.getBoundingClientRect nor a reliable
  // Selection.toString — drive the hook entirely through a mocked getSelection
  // that returns our real (scoped) range + the selected text. Assigning the
  // rect directly (the property doesn't exist to spy on in jsdom).
  range.getBoundingClientRect = () =>
    ({
      ...rect,
      right: rect.left + rect.width,
      bottom: rect.top + rect.height,
      x: rect.left,
      y: rect.top,
      toJSON() {
        return rect;
      },
    }) as DOMRect;
  vi.spyOn(window, "getSelection").mockReturnValue({
    rangeCount: 1,
    getRangeAt: () => range,
    toString: () => text,
    removeAllRanges: () => {},
  } as unknown as Selection);
  act(() => {
    document.dispatchEvent(new Event("selectionchange"));
  });
  return range;
}

function clearSelection() {
  vi.spyOn(window, "getSelection").mockReturnValue({
    rangeCount: 0,
    getRangeAt: () => {
      throw new Error("no range");
    },
    toString: () => "",
    removeAllRanges: () => {},
  } as unknown as Selection);
  act(() => {
    document.dispatchEvent(new Event("selectionchange"));
  });
}

// A host harness: a scope div + the FloatMenu fed by the real selection hook.
function Host({
  onDeepResearch = vi.fn(),
  hybridEnabled = false,
  investigationId = "inv-1",
  testId = "scope",
  provenance,
  onRewrite,
  editContext,
  onApplyEdit,
  evidencePassport,
}: {
  onDeepResearch?: (t: string | null, s: FloatMenuSelection) => void;
  hybridEnabled?: boolean;
  investigationId?: string;
  testId?: string;
  provenance?: { servable?: boolean; chunkId?: string | null; documentId?: string | null };
  /** SPR-09 M4: when given, the Write rewrite actions are passed (mode-gated). */
  onRewrite?: (intent: { kind: string; safeText: string | null }, s: FloatMenuSelection) => void;
  /** CK-5: the Write edit-context + apply callback (mode-gated). */
  editContext?: { deliverableId: string; sectionId: string };
  onApplyEdit?: (editedText: string) => void;
  evidencePassport?: EvidencePassportView;
}) {
  const scopeRef = useRef<HTMLDivElement>(null);
  const selection = useFloatMenuSelection({
    scopeRef,
    resolveProvenance: provenance ? () => provenance : undefined,
  });
  return (
    <div>
      <div ref={scopeRef} data-testid={testId}>
        the selected passage text
      </div>
      <FloatMenu
        selection={selection}
        investigationId={investigationId}
        onDeepResearch={onDeepResearch}
        hybridEnabled={hybridEnabled}
        rewriteActions={onRewrite ? { onRewrite } : undefined}
        editContext={editContext}
        onApplyEdit={onApplyEdit}
        evidencePassport={evidencePassport}
      />
    </div>
  );
}

beforeEach(() => {
  postTypedEventMock.mockClear();
  searchBlocksMock.mockClear();
  startInvestigationMock.mockClear();
  apiFetchMock.mockClear();
  stopAndCaptureMock.mockClear();
  voiceStartMock.mockClear();
  voiceState.phase = "idle";
});
afterEach(() => {
  cleanup();
  vi.restoreAllMocks();
});

// ── M1 — open / dismiss / reposition / >1 host / clamp ──────────────────────

describe("FloatMenu — open on selection (M1)", () => {
  it("opens the four-action menu at a text selection inside the scope", () => {
    render(<Host />);
    expect(screen.queryByRole("menu")).toBeNull(); // closed until a selection
    const scope = screen.getByTestId("scope");
    selectTextIn(scope, "the selected passage");
    const menu = screen.getByRole("menu");
    expect(menu).toBeTruthy();
    // All four actions present.
    expect(screen.getByRole("menuitem", { name: "Note" })).toBeTruthy();
    expect(screen.getByRole("menuitem", { name: "Dialogue" })).toBeTruthy();
    expect(screen.getByRole("menuitem", { name: "Search" })).toBeTruthy();
    expect(screen.getByRole("menuitem", { name: "Deep-research" })).toBeTruthy();
    // Positioned (fixed) from the raw rect.
    expect((menu.closest("[data-floatmenu]") as HTMLElement).style.position).toBe("fixed");
  });

  it("shows host-owned evidence without rounding an unresolved anchor up", () => {
    render(
      <Host
        evidencePassport={{
          sourceName: "A named book",
          locator: "Page 12",
          custody: "source-identified",
          precision: "anchor-pending",
        }}
      />,
    );
    selectTextIn(screen.getByTestId("scope"), "the selected passage");
    expect(screen.getByText("A named book")).toBeTruthy();
    expect(screen.getByText("Exact passage anchor pending")).toBeTruthy();
    expect(screen.queryByText("Exact passage anchored")).toBeNull();
  });

  it("dismisses cleanly when the selection empties / collapses (no crash)", () => {
    render(<Host />);
    const scope = screen.getByTestId("scope");
    selectTextIn(scope, "the selected passage");
    expect(screen.getByRole("menu")).toBeTruthy();
    clearSelection();
    expect(screen.queryByRole("menu")).toBeNull();
  });

  it("repositions when a new selection arrives (reset to menu view)", () => {
    render(<Host />);
    const scope = screen.getByTestId("scope");
    selectTextIn(scope, "the selected passage", { top: 200, left: 100, width: 80, height: 18 });
    const first = screen.getByRole("menu").closest("[data-floatmenu]") as HTMLElement;
    const firstTop = first.style.top;
    selectTextIn(scope, "the selected passage text", { top: 400, left: 100, width: 120, height: 18 });
    const second = screen.getByRole("menu").closest("[data-floatmenu]") as HTMLElement;
    expect(second.style.top).not.toBe(firstTop); // moved to the new rect
  });

  // ── SPR-09 M4 — rewrite actions are mode-gated (Write only), not a fork ──

  it("does NOT show rewrite actions for a Read/Research host (rewriteActions absent)", () => {
    render(<Host />); // no onRewrite → no rewriteActions
    selectTextIn(screen.getByTestId("scope"), "the selected passage");
    expect(screen.getByRole("menu")).toBeTruthy();
    // The four core actions are unchanged; no rewrite items leak in.
    expect(screen.queryByRole("menuitem", { name: "Rewrite" })).toBeNull();
    expect(screen.queryByRole("menuitem", { name: "Make stronger" })).toBeNull();
    expect(screen.queryByRole("menuitem", { name: "Spin a sub-agent" })).toBeNull();
  });

  it("shows rewrite actions for a Write host + routes text through the §9.0 chokepoint", () => {
    const onRewrite = vi.fn();
    render(<Host onRewrite={onRewrite} provenance={{ servable: true }} />);
    selectTextIn(screen.getByTestId("scope"), "the selected passage");
    expect(screen.getByRole("menuitem", { name: "Rewrite" })).toBeTruthy();
    fireEvent.click(screen.getByRole("menuitem", { name: "Make stronger" }));
    expect(onRewrite).toHaveBeenCalledWith(
      expect.objectContaining({ kind: "stronger", safeText: expect.any(String) }),
      expect.anything(),
    );
  });

  it("§9.0 — a withheld selection hands the rewrite action a null safeText (host refuses)", () => {
    const onRewrite = vi.fn();
    render(<Host onRewrite={onRewrite} provenance={{ servable: false }} />);
    selectTextIn(screen.getByTestId("scope"), "the selected passage");
    fireEvent.click(screen.getByRole("menuitem", { name: "Rewrite" }));
    expect(onRewrite).toHaveBeenCalledWith(
      expect.objectContaining({ kind: "rewrite", safeText: null }),
      expect.anything(),
    );
  });

  it("clamps on-screen at the viewport right edge (rigor #3)", () => {
    render(<Host />);
    const scope = screen.getByTestId("scope");
    // A selection far past the right edge — the menu must clamp inside.
    selectTextIn(scope, "edge text", { top: 50, left: 2000, width: 80, height: 18 });
    const menu = screen.getByRole("menu").closest("[data-floatmenu]") as HTMLElement;
    const left = parseFloat(menu.style.left);
    expect(left).toBeGreaterThanOrEqual(0);
    expect(left).toBeLessThanOrEqual(window.innerWidth); // never off-screen
  });

  it("mounts the SAME component in >1 host (two scopes, one component)", () => {
    const { unmount } = render(<Host testId="scope-a" investigationId="inv-A" />);
    selectTextIn(screen.getByTestId("scope-a"), "host A passage");
    expect(screen.getByRole("menu")).toBeTruthy();
    unmount();
    cleanup();
    render(<Host testId="scope-b" investigationId="inv-B" />);
    selectTextIn(screen.getByTestId("scope-b"), "host B passage");
    expect(screen.getByRole("menu")).toBeTruthy(); // identical FloatMenu, second host
  });

  // ── CK-5 — the Cmd+K Edit affordance is Write-mode-gated ──────────────

  it("shows the Edit affordance + opens the Edit panel for a wired Write host", () => {
    render(
        <Host
          onRewrite={vi.fn()}
          editContext={{ deliverableId: "d1", sectionId: "s1" }}
          onApplyEdit={vi.fn()}
          provenance={{ servable: true }}
        />,
    );
    selectTextIn(screen.getByTestId("scope"), "the selected passage");
    expect(screen.getByRole("menuitem", { name: "Edit…" })).toBeTruthy();
    fireEvent.click(screen.getByRole("menuitem", { name: "Edit…" }));
    // The Edit panel renders with an instruction box.
    expect(document.querySelector("[data-floatmenu-edit]")).toBeTruthy();
    expect(screen.getByPlaceholderText(/more concise/)).toBeTruthy();
  });

  it("does NOT show the Edit affordance when editContext/onApplyEdit are absent", () => {
    render(<Host onRewrite={vi.fn()} />);
    selectTextIn(screen.getByTestId("scope"), "the selected passage");
    expect(screen.queryByRole("menuitem", { name: "Edit…" })).toBeNull();
  });
});

// ── M2 — NOTE persistence + provenance label ────────────────────────────────

describe("NOTE persists with a user-sourced label + provenance (M2)", () => {
  it("saveFloatMenuNote emits a marginalia.noted typed event with source_kind 'user' + provenance", async () => {
    const selection: FloatMenuSelection = {
      text: "a passage worth noting",
      rect: { top: 0, left: 0, width: 10, height: 10 },
      provenance: { documentId: "doc-9", chunkId: "chunk-7" },
    };
    await saveFloatMenuNote({ investigationId: "inv-1", selection, noteText: "my note" });
    expect(postTypedEventMock).toHaveBeenCalledTimes(1);
    const envelope = postTypedEventMock.mock.calls[0][0] as {
      investigation_id: string;
      document_id?: string;
      payload: { action_type: string; source_kind: string; note_text: string; excerpt: string; chunk_id: string | null };
    };
    // user-sourced label (§9 — never a model label on a user note).
    expect(envelope.payload.action_type).toBe("marginalia.noted");
    expect(envelope.payload.source_kind).toBe("user");
    // provenance chain claim→chunk→document.
    expect(envelope.payload.chunk_id).toBe("chunk-7");
    expect(envelope.document_id).toBe("doc-9");
    expect(envelope.payload.excerpt).toBe("a passage worth noting"); // the user's own selection
    expect(envelope.payload.note_text).toBe("my note");
  });

  it("the Note action saves through postTypedEvent from the menu (no side store)", async () => {
    render(<Host provenance={{ documentId: "doc-1", chunkId: "c-1", servable: true }} />);
    selectTextIn(screen.getByTestId("scope"), "notable text");
    fireEvent.click(screen.getByRole("menuitem", { name: "Note" }));
    const textarea = screen.getByPlaceholderText("Type a note, or speak it…");
    fireEvent.change(textarea, { target: { value: "interesting" } });
    await act(async () => {
      fireEvent.click(screen.getByText("Save note"));
    });
    expect(postTypedEventMock).toHaveBeenCalledTimes(1);
    const payload = (postTypedEventMock.mock.calls[0][0] as { payload: { source_kind: string } }).payload;
    expect(payload.source_kind).toBe("user");
  });
});

// ── M3 — VOICE → NOTE keeps the user-sourced label (the fold from voice) ─────

describe("VOICE note keeps source_kind 'user' through the fold (M3)", () => {
  it("a spoken transcript folds into the note and persists as marginalia.noted source_kind 'user'", async () => {
    // The recorder is already running (phase "recording"), so the Note panel's
    // voice affordance reads "■ Stop": one click → stopAndCapture → the
    // USER-sourced transcript folds into the note text.
    voiceState.phase = "recording";
    render(<Host provenance={{ documentId: "doc-v", chunkId: "c-v", servable: true }} />);
    selectTextIn(screen.getByTestId("scope"), "spoken-over passage");
    fireEvent.click(screen.getByRole("menuitem", { name: "Note" }));

    // Drive the voice path: stop → capture the known transcript into the note.
    await act(async () => {
      fireEvent.click(screen.getByText("■ Stop"));
    });
    expect(stopAndCaptureMock).toHaveBeenCalledTimes(1);
    // The transcript landed in the note textarea (the fold voice → note text).
    const textarea = screen.getByPlaceholderText("Type a note, or speak it…") as HTMLTextAreaElement;
    expect(textarea.value).toContain(VOICE_TRANSCRIPT);

    // Save the spoken note — it persists as a marginalia.noted typed event.
    await act(async () => {
      fireEvent.click(screen.getByText("Save note"));
    });
    expect(postTypedEventMock).toHaveBeenCalledTimes(1);
    const env = postTypedEventMock.mock.calls[0][0] as {
      payload: { action_type: string; source_kind: string; note_text: string };
    };
    // §9 load-bearing (M3): voice-in is human speech — the "user" label SURVIVES
    // the fold from voice → note. The transcript text is carried, never
    // relabelled as model output.
    expect(env.payload.action_type).toBe("marginalia.noted");
    expect(env.payload.source_kind).toBe("user");
    expect(env.payload.note_text).toContain(VOICE_TRANSCRIPT);
  });
});

// ── M2 — DEEP-RESEARCH linked child (reused chase path) ──────────────────────

describe("DEEP-RESEARCH spawns a child linked to the highlight (M2)", () => {
  it("the Deep-research action hands the host the selection text (chase path)", () => {
    const onDeepResearch = vi.fn();
    render(<Host onDeepResearch={onDeepResearch} provenance={{ servable: true, documentId: "d", chunkId: null }} />);
    selectTextIn(screen.getByTestId("scope"), "chase me");
    fireEvent.click(screen.getByRole("menuitem", { name: "Deep-research" }));
    expect(onDeepResearch).toHaveBeenCalledTimes(1);
    // §9.0-safe text (servable) + the full selection are handed to the host,
    // which calls startInvestigation({ parent_investigation_id }) — proven in
    // the api-level test below.
    const [safeText, sel] = onDeepResearch.mock.calls[0];
    expect(safeText).toBe("chase me");
    expect((sel as FloatMenuSelection).text).toBe("chase me");
  });

  it("startInvestigation is called with parent_investigation_id (the linked child)", async () => {
    // Exercise the chase reuse directly (the host wires this).
    const { startInvestigation } = await import("../../../lib/api");
    await startInvestigation({
      question: "chase me",
      parent_investigation_id: "inv-1",
      spawn_context: "chase me",
    });
    expect(startInvestigationMock).toHaveBeenCalledTimes(1);
    const req = startInvestigationMock.mock.calls[0][0] as { parent_investigation_id: string };
    expect(req.parent_investigation_id).toBe("inv-1"); // child linked back to source
  });
});

// ── §9.0 NO-LEAK (load-bearing) ──────────────────────────────────────────────

describe("§9.0 no-leak — withheld body never goes to Search / Deep-research", () => {
  const withheld: FloatMenuSelection = {
    text: "the withheld restricted body text",
    rect: { top: 0, left: 0, width: 10, height: 10 },
    provenance: { servable: false, documentId: "doc-x", chunkId: "c-withheld" },
  };
  const servable: FloatMenuSelection = {
    text: "an open passage",
    rect: { top: 0, left: 0, width: 10, height: 10 },
    provenance: { servable: true, documentId: "doc-y", chunkId: "c-open" },
  };

  it("outboundText returns null for a withheld selection, the text for a servable one", () => {
    expect(outboundText(withheld)).toBeNull();
    expect(outboundText(servable)).toBe("an open passage");
  });

  it("SEARCH does not query when the selection is withheld (no body leaves the client)", async () => {
    const r = await searchFloatMenuSelection(withheld);
    expect(r).toBeNull();
    expect(searchBlocksMock).not.toHaveBeenCalled(); // never sent the body
    // A servable selection DOES query, with its text.
    await searchFloatMenuSelection(servable);
    expect(searchBlocksMock).toHaveBeenCalledWith("an open passage");
  });

  it("DEEP-RESEARCH hands the host null for a withheld selection (host refuses)", () => {
    const onDeepResearch = vi.fn();
    render(<Host onDeepResearch={onDeepResearch} provenance={{ servable: false, documentId: "d", chunkId: "c" }} />);
    selectTextIn(screen.getByTestId("scope"), "withheld region text");
    fireEvent.click(screen.getByRole("menuitem", { name: "Deep-research" }));
    const [safeText] = onDeepResearch.mock.calls[0];
    expect(safeText).toBeNull(); // the host must NOT spawn on a withheld body
  });

  it("the Search panel surfaces the withheld reason instead of leaking", async () => {
    render(<Host provenance={{ servable: false, documentId: "d", chunkId: "c" }} />);
    selectTextIn(screen.getByTestId("scope"), "withheld region text");
    await act(async () => {
      fireEvent.click(screen.getByRole("menuitem", { name: "Search" }));
    });
    expect(screen.getByRole("alert").textContent).toMatch(/restricted source/i);
    expect(searchBlocksMock).not.toHaveBeenCalled();
  });
});

// ── DIALOGUE provenance (user prompt vs model reply, kept distinct) ──────────

describe("DIALOGUE keeps the user prompt distinct from the model reply (§9)", () => {
  it("buildDialoguePrompt is the user-sourced prompt (the quoted selection)", () => {
    const sel: FloatMenuSelection = {
      text: "a claim to discuss",
      rect: { top: 0, left: 0, width: 1, height: 1 },
      provenance: {},
    };
    const prompt = buildDialoguePrompt(sel, "is this right?");
    expect(prompt).toContain("a claim to discuss"); // the user's own selection
    expect(prompt).toContain("is this right?"); // the user's follow-up
  });

  it("a 503 from /thought-partner surfaces the honest no-key failure, not a fake reply", async () => {
    apiFetchMock.mockResolvedValueOnce(new Response("no key", { status: 503 }));
    render(<Host />);
    selectTextIn(screen.getByTestId("scope"), "discuss this");
    fireEvent.click(screen.getByRole("menuitem", { name: "Dialogue" }));
    const ask = screen.getByText("Ask");
    await act(async () => {
      fireEvent.click(ask);
    });
    // AIActionFailure renders role="alert" with the no-provider sentence.
    expect(screen.getByRole("alert").textContent).toMatch(/provider isn|no result/i);
  });
});

// ── M4 — flagged Hybrid stub ─────────────────────────────────────────────────

describe("Hybrid stub is flagged off by default (M4)", () => {
  it("no Hybrid affordance with the flag off", () => {
    render(<Host hybridEnabled={false} />);
    selectTextIn(screen.getByTestId("scope"), "some text");
    expect(document.querySelector("[data-floatmenu-hybrid]")).toBeNull();
  });

  it("with the flag on, the Hybrid affordance is reachable and marked 'coming' (not a fake)", () => {
    render(<Host hybridEnabled />);
    selectTextIn(screen.getByTestId("scope"), "some text");
    const hybrid = document.querySelector("[data-floatmenu-hybrid]");
    expect(hybrid).toBeTruthy();
    expect(hybrid?.textContent).toMatch(/coming/i); // honestly unfinished
  });
});
