/**
 * AttentionBadge.test.tsx — SPR-10 M6: a rollup badge per scope, from the
 * same store; renders nothing when the rollup is null.
 */
import { afterEach, beforeEach, describe, expect, it } from "vitest";
import { act, cleanup, render } from "@testing-library/react";

import { composePreBackendTree } from "../contracts/adapters/preBackend";
import { markTreeUnfed, publishTree } from "../contracts/treeStore";
import { fixtureInputs, summary, tab } from "../contracts/fixtures.test.helpers";
import { useCompanion } from "../companionStore";
import { AttentionBadge } from "./AttentionBadge";
import { useAgentStatusStore, realClock } from "./agentStatusStore";

const MEMBER = [{ member_kind: "investigation" as const, member_id: "X", added_at: "2026-09-18T10:00:00Z" }];

beforeEach(() => {
  window.localStorage.removeItem("antiek:last_seen:v1");
  useCompanion.getState().reset();
  useAgentStatusStore.getState().reset();
  useAgentStatusStore.getState().start(realClock);
});
afterEach(() => {
  cleanup();
  useAgentStatusStore.getState().stop();
  markTreeUnfed();
});

function badge(container: HTMLElement) {
  return container.querySelector<HTMLElement>('[data-attention-scope] [role="img"]');
}

describe("AttentionBadge", () => {
  it("renders nothing with no entries; a blocked member lights its project and the workspace, not another project", () => {
    const ws = render(<AttentionBadge scope={{ kind: "workspace" }} />);
    expect(badge(ws.container)).toBeNull();
    act(() => publishTree(composePreBackendTree(fixtureInputs({
      investigations: [summary("X", { status: "in_progress", completed_at: null })],
      companionTabs: [tab("research-thread", { investigationId: "X", title: "X" })],
      membersByProject: new Map([["p1", MEMBER]]),
    })), new Date().toISOString()));
    const p1 = render(<AttentionBadge scope={{ kind: "project", id: "p1" }} ground="island" />);
    const p2 = render(<AttentionBadge scope={{ kind: "project", id: "p2" }} />);
    expect(badge(ws.container)?.getAttribute("aria-label")).toBe("working");
    expect(badge(p1.container)?.getAttribute("aria-label")).toBe("working");
    expect(badge(p1.container)?.firstElementChild?.className).toContain("ring-[var(--fixed-paper)]");
    expect(badge(p2.container)).toBeNull();
    act(() => useAgentStatusStore.getState().setNeedsInput("X", true));
    expect(badge(ws.container)?.getAttribute("aria-label")).toBe("blocked");
    expect(badge(p1.container)?.getAttribute("aria-label")).toBe("blocked");
    expect(badge(p2.container)).toBeNull();
    // The word is sr-only: colour never alone, and nothing visible to crowd a strip.
    expect(badge(ws.container)?.lastElementChild?.className).toContain("sr-only");
  });
});
