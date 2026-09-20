import { act, cleanup, render, screen } from "@testing-library/react";
import { useRef } from "react";
import { afterEach, describe, expect, it, vi } from "vitest";

import { WERNER_EXPERIENCE_EVENT } from "../../../werner";
import { useFloatMenuSelection } from "./useFloatMenuSelection";

function Host() {
  const scopeRef = useRef<HTMLDivElement>(null);
  useFloatMenuSelection({ scopeRef });
  return <div ref={scopeRef} data-testid="scope">a research passage</div>;
}

function select(scope: HTMLElement, text: string) {
  const node = scope.firstChild as Text;
  const range = document.createRange();
  range.setStart(node, 0);
  range.setEnd(node, node.textContent?.length ?? 0);
  range.getBoundingClientRect = () =>
    ({ top: 20, left: 30, width: 80, height: 18 }) as DOMRect;
  vi.spyOn(window, "getSelection").mockReturnValue({
    rangeCount: 1,
    getRangeAt: () => range,
    toString: () => text,
  } as unknown as Selection);
  act(() => document.dispatchEvent(new Event("selectionchange")));
}

function clearSelection() {
  vi.spyOn(window, "getSelection").mockReturnValue({
    rangeCount: 0,
    toString: () => "",
  } as unknown as Selection);
  act(() => document.dispatchEvent(new Event("selectionchange")));
}

afterEach(() => {
  cleanup();
  vi.restoreAllMocks();
});

describe("FloatMenu selection reactions", () => {
  it("emits once per selection-open episode", () => {
    const listener = vi.fn();
    window.addEventListener(WERNER_EXPERIENCE_EVENT, listener);
    render(<Host />);
    const scope = screen.getByTestId("scope");

    select(scope, "research passage");
    select(scope, "research passage");
    expect(listener).toHaveBeenCalledTimes(1);

    clearSelection();
    select(scope, "research passage");
    expect(listener).toHaveBeenCalledTimes(2);
    expect((listener.mock.calls[1]?.[0] as CustomEvent).detail).toEqual({
      experience: "highlight",
    });
    window.removeEventListener(WERNER_EXPERIENCE_EVENT, listener);
  });
});
