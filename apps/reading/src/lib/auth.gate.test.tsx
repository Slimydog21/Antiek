/**
 * FFX SPR-01 M3 (F-03) — the honest auth gate.
 *
 * Before: ANY /auth/me failure other than 401 — a 5xx while the backend
 * restarts, a dropped connection — was stored as `unauthenticated`
 * (lib/auth.tsx:88-93) and RequireAuth (App.tsx:110-112) bounced a signed-in
 * user to /login. The code's own comment already said a transport failure is
 * not an identity transition.
 *
 * Every transition below names the HTTP status or thrown type producing it.
 */
import { readFileSync } from "node:fs";
import { join } from "node:path";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import { act, cleanup, fireEvent, render, screen, waitFor } from "@testing-library/react";
import { MemoryRouter, useLocation } from "react-router-dom";

const { setReadingStateOwner, posthogIdentify, posthogReset } = vi.hoisted(() => ({
  setReadingStateOwner: vi.fn(),
  posthogIdentify: vi.fn(),
  posthogReset: vi.fn(),
}));

vi.mock("../hooks/useReadingState", async (orig) => ({
  ...(await orig<typeof import("../hooks/useReadingState")>()),
  setReadingStateOwner,
}));

vi.mock("./posthogClient", async (orig) => ({
  ...(await orig<typeof import("./posthogClient")>()),
  posthogEnabled: true,
  posthog: { identify: posthogIdentify, reset: posthogReset, capture: vi.fn() },
}));

import { AUTH_UNAVAILABLE_COPY, AuthProvider, useAuth } from "./auth";
import App from "../App";

type Reply = Response | Error | (() => Promise<Response>);

function json(status: number, body: unknown): Response {
  return new Response(JSON.stringify(body), {
    status,
    headers: { "content-type": "application/json" },
  });
}

const IDENTITY = { user_id: "reader-a", email: "a@example.com", auth_method: "passkey" };

/** Queue of /auth/me replies; the last one repeats. Everything else → 404. */
let authReplies: Reply[] = [];
let authMeCalls = 0;

function stubFetch(): void {
  vi.stubGlobal(
    "fetch",
    vi.fn(async (input: RequestInfo | URL) => {
      const url = String(input instanceof Request ? input.url : input);
      if (url.endsWith("/auth/me")) {
        authMeCalls += 1;
        const reply = authReplies.length > 1 ? authReplies.shift()! : authReplies[0];
        if (reply instanceof Error) throw reply;
        if (typeof reply === "function") return reply();
        return reply.clone();
      }
      if (url.endsWith("/auth/logout")) return new Response(null, { status: 204 });
      return json(404, { detail: "not in this test" });
    }),
  );
}

function AuthProbe() {
  const { state, signOut, refresh } = useAuth();
  return (
    <>
      <output data-testid="auth-status">{state.status}</output>
      <button onClick={() => void signOut()}>sign out</button>
      <button onClick={() => void refresh()}>refresh auth</button>
    </>
  );
}

function renderProvider() {
  return render(
    <AuthProvider>
      <p>protected app</p>
      <AuthProbe />
    </AuthProvider>,
  );
}

function LocationProbe() {
  const { pathname } = useLocation();
  return <output data-testid="location">{pathname}</output>;
}

function renderApp(at: string) {
  return render(
    <MemoryRouter initialEntries={[at]}>
      <LocationProbe />
      <App />
    </MemoryRouter>,
  );
}

beforeEach(() => {
  authReplies = [];
  authMeCalls = 0;
  setReadingStateOwner.mockClear();
  posthogIdentify.mockClear();
  posthogReset.mockClear();
  stubFetch();
});

afterEach(() => {
  cleanup();
  vi.unstubAllGlobals();
});

describe("/auth/me failure is not an identity transition (F-03)", () => {
  it("503 → the unavailable screen, children not rendered, reading-state owner untouched", async () => {
    authReplies = [json(503, { detail: "restarting" })];
    renderProvider();
    expect(await screen.findByText(AUTH_UNAVAILABLE_COPY)).toBeTruthy();
    expect(screen.queryByText("protected app")).toBeNull();
    expect(screen.getByRole("button", { name: "Retry" })).toBeTruthy();
    expect(setReadingStateOwner).not.toHaveBeenCalled();
  });

  it.each([500, 502, 504, 408, 429])("%i → unavailable (a transient server answer, not an identity)", async (status) => {
    authReplies = [json(status, {})];
    renderProvider();
    expect(await screen.findByText(AUTH_UNAVAILABLE_COPY)).toBeTruthy();
  });

  it("fetch TypeError (network down / CORS) → unavailable", async () => {
    authReplies = [new TypeError("Failed to fetch")];
    renderProvider();
    expect(await screen.findByText(AUTH_UNAVAILABLE_COPY)).toBeTruthy();
    expect(screen.getByText(/Check your connection/)).toBeTruthy();
  });

  it("200 with a body that is not JSON (SyntaxError) → unavailable", async () => {
    authReplies = [new Response("<!doctype html><html></html>", { status: 200, headers: { "content-type": "text/html" } })];
    renderProvider();
    expect(await screen.findByText(AUTH_UNAVAILABLE_COPY)).toBeTruthy();
  });

  it("200 JSON without a user_id → unavailable, never 'authenticated as undefined'", async () => {
    authReplies = [json(200, { email: "a@example.com" })];
    renderProvider();
    expect(await screen.findByText(AUTH_UNAVAILABLE_COPY)).toBeTruthy();
  });

  it("an outage does not reset the analytics identity (posthog.reset is for sign-out only)", async () => {
    authReplies = [json(503, {})];
    renderProvider();
    await screen.findByText(AUTH_UNAVAILABLE_COPY);
    expect(posthogReset).not.toHaveBeenCalled();
  });
});

