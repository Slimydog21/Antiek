/**
 * FFX SPR-01 M1 (F-01 / A-02) — the root error boundary.
 *
 * Before this boundary, a render throw anywhere under <App/> unmounted the
 * whole root: the A-02 crawl measured 0 interactive elements and focus on
 * <body>. These tests pin the floor the boundary guarantees instead.
 */
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import { act, cleanup, fireEvent, render, screen } from "@testing-library/react";
import { MemoryRouter, useNavigate } from "react-router-dom";
import { useEffect } from "react";

import { AppErrorBoundary } from "./AppErrorBoundary";

// F-03 (MiMo critic): the wrapper's router read must not be able to take the
// root down. `hostileLocation` swaps useLocation() for one test at a time;
// every other test gets the real hook.
const { routerOverride } = vi.hoisted(() => ({
  routerOverride: { current: null as null | (() => unknown) },
}));
// F-03b (MiMo delta): the fallback's stale-deploy check must not be able to
// throw past the fallback. `chunkOverride` makes the helpers throw per test.
const { chunkOverride } = vi.hoisted(() => ({
  chunkOverride: { isChunkLoadError: null as null | (() => boolean), getChunkLoadFailure: null as null | (() => unknown) },
}));
vi.mock("./chunkLoadRecovery", async (orig) => {
  const real = await orig<typeof import("./chunkLoadRecovery")>();
  return {
    ...real,
    isChunkLoadError: (err: unknown) =>
      chunkOverride.isChunkLoadError ? chunkOverride.isChunkLoadError() : real.isChunkLoadError(err),
    getChunkLoadFailure: () =>
      chunkOverride.getChunkLoadFailure ? chunkOverride.getChunkLoadFailure() : real.getChunkLoadFailure(),
  };
});

vi.mock("react-router-dom", async (orig) => {
  const real = await orig<typeof import("react-router-dom")>();
  return {
    ...real,
    useLocation: () => (routerOverride.current ? routerOverride.current() : real.useLocation()),
  };
});

function Thrower({ when }: { when: boolean }): JSX.Element {
  if (when) throw new Error("render exploded");
  return <p>healthy page</p>;
}

let consoleError: ReturnType<typeof vi.spyOn>;

beforeEach(() => {
  // React logs every caught render error itself; silence it so the one
  // boundary log line we assert on is observable.
  consoleError = vi.spyOn(console, "error").mockImplementation(() => {});
});

afterEach(() => {
  routerOverride.current = null;
  chunkOverride.isChunkLoadError = null;
  chunkOverride.getChunkLoadFailure = null;
  cleanup();
  consoleError.mockRestore();
});

