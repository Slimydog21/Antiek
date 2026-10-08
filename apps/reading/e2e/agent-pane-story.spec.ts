import { expect, test } from "@playwright/test";

const cases = [
  { story: "empty-day", theme: "light", answered: false },
  { story: "empty-night", theme: "dark", answered: false },
  { story: "answered-day", theme: "light", answered: true },
  { story: "answered-night", theme: "dark", answered: true },
] as const;

// These are the existing scripted Storybook fixtures, not provider or book proof.
for (const { story, theme, answered } of cases) {
  test(`AgentPane ${story} renders its actual content without a nested Router`, async ({ page }) => {
    const errors: string[] = [];
    page.on("pageerror", (error) => errors.push(error.message));
    await page.goto(`/iframe.html?id=workspace-agentpane--${story}&viewMode=story&globals=theme:${theme}`);

    const pane = page.getByRole("region", { name: "Agent", exact: true });
    await expect(pane).toBeVisible();
    await expect(pane.getByRole("textbox", { name: "Ask the agent" })).toBeVisible();
    await expect(pane.locator("[data-scope-badge]")).toHaveText("project finches");
    await expect(page.locator("html")).toHaveAttribute("data-theme", theme);
    await expect(page.locator('[data-pane="right"]')).toHaveCSS("width", "320px");

    if (answered) {
      await expect(pane.locator("[data-agent-turn]")).toHaveCount(1);
      await expect(pane.getByText("Read the drought chapter next; the 1977 cohort is where the beak-depth claim is tested.", { exact: true })).toBeVisible();
      await expect(pane.locator("[data-turn-status]")).toContainText("simulated stream: the reply arrives whole");
      await expect(pane.locator("[data-agent-empty-state]")).toHaveCount(0);
    } else {
      await expect(pane.locator("[data-agent-turn]")).toHaveCount(0);
      await expect(pane.getByRole("button", { name: "What should I read next in this project?", exact: true })).toBeVisible();
      await expect(pane.getByRole("button", { name: "What is missing from this project's evidence?", exact: true })).toBeVisible();
      await expect(pane.getByRole("button", { name: "Where is this project's argument weakest?", exact: true })).toBeVisible();
    }
    await expect(page.getByText(/You cannot render a <Router> inside another <Router>/)).toHaveCount(0);
    expect(errors).toEqual([]);
  });
}
