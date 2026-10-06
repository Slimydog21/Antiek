import { act, cleanup, fireEvent, render, screen } from "@testing-library/react";
import { useEffect, useState, useSyncExternalStore } from "react";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";

import { AuthProvider, useAuth, type AuthContextValue } from "./auth";
import { sectionProse } from "../modes/Write/sectionProse";
import { setSectionProseOwner } from "../modes/Write/sectionProseOwner";

function response(status: number, body: unknown = {}): Response {
  return new Response(JSON.stringify(body), { status, headers: { "Content-Type": "application/json" } });
}
function identity(owner: string): Response {
  return response(200, { user_id: owner, email: null, auth_method: "magic_link" });
}
function deferredResponse() {
  let resolve!: (value: Response) => void;
  const promise = new Promise<Response>((done) => { resolve = done; });
  return { promise, resolve };
}

type Reply = () => Promise<Response>;
let authReply: Reply;
let healthReply: Reply;
let patchReply: Reply;
let logoutReply: Reply;
let controller: AuthContextValue | null = null;
let sentProse: string[];
const fetchMock = vi.fn<typeof fetch>();

function auth(): AuthContextValue {
  if (!controller) throw new Error("AuthProvider has not mounted");
  return controller;
}

// Only the view is small: these are the production auth and section mutation
// lifetimes. AuthProvider's outage screen really unmounts this subscription.
function Writer({ owner }: { owner: string }) {
  const [session] = useState(() => sectionProse("piece", "section", `${owner} saved`, {}));
  const state = useSyncExternalStore(session.subscribe, session.getSnapshot);
  return (
    <>
      <textarea aria-label="Draft" value={state.draft ?? ""} disabled={!state.available}
        onChange={(event) => session.edit(event.target.value, null)} />
      <output data-testid="save-state">{state.save.status}</output>
    </>
  );
}
function Consumer() {
  const current = useAuth();
  useEffect(() => { controller = current; }, [current]);
  return (
    <>
      <output data-testid="auth-state">{current.state.status}</output>
      {current.state.status === "authenticated" && <Writer key={current.state.identity.user_id} owner={current.state.identity.user_id} />}
    </>
  );
}
async function mount() {
  render(<AuthProvider><Consumer /></AuthProvider>);
  await screen.findByDisplayValue("owner-a saved");
  vi.useFakeTimers();
}
async function refresh(reply: Reply, options?: Parameters<AuthContextValue["refresh"]>[0]) {
  authReply = reply;
  await act(async () => { await auth().refresh(options); });
}
async function tick(ms = 0) {
  await act(async () => { await vi.advanceTimersByTimeAsync(ms); });
}
function edit(text: string) {
  fireEvent.change(screen.getByRole("textbox", { name: "Draft" }), { target: { value: text } });
}
function outage(kind: "unavailable" | "inferred"): Reply {
  return kind === "unavailable"
    ? async () => response(503)
    : async () => { throw new TypeError("Failed to fetch"); };
}

beforeEach(() => {
  window.localStorage.clear();
  setSectionProseOwner(null);
  controller = null;
  sentProse = [];
  authReply = async () => identity("owner-a");
  healthReply = async () => response(200);
  patchReply = async () => response(200, { status: "saved", section_id: "section", claim_node_id: null, claim_event_id: null });
  logoutReply = async () => new Response(null, { status: 204 });
  fetchMock.mockReset().mockImplementation(async (input, init) => {
    const path = new URL(String(input), "http://localhost").pathname;
    if (path === "/auth/me") return authReply();
    if (path === "/health") return healthReply();
    if (path === "/auth/logout") return logoutReply();
    if (path === "/sections/section/prose" && init?.method === "PATCH") {
      if (typeof init.body !== "string") throw new Error("Missing PATCH body");
      const body: unknown = JSON.parse(init.body);
      if (!body || typeof body !== "object" || !("prose_text" in body) || typeof body.prose_text !== "string") {
        throw new Error("Invalid prose PATCH");
      }
      sentProse.push(body.prose_text);
      return patchReply();
    }
    throw new Error(`Unexpected HTTP request: ${init?.method ?? "GET"} ${path}`);
  });
  vi.stubGlobal("fetch", fetchMock);
});
afterEach(() => {
  act(() => { setSectionProseOwner(null); });
  cleanup();
  vi.useRealTimers();
  vi.unstubAllGlobals();
});

