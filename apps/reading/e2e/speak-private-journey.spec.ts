/**
 * Speak Private↔Public spine — the PRIVATE-lane journey e2e (SPR-02 M6).
 *
 * HONEST SCOPE. The private-lane consent + answer LOGIC is covered
 * server-side (tests/test_speak_api.py — the token-gated resolve →
 * scoped consent → answer → voice flow) and in the component tests
 * (SpeakInvite.test.tsx: publish-off-by-default, the affirmative
 * publish opt-in, the record-only answer path; Speak.test.tsx: the
 * private console). The private-lane SURFACES — the Invites
 * invitation panel and the Speak console — are exercised here against
 * the only thing the browser harness can drive without a backend:
 * Storybook. The ONE thing still missing is a live browser PAGE that
 * walks the whole person → invite → consent → answer → voice journey
 * end-to-end; the REST surface it would call exists
 * (interfaces/research/api/speak_routes.py).
 *
 * So this spec does two honest things:
 *   1. smoke-tests the private-lane Speak surfaces that DO exist — the
 *      private-project Invites story (the supply side: an invitee
 *      lifecycle, with the SPR-02-humanized status words) and the
 *      invitee-landing story — so the e2e harness exercises real
 *      private-lane Speak UI;
 *   2. marks the full live-server journey test.skip with the reason
 *      (Storybook has no live /speak server), rather than faking a
 *      green check.
 *
 * Run against Storybook with `npm run e2e` (STORYBOOK_URL).
 */
import { expect, test, type Page } from "@playwright/test";

const STORYBOOK_URL = process.env.STORYBOOK_URL ?? "http://localhost:6006";

async function loadStory(page: Page, id: string): Promise<void> {
  await page.goto(`${STORYBOOK_URL}/iframe.html?id=${id}&viewMode=story`);
  await page.waitForLoadState("networkidle");
}

test.describe("Speak — private-lane journey", () => {
  test("the private project's invitation surface lists invitees with humanized status", async ({
    page,
  }) => {
    await loadStory(page, "workstation-speak-invites--private-project");
    // A private project: invites capture record consent (publish is never the
    // default), and each invitee shows their lifecycle status as a human word.
    await expect(page.getByText(/invitations/i)).toBeVisible();
    await expect(page.getByText(/private/i)).toBeVisible();
    await expect(page.getByText(/uncle\.fawzi@example\.com/i)).toBeVisible();
    // SPR-02 humanizes the lifecycle word: a "completed" invite reads "Shared".
    await expect(page.getByText(/shared/i)).toBeVisible();
  });

  test("the invitee landing is an honest dead-stop without a valid token", async ({
    page,
  }) => {
    // The friends-and-family page is unauthenticated + token-gated; the URL
    // token is the credential. With no token in Storybook's router it shows
    // its honest invalid/expired-link state — never a broken page.
    await loadStory(page, "workstation-speak-invitee-landing--invalid-link");
    await expect(page.getByText(/invalid or has expired/i)).toBeVisible();
  });

  test.skip(
    "private journey: name a person → invite a friend → token consent → answer → voice arrives (Storybook has no live /speak server)",
    async () => {
      // Deferred: this walks the whole private-lane journey through the live
      // browser PAGE — name a person, invite a friend by link, the friend
      // lands on the token-gated page, gives scoped consent (publish OFF by
      // default), answers, and the voice arrives back in the operator console.
      // It requires the Speak REST endpoints + a server Storybook cannot host
      // (Storybook has no live /speak server). The orchestration is proven in
      // tests/test_speak_api.py; the surfaces are smoke-tested above.
    },
  );
});
