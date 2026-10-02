/**
 * FFX SPR-01 M2 (P-05 / F-01) — chunk-load recovery.
 *
 * After a deploy replaces the hashed chunks, a stale tab's lazy import() of
 * /assets/Settings-<old>.js fails (on antiek.ai the edge even answers it with
 * the SPA HTML, cached immutable — P-05). Vite's preload helper dispatches
 * `vite:preloadError` on window for that failure. The handler reloads ONCE
 * per failed asset URL, and after that lets the root boundary say what
 * happened instead of looping.
 */
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import { cleanup, render, screen } from "@testing-library/react";
import { MemoryRouter } from "react-router-dom";

import {
  __resetChunkLoadRecoveryForTests,
  chunkReloadGuardKey,
  failedAssetUrl,
  getChunkLoadFailure,
  installChunkLoadRecovery,
  isChunkLoadError,
} from "./chunkLoadRecovery";
import { AppErrorBoundary, STALE_DEPLOY_COPY } from "./AppErrorBoundary";

const SETTINGS_URL = "https://antiek.ai/assets/Settings-Bq9x1a2Z.js";
const OTHER_URL = "https://antiek.ai/assets/Library-Zz81kLmN.js";

function chunkError(url: string): TypeError {
  // Chromium's exact wording for a failed dynamic import.
  return new TypeError(`Failed to fetch dynamically imported module: ${url}`);
}

function dispatchPreloadError(url: string): Event {
  const event = new Event("vite:preloadError", { cancelable: true }) as Event & { payload?: unknown };
  event.payload = chunkError(url);
  window.dispatchEvent(event);
  return event;
}

let reload: ReturnType<typeof vi.fn>;
let uninstall: () => void = () => {};
const originalLocation = window.location;

beforeEach(() => {
  window.sessionStorage.clear();
  __resetChunkLoadRecoveryForTests();
  reload = vi.fn();
  Object.defineProperty(window, "location", {
    configurable: true,
    value: { ...originalLocation, reload, pathname: "/settings" },
  });
  uninstall = installChunkLoadRecovery();
});

afterEach(() => {
  uninstall();
  cleanup();
  Object.defineProperty(window, "location", { configurable: true, value: originalLocation });
  vi.restoreAllMocks();
});

