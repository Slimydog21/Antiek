/**
 * windowContract.test.tsx — SPR-09 M4 acceptance (the bounded contract) +
 * SPR-04 M3 acceptance (the windows-default policy INVERSION).
 *
 * PART 1 (SPR-09 M4) — the window-adaptation contract on a REAL product page
 * (Stats):
 *   - rendered at its normal route (useInWindow()=false), the page keeps its
 *     opaque full-bleed bg + h-screen — the full-page route is UNCHANGED;
 *   - rendered inside a WorkspaceWindow (useInWindow()=true via the host
 *     provider), the SAME page drops the opaque bg (→ glass shows through) and
 *     uses h-full (→ fills the window), with NO feature change.
 * This is the whole contract: (a) condition the opaque bg, (b) fill the
 * container. Nothing else about Stats is touched. Library carries the
 * identical two-line surgical diff (asserted by code review, not re-tested —
 * it is the same edit).
 *
 * PART 2 (SPR-04 M3) — the policy INVERSION enforced at the launcher: the
 * DEFAULT (primary) click on a within-contract PRODUCT opens a window
 * (windowsStore.open() is called, no navigation); a click on an OUT-OF-CONTRACT
 * deep mode (ResearchWorkstation / WrestleApp) NAVIGATES full-page (no window).
 * This is the load-bearing jsdom guard that the inversion landed; the BROWSER
 * proof that the window is actually visible over the scene lives in the
 * Playwright gate (e2e/windows-default.spec.ts).
 */
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import {
  cleanup,
  fireEvent,
  render,
  screen,
  waitFor,
} from "@testing-library/react";
import { MemoryRouter } from "react-router-dom";

import Stats from "../../modes/Stats";
import { ProductsLauncher } from "../../shell/ProductsLauncher";
import { useWindows } from "../../workspace/windowsStore";
import { WindowHostProvider } from "./windowHostContext";

const { apiFetchMock, navigateMock } = vi.hoisted(() => ({
  apiFetchMock: vi.fn(),
  navigateMock: vi.fn(),
}));

vi.mock("../../lib/api", async (orig) => {
  const actual = await orig<typeof import("../../lib/api")>();
  return { ...actual, apiFetch: apiFetchMock };
});

// PART 2 (M3) renders the real ProductsLauncher, which calls useNavigate. We
// mock only useNavigate so we can assert "navigated" vs "opened a window"
// without a real router/history.
vi.mock("react-router-dom", async (orig) => {
  const actual = await orig<typeof import("react-router-dom")>();
  return { ...actual, useNavigate: () => navigateMock };
});

function okStats() {
  apiFetchMock.mockResolvedValue({
    ok: true,
    json: async () => ({
      counts: { investigations: 3, documents: 7 },
      warnings: [],
    }),
  } as Response);
}

beforeEach(() => {
  apiFetchMock.mockReset();
  okStats();
});
afterEach(cleanup);

/** Find the page's root flex column + its <main> band, by structure. */
function rootAndMain(container: HTMLElement) {
  const root = container.querySelector("div.flex.flex-col") as HTMLElement;
  const main = container.querySelector(".substrate-atlas__main") as HTMLElement;
  return { root, main };
}

describe("window-adaptation contract — Stats at its full-page route", () => {
  it("keeps the opaque bg + h-screen when NOT in a window (route unchanged)", async () => {
    const { container } = render(<Stats />);
    await waitFor(() => expect(apiFetchMock).toHaveBeenCalled());
    const { root, main } = rootAndMain(container);
    expect(root.className).toContain("h-screen");
    expect(root.className).not.toContain("h-full");
    expect(main.className).toContain("bg-ice-0");
    expect(main.className).not.toContain("bg-transparent");
    expect(main.tagName).toBe("MAIN");
  });
});

