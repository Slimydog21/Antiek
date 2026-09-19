import { afterEach, describe, expect, it } from "vitest";
import { cleanup, renderHook, act } from "@testing-library/react";

import {
  historyPayload,
  normalizeThoughtPartnerShape,
  useThoughtPartnerThread,
} from "./useThoughtPartnerThread";
import { clearReadingFocus, setReadingFocus, READING_FOCUS_EVENT } from "../lib/readingFocus";

afterEach(() => {
  cleanup();
  sessionStorage.clear();
  clearReadingFocus();
});

describe("useThoughtPartnerThread", () => {
  it("normalizes shapes", () => {
    expect(normalizeThoughtPartnerShape("challenge")).toBe("CHALLENGE");
    expect(normalizeThoughtPartnerShape("extension")).toBe("EXTENSION");
    expect(normalizeThoughtPartnerShape("nope")).toBe("SYNTHESIS");
  });

  it("keeps multi-turn history and bounds payload", () => {
    const { result } = renderHook(() => useThoughtPartnerThread());
    act(() => {
      const id = result.current.startTurn("first?");
      result.current.completeTurn(id, "first answer", "SYNTHESIS");
    });
    act(() => {
      const id = result.current.startTurn("second?");
      result.current.completeTurn(id, "second answer", "CHALLENGE");
    });
    expect(result.current.messages).toHaveLength(2);
    const hist = historyPayload(result.current.messages);
    expect(hist).toEqual([
      { question: "first?", answer: "first answer" },
      { question: "second?", answer: "second answer" },
    ]);
  });

  it("scopes thread by reading document", () => {
    setReadingFocus({
      documentId: "doc-a",
      pageIndex: 0,
      title: "A",
      pageText: "hello",
      servable: true,
    });
    window.dispatchEvent(new Event(READING_FOCUS_EVENT));
    const { result, rerender } = renderHook(() => useThoughtPartnerThread());
    act(() => {
      const id = result.current.startTurn("about A?");
      result.current.completeTurn(id, "A reply", "SYNTHESIS");
    });
    expect(result.current.scope).toContain("doc-a");

    setReadingFocus({
      documentId: "doc-b",
      pageIndex: 0,
      title: "B",
      pageText: "other",
      servable: true,
    });
    window.dispatchEvent(new Event(READING_FOCUS_EVENT));
    rerender();
    expect(result.current.messages).toHaveLength(0);
    expect(result.current.scope).toContain("doc-b");
  });
});
