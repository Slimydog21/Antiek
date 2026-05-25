/**
 * Speak SPR-08/SPR-09 e2e — project → biography draft.
 *
 * HONEST SCOPE. The biography authoring + publishing LOGIC is fully
 * covered server-side (tests/test_biography_authoring.py,
 * tests/test_speak_publish.py), and the full operator JOURNEY — project
 * → invite → consent → answer → claim → corroborate → draft → publish →
 * book-order — now runs end-to-end through the real wired app in
 * tests/test_speak_api.py (FastAPI TestClient over the /speak router).
 * The ONLY thing still missing is the browser UI PAGE that walks that
 * journey; the REST surface it would call exists
 * (interfaces/research/api/speak_routes.py).
 *
 * So this spec does two honest things:
 *   1. smoke-tests the Speak surfaces that DO exist — the Invites +
 *      transcript-correction stories — so the e2e harness exercises
 *      real Speak UI;
 *   2. marks the full browser journey test.skip with the reason (no UI
 *      page yet), rather than faking a green check.
 *
 * Run against Storybook with `npm run e2e` (STORYBOOK_URL).
 */
import { expect, test, type Page } from "@playwright/test";

const STORYBOOK_URL = process.env.STORYBOOK_URL ?? "http://localhost:6006";

async function loadStory(page: Page, id: string): Promise<void> {
  await page.goto(`${STORYBOOK_URL}/iframe.html?id=${id}&viewMode=story`);
  await page.waitForLoadState("networkidle");
}

test.describe("Speak — biography flow", () => {
  test("invite surface renders the invitee lifecycle", async ({ page }) => {
    await loadStory(page, "workstation-speak-invites--private-project");
    // The invite-management surface lists invitees with their status and
    // copyable links (the supply side of the biography).
    await expect(page.getByText(/invitations/i)).toBeVisible();
    await expect(page.getByText(/uncle\.fawzi@example\.com/i)).toBeVisible();
    await expect(page.getByText(/completed/i)).toBeVisible();
  });

  test("transcript correction surface renders a pending turn", async ({ page }) => {
    await loadStory(page, "workstation-interview-transcript--pending-correction");
    // A transcribed-but-not-yet-distilled answer is editable before it is
    // distilled (ASR mishears names/places/dates).
    await expect(page.getByText(/pending correction/i)).toBeVisible();
    await expect(page.getByRole("button", { name: /correct/i })).toBeVisible();
  });

  test.skip(
    "project → corroborated biography draft → publish (needs API wiring)",
    async () => {
      // Deferred: requires the Speak authoring/publishing REST endpoints
      // + UI. The orchestration is proven in
      // tests/test_biography_authoring.py and tests/test_speak_publish.py.
    },
  );
});
