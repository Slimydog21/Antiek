import { act, cleanup, render, screen } from "@testing-library/react";
import { useEffect } from "react";
import { MemoryRouter } from "react-router-dom";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import { AUTH_SESSION_CHANGE_KEY, AuthProvider, useAuth, type AuthContextValue } from "./auth";
import { setWorkspaceOwner, workspaceOwnerSession } from "./accountWorkspaceOwner";
import { useWorkspace } from "../workspace/WorkspaceStore";
import { useWorkspaceHydration } from "../workspace/useWorkspaceHydration";
import { readScope } from "../workspace/persistence";

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
    if (path === "/health") return response(200);
    throw new Error(`Unexpected source-control request: ${path}`);
  }));
});
afterEach(() => {
  cleanup();
  setWorkspaceOwner(null);
  vi.unstubAllGlobals();
  vi.useRealTimers();
});

describe("AuthProvider retires private workspace bodies", () => {
  it("retires visible A on a cross-tab signal and only /auth/me can establish B", async () => {
    mount();
    await screen.findByText("account-a", {}, { timeout: 10000 });
    openA();
    let finish: (response: Response) => void = () => { throw new Error("refresh not started"); };
    authReply = () => new Promise((done) => { finish = done; });
    act(() => { window.dispatchEvent(new StorageEvent("storage", {
      key: AUTH_SESSION_CHANGE_KEY, oldValue: "old", newValue: "untrusted-account-name",
    })); });
    expect(screen.queryByTestId("private-panels")).toBeNull();
    expect(workspaceOwnerSession().subject).toBeNull();
    expect(useWorkspace.getState().panels).toEqual({});
    await act(async () => { finish(identity("account-b")); });
    expect(screen.getByTestId("identity").textContent).toBe("account-b");
    expect(screen.getByTestId("private-panels").textContent).not.toContain("A private");
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
});
