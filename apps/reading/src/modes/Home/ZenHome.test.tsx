/**
 * ZenHome.test.tsx — FFX-KPA SPR-03 M2–M6 on the rendered surface.
 *
 * The network is stubbed at `fetch` so "never uploaded" is asserted as zero
 * requests, not as an un-called helper. The recorder and the event stream are
 * mocked at their hook boundaries (VoiceChaseButton and useStartInvestigation
 * run for real). Tab order is asserted as the DOM order of tabbable elements:
 * the surface sets no positive tabIndex, so DOM order IS the Tab order (jsdom
 * has no Tab navigation of its own).
 */
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import { act, cleanup, fireEvent, render, screen, waitFor } from "@testing-library/react";
import { MemoryRouter } from "react-router-dom";

import type { Event } from "../../generated/types";

const { navigateMock, recorderState } = vi.hoisted(() => ({
  navigateMock: vi.fn(),
  recorderState: {
    current: {
      state: "idle" as "idle" | "recording" | "stopped" | "denied" | "error",
      blob: null as Blob | null,
      error: null as string | null,
      start: vi.fn(),
      stop: vi.fn(),
      reset: vi.fn(),
    },
  },
}));

vi.mock("../../hooks/useVoiceRecorder", () => ({ useVoiceRecorder: () => recorderState.current }));
vi.mock("../../hooks/useEventStream", () => ({
  useEventStream: () => ({ events: [] as Event[], status: "closed", reconnects: 0 }),
}));
vi.mock("react-router-dom", async (orig) => {
  const actual = await orig<typeof import("react-router-dom")>();
  return { ...actual, useNavigate: () => navigateMock };
});

import ZenHome, { INTERVIEW_PROMPT, insertAtCaret } from "./ZenHome";
import { REFUSED_UNTIL_INTAKE_COPY, CAP_COPY } from "./intakeKinds";
import { THOUGHT_PARTNER_SEED_EVENT, type ThoughtPartnerSeedDetail } from "../../components/ai/thoughtPartnerSeed";
import { toast } from "../../components/lemon";
import { useWorkspace } from "../../workspace/WorkspaceStore";
import { AISIDECAR_PANEL_ID } from "../../workspace/shortcuts";

type Call = { url: string; method: string; body: string | null };
let calls: Call[] = [];
let transcribeStatus = 200;

function jsonResponse(status: number, body: unknown): Response {
  return new Response(JSON.stringify(body), { status, headers: { "Content-Type": "application/json" } });
}

beforeEach(() => {
  calls = [];
  transcribeStatus = 200;
  navigateMock.mockReset();
  recorderState.current = {
    state: "idle", blob: null, error: null, start: vi.fn(), stop: vi.fn(), reset: vi.fn(),
  };
  vi.stubGlobal(
    "fetch",
    vi.fn(async (input: RequestInfo | URL, init?: RequestInit) => {
      const url = String(input);
      const method = init?.method ?? "GET";
      calls.push({ url, method, body: typeof init?.body === "string" ? init.body : null });
      if (url.includes("/settings/models")) return jsonResponse(200, { models: [] });
      if (url.endsWith("/voice/transcribe")) {
        return transcribeStatus === 200
          ? jsonResponse(200, { transcript: "spoken words" })
          : jsonResponse(transcribeStatus, { detail: "no key" });
      }
      if (url.endsWith("/voice-notes/ingest")) return jsonResponse(200, { document_id: "d1", title: "notes.md" });
      if (url.endsWith("/sources/ingest")) return jsonResponse(200, { status: "ok", title: "Linked", document_id: "d2" });
      if (url.endsWith("/investigations")) {
        return jsonResponse(200, { investigation_id: "inv-9", status: "started", start_event_id: "e0" });
      }
      return jsonResponse(404, {});
    }),
  );
});

afterEach(() => {
  cleanup();
  vi.unstubAllGlobals();
  vi.restoreAllMocks();
  useWorkspace.getState().close(AISIDECAR_PANEL_ID);
});

const writes = () => calls.filter((c) => c.method !== "GET");
const box = () => screen.getByRole("textbox", { name: "What are you working on?" }) as HTMLTextAreaElement;

function renderZen(props: Parameters<typeof ZenHome>[0] = {}) {
  return render(
    <MemoryRouter>
      <ZenHome {...props} />
    </MemoryRouter>,
  );
}