describe("AuthProvider and the writing mutation lifetime", () => {
  it.each(["unavailable", "inferred"] as const)("%s auth retains an unmounted draft and resumes only after same-owner confirmation", async (kind) => {
    await mount();
    edit("owner-a pending draft");
    await refresh(outage(kind));
    expect(screen.queryByRole("textbox", { name: "Draft" })).toBeNull();
    await tick(1000);
    expect(sentProse).toEqual([]);
    await refresh(async () => identity("owner-a"));
    await tick();
    expect(screen.getByDisplayValue("owner-a pending draft")).toBeTruthy();
    expect(sentProse).toEqual(["owner-a pending draft"]);
    expect(screen.getByTestId("save-state").textContent).toBe("saved");
  });

  it.each(["unavailable", "inferred"] as const)("%s auth blocks a pending PATCH's follow-up without losing its draft", async (kind) => {
    await mount();
    const first = deferredResponse();
    patchReply = () => first.promise;
    edit("owner-a first");
    await tick(800);
    expect(sentProse).toEqual(["owner-a first"]);
    edit("owner-a latest");
    await refresh(outage(kind));
    await act(async () => { first.resolve(response(200)); });
    await tick(1000);
    expect(sentProse).toEqual(["owner-a first"]);
    patchReply = async () => response(200);
    await refresh(async () => identity("owner-a"));
    await tick();
    expect(screen.getByDisplayValue("owner-a latest")).toBeTruthy();
    expect(sentProse).toEqual(["owner-a first", "owner-a latest"]);
  });

  it("confirmed A→B revokes A's queued follow-up before the pending PATCH completes", async () => {
    await mount();
    const first = deferredResponse();
    patchReply = () => first.promise;
    edit("A sent");
    await tick(800);
    edit("A queued");
    await refresh(async () => identity("owner-b"));
    expect(screen.getByDisplayValue("owner-b saved")).toBeTruthy();
    await act(async () => { first.resolve(response(200)); });
    await tick(1000);
    expect(sentProse).toEqual(["A sent"]);
    expect(screen.getByDisplayValue("owner-b saved")).toBeTruthy();
  });

  it("signOut revokes queued prose before awaiting logout, including an older pending PATCH", async () => {
    await mount();
    const first = deferredResponse();
    const logout = deferredResponse();
    patchReply = () => first.promise;
    logoutReply = () => logout.promise;
    edit("A sent");
    await tick(800);
    edit("A queued");
    let signingOut = Promise.resolve();
    act(() => { signingOut = auth().signOut(); });
    expect(screen.queryByRole("textbox", { name: "Draft" })).toBeNull();
    expect(screen.getByTestId("auth-state").textContent).toBe("unauthenticated");
    await act(async () => { first.resolve(response(200)); });
    await tick(1000);
    expect(sentProse).toEqual(["A sent"]);
    await act(async () => { logout.resolve(new Response(null, { status: 204 })); await signingOut; });
    expect(screen.queryByRole("textbox", { name: "Draft" })).toBeNull();
  });

  it("an older A identity reply cannot restart a draft suspended by a newer unavailable answer", async () => {
    await mount();
    edit("Retain but do not send");
    const stale = deferredResponse();
    authReply = () => stale.promise;
    let staleRefresh = Promise.resolve();
    act(() => { staleRefresh = auth().refresh(); });
    await refresh(outage("unavailable"));
    await act(async () => { stale.resolve(identity("owner-a")); await staleRefresh; });
    await tick(1000);
    expect(screen.queryByRole("textbox", { name: "Draft" })).toBeNull();
    expect(sentProse).toEqual([]);
    await refresh(async () => identity("owner-a"));
    await tick();
    expect(sentProse).toEqual(["Retain but do not send"]);
  });

  it("a refresh started before logout cannot reactivate A after B is confirmed", async () => {
    await mount();
    edit("A never sent");
    const stale = deferredResponse();
    authReply = () => stale.promise;
    let staleRefresh = Promise.resolve();
    act(() => { staleRefresh = auth().refresh(); });
    await act(async () => { await auth().signOut(); });
    await refresh(async () => identity("owner-b"), { afterSignIn: true });
    await act(async () => { stale.resolve(identity("owner-a")); await staleRefresh; });
    expect(screen.getByDisplayValue("owner-b saved")).toBeTruthy();
    edit("B new draft");
    await tick(800);
    expect(sentProse).toEqual(["B new draft"]);
  });
});
