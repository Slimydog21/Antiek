import { expect, test } from "@playwright/test";

/**
 * ANT-AUTH-DIAG SPR-05 — tier-B login surface (hermetic network mocks).
 * Matrix rows: A-TRANSPORT-FETCH, B-POLICY-ALLOWLIST-SILENT (sent UI).
 *
 * Run: npm run build && npx vite preview --port 4173 &
 *      npx playwright test --project=login-real
 */

test.describe("login magic-link surface", () => {
  test("A-TRANSPORT-FETCH shows Cannot reach Antiek API on fetch failure", async ({
    page,
  }) => {
    await page.route("**/auth/request", (route) => route.abort("failed"));
    await page.goto("/login");
    await page.getByPlaceholder("you@example.com").fill("operator@antiek.test");
    await page.getByRole("button", { name: /send sign-in link/i }).click();
    await expect(page.getByText("Cannot reach Antiek API")).toBeVisible();
    await expect(page.locator("[data-auth-diagnostic]")).toHaveAttribute(
      "data-auth-diagnostic",
      "A-TRANSPORT-FETCH",
    );
  });

  test("B-POLICY-ALLOWLIST-SILENT shows Check your email on 200 sent", async ({
    page,
  }) => {
    await page.route("**/auth/request", (route) =>
      route.fulfill({
        status: 200,
        contentType: "application/json",
        body: JSON.stringify({ sent: true }),
      }),
    );
    await page.goto("/login");
    await page.getByPlaceholder("you@example.com").fill("not-on-allowlist@example.com");
    await page.getByRole("button", { name: /send sign-in link/i }).click();
    await expect(page.getByText("Check your email")).toBeVisible();
  });

  test("B-POLICY-CALLBACK-INVALID shows message from ?error= param", async ({
    page,
  }) => {
    await page.goto("/login?error=magic_link_invalid");
    await expect(page.getByText("This sign-in link is not valid")).toBeVisible();
    await expect(page.locator("[data-auth-diagnostic]")).toHaveAttribute(
      "data-auth-diagnostic",
      "B-POLICY-CALLBACK-INVALID",
    );
  });
});