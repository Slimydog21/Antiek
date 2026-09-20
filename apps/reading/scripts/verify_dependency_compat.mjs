// Local compatibility proof for the Lost Pixel dependency overrides.
// Uses synthetic credentials and loopback servers; no baseline updates.
import assert from "node:assert/strict";
import http from "node:http";
import { createRequire } from "node:module";
import { mkdtemp, writeFile, rm } from "node:fs/promises";
import { tmpdir } from "node:os";
import path from "node:path";
process.env.NO_PROXY = [process.env.NO_PROXY, "127.0.0.1", "localhost"]
  .filter(Boolean)
  .join(",");
const require = createRequire(new URL("../package.json", import.meta.url));
const lostRequire = createRequire(require.resolve("lost-pixel/package.json"));
const api = require("lost-pixel/dist/api.js");
const axios = lostRequire("axios");
const serve = lostRequire("serve-handler");
const directory = await mkdtemp(path.join(tmpdir(), "antiek-lostpixel-"));
const png = Buffer.from(
  "iVBORw0KGgoAAAANSUhEUgAAAAEAAAABCAQAAAC1HAwCAAAAC0lEQVR42mP8/x8AAwMCAO+aWQAAAABJRU5ErkJggg==",
  "base64",
);
const file = path.join(directory, "probe.png");
const requests = [];
const errors = [];
let rejectUpload = false;
const deadline = setTimeout(() => {
  console.error("Probe deadline exceeded");
  process.exit(1);
}, 15000);
const server = http.createServer(async (req, res) => {
  try {
    const chunks = [];
    for await (const chunk of req) chunks.push(chunk);
    const body = Buffer.concat(chunks);
    requests.push(req.url);
    assert.equal(req.headers.authorization, "Bearer local-probe");
    assert.equal(req.headers["x-api-key"], "synthetic-key");
    assert.equal(req.headers["x-api-version"], "3");
    if (req.url === "/file/upload-shot") {
      const boundary = /boundary=(.+)$/.exec(
        req.headers["content-type"] ?? "",
      )?.[1];
      assert.ok(boundary);
      assert.ok(body.includes(Buffer.from("--" + boundary)));
      assert.ok(
        body.includes(Buffer.from('name="uploadToken"\r\n\r\nlocal-upload')),
      );
      assert.ok(body.includes(Buffer.from('name="name"\r\n\r\nfixture')));
      assert.ok(body.includes(Buffer.from('filename="probe.png"')));
      assert.ok(body.includes(png));
      res.writeHead(rejectUpload ? 400 : 200, {
        "content-type": "application/json",
      });
      res.end(JSON.stringify({ accepted: !rejectUpload }));
    } else {
      assert.equal(req.url, "/app/check-cache");
      assert.deepEqual(JSON.parse(body.toString()), {
        projectId: "local-project",
        cacheKey: "cache-probe",
      });
      res.writeHead(200, { "content-type": "application/json" });
      res.end('{"cacheExists":false}');
    }
  } catch (error) {
    errors.push(String(error));
    res.writeHead(500);
    res.end("probe assertion failed");
  }
});
const staticServer = http.createServer((req, res) =>
  serve(req, res, { public: directory, cleanUrls: false }),
);
const listen = (server) =>
  new Promise((resolve) => server.listen(0, "127.0.0.1", resolve));
try {
  await writeFile(file, png);
  await writeFile(path.join(directory, "page.html"), "<p>static-probe</p>");
  await listen(server);
  await listen(staticServer);
  const origin = "http://127.0.0.1:" + server.address().port;
  const config = {
    apiKey: "synthetic-key",
    lostPixelPlatform: origin,
    lostPixelProjectId: "local-project",
  };
  const args = {
    config,
    apiToken: "local-probe",
    uploadToken: "local-upload",
    uploadUrl: origin,
    name: "fixture",
    file,
    logger: { process() {} },
  };
  assert.deepEqual(await api.uploadShot(args), { accepted: true });
  assert.deepEqual(
    await api.sendCheckCacheToAPI(config, "local-probe", "cache-probe"),
    { cacheExists: false },
  );
  rejectUpload = true;
  await assert.rejects(
    api.uploadShot(args),
    (error) => axios.isAxiosError(error) && error.response.status === 400,
  );
  assert.equal(requests.filter((x) => x === "/file/upload-shot").length, 2);
  const staticOrigin = "http://127.0.0.1:" + staticServer.address().port;
  assert.equal(
    await (await fetch(staticOrigin + "/page.html")).text(),
    "<p>static-probe</p>",
  );
  assert.deepEqual(
    Buffer.from(await (await fetch(staticOrigin + "/probe.png")).arrayBuffer()),
    png,
  );
  assert.equal(
    (await fetch(staticOrigin + "/probe.png", { method: "HEAD" })).status,
    200,
  );
  assert.equal((await fetch(staticOrigin + "/missing")).status, 404);
  assert.equal((await fetch(staticOrigin + "/page")).status, 404);
  assert.deepEqual(errors, []);
  console.log(
    JSON.stringify(
      {
        result: "PASS",
        versions: Object.fromEntries(
          ["axios", "form-data", "serve-handler"].map((n) => [
            n,
            lostRequire(n + "/package.json").version,
          ]),
        ),
        upload: "actual Lost Pixel uploadShot, binary multipart and boundary",
        json: "actual sendCheckCacheToAPI",
        error: "HTTP400 rejected once without retries",
        static: "real serve-handler options, HTML/PNG/HEAD/404/cleanUrls:false",
        not_proved: [
          "Lost Pixel screenshot renderer",
          "static wrapper port allocator",
          "remote service compatibility",
        ],
      },
      null,
      2,
    ),
  );
} finally {
  clearTimeout(deadline);
  server.closeAllConnections();
  staticServer.closeAllConnections();
  await Promise.all([
    new Promise((resolve) => server.close(resolve)),
    new Promise((resolve) => staticServer.close(resolve)),
  ]);
  await rm(directory, { recursive: true, force: true });
}
