/**
 * SceneStatusBadge.test.tsx — antiek-living-caliber SPR-04, milestone 5.
 *
 * The operator-only fallback badge contract (the WHOLE privacy + signal rule):
 *
 *   operator + fallback     ⇒ badge PRESENT, naming the reason
 *   operator + live         ⇒ badge ABSENT (no badge when art is live)
 *   NON-operator + fallback ⇒ badge ABSENT FROM THE DOM (not CSS-hidden — a
 *                             logged-out reader must never see internal
 *                             degradation reasons)
 *
 * "Operator" = an authenticated auth state (single-operator product; auth IS
 * the operator signal). We drive auth via the real AuthCtx provider.
 *
 * NO NETWORK (asserted): the badge consumes only the props threaded from the
 * hook (isFallback + reason). It never fetches — we stub global fetch and
 * assert it is never called while the badge renders.
 */
import { afterEach, describe, expect, it, vi } from "vitest";
import { cleanup, render } from "@testing-library/react";
import type { ReactNode } from "react";

import { SceneStatusBadge } from "./SceneStatusBadge";
import { KreaArtLayer } from "./layers/KreaArtLayer";
import { AuthCtx, type AuthContextValue, type AuthState } from "../lib/auth";
import type { SceneArt } from "./useSceneArt";

afterEach(() => cleanup());

/** Wrap children in an AuthCtx provider at a given auth state. */
function withAuth(state: AuthState): (children: ReactNode) => ReactNode {
  const value: AuthContextValue = {
    state,
    refresh: async () => {},
    signOut: async () => {},
  };
  return (children) => (
    <AuthCtx.Provider value={value}>{children}</AuthCtx.Provider>
  );
}

const OPERATOR: AuthState = {
  status: "authenticated",
  identity: { user_id: "op-1", email: "op@antiek.ai", auth_method: "bearer_token" },
};
const READER_LOGGED_OUT: AuthState = { status: "unauthenticated" };
const LOADING: AuthState = { status: "loading" };

describe("SceneStatusBadge — the operator-only fallback rule", () => {
  it("operator + fallback ⇒ badge present, naming the reason", () => {
    const wrap = withAuth(OPERATOR);
    const { queryByTestId } = render(
      wrap(<SceneStatusBadge isFallback reason="no_api_balance" />) as JSX.Element,
    );
    const badge = queryByTestId("scene-status-badge");
    expect(badge).not.toBeNull();
    expect(badge!.textContent).toBe("scene: procedural · no_api_balance");
    expect(badge!.getAttribute("data-reason")).toBe("no_api_balance");
  });

  it("operator + live (isFallback=false) ⇒ badge ABSENT", () => {
    const wrap = withAuth(OPERATOR);
    const { queryByTestId } = render(
      wrap(<SceneStatusBadge isFallback={false} reason={null} />) as JSX.Element,
    );
    expect(queryByTestId("scene-status-badge")).toBeNull();
  });

  it("NON-operator (logged out) + fallback ⇒ badge ABSENT FROM THE DOM (not hidden)", () => {
    const wrap = withAuth(READER_LOGGED_OUT);
    const { queryByTestId, container } = render(
      wrap(<SceneStatusBadge isFallback reason="no_api_balance" />) as JSX.Element,
    );
    // ABSENT, not hidden: querying returns null AND the container has no
    // badge node at all (we did not render a display:none element).
    expect(queryByTestId("scene-status-badge")).toBeNull();
    expect(container.querySelector('[data-testid="scene-status-badge"]')).toBeNull();
    // And the reason string never reaches the DOM for a logged-out reader.
    expect(container.textContent).not.toContain("no_api_balance");
  });

  it("auth still loading + fallback ⇒ badge ABSENT (not yet an operator)", () => {
    const wrap = withAuth(LOADING);
    const { queryByTestId } = render(
      wrap(<SceneStatusBadge isFallback reason="no_key" />) as JSX.Element,
    );
    expect(queryByTestId("scene-status-badge")).toBeNull();
  });

  it("NO AuthProvider above it + fallback ⇒ badge ABSENT (renders safely, never throws)", () => {
    // The scene layers are rendered standalone in tests; the badge must not
    // throw without a provider (it uses the optional context read).
    const { queryByTestId } = render(
      <SceneStatusBadge isFallback reason="no_key" />,
    );
    expect(queryByTestId("scene-status-badge")).toBeNull();
  });

  it("operator + fallback with no reason ⇒ badge present with the bare label", () => {
    const wrap = withAuth(OPERATOR);
    const { queryByTestId } = render(
      wrap(<SceneStatusBadge isFallback reason={null} />) as JSX.Element,
    );
    const badge = queryByTestId("scene-status-badge");
    expect(badge).not.toBeNull();
    expect(badge!.textContent).toBe("scene: procedural");
  });

  it("consumes only props — renders without ANY network call", () => {
    // Prove "no network" WITHOUT polluting globals (vi.stubGlobal +
    // unstubAllGlobals can disturb sibling suites that rely on real Web
    // Crypto / fetch in the same run). We swap the exact current
    // global.fetch for a spy and restore the original reference by hand in
    // a finally — no vitest global-stub registry is touched.
    const original = globalThis.fetch;
    const fetchSpy = vi.fn();
    // eslint-disable-next-line @typescript-eslint/no-explicit-any
    (globalThis as any).fetch = fetchSpy;
    try {
      const wrap = withAuth(OPERATOR);
      render(
        wrap(<SceneStatusBadge isFallback reason="rate_limited" />) as JSX.Element,
      );
      expect(fetchSpy).not.toHaveBeenCalled();
    } finally {
      // eslint-disable-next-line @typescript-eslint/no-explicit-any
      (globalThis as any).fetch = original;
    }
  });
});

