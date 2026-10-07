/**
 * useProjectIntake.test.ts — FFX-KPA SPR-03 M1 + M6.
 *
 * The intake machine moved out of StartResearch (StartResearch.test.tsx and
 * StartResearch.spr05.test.tsx still pin the rendered surface). This file pins
 * the hook on its own: each intake path, the attachment-only derived prompt,
 * the 1.5 s navigate grace, the owner-model both-or-neither rule, the
 * byte-exact POST /investigations bodies, and SPR-03 M6's two project
 * branches (pre-contract: no registry call, project id = investigation id;
 * contract live: POST /projects first, then the investigation joins it).
 *
 * The network is stubbed at `fetch`, not at `startInvestigation`, so the body
 * snapshots below are the bytes the browser would send.
 */
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import { act, renderHook, waitFor } from "@testing-library/react";
import { createElement, type ReactNode } from "react";
import { MemoryRouter } from "react-router-dom";

import type { Event } from "../../generated/types";

const { navigateMock, fetchUserModelsMock, celebrateMock, eventStreamState } = vi.hoisted(() => ({
  navigateMock: vi.fn(),
  celebrateMock: vi.fn(),
  fetchUserModelsMock: vi.fn(),
  eventStreamState: {
    current: {
      events: [] as Event[],
      status: "closed" as "connecting" | "open" | "closed" | "error",
      reconnects: 0,
    },
  },
}));

vi.mock("../../api/settingsModels", () => ({ fetchUserModels: fetchUserModelsMock }));
vi.mock("../../hooks/useEventStream", () => ({
  useEventStream: (id: string | null) =>
    id ? eventStreamState.current : { events: [], status: "closed", reconnects: 0 },
}));
vi.mock("../../shared/delight", async (orig) => {
  const actual = await orig<typeof import("../../shared/delight")>();
  return { ...actual, useCelebrate: () => ({ celebrating: false, celebrate: celebrateMock }) };
});
vi.mock("react-router-dom", async (orig) => {
  const actual = await orig<typeof import("react-router-dom")>();
  return { ...actual, useNavigate: () => navigateMock };
});

import { NAVIGATE_GRACE_MS, derivePromptFor, useProjectIntake } from "./useProjectIntake";

type Call = { url: string; method: string; body: string | null };
let calls: Call[] = [];
let responder: (url: string, method: string) => Response;
let lastBody: { title?: string } | null = null;

function jsonResponse(status: number, body: unknown): Response {
  return new Response(JSON.stringify(body), {
    status,
    headers: { "Content-Type": "application/json" },
  });
}

const PROJECT_ROW = {
  project_id: "proj-1",
  title: "t",
  kind: "project",
  order: 0,
  pinned: false,
  archived_at: null,
  primary_document_id: null,
  created_at: "2026-10-07T00:00:00Z",
  updated_at: null,
  member_count: 0,
};

function defaultResponder(url: string, method: string): Response {
  if (url.endsWith("/investigations") && method === "POST") {
    return jsonResponse(200, { investigation_id: "inv-1", status: "started", start_event_id: "e0" });
  }
  if (url.endsWith("/sources/ingest")) {
    return jsonResponse(200, { status: "ok", title: "A Linked Page", document_id: "d1" });
  }
  if (url.endsWith("/voice-notes/ingest")) {
    // Echo the posted title, as the server does, so tests pin the contract
    // (the response title wins) rather than the stub.
    return jsonResponse(200, { document_id: "d2", title: lastBody?.title ?? "untitled" });
  }
  if (url.endsWith("/projects") && method === "POST") return jsonResponse(200, PROJECT_ROW);
  if (url.endsWith("/members") && method === "POST") return jsonResponse(200, { status: "added" });
  return jsonResponse(404, { detail: "unmocked" });
}

const wrapper = ({ children }: { children: ReactNode }) => createElement(MemoryRouter, null, children);

beforeEach(() => {
  calls = [];
  responder = defaultResponder;
  navigateMock.mockReset();
  celebrateMock.mockReset();
  fetchUserModelsMock.mockReset().mockResolvedValue({ models: [] });
  eventStreamState.current = { events: [], status: "closed", reconnects: 0 };
  vi.stubGlobal(
    "fetch",
    vi.fn(async (input: RequestInfo | URL, init?: RequestInit) => {
      const url = String(input);
      const method = init?.method ?? "GET";
      calls.push({ url, method, body: typeof init?.body === "string" ? init.body : null });
      lastBody = typeof init?.body === "string" ? (JSON.parse(init.body) as { title?: string }) : null;
      return responder(url, method);
    }),
  );
  window.sessionStorage.clear();
});

afterEach(() => {
  vi.unstubAllGlobals();
  vi.useRealTimers();
});

const posts = (suffix: string) => calls.filter((c) => c.method === "POST" && c.url.endsWith(suffix));

