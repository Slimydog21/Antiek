import { expect, test } from "@playwright/test";

/**
 * ANT-AUTH-DIAG SPR-05 — tier-B login surface (hermetic network mocks).
 * Matrix rows: A-TRANSPORT-FETCH, B-POLICY-ALLOWLIST-SILENT (sent UI).
 *
 * Run: npm run build && npx vite preview --port 4173 &
 *      npx playwright test --project=login-real
 */

test.describe("login magic-link surface", () => {
  test.beforeEach(async ({ page }) => {
    await page.route("**/auth/passkey/status", (route) =>
      route.fulfill({
        status: 200,
        contentType: "application/json",
        body: JSON.stringify({ available: false, count: null }),
      }),
    );
  });

  test("A-TRANSPORT-FETCH shows Cannot reach Antiek API on fetch failure", async ({
    page,
  }) => {
    await page.route("**/auth/request", (route) => route.abort("failed"));
    await page.goto("/login");
    await page.getByPlaceholder("you@example.com").fill("operator@antiek.test");
    await page.getByRole("button", { name: /continue with email/i }).click();
    await expect(page.getByText("Cannot reach Antiek API")).toBeVisible();
    await expect(page.locator("[data-auth-diagnostic]")).toHaveAttribute(
      "data-auth-diagnostic",
      "A-TRANSPORT-FETCH",
    );
  });

  test("B-POLICY-ALLOWLIST-SILENT shows the code-entry screen on 200 sent", async ({
    page,
  }) => {
    await page.route("**/auth/claim", (route) => route.fulfill({ status: 202 }));
    await page.route("**/auth/request", (route) =>
      route.fulfill({
        status: 200,
        contentType: "application/json",
        body: JSON.stringify({
          sent: true,
          attempt_id: "attempt-1234567890",
          claim_secret: "secret-1234567890",
        }),
      }),
    );
    await page.goto("/login");
    await page.getByPlaceholder("you@example.com").fill("not-on-allowlist@example.com");
    await page.getByRole("button", { name: /continue with email/i }).click();
    await expect(page.getByRole("heading", { name: "Type the code from the email." })).toBeVisible();
    await expect(page.getByLabel("4-digit code from the email")).toBeVisible();
    // The code is email-only: it must NOT be rendered from the API response.
    await expect(page.getByText("4821")).toBeHidden();
    await expect(page.getByText("or open the link in the email", { exact: false })).toBeVisible();
  });

  test("typing the emailed code unlocks", async ({ page }) => {
    await page.route("**/auth/request", (route) =>
      route.fulfill({
        status: 200,
        contentType: "application/json",
        body: JSON.stringify({
          sent: true,
          attempt_id: "attempt-1234567890",
          claim_secret: "secret-1234567890",
        }),
      }),
    );
    await page.route("**/auth/claim", (route) =>
      route.fulfill({
        status: 200,
        contentType: "application/json",
        body: JSON.stringify({ authenticated: true, setup_passkey: false, next: "/trust" }),
      }),
    );
    await page.route("**/auth/me", (route) =>
      route.fulfill({
        status: 200,
        contentType: "application/json",
        body: JSON.stringify({ user_id: "__operator__", email: "operator@antiek.test", auth_method: "antiek_session_cookie" }),
      }),
    );
    await page.goto("/login?next=/trust");
    await page.getByPlaceholder("you@example.com").fill("operator@antiek.test");
    await page.getByRole("button", { name: /continue with email/i }).click();

    const claim = page.waitForRequest((request) => {
      if (!request.url().endsWith("/auth/claim")) return false;
      try {
        return request.postDataJSON()?.code === "4821";
      } catch {
        return false;
      }
    });
    await page.getByLabel("4-digit code from the email").fill("4821");
    await page.getByRole("button", { name: "Unlock", exact: true }).click();
    const claimRequest = await claim;
    expect(claimRequest.postDataJSON()).toEqual({
      attempt_id: "attempt-1234567890",
      claim_secret: "secret-1234567890",
      code: "4821",
    });
    await expect(page).toHaveURL(/\/trust/);
  });

  test("phone approval requires the matching code and leaves a clear receipt", async ({ page }) => {
    await page.route("**/auth/approve", (route) => route.fulfill({ status: 204 }));
    await page.goto("/login?approve=attempt-1234567890&code=4821");

    await expect(page.getByRole("heading", { name: "Same four digits?" })).toBeVisible();
    await expect(page.getByLabel("Device code 4821")).toHaveText("4821");
    await page.getByRole("button", { name: /yes, open that screen/i }).click();

    await expect(page.getByText("Approved")).toBeVisible();
    await expect(page.getByRole("heading", { name: "Your other screen is opening." })).toBeVisible();
    await expect(page.getByText("You can close this page.", { exact: false })).toBeVisible();
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

  test("email is the primary unlock; passkey stays available", async ({ page }) => {
    await page.unroute("**/auth/passkey/status");
    await page.route("**/auth/passkey/status", (route) =>
      route.fulfill({
        status: 200,
        contentType: "application/json",
        body: JSON.stringify({ available: true, count: null }),
      }),
    );
    await page.goto("/login");

    // Email first — the code flow is the obvious action.
    await expect(page.getByPlaceholder("you@example.com")).toBeVisible();
    await expect(page.getByRole("button", { name: /continue with email/i })).toBeVisible();
    // Passkey remains reachable as the alternative.
    await expect(page.getByRole("button", { name: /unlock with passkey/i })).toBeVisible();
  });

  test("visual review states", async ({ page }) => {
    test.skip(!process.env.LOGIN_VISUAL, "Operator-only visual review harness");
    await page.route("**/auth/claim", (route) => route.fulfill({ status: 202 }));
    await page.route("**/auth/request", (route) =>
      route.fulfill({
        status: 200,
        contentType: "application/json",
        body: JSON.stringify({
          sent: true,
          attempt_id: "attempt-1234567890",
          claim_secret: "secret-1234567890",
        }),
      }),
    );
    await page.goto("/login");
    await page.screenshot({ path: "test-results/login-first-unlock.png", fullPage: true });

    await page.getByPlaceholder("you@example.com").fill("operator@antiek.test");
    await page.getByRole("button", { name: /continue with email/i }).click();
    await expect(page.getByLabel("4-digit code from the email")).toBeVisible();
    await page.screenshot({ path: "test-results/login-waiting.png", fullPage: true });

    await page.setViewportSize({ width: 390, height: 844 });
    await page.goto("/login?approve=attempt-1234567890&code=4821");
    await page.screenshot({ path: "test-results/login-phone-approval.png", fullPage: true });
  });
});
