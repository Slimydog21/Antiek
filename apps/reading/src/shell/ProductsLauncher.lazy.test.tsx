/**
 * ProductsLauncher.lazy.test — the More drawer loads on demand.
 *
 * The launcher is about 6.6 KB of minified entry JS that nothing needs until
 * More is pressed. With the shared states adopted the entry chunk measured
 * 700,160 B gzip against its 700,000 B ceiling (design spec §7), so the
 * NavRail now imports the launcher lazily (and prefetches it when idle).
 *
 * The behaviour is unchanged: More opens the "More" dialog and closing it
 * removes it. The source check pins the lazy import, so a later static
 * import that puts the drawer back in the entry chunk fails here first.
 */
import { readFileSync } from "node:fs";
import { dirname, join } from "node:path";
import { fileURLToPath } from "node:url";
import { afterEach, describe, expect, it } from "vitest";
import { cleanup, fireEvent, render, screen, waitFor } from "@testing-library/react";
import { MemoryRouter } from "react-router-dom";

import { NavRail } from "./NavRail";

afterEach(cleanup);

describe("the More launcher loads on demand", () => {
  it("More still opens the launcher, and closing it removes it", async () => {
    render(
      <MemoryRouter>
        <NavRail />
      </MemoryRouter>,
    );
    expect(screen.queryByRole("dialog", { name: "More" })).toBeNull();

    fireEvent.click(screen.getByTitle(/More - all products/));
    const dialog = await screen.findByRole("dialog", { name: "More" });
    expect(dialog.textContent).toMatch(/Settings/);

    fireEvent.click(screen.getByRole("button", { name: "Close" }));
    await waitFor(() => expect(screen.queryByRole("dialog", { name: "More" })).toBeNull());
  });

  it("NavRail imports the launcher lazily, not into the entry chunk", () => {
    const here = dirname(fileURLToPath(import.meta.url));
    const text = readFileSync(join(here, "NavRail.tsx"), "utf8");
    expect(text).not.toMatch(/^import[^;]*from "\.\/ProductsLauncher";/m);
    expect(text).toMatch(/import\("\.\/ProductsLauncher"\)/);
  });
});
