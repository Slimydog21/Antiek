/**
 * windowContract.test.tsx — SPR-09 M4 acceptance (the bounded contract).
 *
 * Proves the window-adaptation contract on a REAL product page (Stats):
 *   - rendered at its normal route (useInWindow()=false), the page keeps its
 *     opaque full-bleed bg + h-screen — the full-page route is UNCHANGED;
 *   - rendered inside a WorkspaceWindow (useInWindow()=true via the host
 *     provider), the SAME page drops the opaque bg (→ glass shows through) and
 *     uses h-full (→ fills the window), with NO feature change.
 *
 * This is the whole contract: (a) condition the opaque bg, (b) fill the
 * container. Nothing else about Stats is touched. Library carries the
 * identical two-line surgical diff (asserted by code review, not re-tested —
 * it is the same edit).
 */
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import { cleanup, render, screen, waitFor } from "@testing-library/react";

import Stats from "../../modes/Stats";
import { WindowHostProvider } from "./windowHostContext";

const { apiFetchMock } = vi.hoisted(() => ({ apiFetchMock: vi.fn() }));

vi.mock("../../lib/api", async (orig) => {
  const actual = await orig<typeof import("../../lib/api")>();
  return { ...actual, apiFetch: apiFetchMock };
});

function okStats() {
  apiFetchMock.mockResolvedValue({
    ok: true,
    json: async () => ({ counts: { investigations: 3, documents: 7 }, warnings: [] }),
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
  const main = container.querySelector("main") as HTMLElement;
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
  });

  it("still renders the page's real content (no feature change)", async () => {
    render(
      <WindowHostProvider value={true}>
        <Stats />
      </WindowHostProvider>,
    );
    // The substrate counts still load + render — the adaptation is cosmetic only.
    await waitFor(() => expect(screen.getByText("investigations")).toBeTruthy());
    expect(screen.getByText("3")).toBeTruthy();
  });
});
