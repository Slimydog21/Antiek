import { expect, test, type Page, type Route } from "@playwright/test";
import AxeBuilder from "@axe-core/playwright";

import { loginAndGotoApp } from "./_ams/auth";

const authority = "a".repeat(64);

function snapshot(state: "closed_unresolved" | "closed_reconciled") {
  const unresolved = state === "closed_unresolved";
  return {
    currency: "USD",
    approval_revision: 3,
    authority_digest: authority,
    ceiling_cents: 500,
    authorized_spent_cents: 125,
    observed_provider_spend_cents: 140,
    held_cents: unresolved ? 200 : 0,
    available_cents: unresolved ? 175 : 375,
    run_state: state,
    ceiling_breached: false,
    unknown_outcome_count: unresolved ? 1 : 0,
    blocked_stages: ["synthesizer", "knowledge_extractor"],
  };
}

async function json(route: Route, body: unknown): Promise<void> {
  await route.fulfill({
    status: 200,
    contentType: "application/json",
    body: JSON.stringify(body),
  });
}

async function installSession(page: Page): Promise<void> {
  await page.route("**/research/sessions/session-hard/spend/reconcile", (route) =>
    json(route, {
      hard_ceiling: snapshot("closed_unresolved"),
      provider_checks_started: 0,
      message: "Unresolved provider outcomes remain held until an adapter supplies evidence.",
    }),
  );
  await page.route("**/research/sessions/session-hard", (route) =>
    json(route, {
      session_id: "session-hard",
      live: false,
      all_terminal: true,
      researches: [
        { investigation_id: "inv-1", sub_question: "Which evidence changed?", state: "done" },
      ],
      hard_ceiling: snapshot("closed_unresolved"),
    }),
  );
}

test.describe("research hard ceiling operator evidence", () => {
  for (const viewport of [
    { name: "desktop", width: 1280, height: 800 },
    { name: "mobile", width: 390, height: 844 },
  ]) {
    test(`${viewport.name}: balances and unresolved recovery remain truthful`, async ({ page }) => {
      await page.setViewportSize({ width: viewport.width, height: viewport.height });
      await installSession(page);
      await loginAndGotoApp(page, "/deep-research/session-hard");

      const evidence = page.getByRole("region", { name: "Hard spend ceiling evidence" });
      await expect(evidence).toBeVisible();
      await expect(evidence).toContainText("closed unresolved");
      await expect(evidence).toContainText("$5.00");
      await expect(evidence).toContainText("$1.25");
      await expect(evidence).toContainText("$1.40");
      await expect(evidence).toContainText("$2.00");
      await expect(evidence).toContainText("$1.75");
      await expect(evidence).toContainText("will not be released without provider evidence");
      await expect(page.getByRole("button", { name: /retry/i })).toHaveCount(0);

      await page.getByRole("button", { name: "Check provider status" }).click();
      await expect(evidence).toContainText("closed unresolved");
      await expect(evidence).toContainText("$2.00");
      await expect(page.getByRole("button", { name: "Check provider status" })).toBeVisible();

      const overflow = await page.evaluate(() => document.documentElement.scrollWidth - window.innerWidth);
      expect(overflow).toBeLessThanOrEqual(1);
      const accessibility = await new AxeBuilder({ page })
        .include('[aria-label="Hard spend ceiling evidence"]')
        .analyze();
      expect(
        accessibility.violations.filter((violation) =>
          violation.impact === "serious" || violation.impact === "critical"),
      ).toEqual([]);
    });
  }
});
