/**
 * SceneChrome.keys.test.tsx — MS-01 milestone 5: the action-bar verb that
 * shares a keymap action ("Ask" = toggle the AI sidecar, ⌘/) carries
 * aria-keyshortcuts generated from the keymap, not typed by hand.
 */
import { afterEach, describe, expect, it } from "vitest";
import { cleanup, render, screen } from "@testing-library/react";
import { MemoryRouter } from "react-router-dom";

import { SceneChrome } from "./SceneChrome";
import { ariaKeyshortcutsFor } from "../components/hotkeys/bindings";

afterEach(cleanup);

describe("SceneChrome — bound verbs announce their keys", () => {
  it("Ask carries the AI sidecar's keys; a verb with no key carries none", () => {
    render(
      <MemoryRouter initialEntries={["/"]}>
        <SceneChrome>
          <p>route</p>
        </SceneChrome>
      </MemoryRouter>,
    );
    const ask = screen.getByRole("button", { name: "Ask" });
    expect(ask.getAttribute("aria-keyshortcuts")).toBe(ariaKeyshortcutsFor("aisidecar.toggle"));
    expect(ask.getAttribute("aria-keyshortcuts")).toMatch(/^(Meta|Control)\+\/$/);
    expect(screen.getByRole("button", { name: "New investigation" }).getAttribute("aria-keyshortcuts")).toBeNull();
  });
});
