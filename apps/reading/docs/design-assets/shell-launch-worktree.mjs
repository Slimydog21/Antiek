/**
 * Honest authenticated shell-launch harness for branding AC.
 *
 * Gate: nonForceClickWorked := parent [data-testid=scene-hotspots]
 *       data-last-click === "peak-left" AFTER a real mouse.click.
 * Never treats static data-hotspot-id as click activation.
 */
import { chromium } from "/Users/slimydog/Antiek/worktrees/goal-twin-autoload-session-alpha/apps/reading/node_modules/playwright/index.mjs";
import fs from "fs";
import path from "path";

const SCRATCH = process.env.SCRATCH;
const BASE = process.env.SHELL_BASE || "http://127.0.0.1:5212";

if (!SCRATCH) {
  console.error("SCRATCH env required");
  process.exit(2);
}

// Unexpected = pageerror OR non-network console errors. Resource 500s from
// unmocked API side-fetches are expected when only auth is stubbed.
function isUnexpected(e) {
  if (/favicon|Download the React DevTools/i.test(e)) return false;
  if (/Failed to load resource/i.test(e)) return false;
  if (/net::ERR_/i.test(e)) return false;
  if (/console:Failed to load resource/i.test(e)) return false;
  return true;
}

async function installApiStubs(page) {
  // IMPORTANT: never use loose globs like **/krea/** — that steals Vite
  // source modules under /src/krea/*.ts and returns JSON, leaving #root empty.
  // Only intercept fetch-style API paths (no file extension).
  const isApiPath = (url) => {
    try {
      const u = new URL(url);
      const p = u.pathname;
      // Vite/dev assets always have an extension or /@ /src /node_modules
      if (
        p.startsWith("/src/") ||
        p.startsWith("/@") ||
        p.startsWith("/node_modules") ||
        p.includes(".")
      )
        return false;
      return true;
    } catch {
      return false;
    }
  };

  await page.route((url) => {
    const s = url.toString();
    if (!isApiPath(s)) return false;
    const p = new URL(s).pathname;
    return p === "/auth/me" || p.endsWith("/auth/me");
  }, async (route) => {
    await route.fulfill({
      status: 200,
      contentType: "application/json",
      body: JSON.stringify({
        user_id: "verify-user",
        email: "verify@antiek.local",
        auth_method: "mock",
      }),
    });
  });

  await page.route((url) => {
    const s = url.toString();
    if (!isApiPath(s)) return false;
    const p = new URL(s).pathname;
    return p === "/auth/logout" || p.endsWith("/auth/logout");
  }, async (route) => {
    await route.fulfill({ status: 204, body: "" });
  });

  await page.route((url) => {
    const s = url.toString();
    if (!isApiPath(s)) return false;
    const p = new URL(s).pathname;
    return p === "/auth/request" || p.endsWith("/auth/request");
  }, async (route) => {
    await route.fulfill({
      status: 200,
      contentType: "application/json",
      body: JSON.stringify({ sent: true }),
    });
  });

  // KEY-FREE scene path — API only, not /src/krea/*
  // Status shape must include failures:[] so SceneStatusBadge.sceneStatusReason
  // does not crash on status.failures.at(-1) (React root wipe → no shell).
  await page.route((url) => {
    const s = url.toString();
    if (!isApiPath(s)) return false;
    const p = new URL(s).pathname;
    return p === "/krea/status" || p.endsWith("/krea/status");
  }, async (route) => {
    await route.fulfill({
      status: 200,
      contentType: "application/json",
      body: JSON.stringify({
        enabled: false,
        key_present: false,
        kill_switch: false,
        gate_verdict: "no_key",
        reasons: ["no_key"],
        budget: { spent_today: 0, cap: 0, remaining: 0 },
        rate_window: { occupancy: 0, max: 0, window_s: 0 },
        cache: { entries: 0, max_entries: 0 },
        last_success_at: null,
        failure_counts: {},
        failures: [],
      }),
    });
  });

  await page.route((url) => {
    const s = url.toString();
    if (!isApiPath(s)) return false;
    const p = new URL(s).pathname;
    return p === "/krea/scene" || p.startsWith("/krea/scene");
  }, async (route) => {
    // 503 typed disabled signal — procedural floor remains authoritative.
    await route.fulfill({
      status: 503,
      contentType: "application/json",
      body: JSON.stringify({ disabled: true, reason: "no_key" }),
    });
  });
}