function drop(target: Element, files: File[]) {
  fireEvent.drop(target, { dataTransfer: { files, types: ["Files"], getData: () => "" } });
}

function tabbables(root: HTMLElement): HTMLElement[] {
  return Array.from(
    root.querySelectorAll<HTMLElement>("button, textarea, input, select, a[href], [tabindex]"),
  ).filter((el) => !(el as HTMLButtonElement).disabled && el.tabIndex >= 0 && !el.closest("[hidden]") && !el.classList.contains("hidden"));
}

const nameOf = (el: HTMLElement) => el.getAttribute("aria-label") ?? el.textContent?.trim() ?? "";

describe("ZenHome — M2 surface", () => {
  it("focus lands in the box and the placeholder is the one question", () => {
    renderZen();
    expect(document.activeElement).toBe(box());
    expect(box().placeholder).toBe("What are you working on?");
  });

  it("Tab order is box → attach → voice → talk → submit → options", () => {
    const { container } = renderZen();
    fireEvent.change(box(), { target: { value: "a draft" } }); // enables submit
    expect(tabbables(container).map(nameOf)).toEqual([
      "What are you working on?",
      "Attach a file",
      "Voice",
      "Talk it through",
      "Start",
      "Options",
    ]);
  });

  it("zen is counted: six interactive elements with no switch, seven with the SPR-04 slot filled", () => {
    const { container, unmount } = renderZen();
    fireEvent.change(box(), { target: { value: "a draft" } });
    expect(tabbables(container)).toHaveLength(6);
    unmount();
    const withSlot = renderZen({ switchSlot: <button type="button">Switch</button> });
    fireEvent.change(box(), { target: { value: "a draft" } });
    expect(tabbables(withSlot.container)).toHaveLength(7);
  });

  it("no product doors, cards or biography call to action", () => {
    renderZen();
    expect(screen.queryByText(/biograph/i)).toBeNull();
    expect(screen.queryByRole("link")).toBeNull();
  });

  it("Options is a keyboard disclosure over tier, sources and model", () => {
    renderZen();
    const options = screen.getByRole("button", { name: "Options" });
    expect(options.getAttribute("aria-expanded")).toBe("false");
    expect(screen.queryByRole("radiogroup", { name: "Research depth" })).toBeNull();
    fireEvent.click(options);
    expect(options.getAttribute("aria-expanded")).toBe("true");
    expect(screen.getByRole("radiogroup", { name: "Research depth" })).toBeTruthy();
    expect(screen.getByRole("group", { name: "Sources" })).toBeTruthy();
  });
});

