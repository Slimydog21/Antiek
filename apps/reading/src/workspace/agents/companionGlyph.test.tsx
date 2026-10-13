/**
 * companionGlyph.test.tsx — SPR-10 M6: the companion tab glyph reads the
 * status store once the tree is fed (the registry glyph stays the fallback
 * while "unfed"); the strip carries the workspace rollup badge; a dialogue
 * tab keeps its brand dot.
 */
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import { act, cleanup, render, waitFor } from "@testing-library/react";
import { MemoryRouter } from "react-router-dom";

import type { InvestigationSummary } from "../../lib/api";

const SUMMARIES: InvestigationSummary[] = [
  { investigation_id: "X", question: "Is the gate safe?", status: "in_progress", started_at: "2026-09-20T10:00:00Z", completed_at: null, cost_usd_total: 0.1, parent_investigation_id: null },
];
vi.mock("../../lib/api", async (orig) => ({
  ...(await orig<typeof import("../../lib/api")>()),
  listInvestigations: vi.fn(async () => ({ count: SUMMARIES.length, investigations: SUMMARIES })),
}));

import CompanionPane from "../CompanionPane";
import { composePreBackendTree } from "../contracts/adapters/preBackend";
import { markTreeUnfed, publishTree } from "../contracts/treeStore";
import { fixtureInputs, tab } from "../contracts/fixtures.test.helpers";
import { useCompanion } from "../companionStore";
import { useWorkspace } from "../WorkspaceStore";
import { useAgentStatusStore, realClock } from "./agentStatusStore";

beforeEach(() => {
  window.localStorage.removeItem("antiek:last_seen:v1");
  useWorkspace.getState().reset();
  useWorkspace.getState().setLayoutPreset("omarchy-inset");
  useCompanion.getState().reset();
  useAgentStatusStore.getState().reset();
  useAgentStatusStore.getState().start(realClock);
});
afterEach(() => {
  cleanup();
  useAgentStatusStore.getState().stop();
  markTreeUnfed();
  useCompanion.getState().reset();
});

const tabGlyph = (c: HTMLElement, id: string) => c.querySelector<HTMLElement>(`[data-agent-tab="${id}"] [role="tab"] [role="img"]`);

describe("CompanionPane glyph on the store", () => {
  it("unfed: the registry glyph; fed: StatusDot from the store; needsInput flips it to blocked; dialogue keeps the brand dot; the strip shows the workspace badge", async () => {
    act(() => { useCompanion.getState().openAgentTab({ kind: "research-thread", investigationId: "X", title: "X" }); });
    act(() => { useCompanion.getState().openAgentTab({ kind: "dialogue" }); });
    const { container } = render(<MemoryRouter><CompanionPane /></MemoryRouter>);
    await waitFor(() => expect(tabGlyph(container, "agent:thread:X")?.getAttribute("aria-label")).toBe("working"));
    expect(tabGlyph(container, "agent:thread:X")?.hasAttribute("data-status")).toBe(false);
    expect(container.querySelector('[data-attention-scope="workspace"] [role="img"]')).toBeNull();

    act(() => publishTree(composePreBackendTree(fixtureInputs({
      investigations: SUMMARIES,
      companionTabs: [tab("research-thread", { investigationId: "X", title: "X" }), tab("dialogue")],
    })), new Date().toISOString()));
    await waitFor(() => expect(tabGlyph(container, "agent:thread:X")?.getAttribute("data-status")).toBe("working"));
    expect(container.querySelector('[data-attention-scope="workspace"] [role="img"]')?.getAttribute("aria-label")).toBe("working");

    act(() => useAgentStatusStore.getState().setNeedsInput("X", true));
    await waitFor(() => expect(tabGlyph(container, "agent:thread:X")?.getAttribute("data-status")).toBe("blocked"));
    expect(tabGlyph(container, "agent:thread:X")?.getAttribute("aria-label")).toBe("blocked");
    expect(container.querySelector('[data-attention-scope="workspace"] [role="img"]')?.getAttribute("aria-label")).toBe("blocked");

    const dialogue = tabGlyph(container, "agent:dialogue");
    expect(dialogue?.getAttribute("aria-label")).toBe("dialogue");
    expect(dialogue?.hasAttribute("data-status")).toBe(false);
    expect(dialogue?.className).toContain("bg-sun");
  });
});
