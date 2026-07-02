import { expect, test, type Page } from "@playwright/test";

const STORYBOOK_URL = process.env.STORYBOOK_URL ?? "http://localhost:6006";
const APPSHELL_STORY = "navigation-appshell--with-project-tree";
const MIN_FLOOR_FPS = 20;
const SAMPLE_MS = 2000;

function storyUrl(id: string): string {
  return `${STORYBOOK_URL}/iframe.html?args=&id=${id}&viewMode=story`;
}

test.use({ contextOptions: { reducedMotion: "no-preference" } });

async function loadScene(page: Page) {
  await page.setViewportSize({ width: 1280, height: 900 });
  await page.goto(storyUrl(APPSHELL_STORY), { waitUntil: "domcontentloaded" });
  const root = page.locator('[data-testid="scene-root"]');
  await expect(root).toBeAttached({ timeout: 10_000 });
  await expect(root).toHaveAttribute("data-scene-frozen", "false", { timeout: 10_000 });
  await expect(page.locator('[data-testid="snow-layer"]')).toBeAttached({
    timeout: 10_000,
  });
}

test("motion-enabled procedural canvas produces distinct frames at the honest floor", async ({
  page,
}, testInfo) => {
  await loadScene(page);

  const result = await page.evaluate(async (sampleMs) => {
    const canvas = document.querySelector<HTMLCanvasElement>('[data-testid="snow-layer"]');
    if (!canvas) throw new Error("snow-layer canvas not found");
    const ctx = canvas.getContext("2d", { willReadFrequently: true });
    if (!ctx) throw new Error("snow-layer 2d context not available");

    const hashes = new Set<number>();
    let sampledFrames = 0;
    const started = performance.now();

    function hashCanvas(): number {
      const { width, height } = canvas;
      const data = ctx.getImageData(0, 0, width, height).data;
      let hash = 2166136261;
      const stride = Math.max(4, Math.floor(data.length / 4096));
      for (let i = 0; i < data.length; i += stride) {
        hash ^= data[i];
        hash = Math.imul(hash, 16777619);
      }
      return hash >>> 0;
    }

    await new Promise<void>((resolve) => {
      const tick = () => {
        sampledFrames += 1;
        hashes.add(hashCanvas());
        if (performance.now() - started >= sampleMs) {
          resolve();
          return;
        }
        requestAnimationFrame(tick);
      };
      requestAnimationFrame(tick);
    });

    const elapsedMs = performance.now() - started;
    return {
      elapsedMs,
      sampledFrames,
      distinctFrames: hashes.size,
      fps: hashes.size / (elapsedMs / 1000),
    };
  }, SAMPLE_MS);

  await testInfo.attach("scene-motion-fps.json", {
    body: JSON.stringify(result, null, 2),
    contentType: "application/json",
  });
  // eslint-disable-next-line no-console
  console.log(`scene motion distinct-frame fps: ${result.fps.toFixed(2)}`);

  expect(result.fps).toBeGreaterThanOrEqual(MIN_FLOOR_FPS);
});
