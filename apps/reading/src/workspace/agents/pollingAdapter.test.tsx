/**
 * pollingAdapter.test.tsx — SPR-10 M2: the list-only polling source over
 * useInvestigationList. Fake timers; listInvestigations mocked; the per-id
 * route is never imported under agents/ (fs grep).
 */
import { readFileSync, readdirSync } from "node:fs";
import { join } from "node:path";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import { act, cleanup, render } from "@testing-library/react";

const { listMock } = vi.hoisted(() => ({ listMock: vi.fn() }));
vi.mock("../../lib/api", async (orig) => ({
  ...(await orig<typeof import("../../lib/api")>()),
  listInvestigations: listMock,
}));

import type { InvestigationSummary } from "../../lib/api";
import { summary } from "../contracts/fixtures.test.helpers";
import { attentionOf } from "./agentStatus";
import { useAgentStatusStore } from "./agentStatusStore";
import { DEBOUNCE } from "./debounce";
import { latestSnapshot, usePollingStatusSource } from "./pollingAdapter";

const clock = { now: () => Date.now(), setTimeout: (fn: () => void, ms: number) => window.setTimeout(fn, ms), clearTimeout: (h: unknown) => window.clearTimeout(h as number) };

function Source({ watched }: { watched: ReadonlySet<string> }) {
  usePollingStatusSource(watched, clock);
  return null;
}

let rows: InvestigationSummary[] = [];
function setVisibility(state: "visible" | "hidden") {
  Object.defineProperty(document, "visibilityState", { configurable: true, get: () => state });
}

beforeEach(() => {
  vi.useFakeTimers();
  setVisibility("visible");
  rows = [summary("inv-w", { status: "in_progress", completed_at: null })];
  listMock.mockReset();
  listMock.mockImplementation(async () => ({ count: rows.length, investigations: rows }));
  useAgentStatusStore.getState().reset();
  useAgentStatusStore.getState().start(clock);
});

afterEach(() => {
  cleanup();
  useAgentStatusStore.getState().stop();
  vi.useRealTimers();
});

async function flush() {
  await act(async () => {
    await Promise.resolve();
    await Promise.resolve();
  });
}

describe("usePollingStatusSource", () => {
  it("visible + one working watched id: list calls at t=0, 2000, 4000 (limit 200)", async () => {
    render(<Source watched={new Set(["inv-w"])} />);
    await flush();
    expect(listMock).toHaveBeenCalledTimes(1);
    expect(listMock.mock.calls[0][0]).toEqual({ limit: 200 });
    await act(async () => { vi.advanceTimersByTime(DEBOUNCE.pollMs); });
    await flush();
    expect(listMock).toHaveBeenCalledTimes(2);
    await act(async () => { vi.advanceTimersByTime(DEBOUNCE.pollMs); });
    await flush();
    expect(listMock).toHaveBeenCalledTimes(3);
    expect(useAgentStatusStore.getState().raw.get("inv-w")?.status).toBe("in_progress");
    expect(latestSnapshot()).toBe(rows);
  });

  it("hidden: no polls across 10 s; visibilitychange→visible: one immediate call", async () => {
    render(<Source watched={new Set(["inv-w"])} />);
    await flush();
    expect(listMock).toHaveBeenCalledTimes(1);
    setVisibility("hidden");
    await act(async () => { vi.advanceTimersByTime(10_000); });
    await flush();
    expect(listMock).toHaveBeenCalledTimes(1);
    setVisibility("visible");
    await act(async () => { document.dispatchEvent(new Event("visibilitychange")); });
    await flush();
    expect(listMock).toHaveBeenCalledTimes(2);
  });

  it("no working ids: the cadence is 30 s", async () => {
    rows = [summary("inv-done", { status: "completed" })];
    render(<Source watched={new Set(["inv-done"])} />);
    await flush();
    expect(listMock).toHaveBeenCalledTimes(1);
    // After the first observation the only watched run is finished → idle cadence.
    await act(async () => { vi.advanceTimersByTime(DEBOUNCE.pollMs * 5); });
    await flush();
    expect(listMock).toHaveBeenCalledTimes(1);
    await act(async () => { vi.advanceTimersByTime(DEBOUNCE.idlePollMs); });
    await flush();
    expect(listMock).toHaveBeenCalledTimes(2);
  });

  it("a rejected call leaves the previous snapshot and derived states unchanged (no regression to unknown)", async () => {
    render(<Source watched={new Set(["inv-w"])} />);
    await flush();
    const before = useAgentStatusStore.getState().raw.get("inv-w");
    expect(attentionOf(before, null).state).toBe("working");
    listMock.mockImplementationOnce(async () => { throw new Error("503"); });
    await act(async () => { vi.advanceTimersByTime(DEBOUNCE.pollMs); });
    await flush();
    expect(listMock).toHaveBeenCalledTimes(2);
    expect(useAgentStatusStore.getState().raw.get("inv-w")).toBe(before);
    expect(attentionOf(useAgentStatusStore.getState().raw.get("inv-w"), null).state).toBe("working");
    expect(latestSnapshot()).toBe(rows);
  });

  it("a watched id absent from the window reads unknown/outside-window; a prior raw for it is retained", async () => {
    render(<Source watched={new Set(["inv-w", "inv-gone"])} />);
    await flush();
    expect(useAgentStatusStore.getState().raw.has("inv-gone")).toBe(false);
    expect(attentionOf(useAgentStatusStore.getState().raw.get("inv-gone"), null)).toEqual({ state: "unknown", reason: "outside-window" });
    // It appears once, then drops out of the window: the raw stays.
    rows = [...rows, summary("inv-gone", { status: "completed" })];
    await act(async () => { vi.advanceTimersByTime(DEBOUNCE.pollMs); });
    await flush();
    const seen = useAgentStatusStore.getState().raw.get("inv-gone");
    expect(seen?.status).toBe("completed");
    rows = rows.filter((r) => r.investigation_id !== "inv-gone");
    await act(async () => { vi.advanceTimersByTime(DEBOUNCE.pollMs); });
    await flush();
    expect(useAgentStatusStore.getState().raw.get("inv-gone")).toBe(seen);
  });

  it("getInvestigationStatus (the lying per-id route) is never imported under agents/", () => {
    const dir = __dirname;
    const files = readdirSync(dir).filter((f) => /\.(ts|tsx)$/.test(f) && !/\.test\./.test(f));
    expect(files.length).toBeGreaterThan(0);
    for (const f of files) expect(readFileSync(join(dir, f), "utf8"), f).not.toMatch(/getInvestigationStatus/);
  });
});