async function runPass(page, pass) {
  const pageErrors = [];
  const consoleErrors = [];
  page.on("pageerror", (e) => pageErrors.push(String(e.message || e)));
  page.on("console", (msg) => {
    if (msg.type() === "error") consoleErrors.push(`console:${msg.text()}`);
  });

  await installApiStubs(page);
  await page.setViewportSize({ width: 1440, height: 900 });
  // domcontentloaded — not networkidle: Vite HMR keeps a WebSocket open so
  // networkidle never settles in dev.
  await page.goto(BASE + "/", { waitUntil: "domcontentloaded", timeout: 60000 });
  await page.waitForFunction(() => {
    const root = document.getElementById("root");
    return !!root && root.childElementCount > 0;
  }, { timeout: 20000 });
  // Auth settle: shell may mount a tick after /auth/me fulfills.
  await page.waitForSelector("[data-akb-shell-frame]", {
    state: "attached",
    timeout: 60000,
  });
  // Penguin may sit near a viewport edge; attached (not visible) is the
  // honest presence gate — visibility can flap under reduced-layout races.
  await page.waitForSelector(
    '[data-testid="penguin-mascot"], [data-werner-emote]',
    { state: "attached", timeout: 30000 },
  );
  await page.waitForSelector('[data-testid="scene-hotspots"]', {
    state: "attached",
    timeout: 15000,
  });
  await page.waitForTimeout(1200);

  const bodyLen = await page.evaluate(
    () => document.body?.innerText?.length ?? 0,
  );
  const penguinCount = await page
    .locator('[data-testid="penguin-mascot"]')
    .count();
  const shellFrame =
    (await page.locator("[data-akb-shell-frame]").count()) > 0;
  const painted = bodyLen > 200 && shellFrame;

  const hotspot = page.getByTestId("scene-hotspot-peak-left");
  await hotspot.waitFor({ state: "visible", timeout: 15000 });
  const box = await hotspot.boundingBox();
  if (!box) throw new Error("peak-left no bounding box");
  const cx = box.x + box.width / 2;
  const cy = box.y + box.height / 2;

  const lastClickBefore = await page.evaluate(() => {
    const layer = document.querySelector('[data-testid="scene-hotspots"]');
    return layer?.getAttribute("data-last-click") ?? "";
  });

  const edgeHit = await page.evaluate(
    ({ x, y }) => {
      const el = document.elementFromPoint(x, y);
      if (!el) return null;
      const btn = el.closest?.('[data-testid^="scene-hotspot-"]') || el;
      return {
        tag: btn.tagName,
        testid: btn.getAttribute("data-testid"),
        hotspotId:
          btn.getAttribute("data-hotspot-id") ||
          btn.getAttribute("data-testid")?.replace("scene-hotspot-", ""),
        pe: getComputedStyle(btn).pointerEvents,
      };
    },
    { x: cx, y: cy },
  );

  const elementFromPointIsHotspot =
    edgeHit?.testid === "scene-hotspot-peak-left";

  // Honest activation: real mouse.click, then read runtime last-click state
  await page.mouse.click(cx, cy);
  await page.waitForTimeout(200);
  const lastClick = await page.evaluate(() => {
    const layer = document.querySelector('[data-testid="scene-hotspots"]');
    return layer?.getAttribute("data-last-click") || null;
  });

  const centerHit = await page.evaluate(() => {
    const el = document.elementFromPoint(
      window.innerWidth / 2,
      window.innerHeight / 2,
    );
    const hs = el?.closest?.('[data-testid^="scene-hotspot-"]');
    const chrome = el?.closest?.("[data-akb-primary-chrome]");
    return {
      isHotspot: !!hs,
      primaryChrome: chrome?.getAttribute("data-akb-primary-chrome") || null,
      tag: el?.tagName || null,
    };
  });

  const topbarHit = await page.evaluate(() => {
    const el = document.elementFromPoint(window.innerWidth / 2, 36);
    const hs = el?.closest?.('[data-testid^="scene-hotspot-"]');
    return {
      isHotspot: !!hs,
      tag: el?.tagName || null,
      primaryChrome:
        el
          ?.closest?.("[data-akb-primary-chrome]")
          ?.getAttribute("data-akb-primary-chrome") || null,
    };
  });

  const emoteBefore = await page.evaluate(() => {
    const el =
      document.querySelector("[data-werner-emote]") ||
      document.querySelector('[data-testid="penguin-mascot"]');
    return el?.getAttribute("data-werner-emote") || null;
  });
  await page.evaluate(() => {
    window.dispatchEvent(
      new CustomEvent("antiek:werner-experience", {
        detail: { experience: "deep_research_complete" },
      }),
    );
  });
  await page.waitForTimeout(300);
  const emoteAfter = await page.evaluate(() => {
    const el =
      document.querySelector("[data-werner-emote]") ||
      document.querySelector('[data-testid="penguin-mascot"]');
    return el?.getAttribute("data-werner-emote") || null;
  });

  await page.screenshot({
    path: path.join(SCRATCH, `shell-launch-pass${pass}.png`),
    fullPage: false,
  });

  const unexpected = [...pageErrors, ...consoleErrors].filter(isUnexpected);

  // HONESTY: nonForceClickWorked requires runtime data-last-click on parent,
  // never static data-hotspot-id / elementFromPoint alone.
  const nonForceClickWorked =
    elementFromPointIsHotspot && lastClick === "peak-left";

  return {
    pass,
    penguinCount,
    shellFrame,
    bodyLen,
    painted,
    edgeHit,
    elementFromPointIsHotspot,
    lastClickBefore,
    lastClick,
    nonForceClickWorked,
    centerHit,
    centerNotHotspot: !centerHit.isHotspot,
    topbarHit,
    topbarNotHotspot: !topbarHit.isHotspot,
    emoteBefore,
    emoteAfter,
    reactionChanged:
      emoteAfter === "happy" ||
      (emoteBefore !== emoteAfter && !!emoteAfter),
    errors: unexpected,
    pageErrors,
    rawConsoleErrorCount: consoleErrors.length,
    tree: "Antiek/apps/reading",
  };
}