describe("the identity answers still mean what they meant", () => {
  it("401 → unauthenticated, children render (RequireAuth owns the /login redirect)", async () => {
    authReplies = [json(401, { detail: "no session" })];
    renderProvider();
    await waitFor(() => expect(screen.getByTestId("auth-status").textContent).toBe("unauthenticated"));
    expect(screen.getByText("protected app")).toBeTruthy();
    expect(setReadingStateOwner).toHaveBeenCalledWith(null);
    expect(screen.queryByText(AUTH_UNAVAILABLE_COPY)).toBeNull();
  });

  it.each([403, 404])(
    "%i → unauthenticated as before (a definitive client-error answer, not a transient outage; keeps Storybook's 404 probe rendering)",
    async (status) => {
      authReplies = [json(status, {})];
      renderProvider();
      await waitFor(() => expect(screen.getByTestId("auth-status").textContent).toBe("unauthenticated"));
    },
  );

  it("200 identity → authenticated", async () => {
    authReplies = [json(200, IDENTITY)];
    renderProvider();
    await waitFor(() => expect(screen.getByTestId("auth-status").textContent).toBe("authenticated"));
    expect(setReadingStateOwner).toHaveBeenCalledWith("reader-a");
  });
});

describe("Retry", () => {
  it("503 then Retry after a 200 → authenticated, children back", async () => {
    authReplies = [json(503, {}), json(200, IDENTITY)];
    renderProvider();
    fireEvent.click(await screen.findByRole("button", { name: "Retry" }));
    await waitFor(() => expect(screen.getByTestId("auth-status").textContent).toBe("authenticated"));
    expect(screen.getByText("protected app")).toBeTruthy();
    expect(authMeCalls).toBe(2);
  });

  it("503 then Retry into another TypeError → still the unavailable screen", async () => {
    authReplies = [json(503, {}), new TypeError("Failed to fetch")];
    renderProvider();
    fireEvent.click(await screen.findByRole("button", { name: "Retry" }));
    await waitFor(() => expect(authMeCalls).toBe(2));
    expect(await screen.findByText(AUTH_UNAVAILABLE_COPY)).toBeTruthy();
    expect(screen.getByText(/Check your connection/)).toBeTruthy();
  });

  it("Retry has a visible keyboard focus ring (F-17 rule)", async () => {
    authReplies = [json(503, {})];
    renderProvider();
    const retry = await screen.findByRole("button", { name: "Retry" });
    expect(retry.className).toMatch(/focus-visible:ring-2/);
  });
});

describe("the epoch guard still wins races", () => {
  it("a stale 503 that lands after sign-out cannot flip the state to unavailable", async () => {
    let release: (r: Response) => void = () => {};
    const held = new Promise<Response>((resolve) => {
      release = resolve;
    });
    authReplies = [() => held, json(401, {})];
    renderProvider();
    fireEvent.click(screen.getByText("sign out"));
    await waitFor(() => expect(screen.getByTestId("auth-status").textContent).toBe("unauthenticated"));
    await act(async () => {
      release(json(503, {}));
      await held;
    });
    expect(screen.getByTestId("auth-status").textContent).toBe("unauthenticated");
    expect(screen.queryByText(AUTH_UNAVAILABLE_COPY)).toBeNull();
  });
});

describe("through the real App route tree (RequireAuth unchanged)", () => {
  it("503 on /settings: the unavailable screen, and the URL never becomes /login", async () => {
    authReplies = [json(503, {})];
    renderApp("/settings");
    expect(await screen.findByText(AUTH_UNAVAILABLE_COPY)).toBeTruthy();
    expect(screen.getByTestId("location").textContent).toBe("/settings");
  });

  it("network TypeError on /settings: same", async () => {
    authReplies = [new TypeError("Failed to fetch")];
    renderApp("/settings");
    expect(await screen.findByText(AUTH_UNAVAILABLE_COPY)).toBeTruthy();
    expect(screen.getByTestId("location").textContent).toBe("/settings");
  });

  it("401 on /settings still redirects to /login?next=", async () => {
    authReplies = [json(401, {})];
    renderApp("/settings");
    await waitFor(() => expect(screen.getByTestId("location").textContent).toBe("/login"));
  });
});

describe("the unavailable screen stays out of the lemon chunk", () => {
  it("lib/auth.tsx imports nothing from components/lemon", () => {
    const source = readFileSync(join(__dirname, "auth.tsx"), "utf8");
    expect(source).not.toMatch(/from\s+["'][^"']*components\/lemon/);
  });
});