describe("ZenHome — M3 drop zone", () => {
  it("a dropped .md is staged without network, then ingested once on submit", async () => {
    renderZen();
    await act(async () => { drop(box(), [new File(["# Title\nbody"], "notes.md", { type: "text/markdown" })]); });
    await screen.findByText("notes.md");
    expect(writes()).toHaveLength(0);
    expect(box().value).toMatch(/^Understand and distill “notes.md”/);
    await act(async () => { fireEvent.keyDown(box(), { key: "Enter", metaKey: true }); });
    await waitFor(() => expect(writes().map((c) => new URL(c.url, "http://x").pathname)).toEqual([
      "/voice-notes/ingest",
      "/investigations",
    ]));
    expect(JSON.parse(writes()[0].body ?? "{}")).toMatchObject({ transcript: "# Title\nbody", title: "notes.md" });
  });

  it("a dropped URL goes to /sources/ingest once with {url}", async () => {
    renderZen();
    await act(async () => {
      fireEvent.drop(box(), {
        dataTransfer: { files: [], types: ["text/uri-list"], getData: (t: string) => (t === "text/uri-list" ? "https://example.org/x" : "") },
      });
    });
    await screen.findByText("https://example.org/x");
    await act(async () => { fireEvent.keyDown(box(), { key: "Enter", ctrlKey: true }); });
    await waitFor(() => expect(writes().filter((c) => c.url.endsWith("/sources/ingest"))).toHaveLength(1));
    expect(JSON.parse(writes()[0].body ?? "{}")).toEqual({ url: "https://example.org/x" });
  });

  it.each([
    ["photo.png", "image/png"],
    ["paper.pdf", "application/pdf"],
    ["draft.docx", "application/vnd.openxmlformats-officedocument.wordprocessingml.document"],
  ])("refused kinds: %s shows the intake copy and never reaches the network", async (name, type) => {
    const createObjectURL = vi.fn();
    vi.stubGlobal("URL", Object.assign(URL, { createObjectURL }));
    renderZen();
    const file = new File([new Uint8Array([1, 2, 3])], name, { type });
    const textSpy = vi.spyOn(file, "text");
    await act(async () => { drop(box(), [file]); });
    expect(await screen.findByText(REFUSED_UNTIL_INTAKE_COPY)).toBeTruthy();
    fireEvent.change(box(), { target: { value: "submit anyway" } });
    await act(async () => { fireEvent.keyDown(box(), { key: "Enter", metaKey: true }); });
    await waitFor(() => expect(writes().map((c) => new URL(c.url, "http://x").pathname)).toEqual(["/investigations"]));
    expect(textSpy).not.toHaveBeenCalled();
    expect(createObjectURL).not.toHaveBeenCalled();
  });

  it("caps at six attachments and announces the cap", async () => {
    renderZen();
    const files = Array.from({ length: 7 }, (_, i) => new File([`t${i}`], `n${i}.txt`, { type: "text/plain" }));
    await act(async () => { drop(box(), files); });
    await screen.findByText("n5.txt");
    expect(screen.queryByText("n6.txt")).toBeNull();
    expect(screen.getByText(CAP_COPY)).toBeTruthy();
  });

  it("Escape with a staged attachment clears it and announces it", async () => {
    renderZen();
    await act(async () => { drop(box(), [new File(["x"], "a.txt", { type: "text/plain" })]); });
    await screen.findByText("a.txt");
    fireEvent.keyDown(box(), { key: "Escape" });
    expect(screen.queryByText("a.txt")).toBeNull();
    expect(screen.getByRole("status").textContent).toContain("Removed a.txt");
    expect(box().value).toBe(""); // the derived prompt goes with it
  });

  it("the drag overlay survives crossing a child (depth counter)", () => {
    renderZen();
    const zone = box().closest("[data-zen-drop]") as HTMLElement;
    const dt = { types: ["Files"], files: [], getData: () => "" };
    fireEvent.dragEnter(zone, { dataTransfer: dt });
    fireEvent.dragEnter(box(), { dataTransfer: dt });
    fireEvent.dragLeave(zone, { dataTransfer: dt });
    expect(screen.getByTestId("zen-drop-overlay")).toBeTruthy();
    fireEvent.dragLeave(box(), { dataTransfer: dt });
    expect(screen.queryByTestId("zen-drop-overlay")).toBeNull();
  });
});

describe("ZenHome — M4 voice at the caret", () => {
  it("insertAtCaret adds a leading space only when needed", () => {
    expect(insertAtCaret("ab", 2, "cd")).toEqual({ value: "ab cd", caret: 5 });
    expect(insertAtCaret("ab ", 3, "cd")).toEqual({ value: "ab cd", caret: 5 });
    expect(insertAtCaret("", 0, "cd")).toEqual({ value: "cd", caret: 2 });
    expect(insertAtCaret("one three", 3, "two")).toEqual({ value: "one two three", caret: 7 });
  });

  it("the transcript lands at the caret, not appended", async () => {
    const { rerender } = renderZen();
    fireEvent.change(box(), { target: { value: "first last" } });
    box().setSelectionRange(5, 5);
    recorderState.current = { ...recorderState.current, state: "stopped", blob: new Blob(["a"]) };
    await act(async () => {
      rerender(<MemoryRouter><ZenHome /></MemoryRouter>);
    });
    await waitFor(() => expect(box().value).toBe("first spoken words last"));
  });

  it("Escape while recording cancels: nothing is transcribed", async () => {
    recorderState.current = { ...recorderState.current, state: "recording" };
    const { rerender } = renderZen();
    fireEvent.keyDown(window, { key: "Escape" });
    expect(recorderState.current.stop).toHaveBeenCalledTimes(1);
    recorderState.current = { ...recorderState.current, state: "stopped", blob: new Blob(["a"]) };
    await act(async () => { rerender(<MemoryRouter><ZenHome /></MemoryRouter>); });
    expect(calls.some((c) => c.url.endsWith("/voice/transcribe"))).toBe(false);
    expect(recorderState.current.reset).toHaveBeenCalled();
  });

  it("a 503 shows the existing honest no-key copy", async () => {
    transcribeStatus = 503;
    recorderState.current = { ...recorderState.current, state: "stopped", blob: new Blob(["a"]) };
    renderZen();
    const alert = await screen.findByRole("alert");
    expect(alert.textContent).toContain(
      "Couldn’t turn that into a question — the engine returned no result. This usually means the model provider isn’t configured. Try again, or check provider keys.",
    );
  });
});