describe("useProjectIntake — M1 extraction", () => {
  it("submits the tier path with a byte-identical POST /investigations body", async () => {
    const { result } = renderHook(() => useProjectIntake(), { wrapper });
    await waitFor(() => expect(result.current.modelsState).toBe("ready"));
    act(() => result.current.editQuestion("Why do tides lag the moon?"));
    await act(async () => { await result.current.onSubmit(); });
    expect(posts("/investigations")).toHaveLength(1);
    expect(posts("/investigations")[0].body).toMatchInlineSnapshot(
      `"{"question":"Why do tides lag the moon?","research_tier":"deep","source_policy":["operator_corpus","web"]}"`,
    );
    expect(result.current.question).toBe("");
  });

  it("owner-model path sends model_choice and operation_id together (both-or-neither)", async () => {
    fetchUserModelsMock.mockResolvedValue({
      models: [{
        id: "row-a", model_id: "m-1", display_name: "Mine", enabled: true, key_present: true,
        registered: true, route_eligible: true, pricing_status: "known",
        hard_ceiling_eligible: true, execution_status: "executable",
      }],
    });
    const { result } = renderHook(() => useProjectIntake(), { wrapper });
    await waitFor(() => expect(result.current.models).toHaveLength(1));
    act(() => result.current.selectModel("row-a\u0000m-1"));
    act(() => result.current.editQuestion("Owner question"));
    const op = result.current.operationId;
    await act(async () => { await result.current.onSubmit(); });
    const body = JSON.parse(posts("/investigations")[0].body ?? "{}");
    expect(body).toEqual({
      question: "Owner question",
      source_policy: ["operator_corpus", "web"],
      model_choice: { authority: "user_model", provider_id: "row-a", model_id: "m-1" },
      operation_id: op,
    });
    expect(body).not.toHaveProperty("research_tier");
  });

  it("URL path posts /sources/ingest once and derives the prompt from the title", async () => {
    const { result } = renderHook(() => useProjectIntake(), { wrapper });
    await act(async () => { await result.current.absorbUrl("https://example.org/a"); });
    expect(posts("/sources/ingest")).toHaveLength(1);
    expect(JSON.parse(posts("/sources/ingest")[0].body ?? "{}")).toEqual({ url: "https://example.org/a" });
    expect(result.current.attach).toEqual({ kind: "absorbed", title: "A Linked Page" });
    expect(result.current.question).toBe(derivePromptFor("A Linked Page"));
    expect(result.current.promptDerived).toBe(true);
  });

  it("text-file path posts /voice-notes/ingest with the file text and keeps an explicit prompt", async () => {
    const { result } = renderHook(() => useProjectIntake(), { wrapper });
    act(() => result.current.editQuestion("My own question"));
    const file = new File(["# heading\nbody"], "notes.md", { type: "text/markdown" });
    await act(async () => { await result.current.handleFile(file); });
    expect(posts("/voice-notes/ingest")).toHaveLength(1);
    expect(JSON.parse(posts("/voice-notes/ingest")[0].body ?? "{}")).toMatchObject({
      transcript: "# heading\nbody",
      title: "notes.md",
    });
    expect(result.current.question).toBe("My own question");
    expect(result.current.promptDerived).toBe(false);
  });

  it("refuses a binary file with StartResearch's copy and never calls fetch", async () => {
    const { result } = renderHook(() => useProjectIntake(), { wrapper });
    await waitFor(() => expect(result.current.modelsState).toBe("ready"));
    const before = calls.length;
    const file = new File([new Uint8Array([0x25, 0x50, 0x44, 0x46])], "paper.pdf", { type: "application/pdf" });
    await act(async () => { await result.current.handleFile(file); });
    expect(calls.length).toBe(before);
    expect(result.current.attach).toEqual({
      kind: "rejected",
      why: "“paper.pdf” isn’t a kind I can absorb directly yet. Paste a link to it, or paste its text.",
    });
  });

  it("attachment-only: derived prompt is submitted when the box was empty", async () => {
    const { result } = renderHook(() => useProjectIntake(), { wrapper });
    await act(async () => { await result.current.absorbText("some passage", "passage.txt"); });
    expect(result.current.question).toBe(derivePromptFor("passage.txt"));
    await act(async () => { await result.current.onSubmit(); });
    expect(JSON.parse(posts("/investigations")[0].body ?? "{}").question).toBe(derivePromptFor("passage.txt"));
  });

  it("navigates to /inv/:id after the 1.5 s grace when no event has streamed", async () => {
    vi.useFakeTimers();
    const { result } = renderHook(() => useProjectIntake(), { wrapper });
    act(() => result.current.editQuestion("Grace window question"));
    await act(async () => { await result.current.onSubmit(); });
    expect(result.current.start.startedId).toBe("inv-1");
    act(() => { vi.advanceTimersByTime(NAVIGATE_GRACE_MS - 1); });
    expect(navigateMock).not.toHaveBeenCalled();
    act(() => { vi.advanceTimersByTime(1); });
    expect(navigateMock).toHaveBeenCalledWith("/inv/inv-1");
    expect(NAVIGATE_GRACE_MS).toBe(1500);
  });

  it("navigates immediately on the first streamed event", async () => {
    const { result, rerender } = renderHook(() => useProjectIntake(), { wrapper });
    act(() => result.current.editQuestion("Event question"));
    eventStreamState.current = {
      events: [{ event_id: "e1", action_type: "phase.start", payload: {} } as unknown as Event],
      status: "open",
      reconnects: 0,
    };
    await act(async () => { await result.current.onSubmit(); });
    rerender();
    expect(navigateMock).toHaveBeenCalledWith("/inv/inv-1");
  });

  it("a failed POST keeps the question and does not navigate", async () => {
    responder = (url, method) =>
      url.endsWith("/investigations") && method === "POST"
        ? jsonResponse(500, { detail: "boom" })
        : defaultResponder(url, method);
    const { result } = renderHook(() => useProjectIntake(), { wrapper });
    act(() => result.current.editQuestion("Will fail"));
    await act(async () => { await result.current.onSubmit(); });
    expect(result.current.start.error).toMatch(/^Submit failed/);
    expect(result.current.question).toBe("Will fail");
    expect(navigateMock).not.toHaveBeenCalled();
  });
});

