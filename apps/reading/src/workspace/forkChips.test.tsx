/**
 * forkChips.test.tsx — the strip's fork lineage chrome (thread-merge +
 * document fork SPR-01, verdict C): the fork tab's badge answers "what is
 * this, what did it come from" from the chrome itself, and the source tab's
 * forks chip answers the reverse — both HOP (open-or-activate through the
 * landed store), never mutate.
 *
 * The strip runs over the REAL tab-tree store with the in-memory adapter
 * (the documentTabStrip.test.tsx harness shape); the lineage is the
 * session's learned view, seeded through recordFork exactly as the reader
 * mount's fetchDocumentForks would.
 */
import { afterEach, beforeAll, beforeEach, describe, expect, it, vi } from "vitest";
import { act, cleanup, render, screen, waitFor } from "@testing-library/react";
import { BrowserRouter } from "react-router-dom";

beforeAll(() => {
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
});

vi.mock("../lib/api", async (orig) => ({
  ...(await orig<typeof import("../lib/api")>()),
  apiFetch: vi.fn(() => Promise.resolve({ ok: false, status: 404, json: async () => ({}) })),
}));

import { DocumentTabStrip } from "./DocumentTabStrip";
import { recordFork, resetForkLineage } from "./forkLineage";
import type { DocumentFork } from "../api/forks";
import { useTabTrees } from "./tabTreeStore";

const FORK_ROW: DocumentFork = {
  fork_id: "fork-1",
  parent_document_id: "doc-1",
  fork_document_id: "doc-fork-1",
  operation_id: "op-1",
  fork_point_locator: null,
  note: null,
  generation_id: null,
  parent_body_sha256: "a".repeat(64),
  fork_body_sha256: "a".repeat(64),
  created_at: "2026-10-01T09:30:00Z",
  parent_title: "Meditations",
};

const tabs = () => useTabTrees.getState();

function mountAt(path: string) {
  window.history.replaceState({}, "", path);
  return render(
    <BrowserRouter>
      <DocumentTabStrip />
    </BrowserRouter>,
  );
}

beforeEach(() => {
  tabs().resetTabTrees();
});

afterEach(() => {
  cleanup();
  tabs().resetTabTrees();
  resetForkLineage();
  document.body.innerHTML = "";
  window.history.replaceState({}, "", "/");
});

async function loadedRootTab(): Promise<string> {
  await waitFor(() =>
    expect(tabs().trees.reading?.active_tab_id ?? null).not.toBeNull(),
  );
  return tabs().trees.reading!.active_tab_id!;
}

describe("the strip's fork lineage chrome (SPR-01 verdict C)", () => {
  it("the source tab's chip hops to the fork tab; the fork tab's badge hops back", async () => {
    mountAt("/read/doc-1");
    const rootId = await loadedRootTab();

    // The session learns the lineage (the reader mount's fetch), and the
    // fork tab is open beside the source (the fork action's branch).
    act(() => {
      recordFork(FORK_ROW);
      tabs().spawnTab("reading", rootId, {
        tab_id: "fork-tab",
        kind: "reader",
        ref: "doc-fork-1",
        mothership: "reading",
        activate: false,
      });
    });

    // The source tab answers "what came from it" from the chrome itself.
    const chip = await screen.findByRole("button", { name: /1 fork of this document/ });
    expect(chip.textContent).toBe("1 fork ▸");

    // The chip hops to the fork tab (already open → ACTIVATED, not a
    // second tab).
    act(() => chip.click());
    expect(tabs().trees.reading!.active_tab_id).toBe("fork-tab");
    expect(
      Object.values(tabs().trees.reading!.nodes).filter((n) => n.ref === "doc-fork-1"),
    ).toHaveLength(1);

    // The fork tab answers "what is this, what did it come from" — the
    // badge, from the chrome, without visiting a pane.
    const badge = await screen.findByRole("button", {
      name: /This tab is a fork of Meditations/,
    });
    expect(badge.textContent).toBe("fork of Meditations");

    // The badge hops back to the original.
    act(() => badge.click());
    expect(tabs().trees.reading!.active_tab_id).toBe(rootId);
  });

  it("renders neither chip nor badge when the session knows no lineage", async () => {
    mountAt("/read/doc-1");
    await loadedRootTab();
    expect(screen.queryByText(/fork/)).toBeNull();
  });
});
