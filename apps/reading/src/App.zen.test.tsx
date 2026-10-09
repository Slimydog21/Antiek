/**
 * App.zen.test.tsx — FFX-KPA SPR-03 M7: /zen renders ZenHome only behind
 * the "nav.zenhome" feature flag (localStorage antiek.flag.nav.zenhome). With
 * the flag off the path is not a route, so the existing "*" handler sends it
 * to "/" like any unknown path. The whole App is rendered (auth gate included)
 * against a stubbed fetch, as auth.gate.test.tsx does.
 */
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import { cleanup, render, screen, waitFor } from "@testing-library/react";
import { MemoryRouter, useLocation } from "react-router-dom";

import App from "./App";
import { setFeatureFlag } from "./lib/featureFlags";

const IDENTITY = { user_id: "reader-a", email: "a@example.com", auth_method: "passkey" };

function json(status: number, body: unknown): Response {
  return new Response(JSON.stringify(body), { status, headers: { "content-type": "application/json" } });
}

function LocationProbe() {
  const { pathname } = useLocation();
  return <output data-testid="location">{pathname}</output>;
}

/** The real route tree is lazy; under fleet load the first chunk import has
 *  taken over a second (auth.gate.test.tsx:120-126). */
const APP_TREE_WAIT = { timeout: 15_000 };

beforeEach(() => {
  window.localStorage.clear();
  Object.defineProperty(window, "matchMedia", {
    writable: true,
    configurable: true,
    value: (query: string) => ({
      matches: false, media: query, onchange: null,
      addEventListener: () => {}, removeEventListener: () => {},
      addListener: () => {}, removeListener: () => {}, dispatchEvent: () => false,
    }),
  });
  vi.stubGlobal(
    "fetch",
    vi.fn(async (input: RequestInfo | URL) => {
      const url = String(input instanceof Request ? input.url : input);
      if (url.endsWith("/auth/me")) return json(200, IDENTITY);
      return json(404, { detail: "not in this test" });
    }),
  );
});

afterEach(() => {
  cleanup();
  vi.unstubAllGlobals();
  window.localStorage.clear();
});

function renderAt(at: string) {
  return render(
    <MemoryRouter initialEntries={[at]}>
      <LocationProbe />
      <App />
    </MemoryRouter>,
  );
}

describe("/zen route (SPR-03 M7)", () => {
  it("flag on: /zen renders the zen home", async () => {
    setFeatureFlag("nav.zenhome", true);
    renderAt("/zen");
    expect(
      await screen.findByRole("textbox", { name: "What are you working on?" }, APP_TREE_WAIT),
    ).toBeTruthy();
    expect(screen.getByTestId("location").textContent).toBe("/zen");
  });

  it("flag off: /zen falls to the existing * handler (→ /)", async () => {
    renderAt("/zen");
    await waitFor(() => expect(screen.getByTestId("location").textContent).toBe("/"), APP_TREE_WAIT);
    expect(screen.queryByRole("textbox", { name: "What are you working on?" })).toBeNull();
  });
});