describe("SceneStatusBadge — wired through KreaArtLayer", () => {
  const fallbackArt = (reason: string | null): SceneArt => ({
    imageUrl: null,
    prevImageUrl: null,
    fadeKey: 0,
    isFallback: true,
    status: "fallback",
    reason,
  });

  const liveArt = (): SceneArt => ({
    imageUrl: "https://art/x.png",
    prevImageUrl: null,
    fadeKey: 1,
    isFallback: false,
    status: "ready",
    reason: null,
  });

  it("operator + KreaArtLayer fallback ⇒ the badge shows the threaded reason", () => {
    const wrap = withAuth(OPERATOR);
    const { queryByTestId, getByTestId } = render(
      wrap(<KreaArtLayer art={fallbackArt("over_daily_budget")} />) as JSX.Element,
    );
    // The fallback layer still paints nothing visual (data-krea="fallback")...
    expect(getByTestId("krea-art-layer").getAttribute("data-krea")).toBe("fallback");
    // ...but the operator badge is mounted inside it with the reason.
    const badge = queryByTestId("scene-status-badge");
    expect(badge).not.toBeNull();
    expect(badge!.textContent).toBe("scene: procedural · over_daily_budget");
  });

  it("NON-operator + KreaArtLayer fallback ⇒ layer is empty, badge ABSENT (no regression to the SPR-05 'fallback paints nothing' invariant)", () => {
    const wrap = withAuth(READER_LOGGED_OUT);
    const { getByTestId } = render(
      wrap(<KreaArtLayer art={fallbackArt("no_key")} />) as JSX.Element,
    );
    const layer = getByTestId("krea-art-layer");
    expect(layer.getAttribute("data-krea")).toBe("fallback");
    // The fallback layer renders NO child divs for a non-operator — the
    // SPR-05 crossfade invariant ("fallback paints nothing") is preserved.
    expect(layer.querySelectorAll("div").length).toBe(0);
  });

  it("operator + KreaArtLayer LIVE ⇒ no badge (badge only appears on fallback)", () => {
    const wrap = withAuth(OPERATOR);
    const { queryByTestId } = render(
      wrap(<KreaArtLayer art={liveArt()} />) as JSX.Element,
    );
    expect(queryByTestId("scene-status-badge")).toBeNull();
  });
});
