/**
 * NewTabPicker.test.tsx — prefix+c opens a REAL picker (the D2.4 defect:
 * the advertised key disarmed the prefix and opened nothing).
 *
 * The load-bearing test presses the advertised binding through the REAL
 * dispatcher (installShortcuts, real keydown events, no handler invoked
 * directly) and watches the dialog open — the exact probe the independent
 * verification ran against production, now at the code level. On the
 * unfixed code this dialog never appears: the handler was `notBuiltYet`,
 * which returned false and left the key to the page.
 */
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import { act, cleanup, fireEvent, render, waitFor } from "@testing-library/react";

import { MemoryRouter } from "react-router-dom";

import { installShortcuts } from "./shortcuts";
import { NewTabPicker } from "./NewTabPicker";
import { DocumentTabStrip } from "./DocumentTabStrip";
import { press } from "./keymapTestKit";
import { useTabTrees } from "./tabTreeStore";

const tabs = () => useTabTrees.getState();
const dialog = () => document.body.querySelector('[role="dialog"]');

/** The corpus the picker lists, as the APIs answer it. */
const BOOKS = {
  books: [
    {
      document_id: "doc-picker-1",
      title: "A Modest Proposal",
      author: "Jonathan Swift",
      servability: "public_domain",
      servable_full_text: true,
      page_count: 12,
      cover_uri: null,
      ip_holder_id: null,
      taken_down: false,
    },
  ],
  count: 1,
};
const INVESTIGATIONS = {
  count: 1,
  investigations: [
    {
      investigation_id: "inv-picker-123456",
      question: "What killed the dodo?",
      status: "in_progress",
      completed_at: null,
    },
  ],
};

function respond(body: unknown, status = 200) {
  return Promise.resolve({
    ok: status >= 200 && status < 300,
    status,
    json: async () => body,
    text: async () => JSON.stringify(body),
  } as Response);
}

function stubCorpus() {
  vi.stubGlobal("fetch", (input: RequestInfo | URL) => {
    const url = String(input);
    if (url.includes("/books")) return respond(BOOKS);
    if (url.includes("/investigations")) return respond(INVESTIGATIONS);
    return respond({}, 404);
  });
}

async function pressKeys(...specs: string[]) {
  await act(async () => {
    for (const spec of specs) press(window, spec, "mac");
  });
}

describe("the new-tab picker (prefix+c)", () => {
  let uninstall: () => void;

  beforeEach(() => {
    stubCorpus();
    tabs().resetTabTrees();
    uninstall = installShortcuts(vi.fn() as never);
  });

  afterEach(() => {
    uninstall();
    cleanup();
    vi.unstubAllGlobals();
    tabs().resetTabTrees();
    document.body.innerHTML = "";
  });

  it("prefix+c opens the picker: the advertised binding ACTS", async () => {
    render(<NewTabPicker />);
    expect(dialog()).toBeNull();
    await pressKeys("ctrl+b", "c");
    await waitFor(() => expect(dialog()).toBeTruthy());
    expect(dialog()!.textContent).toContain("New tab");
    // The corpus rows arrive (the dialog owns every key while open).
    await waitFor(() => expect(dialog()!.textContent).toContain("A Modest Proposal"));
    expect(dialog()!.textContent).toContain("What killed the dodo?");
  });

  it("ctrl+alt+c, the chord twin, opens the same picker", async () => {
    render(<NewTabPicker />);
    await pressKeys("ctrl+alt+c");
    await waitFor(() => expect(dialog()).toBeTruthy());
  });

  it("the prefix does not arm from the picker's own filter, and Esc closes", async () => {
    render(<NewTabPicker />);
    await pressKeys("ctrl+b", "c");
    await waitFor(() => expect(dialog()).toBeTruthy());
    const filter = dialog()!.querySelector<HTMLInputElement>('input[type="search"]')!;
    // Typing into the filter is the filter's, never a keymap row's.
    fireEvent.change(filter, { target: { value: "dodo" } });
    await waitFor(() => {
      expect(dialog()!.textContent).toContain("What killed the dodo?");
      expect(dialog()!.textContent).not.toContain("A Modest Proposal");
    });
    await act(async () => {
      fireEvent.keyDown(window, { key: "Escape", bubbles: true, cancelable: true });
    });
    await waitFor(() => expect(dialog()).toBeNull());
  });

  it("picking a document closes the picker and spawns its root tab, shown at once", async () => {
    render(<NewTabPicker />);
    await pressKeys("ctrl+b", "c");
    await waitFor(() => expect(dialog()?.textContent).toContain("A Modest Proposal"));
    const option = Array.from(dialog()!.querySelectorAll<HTMLElement>('[role="option"]')).find(
      (el) => el.textContent?.includes("A Modest Proposal"),
    )!;
    await act(async () => {
      fireEvent.click(option);
    });
    await waitFor(() => expect(dialog()).toBeNull());
    const tree = tabs().trees.reading;
    expect(tree?.nodes["root:reader:doc-picker-1"]).toBeTruthy();
    expect(tree?.active_tab_id).toBe("root:reader:doc-picker-1");
    expect(tabs().navIntent).toMatchObject({ mothership: "reading", tabId: "root:reader:doc-picker-1" });
  });

  it("picking an investigation files it under research", async () => {
    render(<NewTabPicker />);
    await pressKeys("ctrl+b", "c");
    await waitFor(() => expect(dialog()?.textContent).toContain("What killed the dodo?"));
    const option = Array.from(dialog()!.querySelectorAll<HTMLElement>('[role="option"]')).find(
      (el) => el.textContent?.includes("What killed the dodo?"),
    )!;
    await act(async () => {
      fireEvent.click(option);
    });
    const tree = tabs().trees.research;
    expect(tree?.nodes["root:research:/inv/inv-picker-123456"]).toBeTruthy();
  });

  it("the document strip's + button takes the SAME path as the key", async () => {
    // The REAL container (not the view with a hand-wired prop): its onNewTab
    // IS toggleNewTabPicker, so this click proves the strip and the key can
    // never drift apart.
    await tabs().ensureMothership("reading");
    render(
      <>
        <NewTabPicker />
        <MemoryRouter initialEntries={["/library"]}>
          <DocumentTabStrip />
        </MemoryRouter>
      </>,
    );
    const button = await waitFor(() => {
      const el = document.body.querySelector<HTMLElement>("[data-new-tab]");
      expect(el).toBeTruthy();
      return el!;
    });
    expect(button.getAttribute("aria-label")).toContain("New tab");
    await act(async () => {
      fireEvent.click(button);
    });
    await waitFor(() => expect(dialog()).toBeTruthy());
  });
});
