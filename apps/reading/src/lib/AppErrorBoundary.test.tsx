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
});