describe("window-adaptation contract — Stats hosted in a window", () => {
  it("drops the opaque bg (glass shows through) and uses h-full to fill", async () => {
    const { container } = render(
      <WindowHostProvider value={true}>
        <Stats />
      </WindowHostProvider>,
    );
    await waitFor(() => expect(apiFetchMock).toHaveBeenCalled());
    const { root, main } = rootAndMain(container);
    // (a) fills the container, not the viewport
    expect(root.className).toContain("h-full");
    expect(root.className).not.toContain("h-screen");
    // (b) opaque full-bleed bg removed → transparent so the glass/scene shows
    expect(main.className).toContain("bg-transparent");
    expect(main.className).not.toContain("bg-ice-0");
    expect(main.tagName).toBe("SECTION");
    expect(main.getAttribute("aria-label")).toBe("Substrate atlas");
    expect(container.querySelector("main")).toBeNull();
  });

  it("still renders the page's real content (no feature change)", async () => {
    render(
      <WindowHostProvider value={true}>
        <Stats />
      </WindowHostProvider>,
    );
    // The substrate counts still load + render — the adaptation is cosmetic only.
    await waitFor(() =>
      expect(screen.getByText("investigations")).toBeTruthy(),
    );
    expect(screen.getByText("3")).toBeTruthy();
  });
});

// ───────────────────────────────────────────────────────────────────────────
// PART 2 — SPR-04 M3: the windows-default policy INVERSION at the launcher.
// ───────────────────────────────────────────────────────────────────────────

function renderLauncher() {
  render(
    <MemoryRouter>
      <ProductsLauncher open onClose={vi.fn()} />
    </MemoryRouter>,
  );
}

describe("windows-default policy inversion — ProductsLauncher (M3)", () => {
  beforeEach(() => {
    navigateMock.mockReset();
    useWindows.getState().reset();
  });

  it("DEFAULT click on a within-contract PRODUCT opens a window (open() called, no navigate)", () => {
    renderLauncher();
    // The Research product header is the default product activation. Its
    // accessible name carries the "workflow" keyword so the product-window
    // name-space can never converge with the eligible-mode ⊞ name-space.
    fireEvent.click(
      screen.getByLabelText("Open Research workflow in a window"),
    );
    const ws = useWindows.getState();
    expect(ws.order.length).toBe(1);
    expect(ws.windows[ws.order[0]].kind).toBe("subaction");
    expect(ws.windows[ws.order[0]].payload.workflow).toBe("research");
    // The window is the DEFAULT — the product click does NOT navigate away.
    expect(navigateMock).not.toHaveBeenCalled();
  });

  it("a second click on the SAME product focuses the one window (stable id, no duplicate)", () => {
    renderLauncher();
    fireEvent.click(
      screen.getByLabelText("Open Research workflow in a window"),
    );
    fireEvent.click(
      screen.getByLabelText("Open Research workflow in a window"),
    );
    expect(useWindows.getState().order.length).toBe(1);
  });

  it("each of the four products opens its OWN sub-action window (per-workflow id)", () => {
    renderLauncher();
    for (const label of ["Research", "Read", "Write", "Speak"]) {
      fireEvent.click(
        screen.getByLabelText(`Open ${label} workflow in a window`),
      );
    }
    const ws = useWindows.getState();
    expect(ws.order.length).toBe(4);
    expect(
      new Set(ws.order.map((id) => ws.windows[id].payload.workflow)),
    ).toEqual(new Set(["research", "read", "write", "speak"]));
  });

  it("a click on an OUT-OF-CONTRACT deep mode NAVIGATES full-page (no window)", () => {
    renderLauncher();
    // ResearchWorkstation owns a PanelHost dock + the dense-opaque /inv view —
    // out-of-contract → it navigates, never floats.
    fireEvent.click(
      document.querySelector('[data-mode-id="ResearchWorkstation"]') as Element,
    );
    expect(navigateMock).toHaveBeenCalledWith("/");
    expect(useWindows.getState().order.length).toBe(0);

    // The PDF wrestler (WrestleApp) is likewise out-of-contract → navigate.
    fireEvent.click(
      document.querySelector('[data-mode-id="WrestleApp"]') as Element,
    );
    expect(navigateMock).toHaveBeenCalledWith("/wrestle");
    expect(useWindows.getState().order.length).toBe(0);
  });
});
