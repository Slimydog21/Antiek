import { describe, it, expect, beforeEach, afterEach } from "vitest";
import { renderHook, act } from "@testing-library/react";

import { useCustomHotkeys } from "./useCustomHotkeys";
import { getCustomHotkeys } from "../../workspace/shortcuts";
import { readCustomHotkeys } from "../../workspace/persistence";

const ENTITY = {
  entityId: "inv-1",
  route: "/inv/inv-1",
  entityKind: "investigation" as const,
  label: "My investigation",
};

describe("useCustomHotkeys — SPR-08", () => {
  beforeEach(() => {
    window.localStorage.clear();
  });
  afterEach(() => {
    window.localStorage.clear();
  });

  it("assigns a free key and persists it (versioned blob)", () => {
    const { result } = renderHook(() => useCustomHotkeys());
    act(() => {
      const res = result.current.assign({ ...ENTITY, spec: "j" });
      expect(res.ok).toBe(true);
    });
    expect(result.current.bindings).toHaveLength(1);
    // Persisted blob is versioned.
    const blob = readCustomHotkeys();
    expect(blob.schemaVersion).toBe(1);
    expect(blob.bindings[0].spec).toBe("j");
    expect(blob.bindings[0].entityId).toBe("inv-1");
  });

  it("persists across reload (re-mount reads from localStorage)", () => {
    const first = renderHook(() => useCustomHotkeys());
    act(() => {
      first.result.current.assign({ ...ENTITY, spec: "g 1" });
    });
    first.unmount();

    // Simulate a reload: a fresh hook instance.
    const second = renderHook(() => useCustomHotkeys());
    expect(second.result.current.bindings).toHaveLength(1);
    expect(second.result.current.bindings[0].spec).toBe("g 1");
    expect(second.result.current.bindingForEntity("inv-1")?.route).toBe(
      "/inv/inv-1",
    );
  });

  it("pushes the live map into the keydown handler", () => {
    const { result } = renderHook(() => useCustomHotkeys());
    act(() => {
      result.current.assign({ ...ENTITY, spec: "j" });
    });
    const live = getCustomHotkeys();
    expect(live.some((b) => b.spec === "j" && b.entityId === "inv-1")).toBe(true);
  });

  it("REJECTS assigning a key that shadows a built-in (precedence)", () => {
    const { result } = renderHook(() => useCustomHotkeys());
    let res: ReturnType<typeof result.current.assign>;
    act(() => {
      res = result.current.assign({ ...ENTITY, spec: "mod+k" });
    });
    expect(res!.ok).toBe(false);
    expect(res!.conflict?.kind).toBe("builtin");
    expect(result.current.bindings).toHaveLength(0);
  });

  it("REJECTS a reserved browser combo", () => {
    const { result } = renderHook(() => useCustomHotkeys());
    let res: ReturnType<typeof result.current.assign>;
    act(() => {
      res = result.current.assign({ ...ENTITY, spec: "mod+t" });
    });
    expect(res!.ok).toBe(false);
    expect(res!.conflict?.kind).toBe("reserved");
  });

  it("custom-vs-custom: warns without force, overrides with force", () => {
    const { result } = renderHook(() => useCustomHotkeys());
    act(() => {
      result.current.assign({
        entityId: "inv-1",
        route: "/inv/inv-1",
        entityKind: "investigation",
        label: "A",
        spec: "j",
      });
    });
    // Second entity wants the same key — without force it's rejected.
    let res: ReturnType<typeof result.current.assign>;
    act(() => {
      res = result.current.assign({
        entityId: "inv-2",
        route: "/inv/inv-2",
        entityKind: "investigation",
        label: "B",
        spec: "j",
      });
    });
    expect(res!.ok).toBe(false);
    expect(res!.conflict?.kind).toBe("custom");
    expect(result.current.bindings).toHaveLength(1); // still only inv-1

    // With force, it moves to inv-2 (last-write-wins; inv-1 dropped).
    act(() => {
      result.current.assign(
        {
          entityId: "inv-2",
          route: "/inv/inv-2",
          entityKind: "investigation",
          label: "B",
          spec: "j",
        },
        true,
      );
    });
    expect(result.current.bindings).toHaveLength(1);
    expect(result.current.bindings[0].entityId).toBe("inv-2");
  });

  it("re-binding the same entity replaces its key (no self-conflict)", () => {
    const { result } = renderHook(() => useCustomHotkeys());
    act(() => {
      result.current.assign({ ...ENTITY, spec: "j" });
    });
    act(() => {
      const res = result.current.assign({ ...ENTITY, spec: "k" });
      expect(res.ok).toBe(true);
    });
    expect(result.current.bindings).toHaveLength(1);
    expect(result.current.bindings[0].spec).toBe("k");
  });

  it("removeForEntity drops the binding", () => {
    const { result } = renderHook(() => useCustomHotkeys());
    act(() => {
      result.current.assign({ ...ENTITY, spec: "j" });
    });
    act(() => {
      result.current.removeForEntity("inv-1");
    });
    expect(result.current.bindings).toHaveLength(0);
    expect(readCustomHotkeys().bindings).toHaveLength(0);
  });

  it("resetAll clears everything", () => {
    const { result } = renderHook(() => useCustomHotkeys());
    act(() => {
      result.current.assign({ ...ENTITY, spec: "j" });
      result.current.assign({
        entityId: "inv-2",
        route: "/inv/inv-2",
        entityKind: "investigation",
        label: "B",
        spec: "k",
      });
    });
    act(() => {
      result.current.resetAll();
    });
    expect(result.current.bindings).toHaveLength(0);
    // The reset clears the blob; the subsequent effect re-persists an EMPTY
    // versioned envelope (no bindings) — both states mean "no custom hotkeys".
    expect(readCustomHotkeys().bindings).toHaveLength(0);
  });

  it("a sibling instance stays live — an assign in one surfaces in another without a remount", () => {
    // Two concurrently-mounted <AssignHotkey>-style consumers of the hook
    // (e.g. one per research card). Before the SPR-08 sharpen, an assign in A
    // left B stale until B remounted. The in-process pub-sub (+ storage event)
    // keeps siblings in sync.
    const a = renderHook(() => useCustomHotkeys());
    const b = renderHook(() => useCustomHotkeys());
    expect(b.result.current.bindings).toHaveLength(0);

    act(() => {
      a.result.current.assign({
        entityId: "inv-9",
        route: "/inv/inv-9",
        entityKind: "investigation",
        label: "Sibling-live research",
        spec: "alt+j",
      });
    });

    // B must reflect A's assign without B remounting.
    expect(b.result.current.bindings).toHaveLength(1);
    expect(b.result.current.bindings[0].spec).toBe("alt+j");
    expect(b.result.current.bindingForEntity("inv-9")?.label).toBe(
      "Sibling-live research",
    );

    a.unmount();
    b.unmount();
  });
});
