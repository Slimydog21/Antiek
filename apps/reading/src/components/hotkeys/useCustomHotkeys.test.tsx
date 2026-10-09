import { awaitWorkspaceOwnerSession, setWorkspaceOwner, workspaceOwnerSession } from "../../lib/accountWorkspaceOwner";
import { describe, it, expect, beforeEach, afterEach } from "vitest";
import { renderHook, act } from "@testing-library/react";

import { useCustomHotkeys } from "./useCustomHotkeys";
import { getCustomHotkeys } from "../../workspace/shortcuts";
import { readCustomHotkeys } from "../../workspace/persistence";

beforeEach(() => { setWorkspaceOwner("custom-hotkey-positive-unit"); });
afterEach(() => { setWorkspaceOwner(null); });

const ENTITY = {
  entityId: "inv-1",
  route: "/inv/inv-1",
  entityKind: "investigation" as const,
  label: "My investigation",
};

describe("useCustomHotkeys — SPR-08 (⌘+key only)", () => {
  beforeEach(() => {
    window.localStorage.clear();
  });
  afterEach(() => {
    window.localStorage.clear();
  });

  it("assigns a free ⌘+key combo and persists it (versioned blob)", async () => {
    const { result } = renderHook(() => useCustomHotkeys());
    await act(async () => { await awaitWorkspaceOwnerSession(workspaceOwnerSession()); });
    act(() => {
      const res = result.current.assign({ ...ENTITY, spec: "mod+." });
      expect(res.ok).toBe(true);
    });
    expect(result.current.bindings).toHaveLength(1);
    const blob = readCustomHotkeys();
    expect(blob.schemaVersion).toBe(1);
    expect(blob.bindings[0].spec).toBe("mod+.");
    expect(blob.bindings[0].entityId).toBe("inv-1");
  });

  it("REJECTS an Option-only (⌥) combo — the scheme is ⌘+key only", async () => {
    const { result } = renderHook(() => useCustomHotkeys());
    await act(async () => { await awaitWorkspaceOwnerSession(workspaceOwnerSession()); });
    let res: ReturnType<typeof result.current.assign>;
    act(() => {
      res = result.current.assign({ ...ENTITY, spec: "alt+j" });
    });
    expect(res!.ok).toBe(false);
    expect(res!.conflict?.message).toMatch(/⌘|option-only/i);
    expect(result.current.bindings).toHaveLength(0);
  });

  it("REJECTS a bare single key (a custom binding must carry a modifier)", async () => {
    const { result } = renderHook(() => useCustomHotkeys());
    await act(async () => { await awaitWorkspaceOwnerSession(workspaceOwnerSession()); });
    let res: ReturnType<typeof result.current.assign>;
    act(() => {
      res = result.current.assign({ ...ENTITY, spec: "j" });
    });
    expect(res!.ok).toBe(false);
    expect(res!.conflict?.message).toMatch(/add ⌘|single key/i);
    expect(result.current.bindings).toHaveLength(0);
  });

  it("REJECTS a chord (no key sequences after SPR-08)", async () => {
    const { result } = renderHook(() => useCustomHotkeys());
    await act(async () => { await awaitWorkspaceOwnerSession(workspaceOwnerSession()); });
    let res: ReturnType<typeof result.current.assign>;
    act(() => {
      res = result.current.assign({ ...ENTITY, spec: "g 1" });
    });
    expect(res!.ok).toBe(false);
    expect(res!.conflict?.message).toMatch(/sequence|single ⌘ combo/i);
    expect(result.current.bindings).toHaveLength(0);
  });

  it("persists a ⌘+key custom binding across reload (re-mount reads from localStorage)", async () => {
    const first = renderHook(() => useCustomHotkeys());
    await act(async () => { await awaitWorkspaceOwnerSession(workspaceOwnerSession()); });
    act(() => {
      const res = first.result.current.assign({ ...ENTITY, spec: "mod+." });
      expect(res.ok).toBe(true);
    });
    first.unmount();

    // Simulate a reload: a fresh hook instance round-trips the persisted ⌘ combo.
    const second = renderHook(() => useCustomHotkeys());
    await act(async () => { await awaitWorkspaceOwnerSession(workspaceOwnerSession()); });
    expect(second.result.current.bindings).toHaveLength(1);
    expect(second.result.current.bindings[0].spec).toBe("mod+.");
    expect(second.result.current.bindingForEntity("inv-1")?.route).toBe(
      "/inv/inv-1",
    );
  });

  it("pushes the live map into the keydown handler", async () => {
    const { result } = renderHook(() => useCustomHotkeys());
    await act(async () => { await awaitWorkspaceOwnerSession(workspaceOwnerSession()); });
    act(() => {
      result.current.assign({ ...ENTITY, spec: "mod+." });
    });
    const live = getCustomHotkeys();
    expect(live.some((b) => b.spec === "mod+." && b.entityId === "inv-1")).toBe(true);
  });

  it("REJECTS assigning a key that shadows a built-in (precedence)", async () => {
    const { result } = renderHook(() => useCustomHotkeys());
    await act(async () => { await awaitWorkspaceOwnerSession(workspaceOwnerSession()); });
    let res: ReturnType<typeof result.current.assign>;
    act(() => {
      res = result.current.assign({ ...ENTITY, spec: "mod+k" });
    });
    expect(res!.ok).toBe(false);
    expect(res!.conflict?.kind).toBe("builtin");
    expect(result.current.bindings).toHaveLength(0);
  });

  it("REJECTS assigning a key that shadows a PRODUCT combo", async () => {
    const { result } = renderHook(() => useCustomHotkeys());
    await act(async () => { await awaitWorkspaceOwnerSession(workspaceOwnerSession()); });
    let res: ReturnType<typeof result.current.assign>;
    act(() => {
      res = result.current.assign({ ...ENTITY, spec: "mod+e" }); // Read
    });
    expect(res!.ok).toBe(false);
    expect(res!.conflict?.kind).toBe("product");
    expect(result.current.bindings).toHaveLength(0);
  });

  it("REJECTS a reserved browser combo", async () => {
    const { result } = renderHook(() => useCustomHotkeys());
    await act(async () => { await awaitWorkspaceOwnerSession(workspaceOwnerSession()); });
    let res: ReturnType<typeof result.current.assign>;
    act(() => {
      res = result.current.assign({ ...ENTITY, spec: "mod+t" });
    });
    expect(res!.ok).toBe(false);
    expect(res!.conflict?.kind).toBe("reserved");
  });

  it("custom-vs-custom: warns without force, overrides with force", async () => {
    const { result } = renderHook(() => useCustomHotkeys());
    await act(async () => { await awaitWorkspaceOwnerSession(workspaceOwnerSession()); });
    act(() => {
      result.current.assign({
        entityId: "inv-1",
        route: "/inv/inv-1",
        entityKind: "investigation",
        label: "A",
        spec: "mod+.",
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
        spec: "mod+.",
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
          spec: "mod+.",
        },
        true,
      );
    });
    expect(result.current.bindings).toHaveLength(1);
    expect(result.current.bindings[0].entityId).toBe("inv-2");
  });

  it("re-binding the same entity replaces its key (no self-conflict)", async () => {
    const { result } = renderHook(() => useCustomHotkeys());
    await act(async () => { await awaitWorkspaceOwnerSession(workspaceOwnerSession()); });
    act(() => {
      result.current.assign({ ...ENTITY, spec: "mod+." });
    });
    act(() => {
      const res = result.current.assign({ ...ENTITY, spec: "mod+," });
      expect(res.ok).toBe(true);
    });
    expect(result.current.bindings).toHaveLength(1);
    expect(result.current.bindings[0].spec).toBe("mod+,");
  });

  it("removeForEntity drops the binding", async () => {
    const { result } = renderHook(() => useCustomHotkeys());
    await act(async () => { await awaitWorkspaceOwnerSession(workspaceOwnerSession()); });
    act(() => {
      result.current.assign({ ...ENTITY, spec: "mod+." });
    });
    act(() => {
      result.current.removeForEntity("inv-1");
    });
    expect(result.current.bindings).toHaveLength(0);
    expect(readCustomHotkeys().bindings).toHaveLength(0);
  });

  it("resetAll clears everything", async () => {
    const { result } = renderHook(() => useCustomHotkeys());
    await act(async () => { await awaitWorkspaceOwnerSession(workspaceOwnerSession()); });
    act(() => {
      result.current.assign({ ...ENTITY, spec: "mod+." });
      result.current.assign({
        entityId: "inv-2",
        route: "/inv/inv-2",
        entityKind: "investigation",
        label: "B",
        spec: "mod+,",
      });
    });
    act(() => {
      result.current.resetAll();
    });
    expect(result.current.bindings).toHaveLength(0);
    expect(readCustomHotkeys().bindings).toHaveLength(0);
  });

  it("a sibling instance stays live — an assign in one surfaces in another without a remount", async () => {
    const a = renderHook(() => useCustomHotkeys());
    await act(async () => { await awaitWorkspaceOwnerSession(workspaceOwnerSession()); });
    const b = renderHook(() => useCustomHotkeys());
    await act(async () => { await awaitWorkspaceOwnerSession(workspaceOwnerSession()); });
    expect(b.result.current.bindings).toHaveLength(0);

    act(() => {
      a.result.current.assign({
        entityId: "inv-9",
        route: "/inv/inv-9",
        entityKind: "investigation",
        label: "Sibling-live research",
        spec: "mod+.",
      });
    });

    expect(b.result.current.bindings).toHaveLength(1);
    expect(b.result.current.bindings[0].spec).toBe("mod+.");
    expect(b.result.current.bindingForEntity("inv-9")?.label).toBe(
      "Sibling-live research",
    );

    a.unmount();
    b.unmount();
  });
});
