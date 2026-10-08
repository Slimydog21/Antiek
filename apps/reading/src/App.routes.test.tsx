/**
 * App.routes.test.tsx — SPR-05 M6 (first half): every taxonomy route resolves
 * for an authenticated session. "Resolves" = the router stays on the route
 * (no catch-all redirect to "/", no bounce to /login). Exhaustive by count
 * over MODE_TAXONOMY so a route added to the taxonomy without an App <Route>
 * fails here, not in production. Param routes get a placeholder id.
 */
import { afterEach, beforeAll, beforeEach, describe, expect, it, vi } from "vitest";
import { cleanup, waitFor } from "@testing-library/react";

beforeAll(() => {
  if (!window.matchMedia) {
    Object.defineProperty(window, "matchMedia", {
      writable: true,
      configurable: true,
      value: (query: string) => ({
        matches: false,
        media: query,
        onchange: null,
        addEventListener: () => {},
        removeEventListener: () => {},
        addListener: () => {},
        removeListener: () => {},
        dispatchEvent: () => false,
      }),
    });
  }
});

vi.mock("./lib/api", async (orig) => ({
  ...(await orig<typeof import("./lib/api")>()),
  apiFetch: vi.fn(() => Promise.resolve({ ok: false, status: 404, json: async () => ({}) })),
}));
vi.mock("./lib/auth", async (orig) => {
  const actual = await orig<typeof import("./lib/auth")>();
  return {
    ...actual,
    useAuth: () => ({
      state: { status: "authenticated", identity: { user_id: "u-routes", email: "routes@example.test", auth_method: "test" } },
      refresh: async () => {},
      logout: async () => {},
    }),
  };
});
vi.mock("./scene/Scene", () => ({ Scene: () => null }));
vi.mock("./components/ad/AdBorderMount", () => ({ AdBorderMount: () => null }));

import { locationSpy, mountApp } from "./journeys/harness";
import { MODE_TAXONOMY } from "./shell/workflowTaxonomy";

const ROUTE_ENTRIES = MODE_TAXONOMY.filter((m) => m.route).map((m) => m.route!);
const ROUTES = [...new Set(ROUTE_ENTRIES)];
// Routes that are for UNAUTHENTICATED visitors only and bounce (or re-route)
// an authenticated session on purpose. /trust and /speak/browse are public
// too, but they stay on their path for a signed-in user, so they ARE tested.
const UNAUTHENTICATED_ONLY = new Set(["/login", "/speak/invite/:token"]);
// The count the taxonomy carries today. Asserted as a literal so that adding
// or removing a route changes this test on purpose, never silently (critique
// F1: the previous version compared a Set to its own size — always true).
const EXPECTED_UNIQUE_ROUTES = 44;
const concrete = (r: string) => r.replace(/:[a-zA-Z]+/g, "test-id");

beforeEach(() => {
  window.localStorage.clear();
  Object.defineProperty(window, "innerWidth", { configurable: true, writable: true, value: 1280 });
});
afterEach(cleanup);

describe("every MODE_TAXONOMY route resolves for an authenticated session", () => {
  it("the table is exhaustive over the taxonomy (literal count; duplicates collapsed, nothing dropped)", () => {
    expect(ROUTES.length).toBe(EXPECTED_UNIQUE_ROUTES);
    // Every routed taxonomy entry is represented: no entry's route is outside
    // the table, and the table has no route the taxonomy lacks.
    for (const route of ROUTE_ENTRIES) expect(ROUTES).toContain(route);
    for (const route of ROUTES) expect(ROUTE_ENTRIES).toContain(route);
    for (const route of UNAUTHENTICATED_ONLY) expect(ROUTES).toContain(route);
  });

  it.each(ROUTES.filter((r) => !UNAUTHENTICATED_ONLY.has(r)))("%s stays on its route (no catch-all, no /login)", async (route) => {
    const path = concrete(route);
    mountApp(path);
    await waitFor(() => expect(locationSpy.pathname).not.toBe(""));
    // Give the catch-all a tick to redirect if it were going to.
    await new Promise((r) => setTimeout(r, 20));
    expect(locationSpy.pathname).toBe(path);
    expect(locationSpy.pathname.startsWith("/login")).toBe(false);
  });
});
