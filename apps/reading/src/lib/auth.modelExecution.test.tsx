import { StrictMode } from "react";
import { act, cleanup, render, waitFor } from "@testing-library/react";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
vi.mock("./posthogClient", () => ({
  posthogEnabled: false,
  posthog: { identify: vi.fn(), reset: vi.fn() },
}));
vi.mock("../hooks/useReadingState", () => ({ setReadingStateOwner: vi.fn() }));
vi.mock("../modes/Write/sectionProseOwner", () => ({
  setSectionProseOwner: vi.fn(),
  suspendSectionProseDispatch: vi.fn(),
}));
import { AuthProvider, useAuth, type AuthContextValue } from "./auth";
const A = { user_id: "a", email: null, auth_method: "antiek_session_cookie" };
function deferred<T>() {
  let resolve!: (value: T) => void;
  let reject!: (error: Error) => void;
  const promise = new Promise<T>((yes, no) => {
    resolve = yes;
    reject = no;
  });
  return { promise, resolve, reject };
}
let auth: AuthContextValue;
function Probe() {
  auth = useAuth();
  return <span>{auth.state.status}</span>;
}
const json = (body: unknown) =>
  new Response(JSON.stringify(body), { status: 200 });
afterEach(() => {
  cleanup();
  vi.unstubAllGlobals();
});
beforeEach(() => {
  vi.stubGlobal(
    "fetch",
    vi.fn(async (input: RequestInfo | URL) => {
      if (new URL(String(input), "http://fixture").pathname !== "/auth/me")
        throw new Error("fixture denies route");
      return json(A);
    }),
  );
});
async function mount() {
  render(
    <AuthProvider>
      <Probe />
    </AuthProvider>,
  );
  await waitFor(() => expect(auth.state.status).toBe("authenticated"));
}
describe("immediate model execution lifecycle", () => {
  it("suspends before refresh schedules its identity read", async () => {
    await mount();
    const previous = auth.modelExecution.readCurrent();
    const next = deferred<Response>();
    let seen: unknown;
    vi.stubGlobal(
      "fetch",
      vi.fn(() => {
        seen = auth.modelExecution.readCurrent();
        return next.promise;
      }),
    );
    let read!: Promise<void>;
    act(() => {
      read = auth.refresh();
    });
    expect(seen).toMatchObject({
      kind: "suspended",
      reason: "checking_identity",
    });
    if (previous.kind === "ready")
      expect(auth.modelExecution.isCurrent(previous)).toBe(false);
    await act(async () => {
      next.resolve(json(A));
      await read;
    });
    expect(auth.modelExecution.readCurrent().kind).toBe("ready");
  });
  it("shares logout promise and blocks every refresh while pending", async () => {
    await mount();
    const done = deferred<Response>();
    const fetch = vi.fn((input: RequestInfo | URL) => {
      expect(new URL(String(input), "http://fixture").pathname).toBe(
        "/auth/logout",
      );
      expect(auth.modelExecution.readCurrent()).toMatchObject({
        kind: "suspended",
        reason: "logout_pending",
      });
      return done.promise;
    });
    vi.stubGlobal("fetch", fetch);
    let first!: Promise<void>;
    let second!: Promise<void>;
    act(() => {
      first = auth.signOut();
      second = auth.signOut();
    });
    expect(second).toBe(first);
    const token = auth.modelExecution.readCurrent();
    await act(async () => {
      await auth.refresh();
    });
    expect(fetch).toHaveBeenCalledTimes(1);
    expect(auth.modelExecution.readCurrent()).toBe(token);
    await act(async () => {
      done.resolve(new Response(null, { status: 204 }));
      await first;
    });
    expect(auth.modelExecution.readCurrent()).toMatchObject({
      kind: "suspended",
      reason: "no_identity",
    });
  });
  it("retains display identity but suspends after failed logout until explicit recovery", async () => {
    await mount();
    vi.stubGlobal(
      "fetch",
      vi.fn(() => Promise.reject(new Error("fixture failed"))),
    );
    await act(async () => {
      await expect(auth.signOut()).rejects.toThrow("fixture failed");
    });
    expect(auth.state.status).toBe("authenticated");
    expect(auth.modelExecution.readCurrent()).toMatchObject({
      kind: "suspended",
      reason: "logout_failed",
    });
    vi.stubGlobal(
      "fetch",
      vi.fn(async () => json(A)),
    );
    await act(async () => {
      await auth.refresh();
    });
    expect(auth.modelExecution.readCurrent().kind).toBe("ready");
  });
  it("retires tokens on unmount and ignores late reads", async () => {
    await mount();
    const lifecycle = auth.modelExecution;
    const next = deferred<Response>();
    vi.stubGlobal(
      "fetch",
      vi.fn(() => next.promise),
    );
    let read!: Promise<void>;
    act(() => {
      read = auth.refresh();
    });
    cleanup();
    expect(lifecycle.readCurrent()).toMatchObject({
      kind: "suspended",
      reason: "unmounted",
    });
    await act(async () => {
      next.resolve(json(A));
      await read;
    });
    expect(lifecycle.readCurrent()).toMatchObject({
      kind: "suspended",
      reason: "unmounted",
    });
  });

  it("ignores an older identity response throughout pending logout", async () => {
    await mount();
    const older = deferred<Response>();
    const logout = deferred<Response>();
    vi.stubGlobal(
      "fetch",
      vi.fn((input: RequestInfo | URL) => {
        const path = new URL(String(input), "http://fixture").pathname;
        if (path === "/auth/me") return older.promise;
        if (path === "/auth/logout") return logout.promise;
        throw new Error("fixture route denied");
      }),
    );
    let read!: Promise<void>;
    let out!: Promise<void>;
    act(() => {
      read = auth.refresh();
      out = auth.signOut();
    });
    await act(async () => {
      older.resolve(json({ ...A, user_id: "b" }));
      await read;
    });
    expect(auth.modelExecution.readCurrent()).toMatchObject({
      kind: "suspended",
      reason: "logout_pending",
    });
    expect(auth.state).toMatchObject({ status: "authenticated", identity: A });
    await act(async () => {
      logout.resolve(new Response(null, { status: 204 }));
      await out;
    });
    expect(auth.state.status).toBe("unauthenticated");
  });
  it("publishes only the remounted StrictMode identity read", async () => {
    const first = deferred<Response>();
    const second = deferred<Response>();
    let reads = 0;
    vi.stubGlobal(
      "fetch",
      vi.fn((input: RequestInfo | URL) => {
        expect(new URL(String(input), "http://fixture").pathname).toBe(
          "/auth/me",
        );
        return ++reads === 1 ? first.promise : second.promise;
      }),
    );
    render(
      <StrictMode>
        <AuthProvider>
          <Probe />
        </AuthProvider>
      </StrictMode>,
    );
    expect(reads).toBe(2);
    await act(async () => {
      second.resolve(json(A));
      await second.promise;
    });
    const token = auth.modelExecution.readCurrent();
    expect(token.kind).toBe("ready");
    await act(async () => {
      first.resolve(json({ ...A, user_id: "b" }));
      await first.promise;
    });
    expect(auth.modelExecution.readCurrent()).toBe(token);
    expect(auth.state).toMatchObject({ status: "authenticated", identity: A });
  });
  it("keeps permissive display auth separate from model identity admission", async () => {
    vi.stubGlobal(
      "fetch",
      vi.fn(async () => json({ ...A, auth_method: "unauthenticated_local" })),
    );
    await mount();
    expect(auth.modelExecution.readCurrent()).toMatchObject({
      kind: "suspended",
      reason: "invalid_model_identity",
    });
  });

  it("keeps display identity while logout blocks a newer refresh", async () => {
    await mount();
    const logout = deferred<Response>();
    const fetch = vi.fn((input: RequestInfo | URL) => {
      const path = new URL(String(input), "http://fixture").pathname;
      if (path === "/auth/logout") return logout.promise;
      if (path === "/auth/me")
        return Promise.resolve(json({ ...A, user_id: "b" }));
      throw new Error("fixture route denied");
    });
    vi.stubGlobal("fetch", fetch);
    let pending!: Promise<void>;
    act(() => {
      pending = auth.signOut();
    });
    try {
      await act(async () => {
        await auth.refresh();
      });
      expect(auth.state).toMatchObject({
        status: "authenticated",
        identity: A,
      });
      expect(fetch).toHaveBeenCalledTimes(1);
    } finally {
      await act(async () => {
        logout.resolve(new Response(null, { status: 204 }));
        await pending;
      });
    }
  });

  it.each([401, 500])(
    "refuses HTTP %s logout without confirming signed-out state",
    async (status) => {
      await mount();
      vi.stubGlobal(
        "fetch",
        vi.fn(async (input: RequestInfo | URL) => {
          expect(new URL(String(input), "http://fixture").pathname).toBe(
            "/auth/logout",
          );
          return new Response("untrusted response must not appear in errors", {
            status,
          });
        }),
      );
      await act(async () => {
        await expect(auth.signOut()).rejects.toThrow(
          "Antiek couldn't sign you out.",
        );
      });
      expect(auth.state).toMatchObject({
        status: "authenticated",
        identity: A,
      });
      expect(auth.modelExecution.readCurrent()).toMatchObject({
        kind: "suspended",
        reason: "logout_failed",
      });
    },
  );
  it.each([200, 202])(
    "refuses unexpected logout HTTP %s while sharing the pending promise and allowing explicit recovery",
    async (status) => {
      await mount();
      const response = deferred<Response>();
      const fetch = vi.fn((input: RequestInfo | URL) => {
        expect(new URL(String(input), "http://fixture").pathname).toBe(
          "/auth/logout",
        );
        return response.promise;
      });
      vi.stubGlobal("fetch", fetch);
      let first!: Promise<void>;
      let second!: Promise<void>;
      act(() => {
        first = auth.signOut();
        second = auth.signOut();
      });
      expect(second).toBe(first);
      const rejection = expect(first).rejects.toThrow(
        "Antiek couldn't sign you out.",
      );
      await act(async () => {
        await auth.refresh();
      });
      expect(fetch).toHaveBeenCalledTimes(1);
      expect(auth.modelExecution.readCurrent()).toMatchObject({
        kind: "suspended",
        reason: "logout_pending",
      });
      await act(async () => {
        response.resolve(
          new Response(
            status === 200 ? "<!doctype html><title>proxy</title>" : null,
            { status },
          ),
        );
        await rejection;
      });
      expect(auth.state).toMatchObject({
        status: "authenticated",
        identity: A,
      });
      expect(auth.modelExecution.readCurrent()).toMatchObject({
        kind: "suspended",
        reason: "logout_failed",
      });
      vi.stubGlobal(
        "fetch",
        vi.fn(async (input: RequestInfo | URL) => {
          expect(new URL(String(input), "http://fixture").pathname).toBe(
            "/auth/me",
          );
          return json(A);
        }),
      );
      await act(async () => {
        await auth.refresh();
      });
      expect(auth.modelExecution.readCurrent().kind).toBe("ready");
    },
  );
});