const browser = await chromium.launch({ headless: true });
const result = {
  mode: "authenticated-shell-edge-hotspots",
  tree: "Antiek/apps/reading",
  honesty:
    "nonForceClickWorked := data-last-click on [data-testid=scene-hotspots] === peak-left after real mouse.click",
};
try {
  for (const pass of [1, 2]) {
    const ctx = await browser.newContext();
    const page = await ctx.newPage();
    result[`pass${pass}`] = await runPass(page, pass);
    await ctx.close();
  }
  const gates = (p) =>
    p.painted &&
    p.penguinCount >= 1 &&
    p.elementFromPointIsHotspot &&
    p.nonForceClickWorked &&
    p.lastClickBefore === "" &&
    p.lastClick === "peak-left" &&
    p.centerNotHotspot &&
    p.topbarNotHotspot &&
    p.reactionChanged &&
    p.errors.length === 0;
  result.ok = gates(result.pass1) && gates(result.pass2);
} catch (e) {
  result.ok = false;
  result.fatal = String((e && e.stack) || e);
} finally {
  await browser.close();
}

fs.writeFileSync(
  path.join(SCRATCH, "shell-launch-result.json"),
  JSON.stringify(result, null, 2),
);
console.log(JSON.stringify(result, null, 2));
console.log("shell ok", result.ok);
process.exit(result.ok ? 0 : 1);
