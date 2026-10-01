import {
  Suspense,
  startTransition,
  useLayoutEffect,
  type ReactNode,
} from "react";
import { act, cleanup, render, waitFor } from "@testing-library/react";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
vi.mock("../lib/posthogClient", () => ({
  posthogEnabled: false,
  posthog: { identify: vi.fn(), reset: vi.fn() },
}));
vi.mock("./useReadingState", () => ({ setReadingStateOwner: vi.fn() }));
vi.mock("../modes/Write/sectionProseOwner", () => ({
  setSectionProseOwner: vi.fn(),
  suspendSectionProseDispatch: vi.fn(),
}));
import { AuthProvider, useAuth, type AuthContextValue } from "../lib/auth";
import {
  useOwnerModelController,
  type OwnerModelController,
  type OwnerModelControllerOptions,
} from "./useOwnerModelController";
import type { UserModelRow } from "../api/settingsModels";
const A = { user_id: "a", email: null, auth_method: "antiek_session_cookie" };
const row: UserModelRow = {
  id: "key-a",
  provider_kind: "openai_compat",
  provider_catalog_id: null,
  model_id: "primary",
  model_ids: ["primary", "secondary", "secondary"],
  display_name: "Fixture",
  base_url: null,
  enabled: true,
  key_present: true,
  registered: true,
  route_eligible: true,
  pricing_status: "known",
  hard_ceiling_eligible: true,
  execution_status: "executable",
  rate_snapshot: null,
};
let rows: UserModelRow[];
let identity = A;
let invalid = false;
let calls: string[];
let controller: OwnerModelController;
let auth: AuthContextValue;
const options: OwnerModelControllerOptions = {
  operationPrefix: "fixture",
  policy: "strict-owner",
  allowHouse: false,
};
function Probe({
  policy = options.policy,
  allowHouse = false,
  operationPrefix = options.operationPrefix,
  onLayout,
  suspend,
  children,
}: {
  policy?: OwnerModelControllerOptions["policy"];
  allowHouse?: boolean;
  operationPrefix?: string;
  onLayout?: () => void;
  suspend?: Promise<void>;
  children?: ReactNode;
}) {
  auth = useAuth();
  controller = useOwnerModelController({ operationPrefix, policy, allowHouse });
  useLayoutEffect(() => {
    onLayout?.();
  }, [policy, allowHouse, operationPrefix, onLayout]);
  if (suspend) throw suspend;
  return (
    <>
      <span>{controller.inventory.kind}</span>
      {children}
    </>
  );
}
beforeEach(() => {
  rows = [{ ...row, model_ids: [...row.model_ids!] }];
  identity = A;
  invalid = false;
  calls = [];
  vi.stubGlobal(
    "fetch",
    vi.fn(async (input: RequestInfo | URL, init?: RequestInit) => {
      const path = new URL(String(input), "http://fixture").pathname;
      calls.push(path);
      if (init?.method && init.method !== "GET")
        throw new Error("fixture refuses model sends");
      if (path === "/auth/me") return new Response(JSON.stringify(identity));
      if (path === "/settings/models/user")
        return new Response(
          JSON.stringify(
            invalid
              ? []
              : {
                  models: rows,
                  count: rows.length,
                  stale_registered: [],
                  source: "fixture",
                },
          ),
        );
      throw new Error("fixture route denied");
    }),
  );
});
afterEach(() => {
  cleanup();
  vi.unstubAllGlobals();
});
async function mount(props?: Parameters<typeof Probe>[0]) {
  const view = render(
    <AuthProvider>
      <Probe {...props} />
    </AuthProvider>,
  );
  await waitFor(() => expect(controller.inventory.kind).toBe("ready"));
  return view;
}
function saved() {
  act(() =>
    controller.select({
      kind: "saved",
      recordId: row.id,
      modelId: "secondary",
    }),
  );
  return controller.prepareLaunch({ semanticKey: "complete-intent-1" });
}
describe("unused owner model controller", () => {
  it("starts unselected, freezes parsed deduplicated variants and accepted fields", async () => {
    await mount();
    expect(controller.selection).toEqual({ kind: "unselected" });
    expect(controller.prepareLaunch({ semanticKey: "intent" })).toMatchObject({
      kind: "blocked",
      reason: "selection_required",
    });
    if (controller.inventory.kind !== "ready") throw new Error("not ready");
    expect(controller.inventory.rows[0].model_ids).toEqual([
      "primary",
      "secondary",
    ]);
    expect(Object.isFrozen(controller.inventory.rows[0].model_ids)).toBe(true);
    const prepared = saved();
    expect(prepared.kind).toBe("saved");
    if (prepared.kind !== "saved") return;
    expect(Object.isFrozen(prepared.fields.model_choice)).toBe(true);
    expect(prepared.fields.model_choice.model_id).toBe("secondary");
    expect(controller.isCurrent(prepared)).toBe(true);
    expect(controller.prepareLaunch({ semanticKey: "complete-intent-1" })).toBe(
      prepared,
    );
    expect(calls).toEqual(["/auth/me", "/settings/models/user"]);
  });
  it("retains a removed variant as unavailable without choosing primary or house", async () => {
    await mount();
    const prepared = saved();
    rows = [{ ...row, model_ids: ["primary"] }];
    await act(async () => controller.refresh());
    expect(controller.selection).toEqual({
      kind: "unavailable",
      recordId: row.id,
      modelId: "secondary",
      reason: "variant_missing",
    });
    expect(controller.prepareLaunch({ semanticKey: "intent" })).toMatchObject({
      kind: "blocked",
      reason: "selection_unavailable",
    });
    if (prepared.kind !== "blocked")
      expect(controller.isCurrent(prepared)).toBe(false);
  });
  it("refuses malformed inventory instead of treating it as empty", async () => {
    await mount();
    saved();
    invalid = true;
    await act(async () => controller.refresh());
    expect(controller.inventory).toMatchObject({
      kind: "failed",
      reason: "inventory_invalid",
    });
    expect(controller.prepareLaunch({ semanticKey: "intent" })).toMatchObject({
      kind: "blocked",
      reason: "inventory_not_ready",
    });
  });
  it("invalidates old prepared operations on intent and selected tuple changes", async () => {
    await mount();
    const first = saved();
    const second = controller.prepareLaunch({
      semanticKey: "complete-intent-2",
    });
    if (first.kind !== "saved" || second.kind !== "saved")
      throw new Error("not prepared");
    expect(first.fields.operation_id).not.toBe(second.fields.operation_id);
    expect(controller.isCurrent(first)).toBe(false);
    act(() =>
      controller.select({
        kind: "saved",
        recordId: row.id,
        modelId: "primary",
      }),
    );
    expect(controller.isCurrent(second)).toBe(false);
  });
  it("preserves book-route admission without weakening strict owner policy", async () => {
    rows = [
      {
        ...row,
        key_present: false,
        pricing_status: "unknown",
        execution_status: "blocked_unknown_pricing",
      },
    ];
    await mount({ policy: "book-route" });
    expect(saved().kind).toBe("saved");
  });
  it("requires explicit permitted house selection", async () => {
    await mount();
    act(() => controller.select({ kind: "house" }));
    expect(controller.prepareLaunch({ semanticKey: "intent" })).toMatchObject({
      kind: "blocked",
      reason: "house_not_permitted",
    });
  });
  it("does not revive A operations or accept A render closures in B", async () => {
    await mount();
    const oldController = controller;
    const prepared = saved();
    identity = { ...A, user_id: "b" };
    await act(async () => auth.refresh());
    await waitFor(() => expect(controller.inventory.kind).toBe("ready"));
    act(() =>
      oldController.select({
        kind: "saved",
        recordId: row.id,
        modelId: "secondary",
      }),
    );
    expect(controller.selection.kind).toBe("unselected");
    expect(oldController.prepareLaunch({ semanticKey: "stale" })).toMatchObject(
      { kind: "blocked", reason: "identity_suspended" },
    );
    identity = A;
    await act(async () => auth.refresh());
    await waitFor(() => expect(controller.inventory.kind).toBe("ready"));
    if (prepared.kind !== "blocked")
      expect(controller.isCurrent(prepared)).toBe(false);
  });

  it("retains operation identity across a same-scope inventory refresh while retiring prepared snapshots", async () => {
    await mount();
    const first = saved();
    await act(async () => controller.refresh());
    const second = controller.prepareLaunch({
      semanticKey: "complete-intent-1",
    });
    if (first.kind !== "saved" || second.kind !== "saved")
      throw new Error("not prepared");
    expect(first.fields.operation_id).toBe(second.fields.operation_id);
    expect(second).not.toBe(first);
    expect(controller.isCurrent(first)).toBe(false);
    expect(controller.isCurrent(second)).toBe(true);
  });
  it.each(["record_missing", "row_ineligible"] as const)(
    "retains exact unavailable tuple for %s",
    async (reason) => {
      await mount();
      saved();
      rows = reason === "record_missing" ? [] : [{ ...row, enabled: false }];
      await act(async () => controller.refresh());
      expect(controller.selection).toMatchObject({
        kind: "unavailable",
        recordId: row.id,
        modelId: "secondary",
        reason,
      });
      expect(controller.prepareLaunch({ semanticKey: "intent" }).kind).toBe(
        "blocked",
      );
    },
  );
  it("strict owner policy refuses a book-only row", async () => {
    rows = [{ ...row, key_present: false }];
    await mount();
    expect(saved()).toMatchObject({
      kind: "blocked",
      reason: "selection_unavailable",
    });
  });
  it("permits house only after explicit selection and invalidates it on saved choice", async () => {
    await mount({ allowHouse: true });
    expect(controller.prepareLaunch({ semanticKey: "intent" })).toMatchObject({
      kind: "blocked",
      reason: "selection_required",
    });
    act(() => controller.select({ kind: "house" }));
    const house = controller.prepareLaunch({ semanticKey: "intent" });
    expect(house.kind).toBe("house");
    if (house.kind === "blocked") throw new Error("blocked");
    expect(controller.isCurrent(house)).toBe(true);
    saved();
    expect(controller.isCurrent(house)).toBe(false);
  });
  it("ignores a retired inventory failure without clearing a newer ready snapshot", async () => {
    await mount();
    let reject!: (error: Error) => void;
    const stale = new Promise<Response>((_yes, no) => {
      reject = no;
    });
    let reads = 0;
    vi.stubGlobal(
      "fetch",
      vi.fn((input: RequestInfo | URL) => {
        expect(new URL(String(input), "http://fixture").pathname).toBe(
          "/settings/models/user",
        );
        return ++reads === 1
          ? stale
          : Promise.resolve(
              new Response(
                JSON.stringify({
                  models: rows,
                  count: rows.length,
                  stale_registered: [],
                  source: "fixture",
                }),
              ),
            );
      }),
    );
    let old!: Promise<void>;
    act(() => {
      old = controller.refresh();
    });
    await act(async () => controller.refresh());
    const current = controller.inventory;
    expect(current.kind).toBe("ready");
    await act(async () => {
      reject(new Error("stale fixture failure"));
      await old;
    });
    expect(controller.inventory).toBe(current);
  });
  it("rejects old handlers synchronously at refresh entry before effects run", async () => {
    await mount();
    const old = controller;
    const prepared = saved();
    let observed: unknown;
    vi.stubGlobal(
      "fetch",
      vi.fn(async (input: RequestInfo | URL) => {
        const path = new URL(String(input), "http://fixture").pathname;
        if (path === "/auth/me") {
          old.select({ kind: "saved", recordId: row.id, modelId: "primary" });
          observed = old.prepareLaunch({ semanticKey: "stale-before-effect" });
          if (prepared.kind !== "blocked")
            expect(old.isCurrent(prepared)).toBe(false);
          return new Response(JSON.stringify(identity));
        }
        if (path === "/settings/models/user")
          return new Response(
            JSON.stringify({
              models: rows,
              count: rows.length,
              stale_registered: [],
              source: "fixture",
            }),
          );
        throw new Error("fixture route denied");
      }),
    );
    await act(async () => auth.refresh());
    expect(observed).toMatchObject({
      kind: "blocked",
      reason: "identity_suspended",
    });
    await waitFor(() => expect(controller.inventory.kind).toBe("ready"));
    expect(controller.selection).toMatchObject({
      kind: "saved",
      modelId: "secondary",
    });
  });

  it("retires retained house permission during committed layout before passive effects", async () => {
    const view = await mount({ allowHouse: true });
    act(() => controller.select({ kind: "house" }));
    const old = controller;
    const house = old.prepareLaunch({ semanticKey: "intent" });
    if (house.kind !== "house") throw new Error("not house");
    let observed = false;
    view.rerender(
      <AuthProvider>
        <Probe
          allowHouse={false}
          onLayout={() => {
            observed = true;
            expect(old.isCurrent(house)).toBe(false);
            expect(old.prepareLaunch({ semanticKey: "intent" }).kind).toBe(
              "blocked",
            );
          }}
        />
      </AuthProvider>,
    );
    expect(observed).toBe(true);
    await waitFor(() => expect(controller.inventory.kind).toBe("ready"));
    expect(controller.prepareLaunch({ semanticKey: "intent" })).toMatchObject({
      kind: "blocked",
      reason: "house_not_permitted",
    });
    expect(old.isCurrent(house)).toBe(false);
  });
  it("binds house preparation to complete semantic intent", async () => {
    await mount({ allowHouse: true });
    act(() => controller.select({ kind: "house" }));
    const first = controller.prepareLaunch({ semanticKey: "complete-house-1" });
    const second = controller.prepareLaunch({
      semanticKey: "complete-house-2",
    });
    if (first.kind !== "house" || second.kind !== "house")
      throw new Error("not house");
    expect(second).not.toBe(first);
    expect(controller.isCurrent(first)).toBe(false);
    expect(controller.isCurrent(second)).toBe(true);
    expect(controller.prepareLaunch({ semanticKey: "complete-house-2" })).toBe(
      second,
    );
  });
  it("retires old policy callbacks at layout before passive inventory refresh", async () => {
    rows = [{ ...row, key_present: false }];
    const view = await mount({ policy: "book-route" });
    const prepared = saved();
    if (prepared.kind !== "saved") throw new Error("not saved");
    const old = controller;
    let observed = false;
    view.rerender(
      <AuthProvider>
        <Probe
          policy="strict-owner"
          onLayout={() => {
            observed = true;
            expect(old.isCurrent(prepared)).toBe(false);
            expect(
              old.prepareLaunch({ semanticKey: "complete-intent-1" }).kind,
            ).toBe("blocked");
            old.select({ kind: "saved", recordId: row.id, modelId: "primary" });
          }}
        />
      </AuthProvider>,
    );
    expect(observed).toBe(true);
    await waitFor(() => expect(controller.inventory.kind).toBe("ready"));
    expect(controller.selection).toMatchObject({
      kind: "unavailable",
      modelId: "secondary",
      reason: "row_ineligible",
    });
  });
  it("retires old prefix bindings before passive effects and prepares the new prefix", async () => {
    const view = await mount();
    const prepared = saved();
    if (prepared.kind !== "saved") throw new Error("not saved");
    const old = controller;
    view.rerender(
      <AuthProvider>
        <Probe
          operationPrefix="next"
          onLayout={() => {
            expect(old.isCurrent(prepared)).toBe(false);
            expect(
              old.prepareLaunch({ semanticKey: "complete-intent-1" }).kind,
            ).toBe("blocked");
          }}
        />
      </AuthProvider>,
    );
    await waitFor(() => expect(controller.inventory.kind).toBe("ready"));
    const next = controller.prepareLaunch({ semanticKey: "complete-intent-1" });
    if (next.kind !== "saved") throw new Error("not saved");
    expect(next.fields.operation_id).toMatch(/^next-/);
    expect(next.fields.operation_id).not.toBe(prepared.fields.operation_id);
  });
  it("preserves an operation on exact same tuple reselection and immutable semantic intent", async () => {
    await mount();
    const first = saved();
    const second = saved();
    if (first.kind !== "saved" || second.kind !== "saved")
      throw new Error("not saved");
    expect(second.fields.operation_id).toBe(first.fields.operation_id);
    expect(controller.isCurrent(first)).toBe(true);
  });

  it("does not publish speculative options from a suspended transition", async () => {
    const view = render(
      <AuthProvider>
        <Suspense fallback={<span>fixture pending</span>}>
          <Probe allowHouse />
        </Suspense>
      </AuthProvider>,
    );
    await waitFor(() => expect(controller.inventory.kind).toBe("ready"));
    act(() => controller.select({ kind: "house" }));
    const old = controller;
    const prepared = old.prepareLaunch({ semanticKey: "immutable-intent" });
    if (prepared.kind !== "house") throw new Error("not house");
    const initialReads = calls.length;
    const suspended = new Promise<void>(() => {});
    act(() => {
      startTransition(() => {
        view.rerender(
          <AuthProvider>
            <Suspense fallback={<span>fixture pending</span>}>
              <Probe allowHouse={false} suspend={suspended} />
            </Suspense>
          </AuthProvider>,
        );
      });
    });
    expect(old.isCurrent(prepared)).toBe(true);
    expect(old.prepareLaunch({ semanticKey: "immutable-intent" })).toBe(
      prepared,
    );
    expect(calls).toHaveLength(initialReads);
  });
  it("retires previous options before descendant layout effects", async () => {
    const view = await mount({ allowHouse: true });
    act(() => controller.select({ kind: "house" }));
    const old = controller;
    const prepared = old.prepareLaunch({ semanticKey: "intent" });
    if (prepared.kind !== "house") throw new Error("not house");
    const reads = calls.length;
    const house = prepared;
    let observed = false;
    function Descendant() {
      useLayoutEffect(() => {
        observed = true;
        expect(old.isCurrent(house)).toBe(false);
        expect(old.prepareLaunch({ semanticKey: "intent" }).kind).toBe(
          "blocked",
        );
        void old.refresh();
        expect(calls).toHaveLength(reads);
      }, []);
      return null;
    }
    view.rerender(
      <AuthProvider>
        <Probe allowHouse={false}>
          <Descendant />
        </Probe>
      </AuthProvider>,
    );
    expect(observed).toBe(true);
    await waitFor(() => expect(controller.inventory.kind).toBe("ready"));
  });

  it("refuses retained g1 preparation without overwriting g2 immutable intent", async () => {
    await mount();
    saved();
    const old = controller;
    await act(async () => controller.refresh());
    const current = controller.prepareLaunch({ semanticKey: "new-g2-intent" });
    if (current.kind !== "saved") throw new Error("not saved");
    expect(old.prepareLaunch({ semanticKey: "old-g1-intent" }).kind).toBe(
      "blocked",
    );
    expect(controller.isCurrent(current)).toBe(true);
    expect(controller.prepareLaunch({ semanticKey: "new-g2-intent" })).toBe(
      current,
    );
  });
  it("refuses g1 currentness checks for a g2 preparation", async () => {
    await mount();
    saved();
    const old = controller;
    await act(async () => controller.refresh());
    const current = controller.prepareLaunch({ semanticKey: "new-g2-intent" });
    if (current.kind !== "saved") throw new Error("not saved");
    expect(old.isCurrent(current)).toBe(false);
    expect(controller.isCurrent(current)).toBe(true);
  });
  it("does not schedule reads from a retired g1 refresh handler", async () => {
    await mount();
    saved();
    const old = controller;
    await act(async () => controller.refresh());
    const snapshot = controller.inventory;
    const reads = calls.length;
    await act(async () => old.refresh());
    expect(calls).toHaveLength(reads);
    expect(controller.inventory).toBe(snapshot);
  });
  it("requires nonblank semantic intent for permitted house", async () => {
    await mount({ allowHouse: true });
    act(() => controller.select({ kind: "house" }));
    expect(() => controller.prepareLaunch({ semanticKey: "   " })).toThrow(
      "A complete model launch semantic key is required.",
    );
  });
});