describe("useProjectIntake — M6 project creation", () => {
  it("pre-contract: no registry call, project id is the investigation id", async () => {
    const { result } = renderHook(() => useProjectIntake(), { wrapper });
    act(() => result.current.editQuestion("Seed a project"));
    let created: Awaited<ReturnType<typeof result.current.submitProject>> = null;
    await act(async () => { created = await result.current.submitProject(); });
    expect(created).toEqual({ projectId: "inv-1", investigationId: "inv-1", registry: "skipped-pre-contract" });
    expect(posts("/projects")).toHaveLength(0);
    expect(posts("/investigations")).toHaveLength(1);
  });

  it("contract live: POST /projects, then POST /investigations, then the investigation joins the project", async () => {
    const { result } = renderHook(() => useProjectIntake({ projectSeedContract: true }), { wrapper });
    act(() => result.current.editQuestion("Seed a real project"));
    let created: Awaited<ReturnType<typeof result.current.submitProject>> = null;
    await act(async () => { created = await result.current.submitProject(); });
    expect(created).toEqual({ projectId: "proj-1", investigationId: "inv-1", registry: "created" });
    const order = calls.filter((c) => c.method === "POST").map((c) => new URL(c.url, "http://x").pathname);
    expect(order).toEqual(["/projects", "/investigations", "/projects/proj-1/members"]);
    expect(JSON.parse(posts("/projects")[0].body ?? "{}")).toEqual({ title: "Seed a real project", kind: "project" });
    expect(JSON.parse(posts("/members")[0].body ?? "{}")).toEqual({ member_kind: "investigation", member_id: "inv-1" });
  });

  it("contract live: a failed POST /projects starts nothing and keeps the draft", async () => {
    responder = (url, method) =>
      url.endsWith("/projects") && method === "POST" ? jsonResponse(503, {}) : defaultResponder(url, method);
    const { result } = renderHook(() => useProjectIntake({ projectSeedContract: true }), { wrapper });
    act(() => result.current.editQuestion("Registry is down"));
    await act(async () => { await result.current.submitProject(); });
    expect(posts("/investigations")).toHaveLength(0);
    expect(result.current.question).toBe("Registry is down");
    expect(result.current.projectError).toMatch(/project/i);
  });

  it("contract live: a failed POST /investigations after the project exists says so", async () => {
    responder = (url, method) =>
      url.endsWith("/investigations") && method === "POST" ? jsonResponse(500, {}) : defaultResponder(url, method);
    const { result } = renderHook(() => useProjectIntake({ projectSeedContract: true }), { wrapper });
    act(() => result.current.editQuestion("Project then failure"));
    await act(async () => { await result.current.submitProject(); });
    expect(posts("/projects")).toHaveLength(1);
    expect(result.current.projectError).toMatch(/project was created/i);
    expect(result.current.question).toBe("Project then failure");
  });

  it("the research-starts beat fires once per started run", async () => {
    const { result, rerender } = renderHook(() => useProjectIntake(), { wrapper });
    act(() => result.current.editQuestion("Celebrate once"));
    await act(async () => { await result.current.submitProject(); });
    expect(celebrateMock).toHaveBeenCalledTimes(1);
    rerender();
    rerender();
    expect(celebrateMock).toHaveBeenCalledTimes(1);
  });
});
