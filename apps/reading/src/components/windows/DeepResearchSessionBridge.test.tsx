import { act, cleanup, render, screen } from "@testing-library/react";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";

const harness = { generation: 1, requests: [] as Array<{ resolve: (value: unknown) => void; signal?: AbortSignal }> };
vi.mock("../../lib/auth", () => ({ useAuth: () => ({ state: { status: "authenticated" }, sessionGeneration: harness.generation }) }));
vi.mock("../../api/deepResearchSessionRefs", async (original) => {
  const actual = await original<typeof import("../../api/deepResearchSessionRefs")>();
  return { ...actual, fetchDeepResearchSessionReference: vi.fn((_id: string, signal?: AbortSignal) => new Promise((resolve) => harness.requests.push({ resolve, signal }))) };
});
vi.mock("./DeepResearchSessionHost", () => ({ default: (props: Record<string, unknown>) => <div data-testid="deep-host">{JSON.stringify(props)}</div> }));

import DeepResearchSessionBridge from "./DeepResearchSessionBridge";

const projection = (session_id: string) => ({ schema_version: 1 as const, session_id, spawn_id: `spawn-${session_id}`, investigation_id: "inv", parent_asset_id: "asset", status: "running" as const, research_tier: "deep" as const, view_format: "html" as const });

describe("DeepResearchSessionBridge", () => {
  beforeEach(() => { harness.generation = 1; harness.requests = []; });
  afterEach(cleanup);
  it("never passes forged placeholder props to the host", async () => {
    render(<DeepResearchSessionBridge resume_ref={{ session_id: "current" }} selection_text="secret" goal="forged" spawn_id="forged" />);
    await act(async () => harness.requests[0].resolve(projection("current")));
    const body = screen.getByTestId("deep-host").textContent || "";
    expect(body).toContain("spawn-current"); expect(body).not.toContain("secret"); expect(body).not.toContain("forged");
  });
  it("never falls back to forged props when a resume reference is malformed", () => {
    render(<DeepResearchSessionBridge resume_ref={{ session_id: "current", extra: "invalid" }} selection_text="secret" goal="forged" spawn_id="forged" />);
    expect(screen.getByTestId("deep-research-reference-unavailable")).toBeTruthy();
    expect(screen.queryByTestId("deep-host")).toBeNull();
    expect(harness.requests).toHaveLength(0);
  });
  it("fences a slow old reference and clears ready state", async () => {
    const view = render(<DeepResearchSessionBridge resume_ref={{ session_id: "old" }} />);
    view.rerender(<DeepResearchSessionBridge resume_ref={{ session_id: "new" }} />);
    expect(screen.getByTestId("deep-research-reference-loading")).toBeTruthy();
    await act(async () => harness.requests[0].resolve(projection("old")));
    expect(screen.queryByTestId("deep-host")).toBeNull();
    await act(async () => harness.requests[1].resolve(projection("new")));
    expect(screen.getByTestId("deep-host").textContent).toContain("spawn-new");
  });
  it("fences auth generation and aborts the old request", () => {
    const view = render(<DeepResearchSessionBridge resume_ref={{ session_id: "same" }} />);
    const old = harness.requests[0]; harness.generation = 2;
    view.rerender(<DeepResearchSessionBridge resume_ref={{ session_id: "same" }} />);
    expect(old.signal?.aborted).toBe(true); expect(screen.queryByTestId("deep-host")).toBeNull();
  });
});
