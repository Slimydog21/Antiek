import { act, cleanup, fireEvent, isInaccessible, render, screen } from "@testing-library/react";
import { StrictMode, useEffect } from "react";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import { AuthProvider, IDENTITY_REQUEST_TIMEOUT_MS, useAuth, type AuthContextValue } from "./auth";
import { isWorkspaceOwnerSession, setWorkspaceOwner, workspaceOwnerSession } from "./accountWorkspaceOwner";

const A = "acct_aaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaa";
const B = "acct_bbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbb";

function deferred<T>() {
  let finish: ((value: T) => void) | undefined;
  const promise = new Promise<T>((resolve) => { finish = resolve; });
  return {
    promise,
    resolve(value: T) {
      if (!finish) throw new Error("Deferred transport has no resolver");
      finish(value);
    },
  };
}

function identity(subject: string): Response {
  return Response.json({ user_id: subject, email: null, auth_method: "magic_link" });
}

interface RequestObservation {
  path: string;
  signal: AbortSignal | null | undefined;
  credentials: RequestCredentials | undefined;
}

let observations: RequestObservation[];
let identityReply: () => Promise<Response>;
let healthReply: () => Promise<Response>;
let current: AuthContextValue | undefined;

function auth(): AuthContextValue {
  if (!current) throw new Error("Auth consumer has not mounted");
  return current;
}

function Consumer() {
  const value = useAuth();
  useEffect(() => { current = value; }, [value]);
  return <>
    <output data-testid="identity">{value.state.status === "authenticated" ? value.state.identity.user_id : value.state.status}</output>
    <input aria-label="Mounted draft" defaultValue="" />
  </>;
}

async function mount(strict = false) {
  const children = <AuthProvider><Consumer /></AuthProvider>;
  const mounted = render(strict ? <StrictMode>{children}</StrictMode> : children);
  await act(async () => { await Promise.resolve(); });
  return mounted;
}

async function advance(milliseconds: number) {
  await act(async () => { await vi.advanceTimersByTimeAsync(milliseconds); });
}

function request(path: string, index = 0): RequestObservation {
  const result = observations.filter((entry) => entry.path === path)[index];
  if (!result) throw new Error(`Expected ${path} request ${index}`);
  return result;
}

beforeEach(() => {
  vi.useFakeTimers();
  window.localStorage.clear();
  setWorkspaceOwner(null);
  current = undefined;
  observations = [];
  identityReply = async () => identity(A);
  healthReply = async () => Response.json({ status: "ok" });
  vi.stubGlobal("fetch", vi.fn<typeof fetch>(async (input, init) => {
    const path = new URL(input instanceof Request ? input.url : String(input), "http://localhost").pathname;
    observations.push({ path, signal: init?.signal, credentials: init?.credentials });
    if (path === "/auth/me") return identityReply();
    if (path === "/health") return healthReply();
    if (path === "/auth/logout") return new Response(null, { status: 204 });
    throw new Error(`Unexpected identity-control request: ${path}`);
  }));
});

afterEach(() => {
  cleanup();
  setWorkspaceOwner(null);
  vi.restoreAllMocks();
  vi.unstubAllGlobals();
  vi.useRealTimers();
});

