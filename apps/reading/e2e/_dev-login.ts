import { expect, type Page } from "@playwright/test";

/**
 * _dev-login.ts — the one dev-login bootstrap for the real-backend e2e suites.
 *
 * A-20: the credential no longer rides a URL. The old bootstrap was a GET
 * with the token in its query string, which put the operator credential into
 * every access log, proxy log and browser history entry it passed through.
 * The backend now serves a token-free form at
 * `GET /auth/dev-login?next=<relative>` and authenticates only a native
 * `POST /auth/dev-login` whose `application/x-www-form-urlencoded` body is
 * `token=…&next=…`. A GET carrying `token` is a fixed 404 and never sets a
 * cookie, so no caller may put the token in a URL again.
 *
 * The credential is the suite's disposable fixture token (the value its
 * playwright.config.ts webServer already exports to the API), unless
 * `ANTIEK_E2E_DEV_LOGIN_TOKEN` overrides it for a run against a stack with a
 * generated token. The override deliberately does NOT reuse
 * `ANTIEK_DEV_LOGIN_TOKEN`: an operator shell that exports the real one would
 * otherwise submit it to a throwaway test server. The value is never logged;
 * Playwright traces do record `fill` values, so run an override with
 * `--trace off`.
 */

export const DEV_LOGIN_TOKEN_ENV = "ANTIEK_E2E_DEV_LOGIN_TOKEN";
export const SESSION_COOKIE = "ANTIEK_SESSION";

const FORM = 'form[method="post"][action="/auth/dev-login"]';

export interface DevLoginOptions {
  /** API origin that serves the form and mints the cookie, e.g. http://localhost:8011. */
  apiBase: string;
  /** Relative path (may carry its own query) the API redirects to after sign-in. */
  next: string;
  /** The suite's disposable token, used when the env override is unset. */
  fixtureToken: string;
}

/** Sign in through the token-free form and land on `next` with a session cookie. */
export async function devLogin(page: Page, options: DevLoginOptions): Promise<void> {
  const { apiBase, next, fixtureToken } = options;
  const token = process.env[DEV_LOGIN_TOKEN_ENV] || fixtureToken;

  await page.goto(`${apiBase}/auth/dev-login?next=${encodeURIComponent(next)}`);
  const field = page.locator(`${FORM} input[type="password"][name="token"]`);
  await expect(field).toBeVisible();
  await field.fill(token);

  const submitted = page.waitForRequest(
    (request) =>
      request.method() === "POST" && new URL(request.url()).pathname === "/auth/dev-login",
  );
  await page.locator(`${FORM} [type="submit"]`).click();
  const post = await submitted;
  expect(new URL(post.url()).search, "dev-login POST must carry no query string").toBe("");
  expect(post.headers()["content-type"]).toContain("application/x-www-form-urlencoded");
  // A refusal is a fixed 404 whatever the cause; fail here rather than time out below.
  const response = await post.response();
  expect(response?.status(), "dev-login POST must redirect, not refuse").toBe(302);

  await page.waitForURL((url) => url.pathname + url.search === next);
  const cookieNames = (await page.context().cookies(apiBase)).map((cookie) => cookie.name);
  expect(cookieNames, "dev-login must set the session cookie").toContain(SESSION_COOKIE);
}
