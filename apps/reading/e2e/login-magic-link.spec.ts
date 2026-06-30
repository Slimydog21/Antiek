import { promises as fs } from "node:fs";

import { expect, test } from "@playwright/test";

/**
 * ANT-AUTH-DIAG SPR-05 — tier-B login e2e.
 *
 * Hermetic contract: local FastAPI + MockEmailProvider outbox file, local Vite
 * preview, no real inbox and no production antiek.ai dependency.
 *
 * Run: LOGIN_E2E=1 npx playwright test --project=login-real
 */

const API_BASE = process.env.LOGIN_API_URL ?? "http://127.0.0.1:8000";
const OUTBOX =
  process.env.ANTIEK_MOCK_EMAIL_OUTBOX_PATH ?? "/tmp/antiek-login-e2e-outbox.jsonl";
const OPERATOR_EMAIL = "test@antiek.test";

test.describe.configure({ mode: "serial" });
test.setTimeout(60_000);

type OutboxRow = {
  to: string;
  subject: string;
  text_body: string;
};

async function readOutboxRows(): Promise<OutboxRow[]> {
  try {
    const raw = await fs.readFile(OUTBOX, "utf-8");
    return raw
      .trim()
      .split("\n")
      .filter(Boolean)
      .map((line) => JSON.parse(line) as OutboxRow);
  } catch (error) {
    if ((error as NodeJS.ErrnoException).code === "ENOENT") return [];
    throw error;
  }
}

async function waitForMagicLink(): Promise<string> {
  const deadline = Date.now() + 5_000;
  while (Date.now() < deadline) {
    const rows = await readOutboxRows();
    const latest = rows.findLast((row) => row.to === OPERATOR_EMAIL);
    const match = latest?.text_body.match(/https?:\/\/\S+/);
    if (match) return match[0];
    await new Promise((resolve) => setTimeout(resolve, 100));
  }
  throw new Error(`No magic link written to ${OUTBOX}`);
}

test.beforeEach(async () => {
  await fs.rm(OUTBOX, { force: true });
});

test.afterEach(async () => {
  await fs.rm(OUTBOX, { force: true });
});

test("MockEmailProvider link completes browser callback, cookie, and /auth/me", async ({
  page,
}) => {
  await page.goto("/login");
  await page.getByPlaceholder("you@example.com").fill(OPERATOR_EMAIL);
  await page.getByRole("button", { name: /send sign-in link/i }).click();
  await expect(page.getByText("Check your email")).toBeVisible();

  const magicLink = await waitForMagicLink();
  const authMeResponse = page.waitForResponse(
    (response) => response.url() === `${API_BASE}/auth/me` && response.status() === 200,
  );

  await page.goto(magicLink);
  await expect(page).toHaveURL(/^http:\/\/127\.0\.0\.1:4173\/(?:\?.*)?$/);
  await expect(page.getByText("Sign in")).toHaveCount(0);

  const cookies = await page.context().cookies(API_BASE);
  expect(cookies.some((cookie) => cookie.name === "ANTIEK_SESSION")).toBe(true);

  const identity = await authMeResponse;
  expect(identity.ok()).toBe(true);
  await expect(identity.json()).resolves.toMatchObject({
    email: OPERATOR_EMAIL,
    auth_method: "antiek_session_cookie",
  });
});

test("expired callback error renders expired-link copy", async ({
  page,
}) => {
  // Backend expiry + callback redirect semantics are pinned in
  // tests/test_magic_link_auth.py. This browser e2e owns the Login surface copy
  // after the API redirects back with the closed callback error code.
  await page.goto("/login?error=magic_link_expired&next=/");

  await expect(page).toHaveURL(/\/login/);
  await expect(page.getByText("This sign-in link expired.")).toBeVisible();
  await expect(page.locator("[data-auth-diagnostic]")).toHaveAttribute(
    "data-auth-diagnostic",
    "B-POLICY-CALLBACK-EXPIRED",
  );
});
