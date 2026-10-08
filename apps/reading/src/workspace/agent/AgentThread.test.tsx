/** AgentThread.test.tsx — SPR-07 M3: the status row says "simulated stream" for a whole-reply transport (fix 2); caret; tool rows; Jump to latest. */
import { act, cleanup, fireEvent, render } from "@testing-library/react";
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
    const { container } = mount([turn({ status: "streaming", answer: "par", statusWord: "weighing" })], { lifecycle: { phase: "streaming", controller: null, error: null, reason: null } });
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
    const sent = mount([turn({})], { lifecycle: { phase: "sent", controller: new AbortController(), error: null, reason: null } });
    expect(sent.container.textContent).toContain("waiting for the whole reply (no streaming yet)");
    cleanup();
    const failed = mount([turn({ status: "failed" })], { lifecycle: { phase: "failed", controller: null, error: "HTTP 500", reason: "transport" }, interview: true, onRetry });
    expect(failed.container.textContent).toContain("Your agent couldn't get started");
    fireEvent.click(failed.getByRole("button", { name: /retry/i }));
    expect(onRetry).toHaveBeenCalledTimes(1);
  });

  it("Jump to latest is keyboard-reachable (not aria-hidden, in the tab order) and appears once the reader scrolls away (repair C8)", () => {
    const { container } = mount([turn({ status: "done", answer: "a" })]);
    const scroller = container.querySelector<HTMLElement>("[data-agent-thread-scroll]")!;
    Object.defineProperty(scroller, "scrollHeight", { configurable: true, value: 1000 });
    Object.defineProperty(scroller, "clientHeight", { configurable: true, value: 400 });
    fireEvent.wheel(scroller, { deltaY: -10 });
    const jump = container.querySelector<HTMLButtonElement>("[data-jump-to-latest]")!;
    expect(jump).not.toBeNull();
    expect(jump.getAttribute("aria-hidden")).toBeNull();
    expect(jump.tabIndex).toBe(0);
    jump.focus();
    expect(document.activeElement).toBe(jump);
    fireEvent.click(jump);
    expect(container.querySelector("[data-jump-to-latest]")).toBeNull();
  });
});

/** A fake scroll container: geometry fixed, scrollTop writable and readable
 *  (jsdom's own scrollTop is inert), so the snap's write is observable. */
function fakeScroller(container: HTMLElement) {
  const el = container.querySelector<HTMLElement>("[data-agent-thread-scroll]")!;
  let top = 0;
  Object.defineProperty(el, "scrollHeight", { configurable: true, value: 1000 });
  Object.defineProperty(el, "clientHeight", { configurable: true, value: 400 });
  Object.defineProperty(el, "scrollTop", { configurable: true, get: () => top, set: (v: number) => { top = v; } });
  const scrollTo = (v: number) => { top = v; fireEvent.scroll(el); };
  const jump = () => container.querySelector("[data-jump-to-latest]");
  return { el, scrollTo, jump };
}