describe("installChunkLoadRecovery (P-05)", () => {
  it("first failure of an asset URL: reloads exactly once and sets the sessionStorage guard for that URL", () => {
    dispatchPreloadError(SETTINGS_URL);
    expect(reload).toHaveBeenCalledTimes(1);
    expect(window.sessionStorage.getItem(chunkReloadGuardKey(SETTINGS_URL))).not.toBeNull();
  });

  it("second failure of the SAME URL: no reload (no loop) and the boundary state is set", () => {
    dispatchPreloadError(SETTINGS_URL);
    expect(reload).toHaveBeenCalledTimes(1);
    // Simulates the post-reload page hitting the same truly-missing asset.
    dispatchPreloadError(SETTINGS_URL);
    expect(reload).toHaveBeenCalledTimes(1);
    expect(getChunkLoadFailure()).toEqual({ url: SETTINGS_URL });
  });

  it("a DIFFERENT failed URL in the same session gets its own single attempt", () => {
    dispatchPreloadError(SETTINGS_URL);
    dispatchPreloadError(OTHER_URL);
    expect(reload).toHaveBeenCalledTimes(2);
    dispatchPreloadError(OTHER_URL);
    dispatchPreloadError(SETTINGS_URL);
    expect(reload).toHaveBeenCalledTimes(2);
  });

  it("never reloads when sessionStorage cannot hold the guard (a loop is worse than a message)", () => {
    vi.spyOn(Storage.prototype, "setItem").mockImplementation(() => {
      throw new DOMException("quota", "QuotaExceededError");
    });
    dispatchPreloadError(SETTINGS_URL);
    expect(reload).not.toHaveBeenCalled();
    expect(getChunkLoadFailure()).toEqual({ url: SETTINGS_URL });
  });

  it("does not swallow the error: Vite still rethrows it so the lazy route rejects into the boundary", () => {
    const event = dispatchPreloadError(SETTINGS_URL);
    expect(event.defaultPrevented).toBe(false);
  });

  it("installing twice listens once, and each uninstaller really uninstalls (critic F-06)", () => {
    const second = installChunkLoadRecovery();
    dispatchPreloadError(SETTINGS_URL);
    expect(reload).toHaveBeenCalledTimes(1);
    // Releasing the second install keeps the first one's listener.
    second();
    dispatchPreloadError(OTHER_URL);
    expect(reload).toHaveBeenCalledTimes(2);
    // Releasing the first (the real) one removes the listener.
    uninstall();
    window.sessionStorage.clear();
    dispatchPreloadError("https://antiek.ai/assets/Third-Q1w2e3r4.js");
    expect(reload).toHaveBeenCalledTimes(2);
  });

  it("the uninstaller returned by a repeat install is not a no-op when it is the last one standing", () => {
    const second = installChunkLoadRecovery();
    uninstall();
    // One install still outstanding: still listening.
    dispatchPreloadError(SETTINGS_URL);
    expect(reload).toHaveBeenCalledTimes(1);
    second();
    window.sessionStorage.clear();
    dispatchPreloadError(OTHER_URL);
    expect(reload).toHaveBeenCalledTimes(1);
  });

  it("calling one uninstaller twice cannot release another install", () => {
    const second = installChunkLoadRecovery();
    second();
    second();
    dispatchPreloadError(SETTINGS_URL);
    expect(reload).toHaveBeenCalledTimes(1);
  });

  it("uninstall removes the listener", () => {
    uninstall();
    dispatchPreloadError(SETTINGS_URL);
    expect(reload).not.toHaveBeenCalled();
  });
});

describe("failedAssetUrl / isChunkLoadError", () => {
  it("extracts the asset URL from each engine's wording", () => {
    expect(failedAssetUrl(chunkError(SETTINGS_URL))).toBe(SETTINGS_URL);
    expect(failedAssetUrl(new TypeError(`error loading dynamically imported module: ${SETTINGS_URL}`))).toBe(SETTINGS_URL);
    expect(failedAssetUrl(new Error("Unable to preload CSS for /assets/Settings-Bq9x1a2Z.css"))).toBe(
      "/assets/Settings-Bq9x1a2Z.css",
    );
  });

  it("keys a URL-less failure (Safari) by the route, so each route still gets one attempt", () => {
    expect(failedAssetUrl(new TypeError("Importing a module script failed."))).toBe("unknown-asset@/settings");
  });

  it("recognises chunk-load failures and nothing else", () => {
    expect(isChunkLoadError(chunkError(SETTINGS_URL))).toBe(true);
    expect(isChunkLoadError(new TypeError("Importing a module script failed."))).toBe(true);
    expect(isChunkLoadError(new Error("Unable to preload CSS for /assets/a.css"))).toBe(true);
    expect(isChunkLoadError(new Error("render exploded"))).toBe(false);
    expect(isChunkLoadError(null)).toBe(false);
  });
});

describe("the boundary speaks for a stale deploy", () => {
  it("shows the new-version copy and a Reload action when the caught error is a chunk-load failure", () => {
    vi.spyOn(console, "error").mockImplementation(() => {});
    function LazyRouteThatFailed(): JSX.Element {
      throw chunkError(SETTINGS_URL);
    }
    render(
      <MemoryRouter initialEntries={["/settings"]}>
        <AppErrorBoundary>
          <LazyRouteThatFailed />
        </AppErrorBoundary>
      </MemoryRouter>,
    );
    expect(screen.getByText(STALE_DEPLOY_COPY)).toBeTruthy();
    expect(screen.getByRole("button", { name: "Reload" })).toBeTruthy();
    expect(screen.getByRole("link", { name: "Go to Home" })).toBeTruthy();
  });
});
