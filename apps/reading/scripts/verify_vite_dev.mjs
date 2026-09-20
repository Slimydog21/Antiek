// Exercise the real Vite configuration using only synthetic loopback services.
import assert from "node:assert/strict";
import http from "node:http";
import path from "node:path";
import { fileURLToPath } from "node:url";
import { mkdtemp, writeFile, rm } from "node:fs/promises";
import { createServer, loadConfigFromFile } from "vite";
const root = fileURLToPath(new URL("../", import.meta.url));
process.chdir(root);
const fixture = await mkdtemp(path.join(root, ".vite-compat-"));
const backend = http.createServer((req, res) => {
  res.writeHead(200, { "content-type": "application/json" });
  res.end(JSON.stringify({ probe: true, path: req.url }));
});
let vite;
let socket;
let result;
const deadline = setTimeout(() => {
  console.error("Vite probe deadline exceeded");
  process.exit(1);
}, 30000);
try {
  await new Promise((resolve) => backend.listen(0, "127.0.0.1", resolve));
  const target = "http://127.0.0.1:" + backend.address().port;
  const loaded = await loadConfigFromFile(
    { command: "serve", mode: "development" },
    path.join(root, "vite.config.ts"),
    root,
  );
  assert.ok(loaded);
  const originalProxy = loaded.config.server?.proxy;
  assert.ok(originalProxy);
  const proxy = Object.fromEntries(
    Object.entries(originalProxy).map(([prefix, options]) => [
      prefix,
      typeof options === "string"
        ? target
        : {
            ...options,
            target: options.ws ? target.replace("http:", "ws:") : target,
          },
    ]),
  );
  vite = await createServer({
    ...loaded.config,
    root,
    configFile: false,
    envFile: false,
    logLevel: "error",
    server: {
      ...loaded.config.server,
      host: "127.0.0.1",
      port: 0,
      open: false,
      proxy,
    },
  });
  await vite.listen();
  const origin = "http://127.0.0.1:" + vite.httpServer.address().port;
  const page = await fetch(origin + "/login");
  assert.equal(page.status, 200);
  assert.match(await page.text(), /\/src\/main\.tsx/);
  const module = await fetch(origin + "/src/main.tsx");
  assert.equal(module.status, 200);
  const transformed = await module.text();
  assert.match(transformed, /createRoot/);
  const optimizedPath = transformed.match(
    /"(\/node_modules\/\.vite\/deps\/[^" ]+)"/,
  )?.[1];
  assert.ok(optimizedPath, "entry imports an optimized dependency");
  const optimized = await fetch(origin + optimizedPath);
  assert.equal(optimized.status, 200);
  assert.ok((await optimized.text()).length > 0);
  await vite.waitForRequestsIdle();
  const client = await fetch(origin + "/@vite/client");
  assert.equal(client.status, 200);
  assert.match(await client.text(), /WebSocket/);
  const verifiedPrefixes = [];
  for (const prefix of Object.keys(originalProxy).filter((x) => x !== "/ws")) {
    const response = await fetch(origin + prefix + "/compat-probe");
    assert.equal(response.status, 200);
    assert.deepEqual(await response.json(), {
      probe: true,
      path: prefix + "/compat-probe",
    });
    verifiedPrefixes.push(prefix);
  }
  await writeFile(path.join(fixture, "public.txt"), "public-fixture");
  await writeFile(path.join(fixture, ".env"), "SYNTHETIC_DENIED_MARKER");
  const publicPath = "/@fs/" + path.join(fixture, "public.txt");
  const privatePath = "/@fs/" + path.join(fixture, ".env");
  assert.equal(
    await (await fetch(origin + publicPath)).text(),
    "public-fixture",
  );
  const denied = await fetch(origin + privatePath);
  assert.equal(denied.status, 403);
  assert.ok(!(await denied.text()).includes("SYNTHETIC_DENIED_MARKER"));
  await new Promise((resolve, reject) => {
    socket = new WebSocket(origin.replace("http:", "ws:"), "vite-hmr");
    socket.addEventListener("error", () =>
      reject(new Error("HMR websocket failed")),
    );
    socket.addEventListener("message", (event) => {
      const message = JSON.parse(event.data);
      if (message.type === "connected")
        vite.ws.send({
          type: "custom",
          event: "compat-probe",
          data: "confirmed",
        });
      if (message.type === "custom" && message.event === "compat-probe") {
        assert.equal(message.data, "confirmed");
        resolve();
      }
    });
  });
  result = {
    result: "PASS",
    spa: true,
    tsxTransform: true,
    optimizedDependency: true,
    hmrClient: true,
    hmrWebSocket: true,
    proxyPrefixes: verifiedPrefixes,
    fsDeny: "public control served; synthetic .env denied403",
    notProved: [
      "Windows alternate path exploit on macOS",
      "WebSocket API proxy",
      "rendered browser interaction",
    ],
  };
} finally {
  socket?.close();
  await vite?.close();
  backend.closeAllConnections();
  await new Promise((resolve) => backend.close(resolve));
  await rm(fixture, { recursive: true, force: true });
  clearTimeout(deadline);
}

console.log(JSON.stringify(result, null, 2));
