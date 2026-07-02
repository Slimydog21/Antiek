import { renderHook } from "@testing-library/react";
import { afterEach, beforeEach, describe, expect, it } from "vitest";

import type { InvestigationSummary } from "../lib/api";
import {
  INVESTIGATION_TREE_STORAGE_KEY,
  recordSpawnRelationship,
  useInvestigationTree,
} from "./useInvestigationTree";

function inv(
  investigation_id: string,
  over: Partial<InvestigationSummary> = {},
): InvestigationSummary {
  return {
    investigation_id,
    question: investigation_id,
    status: "completed",
    started_at: "2026-07-01T00:00:00Z",
    completed_at: null,
    cost_usd_total: 0,
    parent_investigation_id: null,
    ...over,
  };
}

const originalLocalStorage = window.localStorage;

function installLocalStorageStub() {
  const store = new Map<string, string>();
  Object.defineProperty(window, "localStorage", {
    configurable: true,
    value: {
      getItem: (key: string) => store.get(key) ?? null,
      setItem: (key: string, value: string) => store.set(key, value),
      removeItem: (key: string) => store.delete(key),
      clear: () => store.clear(),
    },
  });
}

beforeEach(() => {
  installLocalStorageStub();
});

afterEach(() => {
  Object.defineProperty(window, "localStorage", {
    configurable: true,
    value: originalLocalStorage,
  });
});

describe("useInvestigationTree", () => {
  it("keeps investigations visible when substrate parent links form a cycle", () => {
    const { result } = renderHook(() =>
      useInvestigationTree([
        inv("inv-a", { parent_investigation_id: "inv-b" }),
        inv("inv-b", { parent_investigation_id: "inv-a" }),
      ]),
    );

    expect(result.current.map((node) => node.investigationId).sort()).toEqual([
      "inv-a",
      "inv-b",
    ]);
    expect(result.current.flatMap((node) => node.children)).toHaveLength(0);
  });

  it("ignores malformed localStorage parent maps instead of hiding roots", () => {
    window.localStorage.setItem(
      INVESTIGATION_TREE_STORAGE_KEY,
      JSON.stringify({
        "inv-child": 42,
        "": "inv-parent",
        "inv-valid-child": "inv-parent",
      }),
    );

    const { result } = renderHook(() =>
      useInvestigationTree([
        inv("inv-parent"),
        inv("inv-child"),
        inv("inv-valid-child"),
      ]),
    );

    const parent = result.current.find((node) => node.investigationId === "inv-parent");
    expect(parent?.children.map((node) => node.investigationId)).toEqual([
      "inv-valid-child",
    ]);
    expect(result.current.some((node) => node.investigationId === "inv-child")).toBe(true);
  });

  it("trims local parent links and summary ids before building the tree", () => {
    window.localStorage.setItem(
      INVESTIGATION_TREE_STORAGE_KEY,
      JSON.stringify({
        " inv-child ": " inv-parent ",
      }),
    );

    const { result } = renderHook(() =>
      useInvestigationTree([
        inv(" inv-parent "),
        inv(" inv-child "),
        inv(" "),
      ]),
    );

    expect(result.current.map((node) => node.investigationId)).toEqual([
      "inv-parent",
    ]);
    expect(result.current[0].children.map((node) => node.investigationId)).toEqual([
      "inv-child",
    ]);
  });

  it("records only valid trimmed spawn relationships", () => {
    recordSpawnRelationship(" child-id ", " parent-id ");
    recordSpawnRelationship(" ", "ignored-parent");
    recordSpawnRelationship("ignored-child", " ");

    expect(
      JSON.parse(window.localStorage.getItem(INVESTIGATION_TREE_STORAGE_KEY) ?? "{}"),
    ).toEqual({
      "child-id": "parent-id",
    });
  });
});
