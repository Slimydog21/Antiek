import { cleanup, render } from "@testing-library/react";
import { afterEach, describe, expect, it } from "vitest";

import { AgentThread } from "./AgentThread";
import type { AgentTurn } from "./agentThreadStore";
import { IDLE } from "./turnLifecycle";

afterEach(cleanup);

const turn: AgentTurn = {
  id: "stream-1", question: "What supports the claim?", answer: "The evidence",
  shape: "SYNTHESIS", status: "streaming", statusWord: "weighing",
  startedAt: 0, actions: [], tools: [],
};

describe("agent streaming caret motion", () => {
  it("uses the shared motion declaration instead of injecting a style into each pane", () => {
    const { container } = render(
      <AgentThread turns={[turn]} transportKind="whole" lifecycle={IDLE} interview={false} reducedMotion={false} onRetry={() => {}} />,
    );
    expect(container.querySelector("style")).toBeNull();
    expect(container.querySelector<HTMLElement>("[data-stream-caret]")?.style.animation).toBe("antiek-agent-caret 1s steps(2) infinite");
  });

  it("keeps the answer and status visible when reduced motion disables the caret", () => {
    const view = render(
      <AgentThread turns={[turn]} transportKind="whole" lifecycle={IDLE} interview={false} reducedMotion={false} onRetry={() => {}} />,
    );
    view.rerender(
      <AgentThread turns={[turn]} transportKind="whole" lifecycle={IDLE} interview={false} reducedMotion={true} onRetry={() => {}} />,
    );
    expect(view.container.querySelector<HTMLElement>("[data-stream-caret]")?.style.animation).toBe("none");
    expect(view.container.textContent).toContain("The evidence");
    expect(view.container.textContent).toContain("weighing");
    expect(view.container.textContent).toContain("simulated stream: the reply arrives whole");
  });
});
