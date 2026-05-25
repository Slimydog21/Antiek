import { test, expect } from "@playwright/test";

/**
 * SPR-04 acceptance e2e: compose → edit → capture in the Write editor.
 *
 * Drives the WriteEditor via its Storybook stories (the `e2e` script runs
 * `build-storybook && playwright test`, serving the static Storybook).
 * This spec is written to the contract; it requires a browser run
 * (`npm run e2e`) which is not executed in the spec-authoring environment.
 *
 * What it asserts:
 *   - the editor mounts and is contenteditable;
 *   - typing produces text (the compose path);
 *   - a lego block + its citation render with the trace affordance;
 *   - clicking a citation dispatches the `write:trace-to-source` intent
 *     (the SPR-07 hook) — verified by listening for the CustomEvent.
 *
 * Edit.captured emission itself is unit-tested in editCapture.test.ts
 * (the diff + revert logic); this e2e covers the live editor surface.
 */

const STORY = (id: string) =>
  `/iframe.html?id=write-editor--${id}&viewMode=story`;

test.describe("Write editor (SPR-04)", () => {
  test("mounts and accepts typed prose", async ({ page }) => {
    await page.goto(STORY("empty"));
    const editable = page.locator('[contenteditable="true"]').first();
    await expect(editable).toBeVisible();
    await editable.click();
    await editable.type("The edit is the writing.");
    await expect(editable).toContainText("The edit is the writing.");
  });

  test("renders a lego block with a trace affordance and emits a trace intent", async ({ page }) => {
    await page.goto(STORY("with-lego-block-and-citation"));
    // The lego block renders its kind label + a trace button.
    await expect(page.getByText("insight", { exact: false }).first()).toBeVisible();
    const traceBtn = page.getByRole("button", { name: /trace/i }).first();
    await expect(traceBtn).toBeVisible();

    // Clicking the citation/trace affordance dispatches write:trace-to-source.
    const intent = await page.evaluate(async () => {
      return await new Promise<boolean>((resolve) => {
        const to = setTimeout(() => resolve(false), 2000);
        window.addEventListener(
          "write:trace-to-source",
          () => {
            clearTimeout(to);
            resolve(true);
          },
          { once: true },
        );
        const btn = document.querySelector<HTMLButtonElement>(
          '[data-block="lego"] button, [data-block="citation"] button',
        );
        btn?.click();
      });
    });
    expect(intent).toBe(true);
  });
});
