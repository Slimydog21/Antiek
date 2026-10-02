// @vitest-environment node
import { createServer, type RequestListener, type Server } from "node:http";
import { once } from "node:events";
import { afterEach, describe, expect, it } from "vitest";
import { waitForHttp } from "./wait_for_http";

const servers: Server[] = [];
afterEach(async () => {
  await Promise.all(servers.map((server) => {
    if (!server.listening) return Promise.resolve();
    return new Promise<void>((resolve, reject) => {
      server.close((error) => error ? reject(error) : resolve());
      server.closeAllConnections();
    });
  }));
  servers.length = 0;
});

async function serve(handler: RequestListener): Promise<string> {
  const server = createServer(handler);
  servers.push(server);
  server.listen(0, "127.0.0.1");
  await once(server, "listening");
  const address = server.address();
  if (!address || typeof address === "string") throw new Error("Expected TCP address");
  return `http://127.0.0.1:${address.port}/health`;
}

describe("e2e dependency readiness", () => {
  it("waits for a backend that binds its port late", async () => {
    const url = await serve((_request, response) => response.writeHead(200).end());
    const server = servers[0];
    const port = Number(new URL(url).port);
    await new Promise<void>((resolve) => server.close(() => resolve()));
    const timer = setTimeout(() => server.listen(port, "127.0.0.1"), 50);
    try {
      await waitForHttp({ name: "backend on :8000", url, timeoutMs: 1_000, pollMs: 10 });
      expect(server.listening).toBe(true);
    } finally {
      clearTimeout(timer);
    }
  });

  it("waits through HTTP 503 until the backend returns HTTP 200", async () => {
    let probes = 0;
    const url = await serve((_request, response) => {
      response.writeHead(++probes < 3 ? 503 : 200).end();
    });
    await waitForHttp({ name: "backend on :8000", url, timeoutMs: 1_000, pollMs: 10 });
    expect(probes).toBe(3);
  });

  it.each([302, 401, 403, 503])("names the dependency when HTTP %s never becomes ready", async (status) => {
    const url = await serve((_request, response) => {
      response.writeHead(status, { location: "/login" }).end();
    });
    await expect(waitForHttp({ name: "backend on :8000", url, timeoutMs: 100, pollMs: 10 }))
      .rejects.toThrow(`backend on :8000 not ready after 0.1s (${url}; last probe:`);
  });

  it("bounds a probe that accepts a connection but never responds", async () => {
    const url = await serve(() => {});
    await expect(waitForHttp({ name: "backend on :8000", url, timeoutMs: 100, pollMs: 10 }))
      .rejects.toThrow("backend on :8000 not ready after 0.1s");
  });

  it("names the dependency when the backend has not bound its port", async () => {
    const url = await serve((_request, response) => response.end());
    await new Promise<void>((resolve) => servers[0].close(() => resolve()));
    servers.length = 0;
    await expect(waitForHttp({ name: "backend on :8000", url, timeoutMs: 100, pollMs: 10 }))
      .rejects.toThrow("backend on :8000 not ready after 0.1s");
  });
});
