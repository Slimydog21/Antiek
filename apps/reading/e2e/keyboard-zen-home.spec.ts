/**
 * keyboard-zen-home.spec.ts — journey J3a (FFX-KPA SPR-03 M8).
 *
 * The zen home on the REAL built app (vite preview, the ams-real project),
 * driven from the keyboard: no mouse click anywhere. The file chooser is
 * opened with Enter on the focused Attach button; the voice Stop button is
 * reached with locator.focus() + Enter.
 *
 *   1. type → mod+Enter → lands in /inv/:id
 *   2. voice: record → stop → POST /voice/transcribe (mocked) → transcript in the box
 *   3. a .md through the keyboard-opened file chooser → /voice-notes/ingest → /inv/:id
 *   4. a .png dropped with the intake contract off → refusal copy, zero uploads
 *
 * The API is mocked at the network layer (installAuthMock + page.route); the
 * flag is turned on with an init script, exactly as an operator would in
 * devtools. Nothing here touches a real backend.
 *
 *   npm run build && npx playwright test e2e/keyboard-zen-home.spec.ts --project=ams-real
 */
import { expect, test, type Page, type Request, type Route } from "@playwright/test";

import { installAuthMock } from "./_ams/auth";

const REFUSED = "Images and documents arrive once the intake lands; paste the text for now.";

test.use({ video: "on" });

async function json(route: Route, status: number, body: unknown) {
  await route.fulfill({ status, contentType: "application/json", body: JSON.stringify(body) });
}

/** Shell writes that are not intake: the AppShell's ad border reports fills
 *  (AdBorderMount). Excluded by name so that any OTHER write, including an
 *  upload route nobody expected, still fails the "zero uploads" checks. */
const SHELL_WRITES = new Set(["/api/ad/fills"]);

/** Mocks + a log of every non-GET request the page makes. */
async function bootZen(page: Page): Promise<Request[]> {
  const writes: Request[] = [];
  page.on("request", (req) => {
    if (req.method() === "GET" || req.method() === "OPTIONS") return;
    if (SHELL_WRITES.has(new URL(req.url()).pathname)) return;
    writes.push(req);
  });
  await page.addInitScript(() => {
    window.localStorage.setItem("antiek.nav.zenhome", "on");
    // A real MediaStream from an oscillator so MediaRecorder runs headless.
    const ctx = new AudioContext();
    navigator.mediaDevices.getUserMedia = async () => {
      const osc = ctx.createOscillator();
      const dest = ctx.createMediaStreamDestination();
      osc.connect(dest);
      osc.start();
      return dest.stream;
    };
  });
  await installAuthMock(page);
  await page.route("**/investigations", (route) =>
    route.request().method() === "POST"
      ? json(route, 200, { investigation_id: "inv-j3a", status: "started", start_event_id: "e0" })
      : route.fallback(),
  );
  await page.route("**/voice/transcribe", (route) => json(route, 200, { transcript: "tidal locking" }));
  await page.route("**/voice-notes/ingest", (route) => json(route, 200, { document_id: "d-md", title: "notes.md" }));
  await page.goto("/zen", { waitUntil: "domcontentloaded" });
  await expect(box(page)).toBeFocused({ timeout: 20_000 });
  return writes;
}

const box = (page: Page) => page.getByRole("textbox", { name: "What are you working on?" });
const path = (req: Request) => new URL(req.url()).pathname;

test.describe("J3a — zen home from the keyboard", () => {
  test("type → mod+Enter → lands in /inv/:id", async ({ page }) => {
    const writes = await bootZen(page);
    await page.keyboard.type("Why does the moon keep one face to us?");
    await page.keyboard.press("Control+Enter");
    await expect(page).toHaveURL(/\/inv\/inv-j3a/, { timeout: 10_000 });
    const start = writes.find((r) => path(r) === "/investigations");
    expect(start?.postDataJSON()).toMatchObject({ question: "Why does the moon keep one face to us?" });
  });

  test("voice → transcript lands in the box (transcribe mocked)", async ({ page }) => {
    const writes = await bootZen(page);
    await page.keyboard.type("explain");
    await page.keyboard.press("Tab"); // attach
    await page.keyboard.press("Tab"); // voice
    await expect(page.getByRole("button", { name: "Voice" })).toBeFocused();
    await page.keyboard.press("Enter");
    const stop = page.getByRole("button", { name: "■ Stop" });
    await expect(stop).toBeVisible({ timeout: 10_000 });
    await page.waitForTimeout(700); // past the 500 ms floor so the take has audio
    await stop.focus();
    await page.keyboard.press("Enter");
    await expect(box(page)).toHaveValue("explain tidal locking", { timeout: 10_000 });
    await expect(box(page)).toBeFocused();
    expect(writes.map(path)).toEqual(["/voice/transcribe"]);
  });

  test("a .md through the keyboard-opened file chooser starts a project", async ({ page }) => {
    const writes = await bootZen(page);
    await page.keyboard.press("Tab");
    await expect(page.getByRole("button", { name: "Attach a file" })).toBeFocused();
    const chooser = page.waitForEvent("filechooser");
    await page.keyboard.press("Enter");
    await (await chooser).setFiles({
      name: "notes.md",
      mimeType: "text/markdown",
      buffer: Buffer.from("# Tides\nThe moon raises two bulges."),
    });
    await expect(page.getByText("notes.md", { exact: true })).toBeVisible();
    expect(writes).toHaveLength(0); // staged, not sent
    await box(page).focus();
    await page.keyboard.press("Control+Enter");
    await expect(page).toHaveURL(/\/inv\/inv-j3a/, { timeout: 10_000 });
    expect(writes.map(path)).toEqual(["/voice-notes/ingest", "/investigations"]);
    expect(writes[0].postDataJSON()).toMatchObject({ transcript: "# Tides\nThe moon raises two bulges.", title: "notes.md" });
  });

  test("a dropped .png is refused with the intake copy and never uploaded", async ({ page }) => {
    const writes = await bootZen(page);
    const dt = await page.evaluateHandle(() => {
      const d = new DataTransfer();
      d.items.add(new File([new Uint8Array([0x89, 0x50, 0x4e, 0x47])], "photo.png", { type: "image/png" }));
      return d;
    });
    await box(page).dispatchEvent("dragenter", { dataTransfer: dt });
    await box(page).dispatchEvent("drop", { dataTransfer: dt });
    await expect(page.getByText(REFUSED)).toBeVisible();
    await expect(page.getByText("Not attached: photo.png.")).toBeVisible();
    await page.waitForTimeout(500);
    expect(writes).toHaveLength(0);
  });
});
