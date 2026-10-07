/** AgentThread.test.tsx — SPR-07 M3: the status row says "simulated stream" for a whole-reply transport (fix 2); caret; tool rows; Jump to latest. */
import { cleanup, fireEvent, render } from "@testing-library/react";
import { afterEach, describe, expect, it, vi } from "vitest";

import type { AgentTurn } from "./agentThreadStore";
import { AgentThread } from "./AgentThread";
import { IDLE, type LifecycleState } from "./turnLifecycle";

afterEach(cleanup);

const turn = (over: Partial<AgentTurn>): AgentTurn => ({
  id: "t1", question: "q", answer: null, shape: "SYNTHESIS", status: "pending", statusWord: "reading",
  startedAt: 0, actions: [], tools: [], ...over,
});

function mount(turns: AgentTurn[], over: { lifecycle?: LifecycleState; transportKind?: "whole" | "sse"; interview?: boolean; reducedMotion?: boolean; onRetry?: () => void } = {}) {
  return render(
    <AgentThread turns={turns} transportKind={over.transportKind ?? "whole"} lifecycle={over.lifecycle ?? IDLE}
      interview={over.interview ?? false} reducedMotion={over.reducedMotion ?? false} onRetry={over.onRetry ?? (() => {})} />,
  );
}

describe("AgentThread", () => {
  it("a streaming turn shows the present-tense word, the caret, and the visible simulated-stream label", () => {
    const { container } = mount([turn({ status: "streaming", answer: "par", statusWord: "weighing" })], { lifecycle: { phase: "streaming", controller: null, error: null } });
    const row = container.querySelector("[data-turn-status]")!;
    expect(row.textContent).toContain("weighing");
    expect(row.textContent).toContain("simulated stream: the reply arrives whole");
    const caret = container.querySelector("[data-stream-caret]")!;
    expect(caret.className).toContain("motion-reduce:animate-none");
  });

  it("an SSE transport does not claim a simulation; a done turn reads answered and shows library_retrieval_status", () => {
    const { container } = mount([turn({ status: "done", answer: "a", libraryRetrievalStatus: "hit" })], { transportKind: "sse" });
    const row = container.querySelector("[data-turn-status]")!;
    expect(row.textContent).toContain("answered");
    expect(row.textContent).not.toContain("simulated stream");
    expect(row.textContent).toContain("library: hit");
    expect(container.querySelector("[data-stream-caret]")).toBeNull();
  });

  it("hidden turns render without a user blockquote; tool rows render collapsed and only when present", () => {
    const { container } = mount([
      turn({ id: "h", hidden: true, status: "done", answer: "hidden" }),
      turn({ id: "v", status: "done", answer: "shown", tools: [{ id: "tool-1", name: "search", status: "done", detail: "3 hits" }] }),
    ]);
    // The hidden (interview) turn renders its ANSWER but never a user blockquote.
    expect(container.querySelectorAll("[data-agent-turn]")).toHaveLength(2);
    expect(container.querySelectorAll("[data-agent-turn] blockquote")).toHaveLength(1);
    expect(container.querySelector('[data-agent-turn][data-hidden-question]')!.textContent).toContain("hidden");
    const tools = container.querySelector("[data-tool-rows]")!;
    expect(tools).not.toBeNull();
    expect(tools.textContent).toContain("search");
    expect(tools.textContent).not.toContain("3 hits");
    fireEvent.click(tools.querySelector("button")!);
    expect(tools.textContent).toContain("3 hits");
    cleanup();
    const bare = mount([turn({ status: "done", answer: "a" })]);
    expect(bare.container.querySelector("[data-tool-rows]")).toBeNull();
  });

  it("the waiting notices and the failure copy come from the lifecycle; Retry calls back", () => {
    const onRetry = vi.fn();
    const sent = mount([turn({})], { lifecycle: { phase: "sent", controller: new AbortController(), error: null } });
    expect(sent.container.textContent).toContain("waiting for the whole reply (no streaming yet)");
    cleanup();
    const failed = mount([turn({ status: "failed" })], { lifecycle: { phase: "failed", controller: null, error: "HTTP 500" }, interview: true, onRetry });
    expect(failed.container.textContent).toContain("Your agent couldn't get started");
    fireEvent.click(failed.getByRole("button", { name: /retry/i }));
    expect(onRetry).toHaveBeenCalledTimes(1);
  });

  it("Jump to latest is pointer-only (aria-hidden, tabIndex -1) and appears once the reader scrolls away", () => {
    const { container } = mount([turn({ status: "done", answer: "a" })]);
    const scroller = container.querySelector<HTMLElement>("[data-agent-thread-scroll]")!;
    Object.defineProperty(scroller, "scrollHeight", { configurable: true, value: 1000 });
    Object.defineProperty(scroller, "clientHeight", { configurable: true, value: 400 });
    fireEvent.wheel(scroller, { deltaY: -10 });
    const jump = container.querySelector<HTMLButtonElement>("[data-jump-to-latest]")!;
    expect(jump).not.toBeNull();
    expect(jump.getAttribute("aria-hidden")).toBe("true");
    expect(jump.tabIndex).toBe(-1);
    fireEvent.click(jump);
    expect(container.querySelector("[data-jump-to-latest]")).toBeNull();
  });
});
