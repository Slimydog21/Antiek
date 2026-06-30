import { execFileSync } from "node:child_process";
import { promises as fs } from "node:fs";
import path from "node:path";

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
const AUTH_SECRET =
  process.env.ANTIEK_AUTH_SECRET
  ?? "antiek-login-e2e-not-a-production-secret-xxxxxxxxxxxxxxxxxxxx";
const REPO_ROOT = path.resolve(process.cwd(), "../..");

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

function mintExpiredToken(): string {
  return execFileSync(
    "uv",
    [
      "run",
      "--extra",
      "dev",
      "--extra",
      "urls",
      "--extra",
      "extraction",
      "python",
      "-c",
      [
        "import time",
        "import os",
        "import substrate.auth.magic_link as m",
        "now=time.time",
        "m.time.time=lambda: int(now()) - 3600",
        "print(m.mint_magic_link_token(os.environ['ANTIEK_LOGIN_E2E_EMAIL']))",
      ].join(";"),
    ],
    {
      cwd: REPO_ROOT,
      env: {
        ...process.env,
        ANTIEK_AUTH_SECRET: AUTH_SECRET,
        ANTIEK_LOGIN_E2E_EMAIL: OPERATOR_EMAIL,
      },
      encoding: "utf-8",
    },
  ).trim();
}

test.beforeEach(async () => {
  await fs.rm(OUTBOX, { force: true });
});

test.afterEach(async () => {
  await fs.rm(OUTBOX, { force: true });
});

test("MockEmailProvider link completes callback, cookie, and /auth/me", async ({
  page,
}) => {
  await page.goto("/login");
  await page.getByPlaceholder("you@example.com").fill(OPERATOR_EMAIL);
  await page.getByRole("button", { name: /send sign-in link/i }).click();
  await expect(page.getByText("Check your email")).toBeVisible();

  const magicLink = await waitForMagicLink();
  const callback = execFileSync(
    "curl",
    ["--max-time", "10", "-sS", "-i", "--max-redirs", "0", magicLink],
    { encoding: "utf-8" },
  );
  expect(callback).toContain("HTTP/1.1 302");
  expect(callback).toContain("location: http://127.0.0.1:4173/");
  const setCookie = callback
    .split("\n")
    .find((line) => line.toLowerCase().startsWith("set-cookie:"));
  expect(setCookie).toContain("ANTIEK_SESSION=");
  const cookieHeader = setCookie
    ?.replace(/^set-cookie:\s*/i, "")
    .split(";")[0] ?? "";
  const body = execFileSync(
    "curl",
    ["--max-time", "5", "-sS", "-H", `Cookie: ${cookieHeader}`, `${API_BASE}/auth/me`],
    { encoding: "utf-8" },
  );
  const identity = { status: 200, body: JSON.parse(body) };

  expect(identity.status).toBe(200);
  expect(identity.body).toMatchObject({
    email: OPERATOR_EMAIL,
    auth_method: "antiek_session_cookie",
  });
});

test("expired callback redirects to login with expired-link copy", async ({
  page,
}) => {
  const token = mintExpiredToken();
  await page.goto(`${API_BASE}/auth/callback?token=${token}&next=/`);

  await expect(page).toHaveURL(/\/login/);
  await expect(page.getByText("This sign-in link expired.")).toBeVisible();
  await expect(page.locator("[data-auth-diagnostic]")).toHaveAttribute(
    "data-auth-diagnostic",
    "B-POLICY-CALLBACK-EXPIRED",
  );
});
