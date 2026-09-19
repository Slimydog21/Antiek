import { act, cleanup, render } from "@testing-library/react";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";

const harness = vi.hoisted(() => ({
  generation: 1,
  gets: [] as Array<{ resolve: (value: unknown) => void; signal?: AbortSignal }>,
  puts: [] as Array<{ body: unknown; resolve: (value: unknown) => void; reject: (reason: unknown) => void; signal?: AbortSignal }>,
  warnings: [] as string[],
}));

vi.mock("../lib/auth", () => ({
  useAuth: () => ({ state: { status: "authenticated", identity: { user_id: "u", email: null, auth_method: "test" } }, sessionGeneration: harness.generation }),
}));
vi.mock("../api/workspaceResume", () => ({
  getWorkspaceResume: vi.fn((signal?: AbortSignal) => new Promise((resolve) => harness.gets.push({ resolve, signal }))),
  putWorkspaceResume: vi.fn((body: unknown, signal?: AbortSignal) => new Promise((resolve, reject) => harness.puts.push({ body, resolve, reject, signal }))),
}));
vi.mock("../components/lemon/LemonToast", () => ({
  toast: { warn: (message: string) => harness.warnings.push(message) },
}));

import { useWindows } from "./windowsStore";
import { hostedDocumentWindowId, useWorkspaceResume } from "./useWorkspaceResume";

function Harness() { useWorkspaceResume(); return null; }

describe("workspace resume auth-generation races", () => {
  beforeEach(() => {
    harness.generation = 1;
    harness.gets.length = 0;
    harness.puts.length = 0;
    harness.warnings.length = 0;
    useWindows.getState().reset();
    vi.useFakeTimers();
  });
  afterEach(() => { cleanup(); vi.useRealTimers(); });

  it("discards and aborts a stale GET before replay", async () => {
    const view = render(<Harness />);
    expect(harness.gets).toHaveLength(1);
    harness.generation = 2;
    view.rerender(<Harness />);
    expect(harness.gets[0].signal?.aborted).toBe(true);
    await act(async () => harness.gets[0].resolve({ schema_version: 1, revision: 1, entries: [{ kind: "stats" }] }));
    expect(useWindows.getState().windows["win:stats"]).toBeUndefined();
    await act(async () => harness.gets[1].resolve({ schema_version: 1, revision: 0, entries: [{ kind: "library" }] }));
    expect(useWindows.getState().windows["win:library"]).toBeDefined();
  });

  it("aborts an in-flight PUT when auth generation changes", async () => {
    const view = render(<Harness />);
    await act(async () => harness.gets[0].resolve({ schema_version: 1, revision: 0, entries: [] }));
    act(() => { useWindows.getState().open("stats", {}, { id: "win:stats" }); vi.advanceTimersByTime(250); });
    expect(harness.puts).toHaveLength(1);
    harness.generation = 2;
    view.rerender(<Harness />);
    expect(harness.puts[0].signal?.aborted).toBe(true);
    await act(async () => harness.puts[0].resolve({ status: "synced", revision: 99, event_id: "stale" }));
  });

  it("persists only exact closed references and excludes raw hosted bytes", async () => {
    render(<Harness />);
    await act(async () => harness.gets[0].resolve({ schema_version: 1, revision: 0, entries: [] }));
    act(() => {
      useWindows.getState().open("hosted_html_document", {
        document_id: "same",
        title: "private title",
        html: "private raw html",
        source: "private source",
        resume_ref: { resolver: "hosted_document", document_id: "same" },
      }, { id: "referenced" });
      useWindows.getState().open("hosted_html_document", {
        document_id: "ephemeral",
        html: "ephemeral raw html",
      }, { id: "ephemeral" });
      vi.advanceTimersByTime(250);
    });
    expect(harness.puts).toHaveLength(1);
    expect((harness.puts[0].body as { entries: unknown[] }).entries).toEqual([{
        kind: "hosted_html_document",
        resolver: "hosted_document",
        document_id: "same",
      }]);
    expect(JSON.stringify(harness.puts[0].body)).not.toMatch(
      /private title|private raw html|private source|ephemeral raw html/,
    );
  });

  it("persists semantic close of a replayed reference", async () => {
    render(<Harness />);
    await act(async () => harness.gets[0].resolve({
      schema_version: 1,
      revision: 7,
      entries: [{
        kind: "hosted_html_document",
        resolver: "engagement_document",
        document_id: "same",
      }],
    }));
    expect(
      useWindows.getState().windows[hostedDocumentWindowId("engagement_document", "same")],
    ).toBeDefined();
    act(() => {
      useWindows.getState().close(
        hostedDocumentWindowId("engagement_document", "same"),
      );
      vi.advanceTimersByTime(250);
    });
    expect((harness.puts[0].body as { base_revision: number }).base_revision).toBe(7);
    expect((harness.puts[0].body as { entries: unknown[] }).entries).toEqual([]);
  });

  it("fetches current authority and visibly surfaces a 409 without blind overwrite", async () => {
    render(<Harness />);
    await act(async () => harness.gets[0].resolve({ schema_version: 1, revision: 1, entries: [] }));
    act(() => { useWindows.getState().open("stats", {}, { id: "win:stats" }); vi.advanceTimersByTime(250); });
    const { ApiError } = await import("../lib/api");
    act(() => harness.puts[0].reject(new ApiError("conflict", 409, "conflict")));
    await act(async () => { await Promise.resolve(); });
    expect(harness.gets).toHaveLength(2);
    await act(async () => harness.gets[1].resolve({ schema_version: 1, revision: 2, entries: [{ kind: "library" }] }));
    expect(harness.warnings).toEqual([
      "Workspace changed on another device. Your local window change was not synced; review the latest workspace and try again.",
    ]);
    expect(useWindows.getState().windows["win:stats"]).toBeDefined();
  });
});