describe("follow-the-tail with the fake scroll container (M3, repair C8)", () => {
  it("the snap's own scroll event never re-follows after a pointerdown unfollow; the user's downward scroll into the band does", () => {
    const view = render(
      <AgentThread turns={[turn({ status: "streaming", answer: "a" })]} transportKind="whole" lifecycle={IDLE} interview={false} reducedMotion={false} onRetry={() => {}} />,
    );
    const { el, scrollTo, jump } = fakeScroller(view.container);
    // A chunk lands while following: the snap writes the end position.
    view.rerender(
      <AgentThread turns={[turn({ status: "streaming", answer: "ab" })]} transportKind="whole" lifecycle={IDLE} interview={false} reducedMotion={false} onRetry={() => {}} />,
    );
    expect(el.scrollTop).toBe(1000);
    expect(jump()).toBeNull();
    fireEvent.pointerDown(el);
    expect(jump()).not.toBeNull();
    // The snap's pending scroll event lands AFTER the pointerdown: same
    // position, "down", near the end — it must not re-follow.
    scrollTo(1000);
    expect(jump()).not.toBeNull();
    // A later chunk while unfollowed never snaps the user back.
    view.rerender(
      <AgentThread turns={[turn({ status: "streaming", answer: "a longer answer" })]} transportKind="whole" lifecycle={IDLE} interview={false} reducedMotion={false} onRetry={() => {}} />,
    );
    expect(el.scrollTop).toBe(1000);
    expect(jump()).not.toBeNull();
    // The user scrolls up, then back down into the 80 px band: re-follow.
    scrollTo(500);
    expect(jump()).not.toBeNull();
    scrollTo(960);
    expect(jump()).toBeNull();
  });

  it("an upward scroll inside the 80 px band unfollows (a scrollbar/keyboard peek), and a wheel up does too", () => {
    const view = render(
      <AgentThread turns={[turn({ status: "streaming", answer: "a" })]} transportKind="whole" lifecycle={IDLE} interview={false} reducedMotion={false} onRetry={() => {}} />,
    );
    const { el, scrollTo, jump } = fakeScroller(view.container);
    view.rerender(
      <AgentThread turns={[turn({ status: "streaming", answer: "ab" })]} transportKind="whole" lifecycle={IDLE} interview={false} reducedMotion={false} onRetry={() => {}} />,
    );
    expect(el.scrollTop).toBe(1000);
    expect(jump()).toBeNull();
    scrollTo(990); // 10 px up from the end, inside the band
    expect(jump()).not.toBeNull();
    fireEvent.click(jump()!);
    expect(jump()).toBeNull();
    fireEvent.wheel(el, { deltaY: -1 });
    expect(jump()).not.toBeNull();
  });
});

describe("the elapsed timer pauses while the document is hidden (M3, repair C4)", () => {
  it("counts visible seconds only: 3 s shown, 60 s hidden, back ⇒ still 3 s (no jump), then 5 s", () => {
    vi.useFakeTimers();
    let hidden = false;
    Object.defineProperty(document, "hidden", { configurable: true, get: () => hidden });
    try {
      const { container } = mount([turn({ status: "pending", startedAt: performance.now() })]);
      const row = () => container.querySelector("[data-turn-status]")!.textContent!;
      act(() => { vi.advanceTimersByTime(3000); });
      expect(row()).toContain("· 3s");
      hidden = true;
      act(() => { document.dispatchEvent(new Event("visibilitychange")); });
      act(() => { vi.advanceTimersByTime(60000); });
      hidden = false;
      act(() => { document.dispatchEvent(new Event("visibilitychange")); });
      expect(row()).toContain("· 3s");
      expect(row()).not.toContain("63s");
      act(() => { vi.advanceTimersByTime(2000); });
      expect(row()).toContain("· 5s");
    } finally {
      delete (document as unknown as Record<string, unknown>).hidden;
      vi.useRealTimers();
    }
  });

  it("a re-render while hidden does not advance the number either (the value, not only the tick, is paused)", () => {
    vi.useFakeTimers();
    let hidden = false;
    Object.defineProperty(document, "hidden", { configurable: true, get: () => hidden });
    try {
      const t = turn({ status: "pending", startedAt: performance.now() });
      const view = mount([t]);
      const row = () => view.container.querySelector("[data-turn-status]")!.textContent!;
      act(() => { vi.advanceTimersByTime(2000); });
      expect(row()).toContain("· 2s");
      hidden = true;
      act(() => { document.dispatchEvent(new Event("visibilitychange")); });
      act(() => { vi.advanceTimersByTime(30000); });
      // A streaming chunk re-renders the turn while the tab is hidden.
      view.rerender(
        <AgentThread turns={[{ ...t, status: "streaming", answer: "par" }]} transportKind="whole" lifecycle={IDLE}
          interview={false} reducedMotion={false} onRetry={() => {}} />,
      );
      expect(row()).toContain("· 2s");
      expect(row()).not.toContain("32s");
    } finally {
      delete (document as unknown as Record<string, unknown>).hidden;
      vi.useRealTimers();
    }
  });
});