describe("bounded identity requests preserve verified account custody", () => {
  it("a transport that ignores abort reaches honest retry at the deadline, never inferred logout", async () => {
    const transport = deferred<Response>();
    identityReply = () => transport.promise;
    await mount();
    expect(screen.getByTestId("identity").textContent).toBe("loading");
    expect(request("/auth/me").credentials).toBe("include");
    await advance(IDENTITY_REQUEST_TIMEOUT_MS - 1);
    expect(screen.queryByRole("alert")).toBeNull();
    expect(request("/auth/me").signal?.aborted).toBe(false);
    await advance(1);
    expect(screen.getByRole("alert").getAttribute("data-auth-unavailable")).toBe("server");
    expect(screen.getByRole("button", { name: "Retry" })).toHaveProperty("disabled", false);
    expect(screen.queryByTestId("identity")).toBeNull();
    expect(request("/auth/me").signal?.aborted).toBe(true);
    expect(observations.some((entry) => entry.path === "/health")).toBe(false);
    expect(workspaceOwnerSession().subject).toBeNull();
    await act(async () => { transport.resolve(identity(A)); });
    expect(screen.getByRole("alert")).toBeTruthy();
    expect(workspaceOwnerSession().subject).toBeNull();
  });

  it("the same deadline covers a 200 body reader that never settles", async () => {
    const body = deferred<unknown>();
    const headers = identity(A);
    vi.spyOn(headers, "json").mockImplementation(() => body.promise);
    identityReply = async () => headers;
    await mount();
    await advance(IDENTITY_REQUEST_TIMEOUT_MS);
    expect(screen.getByRole("alert").getAttribute("data-auth-unavailable")).toBe("server");
    expect(request("/auth/me").signal?.aborted).toBe(true);
    await act(async () => { body.resolve({ user_id: A, email: null, auth_method: "magic_link" }); });
    expect(workspaceOwnerSession().subject).toBeNull();
    expect(screen.queryByTestId("identity")).toBeNull();
  });

  it("a late unreadable reply cannot renew the deadline for its reachability probe", async () => {
    const headers = deferred<Response>();
    const probe = deferred<Response>();
    identityReply = () => headers.promise;
    healthReply = () => probe.promise;
    await mount();
    await advance(IDENTITY_REQUEST_TIMEOUT_MS - 1_000);
    await act(async () => { headers.resolve(Response.json({ missing: "identity" })); });
    expect(request("/health").signal?.aborted).toBe(false);
    await advance(1_000);
    expect(request("/health").signal?.aborted).toBe(true);
    expect(screen.getByRole("alert").getAttribute("data-auth-unavailable")).toBe("server");
    await act(async () => { probe.resolve(Response.json({ status: "ok" })); });
    expect(workspaceOwnerSession().subject).toBeNull();
    expect(screen.getByRole("alert")).toBeTruthy();
  });

  it("retry verifies B and a late timed-out A response cannot replace it", async () => {
    const old = deferred<Response>();
    identityReply = () => old.promise;
    await mount();
    await advance(IDENTITY_REQUEST_TIMEOUT_MS);
    identityReply = async () => identity(B);
    await act(async () => { fireEvent.click(screen.getByRole("button", { name: "Retry" })); });
    expect(screen.getByTestId("identity").textContent).toBe(B);
    const owner = workspaceOwnerSession();
    expect(owner.subject).toBe(B);
    await act(async () => { old.resolve(identity(A)); });
    expect(screen.getByTestId("identity").textContent).toBe(B);
    expect(workspaceOwnerSession()).toBe(owner);
    await advance(IDENTITY_REQUEST_TIMEOUT_MS);
    expect(screen.queryByRole("alert")).toBeNull();
  });

  it("each unresolved retry is bounded and restores the retry control", async () => {
    identityReply = () => new Promise<Response>(() => {});
    await mount();
    await advance(IDENTITY_REQUEST_TIMEOUT_MS);
    fireEvent.click(screen.getByRole("button", { name: "Retry" }));
    expect(screen.getByRole("button", { name: "Retry" })).toHaveProperty("disabled", true);
    await advance(IDENTITY_REQUEST_TIMEOUT_MS);
    expect(screen.getByRole("button", { name: "Retry" })).toHaveProperty("disabled", false);
    expect(request("/auth/me", 1).signal?.aborted).toBe(true);
    expect(observations.filter((entry) => entry.path === "/auth/me")).toHaveLength(2);
    expect(workspaceOwnerSession().subject).toBeNull();
  });

  it("same-A confirmation before the deadline retains the mounted draft and exact owner token", async () => {
    await mount();
    const owner = workspaceOwnerSession();
    const input = screen.getByRole("textbox", { name: "Mounted draft" });
    fireEvent.change(input, { target: { value: "A unsaved text" } });
    const pending = deferred<Response>();
    identityReply = () => pending.promise;
    let refresh = Promise.resolve();
    act(() => { refresh = auth().refresh(); });
    expect(isInaccessible(input)).toBe(true);
    expect(isWorkspaceOwnerSession(owner)).toBe(false);
    await advance(IDENTITY_REQUEST_TIMEOUT_MS - 1);
    await act(async () => { pending.resolve(identity(A)); await refresh; });
    expect(workspaceOwnerSession()).toBe(owner);
    expect(isWorkspaceOwnerSession(owner)).toBe(true);
    expect(screen.getByRole("textbox", { name: "Mounted draft" })).toBe(input);
    expect(input).toHaveProperty("value", "A unsaved text");
    await advance(1);
    expect(screen.queryByRole("alert")).toBeNull();
  });

  it("an A timeout suspends rather than retires its token, and verified same-A retry resumes it", async () => {
    await mount();
    const owner = workspaceOwnerSession();
    identityReply = () => new Promise<Response>(() => {});
    let refresh = Promise.resolve();
    act(() => { refresh = auth().refresh(); });
    await advance(IDENTITY_REQUEST_TIMEOUT_MS);
    await refresh;
    expect(screen.getByRole("alert")).toBeTruthy();
    expect(workspaceOwnerSession()).toBe(owner);
    expect(isWorkspaceOwnerSession(owner)).toBe(false);
    identityReply = async () => identity(A);
    await act(async () => { fireEvent.click(screen.getByRole("button", { name: "Retry" })); });
    expect(workspaceOwnerSession()).toBe(owner);
    expect(isWorkspaceOwnerSession(owner)).toBe(true);
    expect(screen.getByTestId("identity").textContent).toBe(A);
  });

  it("a superseding B refresh aborts and settles unfinished A without admitting its late response", async () => {
    await mount();
    const old = deferred<Response>();
    identityReply = () => old.promise;
    let first = Promise.resolve();
    act(() => { first = auth().refresh(); });
    identityReply = async () => identity(B);
    await act(async () => { await auth().refresh(); await first; });
    expect(request("/auth/me", 1).signal?.aborted).toBe(true);
    expect(screen.getByTestId("identity").textContent).toBe(B);
    await act(async () => { old.resolve(identity(A)); });
    expect(workspaceOwnerSession().subject).toBe(B);
    expect(screen.getByTestId("identity").textContent).toBe(B);
  });

  it("logout aborts pending A and an abort-ignoring transport cannot restore its body owner", async () => {
    await mount();
    const old = deferred<Response>();
    identityReply = () => old.promise;
    let refresh = Promise.resolve();
    act(() => { refresh = auth().refresh(); });
    await act(async () => { await auth().signOut(); await refresh; });
    expect(request("/auth/me", 1).signal?.aborted).toBe(true);
    expect(screen.getByTestId("identity").textContent).toBe("unauthenticated");
    await act(async () => { old.resolve(identity(A)); });
    await advance(IDENTITY_REQUEST_TIMEOUT_MS);
    expect(workspaceOwnerSession().subject).toBeNull();
    expect(screen.getByTestId("identity").textContent).toBe("unauthenticated");
    expect(screen.queryByRole("alert")).toBeNull();
  });

  it("unmount aborts identity and a retained refresh callback cannot dispatch another request", async () => {
    const old = deferred<Response>();
    identityReply = () => old.promise;
    const mounted = await mount();
    const retainedRefresh = auth().refresh;
    mounted.unmount();
    expect(request("/auth/me").signal?.aborted).toBe(true);
    await act(async () => { await retainedRefresh(); old.resolve(identity(A)); });
    await advance(IDENTITY_REQUEST_TIMEOUT_MS);
    expect(observations).toHaveLength(1);
    expect(workspaceOwnerSession().subject).toBeNull();
  });

  it("superseding identity cancels its old health probe and refuses late inferred anonymity", async () => {
    await mount();
    const probe = deferred<Response>();
    healthReply = () => probe.promise;
    identityReply = async () => { throw new TypeError("controlled unreadable identity"); };
    let first = Promise.resolve();
    await act(async () => { first = auth().refresh(); await Promise.resolve(); });
    expect(request("/health").signal?.aborted).toBe(false);
    identityReply = async () => identity(B);
    await act(async () => { await auth().refresh(); await first; });
    expect(request("/health").signal?.aborted).toBe(true);
    await act(async () => { probe.resolve(Response.json({ status: "ok" })); });
    expect(screen.getByTestId("identity").textContent).toBe(B);
    expect(workspaceOwnerSession().subject).toBe(B);
  });

  it("an actual 401 after a timeout still retires A, rather than treating timeout as proof", async () => {
    await mount();
    const owner = workspaceOwnerSession();
    identityReply = () => new Promise<Response>(() => {});
    let refresh = Promise.resolve();
    act(() => { refresh = auth().refresh(); });
    await advance(IDENTITY_REQUEST_TIMEOUT_MS);
    await refresh;
    expect(workspaceOwnerSession()).toBe(owner);
    identityReply = async () => new Response(null, { status: 401 });
    await act(async () => { fireEvent.click(screen.getByRole("button", { name: "Retry" })); });
    expect(workspaceOwnerSession().subject).toBeNull();
    expect(isWorkspaceOwnerSession(owner)).toBe(false);
    expect(screen.getByTestId("identity").textContent).toBe("unauthenticated");
  });

  it("StrictMode cancels the retired initial request and only the active setup admits its subject", async () => {
    await mount(true);
    expect(observations.filter((entry) => entry.path === "/auth/me")).toHaveLength(2);
    expect(request("/auth/me").signal?.aborted).toBe(true);
    expect(screen.getByTestId("identity").textContent).toBe(A);
    expect(workspaceOwnerSession().subject).toBe(A);
    await advance(IDENTITY_REQUEST_TIMEOUT_MS);
    expect(screen.queryByRole("alert")).toBeNull();
  });
});
