import { expect, test } from "@playwright/test";

/**
 * The hard-to-vary passkey proof.
 *
 * Unlike the Login branch tests, this starts Antiek's real FastAPI service,
 * creates a real discoverable WebAuthn credential in Chromium's virtual
 * platform authenticator, clears the session, and proves the stored public
 * key can unlock a fresh browser session. Mocking either ceremony endpoint
 * would make this test meaningless, so there are deliberately no routes.
 */
test("email bootstrap becomes a real passkey-only second unlock", async ({
  page,
  context,
}) => {
  const cdp = await context.newCDPSession(page);
  await cdp.send("WebAuthn.enable");
  await cdp.send("WebAuthn.addVirtualAuthenticator", {
    options: {
      protocol: "ctap2",
      transport: "internal",
      hasResidentKey: true,
      hasUserVerification: true,
      isUserVerified: true,
      automaticPresenceSimulation: true,
    },
  });

  const setupDestination = encodeURIComponent(
    "/login?setup=passkey&next=%2Ftrust",
  );
  await page.goto(
    `http://localhost:8000/auth/dev-login?token=playwright-passkey-bootstrap&next=${setupDestination}`,
  );

  await expect(
    page.getByRole("heading", { name: "Leave email behind." }),
  ).toBeVisible();
  await page.getByRole("button", { name: /save to this/i }).click();
  await expect(page).toHaveURL("http://localhost:5173/trust");

  // A new browser session has no Antiek cookie, but the authenticator still
  // holds its discoverable credential, exactly like the operator's next visit.
  await context.clearCookies();
  const statusRequest = page.waitForResponse((response) =>
    response.url().endsWith("/auth/passkey/status"),
  );
  await page.goto("/login?next=/trust");
  const statusResponse = await statusRequest;
  expect(statusResponse.status()).toBe(200);
  expect(await statusResponse.json()).toEqual({ available: true, count: null });
  await expect(
    page.getByRole("button", { name: /unlock with passkey/i }),
  ).toBeVisible();
  await page.getByRole("button", { name: /unlock with passkey/i }).click();
  await expect(page).toHaveURL("http://localhost:5173/trust");

  const identity = await page.evaluate(async () => {
    const response = await fetch("/auth/me", { credentials: "include" });
    return { status: response.status, body: await response.json() };
  });
  expect(identity.status).toBe(200);
  expect(identity.body.user_id).toBe("__operator__");
});
