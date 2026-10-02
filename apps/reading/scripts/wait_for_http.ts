import { setTimeout as sleep } from "node:timers/promises";
import { pathToFileURL } from "node:url";

/** A listening port or an auth error is not an HTTP readiness signal. */
export async function waitForHttp({
  name,
  url,
  timeoutMs,
  pollMs = 250,
}: {
  name: string;
  url: string;
  timeoutMs: number;
  pollMs?: number;
}): Promise<void> {
  if (!Number.isFinite(timeoutMs) || timeoutMs <= 0 || !Number.isFinite(pollMs) || pollMs <= 0) {
    throw new Error("Readiness timeouts must be positive finite numbers");
  }
  const deadline = performance.now() + timeoutMs;
  let lastResult = "no response";
  while (performance.now() < deadline) {
    try {
      const probeTimeout = Math.max(1, Math.ceil(Math.min(1_000, deadline - performance.now())));
      const response = await fetch(url, {
        redirect: "manual",
        signal: AbortSignal.timeout(probeTimeout),
      });
      void response.body?.cancel().catch(() => {});
      if (response.status === 200) return;
      lastResult = `HTTP ${response.status}`;
    } catch (error) {
      lastResult = error instanceof Error ? error.message : String(error);
    }
    const remaining = deadline - performance.now();
    if (remaining > 0) await sleep(Math.min(pollMs, remaining));
  }
  throw new Error(`${name} not ready after ${timeoutMs / 1_000}s (${url}; last probe: ${lastResult})`);
}

if (process.argv[1] && import.meta.url === pathToFileURL(process.argv[1]).href) {
  const [name, url, seconds] = process.argv.slice(2);
  try {
    if (!name || !url || !seconds) {
      throw new Error("Usage: wait_for_http.ts <dependency name> <url> <timeout seconds>");
    }
    await waitForHttp({ name, url, timeoutMs: Number(seconds) * 1_000 });
    console.log(`${name} ready (${url}; HTTP 200)`);
  } catch (error) {
    console.error(error instanceof Error ? error.message : String(error));
    process.exitCode = 1;
  }
}
