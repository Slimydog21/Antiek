import { act, cleanup, fireEvent, isInaccessible, render, screen, waitFor, within } from "@testing-library/react";
import { useEffect } from "react";
import { MemoryRouter } from "react-router-dom";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import { AUTH_SESSION_CHANGE_KEY, AuthProvider, claimLogin, useAuth, type AuthContextValue } from "./auth";
import { isWorkspaceOwnerSession, setWorkspaceOwner, workspaceOwnerSession } from "./accountWorkspaceOwner";
import { useWorkspace } from "../workspace/WorkspaceStore";
import { useWorkspaceHydration } from "../workspace/useWorkspaceHydration";
import { readScope } from "../workspace/persistence";
import { openPopoutFor, receivePopoutPanel } from "../workspace/popout";

function response(status: number, body: unknown = {}): Response {
  return new Response(JSON.stringify(body), { status, headers: { "Content-Type": "application/json" } });
}
function identity(subject: string): Response {
  return response(200, { user_id: subject, email: null, auth_method: "magic_link" });
}
let authReply: () => Promise<Response>;
let logoutReply: () => Promise<Response>;
let controller: AuthContextValue | null;
function auth(): AuthContextValue {
  if (!controller) throw new Error("auth consumer has not mounted");
  return controller;
}
function WorkspaceView() {
  const current = useAuth();
  useWorkspaceHydration();
  const panels = useWorkspace((state) => state.panels);
  useEffect(() => { controller = current; }, [current]);
  return <>
    <input aria-label="Unsaved mounted draft" defaultValue="" />
    <output data-testid="identity">{current.state.status === "authenticated" ? current.state.identity.user_id : current.state.status}</output>
    {current.state.status === "authenticated" && <output data-testid="private-panels">{JSON.stringify(panels)}</output>}
  </>;
}
function mount() {
  return render(<MemoryRouter initialEntries={["/inv/shared"]}><AuthProvider><WorkspaceView /></AuthProvider></MemoryRouter>);
}
function openA() {
  act(() => { useWorkspace.getState().open("NotebookEditor", {
    notebookId: "shared", initialContent: "A private notebook", provider: "A private provider",
  }, { id: "a-body" }); useWorkspace.getState().pin("a-body"); });
}
async function refresh(reply: () => Promise<Response>) {
  authReply = reply;
  await act(async () => { await auth().refresh(); });
}

function expectPrivatePanelsHidden() {
  const panels = screen.queryByTestId("private-panels");
  expect(panels === null || isInaccessible(panels)).toBe(true);
}

// Only the OS window and cross-window transport are simulated. The auth
// lifecycle, owner token, descriptor and popout publisher/receiver are real.
class UnitChannel extends EventTarget {
  static channels = new Set<UnitChannel>();
  closed = false;
  constructor(readonly name: string) { super(); UnitChannel.channels.add(this); }
  postMessage(data: unknown) {
    for (const peer of UnitChannel.channels) {
      if (peer !== this && !peer.closed && peer.name === this.name) {
        queueMicrotask(() => { if (!peer.closed) peer.dispatchEvent(new MessageEvent("message", { data })); });
      }
    }
  }
  close() { this.closed = true; UnitChannel.channels.delete(this); }
}

beforeEach(() => {
  setWorkspaceOwner(null);
  window.localStorage.clear();
  window.sessionStorage.clear();
  controller = null;
  authReply = async () => identity("account-a");
  logoutReply = async () => new Response(null, { status: 204 });
  vi.stubGlobal("fetch", vi.fn<typeof fetch>().mockImplementation(async (input) => {
    const path = new URL(String(input), "http://localhost").pathname;
    if (path === "/auth/me") return authReply();
    if (path === "/auth/logout") return logoutReply();
    if (path === "/auth/claim") return response(200, { setup_passkey: false, next: "/inv/shared" });
    if (path === "/health") return response(200);
    throw new Error(`Unexpected source-control request: ${path}`);
  }));
});
afterEach(() => {
  cleanup();
  setWorkspaceOwner(null);
  for (const channel of UnitChannel.channels) channel.close();
  vi.restoreAllMocks();
  vi.unstubAllGlobals();
  vi.useRealTimers();
});

