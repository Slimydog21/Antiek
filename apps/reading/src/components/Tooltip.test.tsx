/**
 * Tooltip — the CSS-only tip: data-tip for the eye, aria-describedby for the
 * ear, and a stylesheet that shows it on keyboard focus as well as hover.
 */
import { cleanup, render, screen } from "@testing-library/react";
import { readFileSync } from "node:fs";
import { dirname, join } from "node:path";
import { fileURLToPath } from "node:url";
import { afterEach, describe, expect, it } from "vitest";

import { Tooltip, tipProps } from "./Tooltip";

afterEach(() => cleanup());

const css = readFileSync(join(dirname(fileURLToPath(import.meta.url)), "Tooltip.css"), "utf8");

describe("Tooltip — wiring", () => {
  it("puts the tip on the child and points aria-describedby at a hidden copy", () => {
    render(
      <Tooltip tip="Opens the reader in a new window">
        <button type="button">Pop out</button>
      </Tooltip>,
    );
    const btn = screen.getByRole("button", { name: "Pop out" });
    expect(btn.getAttribute("data-tip")).toBe("Opens the reader in a new window");
    const id = btn.getAttribute("aria-describedby")!;
    const desc = document.getElementById(id)!;
    expect(desc.textContent).toBe("Opens the reader in a new window");
    expect(desc.hidden).toBe(true);
  });

  it("keeps a description the child already had", () => {
    render(
      <Tooltip tip="Saved locally">
        <button type="button" aria-describedby="x">Save</button>
      </Tooltip>,
    );
    expect(screen.getByRole("button").getAttribute("aria-describedby")).toMatch(/^x \S+$/);
  });

  it("renders nothing extra when there is no tip", () => {
    const { container } = render(
      <Tooltip tip={null}>
        <button type="button">Plain</button>
      </Tooltip>,
    );
    expect(screen.getByRole("button").hasAttribute("data-tip")).toBe(false);
    expect(container.querySelectorAll("span[hidden]").length).toBe(0);
  });

  it("placement and alignment ride on data attributes the stylesheet reads", () => {
    const p = tipProps("Why", "t1", undefined, { placement: "bottom", align: "end" });
    expect(p["data-tip-placement"]).toBe("bottom");
    expect(p["data-tip-align"]).toBe("end");
    expect(css).toMatch(/\[data-tip-placement="bottom"\]/);
    expect(css).toMatch(/\[data-tip-align="end"\]/);
  });
});

describe("Tooltip.css — shown to the keyboard, never a hidden overflow box", () => {
  it("shows on :focus-visible as well as :hover", () => {
    expect(css).toMatch(/\[data-tip\]:hover::after,\s*\[data-tip\]:focus-visible::after\s*\{[^}]*content:\s*attr\(data-tip\)/);
  });

  it("the tip box does not exist while hidden (content: none), so it cannot widen the page", () => {
    expect(css).toMatch(/\[data-tip\]::after\s*\{\s*content:\s*none;\s*\}/);
    expect(css).not.toMatch(/visibility:\s*hidden/);
  });

  it("sits on the tooltip rung of the z ladder", () => {
    expect(css).toMatch(/z-index:\s*var\(--z-tooltip\)/);
  });
});
