/**
 * ProductsLauncher.flagGate.test.tsx — the SPR-01 gate verdict: the
 * launcher's visual restyle rides `antiek.flag.pane.flow`.
 *
 * Flag OFF (the default every test sees) renders main's launcher
 * byte-verbatim (ProductsLauncherLegacy): the grouped grid of workflow
 * sections. Flag ON renders the packet's flat ranked list
 * (ProductsLauncherFlow). The stories carry no flag, so the committed
 * shell-products-launcher--open baselines compare against the flag-off
 * build again.
 */
import { cleanup, render, screen } from "@testing-library/react";
import { afterEach, describe, expect, it } from "vitest";
import { MemoryRouter } from "react-router-dom";

import { setFeatureFlag } from "../lib/featureFlags";
import { ProductsLauncher } from "./ProductsLauncher";

function mount() {
  return render(
    <MemoryRouter initialEntries={["/"]}>
      <ProductsLauncher open onClose={() => {}} />
    </MemoryRouter>,
  );
}

afterEach(() => {
  cleanup();
  setFeatureFlag("pane.flow", null);
});

describe("the ProductsLauncher flag gate", () => {
  it("flag off renders main's grouped grid — the committed baselines' launcher", () => {
    setFeatureFlag("pane.flow", false);
    mount();
    // The legacy signature: workflow groups as labelled <section>s in a
    // grid, and no flat ranked list.
    expect(document.querySelectorAll("section[aria-label]").length).toBeGreaterThan(0);
    expect(document.querySelector('[aria-label="Products and surfaces"]')).toBeNull();
    expect(document.querySelector("[data-launcher-active]")).toBeNull();
  });

  it("flag on renders the packet's flat ranked list", () => {
    setFeatureFlag("pane.flow", true);
    mount();
    expect(screen.getByLabelText("Products and surfaces")).toBeTruthy();
    expect(document.querySelector("[data-launcher-active]")).not.toBeNull();
    // No legacy workflow-group sections.
    expect(document.querySelectorAll("section[aria-label]")).toHaveLength(0);
  });
});