describe("ZenHome — M5 talk it through", () => {
  it("opens the agent pane and seeds it with the draft, source_label zen-home", () => {
    const seen: ThoughtPartnerSeedDetail[] = [];
    const onSeed = (e: globalThis.Event) => seen.push((e as CustomEvent<ThoughtPartnerSeedDetail>).detail);
    window.addEventListener(THOUGHT_PARTNER_SEED_EVENT, onSeed);
    renderZen();
    fireEvent.change(box(), { target: { value: "a biography of my grandmother" } });
    fireEvent.click(screen.getByRole("button", { name: "Talk it through" }));
    window.removeEventListener(THOUGHT_PARTNER_SEED_EVENT, onSeed);
    expect(useWorkspace.getState().panels[AISIDECAR_PANEL_ID]).toBeTruthy();
    expect(seen).toEqual([{ prompt: "a biography of my grandmother", system_context: INTERVIEW_PROMPT, source_label: "zen-home" }]);
    expect(screen.getByText("preview")).toBeTruthy();
  });

  it("if the pane fails to open: toast, no seed, and the draft stays", () => {
    const err = vi.spyOn(toast, "err").mockImplementation(() => 0);
    const realOpen = useWorkspace.getState().open;
    useWorkspace.setState({ open: () => { throw new Error("panel system down"); } });
    const seen: unknown[] = [];
    const onSeed = (e: globalThis.Event) => seen.push(e);
    window.addEventListener(THOUGHT_PARTNER_SEED_EVENT, onSeed);
    try {
      renderZen();
      fireEvent.change(box(), { target: { value: "keep me" } });
      fireEvent.click(screen.getByRole("button", { name: "Talk it through" }));
    } finally {
      window.removeEventListener(THOUGHT_PARTNER_SEED_EVENT, onSeed);
      useWorkspace.setState({ open: realOpen });
    }
    expect(err).toHaveBeenCalledWith("Couldn’t open the agent pane. Your draft is still here.");
    expect(seen).toHaveLength(0);
    expect(box().value).toBe("keep me");
  });
});

describe("ZenHome — M6 submit", () => {
  it("mod+Enter starts the investigation without a registry call (pre-contract) and navigates after the grace", async () => {
    renderZen();
    fireEvent.change(box(), { target: { value: "How do glaciers move?" } });
    await act(async () => { fireEvent.keyDown(box(), { key: "Enter", metaKey: true }); });
    await waitFor(() => expect(writes()).toHaveLength(1));
    expect(writes()[0].url.endsWith("/investigations")).toBe(true);
    expect(calls.some((c) => c.url.includes("/projects"))).toBe(false);
    await waitFor(() => expect(navigateMock).toHaveBeenCalledWith("/inv/inv-9"), { timeout: 4000 });
  });

  it("two mod+Enter presses in one tick send one ingest and one POST", async () => {
    renderZen();
    await act(async () => { drop(box(), [new File(["x"], "a.txt", { type: "text/plain" })]); });
    await screen.findByText("a.txt");
    await act(async () => {
      fireEvent.keyDown(box(), { key: "Enter", metaKey: true });
      fireEvent.keyDown(box(), { key: "Enter", metaKey: true });
    });
    await waitFor(() => expect(writes().some((c) => c.url.endsWith("/investigations"))).toBe(true));
    expect(writes().map((c) => new URL(c.url, "http://x").pathname)).toEqual(["/voice-notes/ingest", "/investigations"]);
  });

  it("a bare URL in the box becomes a URL attachment with a derived prompt, not a question", async () => {
    renderZen();
    fireEvent.change(box(), { target: { value: "https://example.org/paper" } });
    await act(async () => { fireEvent.keyDown(box(), { key: "Enter", metaKey: true }); });
    expect(writes()).toHaveLength(0);
    expect(screen.getByText("https://example.org/paper")).toBeTruthy();
    expect(box().value).toMatch(/^Understand and distill “https:\/\/example.org\/paper”/);
  });
});