describe("AuthProvider retires private workspace bodies", () => {
  it("hides and suspends A on a cross-tab signal and only verified B retires its token", async () => {
    mount();
    await screen.findByText("account-a", {}, { timeout: 10000 });
    openA();
    const owner = workspaceOwnerSession();
    let finish: (response: Response) => void = () => { throw new Error("refresh not started"); };
    authReply = () => new Promise((done) => { finish = done; });
    act(() => { window.dispatchEvent(new StorageEvent("storage", {
      key: AUTH_SESSION_CHANGE_KEY, oldValue: "old", newValue: "untrusted-account-name",
    })); });
    expectPrivatePanelsHidden();
    expect(workspaceOwnerSession()).toBe(owner);
    expect(isWorkspaceOwnerSession(owner)).toBe(false);
    expect(useWorkspace.getState().panels["a-body"].props.initialContent).toBe("A private notebook");
    await act(async () => { finish(identity("account-b")); });
    expect(screen.getByTestId("identity").textContent).toBe("account-b");
    expect(screen.getByTestId("private-panels").textContent).not.toContain("A private");
    expect(workspaceOwnerSession()).not.toBe(owner);
    expect(isWorkspaceOwnerSession(owner)).toBe(false);
  }, 15000);
  it("A→B never carries pinned panel bodies and A's reload restores its own partition", async () => {
    const mounted = mount();
    await screen.findByText("account-a", {}, { timeout: 10000 });
    openA();
    expect(screen.getByTestId("private-panels").textContent).toContain("A private notebook");
    await refresh(async () => identity("account-b"));
    expect(screen.getByTestId("identity").textContent).toBe("account-b");
    expect(screen.getByTestId("private-panels").textContent).not.toContain("A private");
    expect(readScope({ kind: "investigation", id: "shared" })).toBeNull();
    mounted.unmount();
    authReply = async () => identity("account-a");
    mount();
    await screen.findByText("account-a", {}, { timeout: 10000 });
    expect(screen.getByTestId("private-panels").textContent).toContain("A private notebook");
    expect(screen.getByTestId("private-panels").textContent).toContain("A private provider");
  }, 15000);

  it("logout immediately removes rendered bodies while the logout request is unresolved", async () => {
    mount();
    await screen.findByText("account-a", {}, { timeout: 10000 });
    openA();
    let finish: (response: Response) => void = () => { throw new Error("logout not sent"); };
    logoutReply = () => new Promise((done) => { finish = done; });
    let pending: Promise<void> | null = null;
    act(() => { pending = auth().signOut(); });
    expect(screen.queryByTestId("private-panels")).toBeNull();
    expect(useWorkspace.getState().panels).toEqual({});
    await act(async () => { finish(new Response(null, { status: 204 })); await pending; });
    expect(screen.getByTestId("identity").textContent).toBe("unauthenticated");
  }, 15000);

  it("definitive 401 retires A but an unreadable transport result never creates a new actor", async () => {
    mount();
    await screen.findByText("account-a", {}, { timeout: 10000 });
    openA();
    await refresh(async () => { throw new TypeError("Failed to fetch"); });
    // Existing inferred-401 behavior remains: no public actor was validated.
    expect(workspaceOwnerSession().subject).toBe("account-a");
    expect(useWorkspace.getState().panels["a-body"].props.initialContent).toBe("A private notebook");
    await refresh(async () => response(401));
    expect(screen.queryByTestId("private-panels")).toBeNull();
    expect(useWorkspace.getState().panels).toEqual({});
    await refresh(async () => identity("account-b"));
    expect(screen.getByTestId("private-panels").textContent).not.toContain("A private");
  }, 15000);

  it("an identity answer started before logout cannot rehydrate the retired owner", async () => {
    mount();
    await screen.findByText("account-a", {}, { timeout: 10000 });
    openA();
    let finish: (response: Response) => void = () => { throw new Error("refresh not started"); };
    authReply = () => new Promise((done) => { finish = done; });
    let pending: Promise<void> | null = null;
    act(() => { pending = auth().refresh(); });
    await act(async () => { await auth().signOut(); });
    await act(async () => { finish(identity("account-a")); await pending; });
    expect(screen.getByTestId("identity").textContent).toBe("unauthenticated");
    expect(useWorkspace.getState().panels).toEqual({});
  }, 15000);

  it("pending logout refuses automatic refresh, focus and cross-tab re-admission", async () => {
    mount();
    await screen.findByText("account-a", {}, { timeout: 10000 });
    openA();
    let finish: (answer: Response) => void = () => { throw new Error("logout not sent"); };
    logoutReply = () => new Promise((done) => { finish = done; });
    const fetches = vi.mocked(fetch);
    const identityCalls = () => fetches.mock.calls.filter(([input]) => String(input).endsWith("/auth/me")).length;
    const before = identityCalls();
    let pending: Promise<void> | null = null;
    act(() => { pending = auth().signOut(); });
    await act(async () => {
      window.dispatchEvent(new Event("focus"));
      window.dispatchEvent(new StorageEvent("storage", {
        key: AUTH_SESSION_CHANGE_KEY, oldValue: "before", newValue: "old-cookie-still-valid",
      }));
      await auth().refresh();
    });
    expect(identityCalls()).toBe(before);
    expect(workspaceOwnerSession().subject).toBeNull();
    expect(screen.getByTestId("identity").textContent).toBe("unauthenticated");
    expect(screen.queryByTestId("private-panels")).toBeNull();
    await act(async () => { finish(new Response(null, { status: 204 })); await pending; });
  }, 15000);

  it.each([
    { name: "network rejection", reply: async (): Promise<Response> => { throw new TypeError("controlled logout rejection"); } },
    { name: "non-2xx response", reply: async () => response(503) },
  ])("$name cannot automatically restore the retired A cookie", async ({ reply }) => {
    mount();
    await screen.findByText("account-a", {}, { timeout: 10000 });
    openA();
    logoutReply = reply;
    await act(async () => { await expect(auth().signOut()).rejects.toThrow(); });
    // The external boundary still answers with the old A session.
    await refresh(async () => identity("account-a"));
    await act(async () => { window.dispatchEvent(new Event("focus")); });
    await waitFor(() => expect(screen.getByTestId("identity").textContent).toBe("unauthenticated"), { timeout: 10000 });
    expect(workspaceOwnerSession().subject).toBeNull();
    expect(useWorkspace.getState().panels).toEqual({});
    expect(screen.queryByTestId("private-panels")).toBeNull();
  }, 15000);

  it("a successful interactive claim still requires verified /auth/me to recover A", async () => {
    mount();
    await screen.findByText("account-a", {}, { timeout: 10000 });
    openA();
    await act(async () => { await auth().signOut(); });
    await refresh(async () => identity("account-a"));
    expect(workspaceOwnerSession().subject).toBeNull();
    let finish: (answer: Response) => void = () => { throw new Error("proof refresh not sent"); };
    authReply = () => new Promise((done) => { finish = done; });
    let pending: Promise<void> | null = null;
    await act(async () => {
      // Real claim helper, synthetic transport proof; no real email/account.
      const proof = await claimLogin("unit-attempt", "unit-claim-secret", "1234");
      expect(proof.status).toBe("authenticated");
      pending = auth().refresh({ afterSignIn: true });
    });
    expect(workspaceOwnerSession().subject).toBeNull();
    expect(screen.queryByTestId("private-panels")).toBeNull();
    await act(async () => { finish(identity("account-a")); await pending; });
    expect(workspaceOwnerSession().subject).toBe("account-a");
    await waitFor(() => expect(screen.getByTestId("private-panels").textContent).toContain("A private notebook"), { timeout: 10000 });
    expect(screen.getByTestId("private-panels").textContent).toContain("A private provider");
  }, 15000);

  it("reload after failed logout denies the old A cookie until interactive proof and /auth/me recover A", async () => {
    const mounted = mount();
    await screen.findByText("account-a", {}, { timeout: 10000 });
    openA();
    logoutReply = async () => response(503);
    await act(async () => { await expect(auth().signOut()).rejects.toThrow(); });
    mounted.unmount();
    controller = null;
    // Keep the browser's storage and old-cookie transport answer intact.
    mount();
    await screen.findByText("unauthenticated", {}, { timeout: 10000 });
    expect(workspaceOwnerSession().subject).toBeNull();
    expect(screen.queryByTestId("private-panels")).toBeNull();
    await refresh(async () => identity("account-a"));
    expect(workspaceOwnerSession().subject).toBeNull();
    let finish: (answer: Response) => void = () => { throw new Error("recovery proof refresh not sent"); };
    authReply = () => new Promise((done) => { finish = done; });
    let pending: Promise<void> | null = null;
    await act(async () => {
      const proof = await claimLogin("unit-returning-attempt", "unit-returning-claim-secret", "1234");
      expect(proof.status).toBe("authenticated");
      pending = auth().refresh({ afterSignIn: true });
    });
    expect(workspaceOwnerSession().subject).toBeNull();
    await act(async () => { finish(identity("account-a")); await pending; });
    await waitFor(() => expect(screen.getByTestId("private-panels").textContent).toContain("A private notebook"), { timeout: 10000 });
    expect(screen.getByTestId("private-panels").textContent).toContain("A private provider");
    expect(workspaceOwnerSession().subject).toBe("account-a");
  }, 15000);

  it.each(["focus", "remote session notification"])("same-owner %s preserves the mounted unsaved input and exact owner token", async (signal) => {
    mount();
    await screen.findByText("account-a", {}, { timeout: 10000 });
    openA();
    const owner = workspaceOwnerSession();
    const input = screen.getByRole("textbox", { name: "Unsaved mounted draft" });
    fireEvent.change(input, { target: { value: "A unsaved mounted text" } });
    let finish: (answer: Response) => void = () => { throw new Error("revalidation not sent"); };
    authReply = () => new Promise((done) => { finish = done; });
    act(() => {
      if (signal === "focus") window.dispatchEvent(new Event("focus"));
      else window.dispatchEvent(new StorageEvent("storage", {
        key: AUTH_SESSION_CHANGE_KEY, oldValue: "old", newValue: "other-window-initial-auth",
      }));
    });
    expect(workspaceOwnerSession()).toBe(owner);
    expect(isWorkspaceOwnerSession(owner)).toBe(false);
    expect(screen.getByLabelText("Unsaved mounted draft")).toBe(input);
    expect(input).toHaveProperty("value", "A unsaved mounted text");
    expect(isInaccessible(input)).toBe(true);
    expectPrivatePanelsHidden();
    await act(async () => { finish(identity("account-a")); });
    expect(workspaceOwnerSession()).toBe(owner);
    expect(isWorkspaceOwnerSession(owner)).toBe(true);
    expect(screen.getByRole("textbox", { name: "Unsaved mounted draft" })).toBe(input);
    expect(input).toHaveProperty("value", "A unsaved mounted text");
    expect(isInaccessible(input)).toBe(false);
    expect(screen.getByTestId("private-panels").textContent).toContain("A private notebook");
  }, 15000);

  it("another real provider's initial A confirmation emits no replacement notification", async () => {
    const first = mount();
    await within(first.container).findByText("account-a", {}, { timeout: 10000 });
    const input = within(first.container).getByRole("textbox", { name: "Unsaved mounted draft" });
    fireEvent.change(input, { target: { value: "First window unsaved text" } });
    const owner = workspaceOwnerSession();
    expect(window.localStorage.getItem(AUTH_SESSION_CHANGE_KEY)).toBeNull();
    let finish: (answer: Response) => void = () => { throw new Error("second initial auth not sent"); };
    authReply = () => new Promise((done) => { finish = done; });
    const second = mount();
    await act(async () => { finish(identity("account-a")); });
    await within(second.container).findByText("account-a", {}, { timeout: 10000 });
    expect(window.localStorage.getItem(AUTH_SESSION_CHANGE_KEY)).toBeNull();
    expect(workspaceOwnerSession()).toBe(owner);
    expect(within(first.container).getByRole("textbox", { name: "Unsaved mounted draft" })).toBe(input);
    expect(input).toHaveProperty("value", "First window unsaved text");
    // A positive interactive proof has a different notification contract.
    authReply = async () => identity("account-a");
    await act(async () => { await auth().refresh({ afterSignIn: true }); });
    expect(window.localStorage.getItem(AUTH_SESSION_CHANGE_KEY)).not.toBeNull();
  }, 15000);

  it("real popout handoff survives same-A focus and closes only after verified B", async () => {
    vi.stubGlobal("BroadcastChannel", UnitChannel);
    const closeWindow = vi.spyOn(window, "close").mockImplementation(() => {});
    vi.spyOn(window, "open").mockReturnValue(window);
    mount();
    await screen.findByText("account-a", {}, { timeout: 10000 });
    openA();
    act(() => { openPopoutFor("a-body"); });
    const publishers = [...UnitChannel.channels];
    expect(publishers).toHaveLength(1);
    const publisher = publishers[0];
    if (publisher === undefined) throw new Error("Popout did not register its publisher");
    const owner = workspaceOwnerSession();
    let finish: (answer: Response) => void = () => { throw new Error("focus auth not sent"); };
    authReply = () => new Promise((done) => { finish = done; });
    act(() => { window.dispatchEvent(new Event("focus")); });
    expect(workspaceOwnerSession()).toBe(owner);
    expect(isWorkspaceOwnerSession(owner)).toBe(false);
    expect(closeWindow).not.toHaveBeenCalled();
    expect(publishers.every((channel) => !channel.closed)).toBe(true);
    expectPrivatePanelsHidden();
    const peer = new UnitChannel(publisher.name);
    const pendingDeliveries: unknown[] = [];
    peer.addEventListener("message", (event) => {
      if (event instanceof MessageEvent) pendingDeliveries.push(event.data);
    });
    await act(async () => {
      peer.postMessage({ kind: "popout-ready", panelId: "a-body" });
      await Promise.resolve();
    });
    expect(pendingDeliveries).toEqual([]);
    peer.close();
    await act(async () => { finish(identity("account-a")); });
    expect(workspaceOwnerSession()).toBe(owner);
    expect(closeWindow).not.toHaveBeenCalled();
    await act(async () => {
      const descriptor = await receivePopoutPanel("a-body");
      expect(descriptor?.props.initialContent).toBe("A private notebook");
    });
    await refresh(async () => identity("account-b"));
    expect(closeWindow).toHaveBeenCalledOnce();
    expect(publishers.every((channel) => channel.closed)).toBe(true);
    expect(workspaceOwnerSession()).not.toBe(owner);
    expect(screen.getByTestId("private-panels").textContent).not.toContain("A private");
    let pending: Promise<Awaited<ReturnType<typeof receivePopoutPanel>>> | null = null;
    act(() => { pending = receivePopoutPanel("a-body"); });
    await refresh(async () => response(401));
    expect(await pending).toBeNull();
  }, 15000);
});