describe("AppErrorBoundary (F-01 / A-02)", () => {
  it("renders the recovery copy and two working actions when a child throws in render", () => {
    render(
      <MemoryRouter initialEntries={["/read/doc-1"]}>
        <AppErrorBoundary>
          <Thrower when />
        </AppErrorBoundary>
      </MemoryRouter>,
    );

    expect(screen.getByText("Something broke on this page.")).toBeTruthy();
    const reload = screen.getByRole("button", { name: "Reload" });
    const home = screen.getByRole("link", { name: "Go to Home" });
    expect(home.getAttribute("href")).toBe("/home");
    // The A-02 measurement was 0 interactive elements; the floor is now 2.
    const interactive = document.querySelectorAll("a[href], button");
    expect(interactive.length).toBeGreaterThanOrEqual(2);
    expect(reload).toBeTruthy();
  });

  it("Reload calls location.reload", () => {
    const reload = vi.fn();
    const original = window.location;
    Object.defineProperty(window, "location", {
      configurable: true,
      value: { ...original, reload, pathname: "/read/doc-1" },
    });
    try {
      render(
        <MemoryRouter>
          <AppErrorBoundary>
            <Thrower when />
          </AppErrorBoundary>
        </MemoryRouter>,
      );
      fireEvent.click(screen.getByRole("button", { name: "Reload" }));
      expect(reload).toHaveBeenCalledTimes(1);
    } finally {
      Object.defineProperty(window, "location", { configurable: true, value: original });
    }
  });

  it("logs the error exactly once with the route pathname", () => {
    render(
      <MemoryRouter initialEntries={["/read/doc-1"]}>
        <AppErrorBoundary>
          <Thrower when />
        </AppErrorBoundary>
      </MemoryRouter>,
    );
    const ours = consoleError.mock.calls.filter(
      (args: unknown[]) => typeof args[0] === "string" && args[0].startsWith("[antiek] app error boundary"),
    );
    expect(ours).toHaveLength(1);
    expect(String(ours[0][0])).toContain(window.location.pathname);
  });

  it("resets when the pathname changes, so a crash on one route does not persist on /home", () => {
    let go: (to: string) => void = () => {};
    function Navigator() {
      const navigate = useNavigate();
      useEffect(() => {
        go = navigate;
      }, [navigate]);
      return null;
    }
    let broken = true;
    function MaybeThrow() {
      return <Thrower when={broken} />;
    }

    render(
      <MemoryRouter initialEntries={["/read/doc-1"]}>
        <Navigator />
        <AppErrorBoundary>
          <MaybeThrow />
        </AppErrorBoundary>
      </MemoryRouter>,
    );
    expect(screen.getByText("Something broke on this page.")).toBeTruthy();

    broken = false;
    act(() => go("/home"));

    expect(screen.queryByText("Something broke on this page.")).toBeNull();
    expect(screen.getByText("healthy page")).toBeTruthy();
  });

  it("does not remount healthy children on navigation (the reset key is not a React key)", () => {
    let mounts = 0;
    function CountMounts() {
      useEffect(() => {
        mounts += 1;
      }, []);
      return <p>app</p>;
    }
    let go: (to: string) => void = () => {};
    function Navigator() {
      const navigate = useNavigate();
      useEffect(() => {
        go = navigate;
      }, [navigate]);
      return null;
    }
    render(
      <MemoryRouter initialEntries={["/library"]}>
        <Navigator />
        <AppErrorBoundary>
          <CountMounts />
        </AppErrorBoundary>
      </MemoryRouter>,
    );
    act(() => go("/notebooks"));
    act(() => go("/write"));
    expect(mounts).toBe(1);
  });

  describe("the wrapper itself cannot take the root down (critic F-03)", () => {
    function interactive(): number {
      return document.querySelectorAll("a[href], button").length;
    }

    it("a pathname getter that throws still renders the boundary fallback", () => {
      routerOverride.current = () => ({
        get pathname(): string {
          throw new Error("pathname getter exploded");
        },
      });
      render(
        <MemoryRouter>
          <AppErrorBoundary>
            <Thrower when />
          </AppErrorBoundary>
        </MemoryRouter>,
      );
      expect(screen.getByText("Something broke on this page.")).toBeTruthy();
      expect(interactive()).toBeGreaterThanOrEqual(2);
    });

    it("a pathname getter that throws does not break a healthy app", () => {
      routerOverride.current = () => ({
        get pathname(): string {
          throw new Error("pathname getter exploded");
        },
      });
      render(
        <MemoryRouter>
          <AppErrorBoundary>
            <Thrower when={false} />
          </AppErrorBoundary>
        </MemoryRouter>,
      );
      expect(screen.getByText("healthy page")).toBeTruthy();
    });

    it("useLocation throwing (no router context) still renders the boundary fallback", () => {
      routerOverride.current = () => {
        throw new Error("useLocation() may be used only in the context of a <Router> component.");
      };
      render(
        <AppErrorBoundary>
          <Thrower when />
        </AppErrorBoundary>,
      );
      expect(screen.getByText("Something broke on this page.")).toBeTruthy();
      expect(interactive()).toBeGreaterThanOrEqual(2);
    });

    it("a null location still renders the boundary fallback", () => {
      routerOverride.current = () => null;
      render(
        <AppErrorBoundary>
          <Thrower when />
        </AppErrorBoundary>,
      );
      expect(screen.getByText("Something broke on this page.")).toBeTruthy();
    });
  });

  describe("the fallback itself cannot throw (critic F-03b)", () => {
    function expectGenericFallback() {
      expect(screen.getByText("Something broke on this page.")).toBeTruthy();
      expect(screen.getByRole("button", { name: "Reload" })).toBeTruthy();
      expect(screen.getByRole("link", { name: "Go to Home" }).getAttribute("href")).toBe("/home");
      expect(document.querySelectorAll("a[href], button").length).toBeGreaterThanOrEqual(2);
    }

    it("isChunkLoadError throwing still renders the generic copy with Reload + Go to Home", () => {
      chunkOverride.isChunkLoadError = () => {
        throw new Error("isChunkLoadError exploded");
      };
      render(
        <MemoryRouter>
          <AppErrorBoundary>
            <Thrower when />
          </AppErrorBoundary>
        </MemoryRouter>,
      );
      expectGenericFallback();
    });

    it("getChunkLoadFailure throwing still renders the generic copy with Reload + Go to Home", () => {
      chunkOverride.getChunkLoadFailure = () => {
        throw new Error("getChunkLoadFailure exploded");
      };
      render(
        <MemoryRouter>
          <AppErrorBoundary>
            <Thrower when />
          </AppErrorBoundary>
        </MemoryRouter>,
      );
      expectGenericFallback();
    });
  });
});
